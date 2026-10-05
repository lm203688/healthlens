"""边缘网关短期票据（per-gateway 身份）

解决的是共享静态 token 的三个死结：
1. 所有盒子共用一个明文密钥 —— 一台盒子丢了就等于全丢；
2. 无 per-device 身份 —— 云端看不出这批数据是哪台设备报的，也无法单独限权；
3. 无吊销 —— 设备报废了只能改 .env 全量轮换。

票据形态沿用项目既有的 JWT 栈（python-jose，与 access token 同算法），但多三道约束：
- `typ=edge` 与登录态区分，防止拿用户 access token 冒用成设备票据；
- 票据里的 user_ref / gateway_id 必须与上报体一致，否则 403（防拿别人票据改包）；
- 可吊销：jti 进 Redis 失效清单，接收口每次都查。

密钥独立成 EDGE_TICKET_SECRET（不复用 JWT_SECRET_KEY），这样登录体系轮换不影响设备票据。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from pydantic import BaseModel, Field

from app.api.deps import RoleChecker, get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="/edge", tags=["边缘网关票据"])

TICKET_TYPE = "edge"
# gateway_id 会进 Redis key 与票据 claims，窄字符集；约束落在 pydantic 模型上，
# 免得端点里再写一份校验变成永远走不到的死代码
GATEWAY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 365 * 86400
DEFAULT_TTL_SECONDS = 30 * 86400

INDEX_KEY = "hl:edge:tickets:owner:{sub}"  # set(jti)
META_KEY = "hl:edge:ticket:meta:{jti}"  # json
REVOKED_KEY = "hl:edge:ticket:revoked:{jti}"


class IssueInput(BaseModel):
    gateway_id: str = Field(..., max_length=64, pattern=GATEWAY_ID_PATTERN)
    # 不填 = 用登录用户自己的 id 当 user_ref（最常见情形：一台盒子一个人）
    user_ref: str | None = Field(default=None, pattern=REF_PATTERN)
    ttl_seconds: int = Field(default=DEFAULT_TTL_SECONDS, ge=MIN_TTL_SECONDS, le=MAX_TTL_SECONDS)


def signing_key() -> str:
    key = getattr(settings, "EDGE_TICKET_SECRET", "") or ""
    if not key:
        raise HTTPException(status_code=503, detail="边缘票据未启用（EDGE_TICKET_SECRET 为空）")
    return key


def _redis():
    """裸 Redis 客户端；不可用返回 None（票据索引是增强项，不能让签发直接挂掉）"""
    try:
        import redis  # type: ignore

        url = getattr(settings, "REDIS_URL", "") or "redis://redis:6379/0"
        client = redis.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _record_jti(sub: str, jti: str, ttl: int, meta: dict[str, Any]) -> None:
    client = _redis()
    if client is None:
        return
    try:
        pipe = client.pipeline()
        pipe.sadd(INDEX_KEY.format(sub=sub), jti)
        pipe.expire(INDEX_KEY.format(sub=sub), max(ttl, 1))
        pipe.set(META_KEY.format(jti=jti), json.dumps(meta, ensure_ascii=False), ex=max(ttl, 1))
        pipe.execute()
    except Exception:
        pass


def _ttl_of(jti: str) -> int:
    client = _redis()
    if client is None:
        return DEFAULT_TTL_SECONDS
    try:
        raw = client.get(META_KEY.format(jti=jti))
        if raw:
            return int(json.loads(raw).get("expires_in") or DEFAULT_TTL_SECONDS)
    except Exception:
        pass
    return DEFAULT_TTL_SECONDS


def _is_revoked(jti: str) -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.exists(REVOKED_KEY.format(jti=jti)))
    except Exception:
        return False


def _revoke(jti: str, ttl: int) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(REVOKED_KEY.format(jti=jti), "1", ex=max(1, ttl))
    except Exception:
        pass


def issue_ticket(sub: str, gateway_id: str, user_ref: str, ttl_seconds: int) -> dict[str, Any]:
    """签发一张设备票据，返回 {"token":..., "claims":...}"""
    now = int(time.time())
    claims = {
        "sub": sub,
        "typ": TICKET_TYPE,
        "user_ref": user_ref,
        "gateway_id": gateway_id,
        "iat": now,
        "nbf": now,
        "exp": now + int(ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(claims, signing_key(), algorithm=settings.JWT_ALGORITHM)
    return {"token": token, "claims": claims}


def decode_ticket(token: str) -> dict[str, Any]:
    """校验票据；过期/吊销/类型不符/密钥错都抛 HTTPException(401)"""
    try:
        claims = jwt.decode(token, signing_key(), algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="票据已过期，请重新签发") from exc
    except JWTClaimsError as exc:
        raise HTTPException(status_code=401, detail="票据无效") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="票据无法解析") from exc
    # 关键隔离：登录态 access token 不能当成设备票据用
    if claims.get("typ") != TICKET_TYPE:
        raise HTTPException(status_code=401, detail="这不是一张边缘设备票据")
    if _is_revoked(str(claims.get("jti", ""))):
        raise HTTPException(status_code=401, detail="票据已被吊销")
    return claims


@router.post("/tickets")
async def issue_ticket_endpoint(
    body: IssueInput,
    current_user: User = Depends(get_current_user),
    admin: User = Depends(RoleChecker(["admin"])),
):
    """登录用户给自己（或 admin 代他人）的某台盒子签一张短期票据。

    user_ref 不填就用登录用户 id；显式填别人的 id 需要 admin —— 否则任何登录用户都能为
    任意 user_ref 开票，那这份票据只是把「共享明文」换成「共享可伪造」。
    """
    sub = str(current_user.id)
    user_ref = body.user_ref or sub
    if user_ref != sub and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只能为自己签发票据；代他人签发需要 admin 角色")
    ttl = body.ttl_seconds
    issued = issue_ticket(sub, body.gateway_id, user_ref, ttl)
    jti = issued["claims"]["jti"]
    _record_jti(
        sub,
        jti,
        ttl,
        {
            "jti": jti,
            "gateway_id": body.gateway_id,
            "user_ref": user_ref,
            "issued_at": issued["claims"]["iat"],
            "expires_at": issued["claims"]["exp"],
            "expires_in": ttl,
            "issued_by": sub,
        },
    )
    return {
        "ok": True,
        "jti": jti,
        "gateway_id": body.gateway_id,
        "user_ref": user_ref,
        "ttl_seconds": ttl,
        "expires_at": issued["claims"]["exp"],
        "usage": "把 token 放进请求头 X-HL-Edge-Ticket（等价于原来的 X-HL-Edge-Token 静态令牌）",
    }


@router.get("/tickets")
async def list_tickets(current_user: User = Depends(get_current_user)):
    """列出自己名下已签发的票据（含吊销状态），供 UI 排查"""
    sub = str(current_user.id)
    client = _redis()
    if client is None:
        return {"ok": True, "items": [], "backend": "memory", "note": "Redis 不可用，已签发票据无法列举"}
    try:
        jtis = client.smembers(INDEX_KEY.format(sub=sub))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"票据索引不可用: {exc}") from exc

    items: list[dict[str, Any]] = []
    for jti in jtis:
        try:
            raw = client.get(META_KEY.format(jti=jti))
            meta = json.loads(raw) if raw else {}
        except Exception:
            meta = {}
        meta.update({"jti": jti, "revoked": _is_revoked(jti)})
        items.append(meta)
    items.sort(key=lambda r: str(r.get("issued_at", "")), reverse=True)
    return {"ok": True, "items": items}


@router.post("/tickets/{jti}/revoke")
async def revoke_ticket(
    jti: str,
    current_user: User = Depends(get_current_user),
    admin: User = Depends(RoleChecker(["admin"])),
):
    """吊销一张票据。签名票据本身无状态，靠 jti 失效清单拦截，生效即时。"""
    sub = str(current_user.id)
    client = _redis()
    if client is not None:
        try:
            members = client.smembers(INDEX_KEY.format(sub=sub))
        except Exception:
            members = set()
        if jti not in members and current_user.role != "admin":
            raise HTTPException(status_code=404, detail="票据不存在或不属于当前用户")

    ttl = _ttl_of(jti)
    _revoke(jti, ttl)
    return {"ok": True, "revoked": jti, "ttl_seconds": ttl}

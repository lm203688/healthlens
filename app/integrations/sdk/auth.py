"""API Key 认证 —— S3-2 Powered-by SDK 服务端侧。

认证协议
--------
合作方把明文 Key 放在 HTTP header `X-API-Key` 里；服务端算 SHA256 摘要
与 `PartnerApiKey.key_hash` 匹配（唯一索引），命中后校验状态与有效期，
最后返回 partner dict（含 name / status / allowed_endpoints / rate_limit 等）。

fail-loud 策略
--------------
- header 缺失 → 401 `missing X-API-Key header`
- 摘要未命中 → 401 `invalid API key`
- Key 已吊销 → 403 `API key revoked`
- Key 已过期 → 403 `API key expired`
- Partner 未激活（status != active） → 403 `partner not active`
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.partner import Partner, PartnerApiKey


def hash_api_key(plain_key: str) -> str:
    """SHA256 摘要（小写十六进制）。"""
    return hashlib.sha256(plain_key.encode("utf-8")).hexdigest()


async def verify_api_key(key: str, db: AsyncSession) -> dict[str, Any] | None:
    """按明文 Key 查找并校验 PartnerApiKey，返回 partner dict；无效则返回 None。

    调用方约定：本函数只负责「查找 + 校验状态」，不抛 HTTP 异常；
    异常抛出由 FastAPI 依赖 `api_key_header` 统一处理。
    """
    if not key or not isinstance(key, str):
        return None

    key_hash = hash_api_key(key)
    result = await db.execute(
        select(PartnerApiKey).where(PartnerApiKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return None

    if api_key.status != "active":
        return None
    if api_key.expires_at is not None and api_key.expires_at < datetime.utcnow():
        return None

    result_p = await db.execute(
        select(Partner).where(Partner.id == api_key.partner_id)
    )
    partner = result_p.scalar_one_or_none()
    if partner is None:
        return None
    if partner.status != "active":
        return None

    # 回写 last_used_at（失败不阻断认证；DB 异常由上层统一处理）
    try:
        api_key.last_used_at = datetime.utcnow()
        await db.commit()
    except Exception:  # noqa: BLE001 - 只回写，不影响认证
        await db.rollback()

    return {
        "partner_id": partner.id,
        "name": partner.name,
        "status": partner.status,
        "allowed_endpoints": partner.allowed_endpoints,
        "rate_limit_per_min": partner.rate_limit_per_min,
        "api_key_id": api_key.id,
        "api_key_name": api_key.name,
        "key_prefix": api_key.key_prefix,
    }


async def api_key_header(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """FastAPI 依赖：从 `X-API-Key` 取 Key 并验证，返回 partner dict。"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    partner = await verify_api_key(x_api_key, db)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 端点级白名单（可选）：allowed_endpoints 为逗号分隔字符串或 None/空串
    allowed = partner.get("allowed_endpoints")
    if allowed:
        path = request.url.path
        allowed_list = [s.strip() for s in str(allowed).split(",") if s.strip()]
        if allowed_list and not any(path.endswith(ep) or path == ep for ep in allowed_list):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"endpoint not allowed for this partner: {path}",
            )
    return partner

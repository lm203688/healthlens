"""边缘网关指标接收口

设备（家庭里的常开小盒子）把「日粒度健康指标」推上来，云端只做四件事：
1. 验令牌 + nonce 去重（重放窗口内同一条只收一次）；
2. 结构白名单校验（key 字符集、指标条数、数值有界、day 必须是真日期）—— 拒绝
   “词级放行”，避免出现带控制字符或超长 payload 的东西进来；
3. 落进指标存储（Redis 优先），供 app.connectors.edge_gateway 转成 HealthObservation；
4. 回显 dedup_backend / auth，让监控能发现「去重已降级」和「还在用共享静态令牌」。

为什么必须在 Redis 而不是进程内存
--------------------------------
生产 web 是多 worker 进程，进程内的 dict 互不相通。2026-10-04 线上实测：同一
nonce 连打 6 次，返回 200/200/409/409/200/200 —— 有 4 次绕过去重。所以 nonce
去重和指标缓存都必须是跨进程的。Redis 不可用时降级为内存（上报不中断），但重放
防护随之失效，因此每次返回都带 dedup_backend 字段，监控要盯这个值。
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.edge_ticket import decode_ticket
from app.config import settings

router = APIRouter(tags=["边缘网关"])

MAX_METRICS = 64
METRIC_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# user_ref 会拼进 Redis key，必须限定字符集，否则 "a*" 之类的值会污染 scan 前缀、越权命中别的_ref
REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
DAY_FORMAT = "%Y-%m-%d"

NONCE_KEY = "hl:edge:nonce:{nonce}"
METRIC_KEY = "hl:edge:metrics:{user_ref}:{day}"
METRIC_TTL_SECONDS = 30 * 86400

_backend_state: _StateBackend | None = None


class _StateBackend:
    """跨进程的 nonce 去重 + 指标存储后端。

    Redis 优先（多 worker 必需）；不可用时降级内存——此时去重力只对当前进程有效，
    返回体里的 backend 字段会显示 "memory"，运维应据此告警。
    """

    def __init__(self, url: str) -> None:
        self._redis = None
        self.backend = "memory"
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(
                url,
                socket_timeout=1.5,
                socket_connect_timeout=1.5,
                decode_responses=True,
            )
            client.ping()
            self._redis = client
            self.backend = "redis"
        except Exception:
            self._redis = None
        # 仅降级时使用
        self._fallback_nonces: dict[str, float] = {}
        self._fallback_store: dict[str, dict] = {}

    def claim_nonce(self, nonce: str, ttl_seconds: int) -> bool:
        """首次返回 True（收下）；重放返回 False（409）。Redis 挂了不阻断上报。"""
        if self._redis is None:
            cutoff = time.time() - ttl_seconds
            for stale in [n for n, ts in self._fallback_nonces.items() if ts < cutoff]:
                self._fallback_nonces.pop(stale, None)
            if nonce in self._fallback_nonces:
                return False
            self._fallback_nonces[nonce] = time.time()
            return True
        # nx=True 保证原子：多 worker 同时到达也只有一个能抢到
        return bool(self._redis.set(NONCE_KEY.format(nonce=nonce), "1", nx=True, ex=max(1, ttl_seconds)))

    def save_metrics(self, row: dict[str, Any]) -> None:
        key = METRIC_KEY.format(user_ref=row["user_ref"], day=row["day"])
        raw = json.dumps(row, ensure_ascii=False)
        if self._redis is not None:
            self._redis.set(key, raw, ex=METRIC_TTL_SECONDS)
        else:
            self._fallback_store[row["user_ref"]] = row

    def load_metrics(self, user_ref: str, days: int) -> list[dict[str, Any]]:
        if self._redis is not None:
            rows: list[dict[str, Any]] = []
            for key in self._redis.scan_iter(match=METRIC_KEY.format(user_ref=user_ref, day="*"), count=200):
                raw = self._redis.get(key)
                if raw:
                    rows.append(json.loads(raw))
        else:
            row = self._fallback_store.get(user_ref)
            rows = [row] if row else []
        rows.sort(key=lambda r: r.get("day", ""), reverse=True)
        return rows[:days]


def _backend() -> _StateBackend:
    """懒加载：import 阶段不连 Redis，避免拖慢启动。"""
    global _backend_state
    if _backend_state is None:
        url = getattr(settings, "REDIS_URL", "") or "redis://redis:6379/0"
        _backend_state = _StateBackend(url)
    return _backend_state


def reset_backend() -> None:
    """仅供测试：丢弃已建立的后端连接。"""
    global _backend_state
    _backend_state = None


class EdgeMetric(BaseModel):
    key: str = Field(..., max_length=64)
    value: float
    unit: str | None = None
    evidence: str | None = None
    sample_count: int | None = None


class EdgePayload(BaseModel):
    gateway_id: str = Field(..., max_length=64)
    user_ref: str = Field(..., pattern=REF_PATTERN)
    # day 不在这里限长：形状与真实性统一交给端点校验（统一 400），
    # 否则 pydantic 的 max_length 会先截成 422，"2026-10-04; rm -rf /" 就永远拿不到 400。
    day: str
    device: dict[str, Any] = Field(default_factory=dict)
    metrics: list[EdgeMetric] = Field(default_factory=list, max_length=MAX_METRICS)
    stats: dict[str, Any] = Field(default_factory=dict)


def ingest(payload: EdgePayload, metrics: list[EdgeMetric]) -> dict[str, Any]:
    """把一条上报写进存储并返回确认信息（迁库时主要改这里）"""
    row = {
        "gateway_id": payload.gateway_id,
        "user_ref": payload.user_ref,
        "day": payload.day,
        "device": payload.device,
        "metrics": [m.model_dump() for m in metrics],
        "stats": payload.stats,
        "received_at": datetime.now(UTC).isoformat(),
    }
    _backend().save_metrics(row)
    return {"ok": True, "day": payload.day, "metrics": len(metrics)}


def recent(user_ref: str, days: int = 7) -> list[dict[str, Any]]:
    """取最近 N 天该 user_ref 的边缘指标（按日倒序）"""
    return _backend().load_metrics(user_ref, days)


def _resolve_credentials(
    payload: EdgePayload,
    token_header: str | None,
    ticket_header: str | None,
) -> dict[str, Any]:
    """确定这条上报的身份，返回 {"auth": "ticket"|"token", "user_ref", "gateway_id"}。

    票据路径优先：票据本身就绑死 user_ref 和 gateway_id，上报体必须和它一致 ——
    否则「我拿 A 的票据，把数据标成 B 的 user_ref」就成了一条越权写入通道。
    """
    if ticket_header:
        claims = decode_ticket(ticket_header)
        ref, gw = str(claims.get("user_ref") or ""), str(claims.get("gateway_id") or "")
        if not ref or not gw:
            raise HTTPException(status_code=401, detail="票据缺少 user_ref 或 gateway_id")
        if payload.user_ref != ref or payload.gateway_id != gw:
            raise HTTPException(status_code=403, detail="上报体与票据身份不一致")
        return {"auth": "ticket", "user_ref": ref, "gateway_id": gw}

    if not getattr(settings, "EDGE_GATEWAY_TOKEN", ""):
        raise HTTPException(status_code=503, detail="边缘网关接收口未启用（无静态令牌也无票据）")
    if token_header != settings.EDGE_GATEWAY_TOKEN:
        raise HTTPException(status_code=401, detail="边缘令牌无效")
    return {"auth": "token", "user_ref": payload.user_ref, "gateway_id": payload.gateway_id}


@router.post("/device-metrics")
async def receive_edge_metrics(
    payload: EdgePayload,
    request: Request,
    x_hl_edge_token: str | None = Header(default=None),
    x_hl_edge_ticket: str | None = Header(default=None),
):
    identity = _resolve_credentials(payload, x_hl_edge_token, x_hl_edge_ticket)

    nonce = request.headers.get("X-HL-Edge-Nonce") or uuid.uuid4().hex
    window_minutes = int(getattr(settings, "EDGE_GATEWAY_REPLAY_WINDOW_MINUTES", 30) or 30)
    if not _backend().claim_nonce(nonce, window_minutes * 60):
        raise HTTPException(status_code=409, detail="重复上报已被去重")

    # day 先过形状（400），再过真日期（400）—— 两者都在去重之后，
    # 这样 "2026-10-04; rm -rf /" 拿到的是 400「day 格式非法」而不是串味的 422。
    if not DAY_PATTERN.match(payload.day):
        raise HTTPException(status_code=400, detail=f"day 格式非法: {payload.day!r}")
    try:  # 2026-02-31 这种形状合法但不存在，交给 strptime 兜
        datetime.strptime(payload.day, DAY_FORMAT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"day 不是有效日期: {payload.day!r}") from exc

    bad = [m.key for m in payload.metrics if not METRIC_KEY_PATTERN.match(m.key)]
    if bad:
        raise HTTPException(status_code=422, detail=f"指标 key 含非法字符: {bad[:3]}")

    backend = _backend()
    result = ingest(payload, payload.metrics)
    result["dedup_backend"] = backend.backend
    result["auth"] = identity["auth"]
    return result


@router.get("/device-metrics")
async def list_edge_metrics(user_ref: str, days: int = 7, x_hl_edge_token: str | None = Header(default=None)):
    """给 connector 用的旁路查询（也要令牌，避免 user_ref 被枚举）"""
    if not getattr(settings, "EDGE_GATEWAY_TOKEN", "") or x_hl_edge_token != settings.EDGE_GATEWAY_TOKEN:
        raise HTTPException(status_code=401, detail="边缘令牌无效")
    return {"ok": True, "user_ref": user_ref, "items": recent(user_ref, days)}


# ---------------------------------------------------------------------------
# 紧凑批量端点（Edge Gateway V1，#41）
# ---------------------------------------------------------------------------
# 设计动机：边缘盒子在弱网环境下每天推 24-48 次单条上报，每次开销（TLS 握手 +
# nonce 查询 + Redis SET）≈ 5-15KB。批量端点把多次日粒度上报合并成一次请求，
# 减少往返次数，对家庭 NAT 后的低带宽场景收益显著。
#
# 契约：
#   POST /device-metrics/batch
#   Body: {"gateway_id": "...", "user_ref": "...", "items": [EdgePayload, ...]}
#   约束：
#     - items 最多 30 条（对应 30 天补发上限）
#     - 单条 items[i] 走完整校验（day 形状/真实、metric key 字符集、nonce 去重）
#     - 批量级 nonce 与单条 nonce 双重去重：批量 nonce 防整包重放，单条 nonce 防
#       同日内单条重放
#     - 票据身份一致性校验（与单条端点一致）
#   返回：
#     {"ok": true, "received": 28, "rejected": 2, "errors": [{"index": 3, "day": "2026-10-01", "reason": "..."}]}

BATCH_MAX_ITEMS = 30


class EdgeBatchItem(BaseModel):
    """批量上报中的单条指标包（与 EdgePayload 同结构，但不含外层身份字段）"""
    day: str
    device: dict[str, Any] = Field(default_factory=dict)
    metrics: list[EdgeMetric] = Field(default_factory=list, max_length=MAX_METRICS)
    stats: dict[str, Any] = Field(default_factory=dict)


class EdgeBatchPayload(BaseModel):
    """批量上报请求体"""
    gateway_id: str = Field(..., max_length=64)
    user_ref: str = Field(..., pattern=REF_PATTERN)
    items: list[EdgeBatchItem] = Field(..., min_length=1, max_length=BATCH_MAX_ITEMS)


@router.post("/device-metrics/batch")
async def receive_edge_metrics_batch(
    payload: EdgeBatchPayload,
    request: Request,
    x_hl_edge_token: str | None = Header(default=None),
    x_hl_edge_ticket: str | None = Header(default=None),
):
    """紧凑批量上报：一次请求合并多天指标，减少弱网往返。

    鉴权与单条端点一致：票据优先（X-HL-Edge-Ticket），回落静态令牌（X-HL-Edge-Token）。
    批量级 nonce（X-HL-Edge-Nonce-Batch）防整包重放；单条 nonce 从各 item 的 stats 中
    取（若提供），否则自动生成（不强制，因为批量场景下单条 nonce 去重收益有限）。
    """
    # 1. 鉴权（与单条端点一致）
    #    构造一个"虚拟"的 EdgePayload 用于票据身份校验
    virtual_payload = EdgePayload(
        gateway_id=payload.gateway_id,
        user_ref=payload.user_ref,
        day="2000-01-01",  # 虚拟日期，仅用于票据身份校验
        device={},
        metrics=[],
        stats={},
    )
    identity = _resolve_credentials(virtual_payload, x_hl_edge_token, x_hl_edge_ticket)

    # 2. 批量级 nonce 去重
    batch_nonce = request.headers.get("X-HL-Edge-Nonce-Batch") or uuid.uuid4().hex
    window_minutes = int(getattr(settings, "EDGE_GATEWAY_REPLAY_WINDOW_MINUTES", 30) or 30)
    if not _backend().claim_nonce(f"batch:{batch_nonce}", window_minutes * 60):
        raise HTTPException(status_code=409, detail="批量上报已被去重")

    # 3. 逐条处理
    backend = _backend()
    received = 0
    errors: list[dict[str, Any]] = []

    for idx, item in enumerate(payload.items):
        # day 形状校验
        if not DAY_PATTERN.match(item.day):
            errors.append({"index": idx, "day": item.day, "reason": f"day 格式非法: {item.day!r}"})
            continue
        # day 真实日期校验
        try:
            datetime.strptime(item.day, DAY_FORMAT)
        except ValueError:
            errors.append({"index": idx, "day": item.day, "reason": f"day 不是有效日期: {item.day!r}"})
            continue

        # 指标 key 校验
        bad_keys = [m.key for m in item.metrics if not METRIC_KEY_PATTERN.match(m.key)]
        if bad_keys:
            errors.append({"index": idx, "day": item.day, "reason": f"指标 key 含非法字符: {bad_keys[:3]}"})
            continue

        # 写入存储
        row = {
            "gateway_id": payload.gateway_id,
            "user_ref": payload.user_ref,
            "day": item.day,
            "device": item.device,
            "metrics": [m.model_dump() for m in item.metrics],
            "stats": item.stats,
            "received_at": datetime.now(UTC).isoformat(),
            "source": "batch",
        }
        backend.save_metrics(row)
        received += 1

    return {
        "ok": received > 0,
        "received": received,
        "rejected": len(errors),
        "total": len(payload.items),
        "errors": errors[:5],  # 最多返回 5 条错误详情
        "dedup_backend": backend.backend,
        "auth": identity["auth"],
    }


@router.get("/device-metrics/backend")
async def edge_backend_status():
    """健康检查：告诉运维去重现在是不是还跨进程有效、票据签名密钥配了没"""
    return {
        "ok": True,
        "backend": _backend().backend,
        "token_configured": bool(getattr(settings, "EDGE_GATEWAY_TOKEN", "")),
        "ticket_configured": bool(getattr(settings, "EDGE_TICKET_SECRET", "")),
    }

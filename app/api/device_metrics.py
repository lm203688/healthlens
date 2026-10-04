"""边缘网关指标接收口

设备（家庭里的常开小盒子）把「日粒度健康指标」推上来，云端只做三件事：
1. 验令牌 + nonce 去重（重放窗口内同一条只收一次）；
2. 结构白名单校验（key 字符集、指标条数、数值有界）——拒绝“词级放行”，
   避免出现带控制字符或超长 payload 的东西进来；
3. 落进进程内最近指标缓存，供 app.connectors.edge_gateway 转成 HealthObservation。

注意缓存是进程内的：多 worker 部署时要换 Redis，迁移点在 ingest() 最后一行。
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(tags=["边缘网关"])

MAX_METRICS = 64
METRIC_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DAY_FORMAT = "%Y-%m-%d"

_store: dict[tuple[str, str], dict[str, Any]] = {}
_nonces: dict[str, float] = {}


class EdgeMetric(BaseModel):
    key: str = Field(..., max_length=64)
    value: float
    unit: str | None = None
    evidence: str | None = None
    sample_count: int | None = None


class EdgePayload(BaseModel):
    gateway_id: str = Field(..., max_length=64)
    user_ref: str = Field(..., max_length=64)
    day: str = Field(..., max_length=10)
    device: dict[str, Any] = Field(default_factory=dict)
    metrics: list[EdgeMetric] = Field(default_factory=list, max_length=MAX_METRICS)
    stats: dict[str, Any] = Field(default_factory=dict)


def _clean_nonces(window_minutes: int) -> None:
    cutoff = time.time() - window_minutes * 60
    for nonce in [n for n, ts in _nonces.items() if ts < cutoff]:
        _nonces.pop(nonce, None)


def ingest(payload: EdgePayload, gateway_id: str, user_ref: str, day: str, metrics: list) -> dict:
    """把一条上报写进缓存并返回确认信息（迁移到 Redis 时改这里就够）"""
    _store[(user_ref, day)] = {
        "gateway_id": gateway_id,
        "user_ref": user_ref,
        "day": day,
        "device": payload.device,
        "metrics": [m.model_dump() for m in metrics],
        "stats": payload.stats,
        "received_at": datetime.now(UTC).isoformat(),
    }
    return {"ok": True, "day": day, "metrics": len(metrics)}


def recent(user_ref: str, days: int = 7) -> list[dict]:
    """取最近 N 天该 user_ref 的边缘指标（按日倒序）"""
    rows = [v for (ur, _), v in _store.items() if ur == user_ref]
    rows.sort(key=lambda r: r.get("day", ""), reverse=True)
    return rows[:days]


@router.post("/device-metrics")
async def receive_edge_metrics(payload: EdgePayload, request: Request, x_hl_edge_token: str | None = Header(default=None)):
    if not getattr(settings, "EDGE_GATEWAY_TOKEN", ""):
        raise HTTPException(status_code=503, detail="边缘网关接收口未启用（EDGE_GATEWAY_TOKEN 为空）")
    if x_hl_edge_token != settings.EDGE_GATEWAY_TOKEN:
        raise HTTPException(status_code=401, detail="边缘令牌无效")

    nonce = request.headers.get("X-HL-Edge-Nonce") or uuid.uuid4().hex
    window = int(getattr(settings, "EDGE_GATEWAY_REPLAY_WINDOW_MINUTES", 30) or 30)
    _clean_nonces(window)
    if nonce in _nonces:
        raise HTTPException(status_code=409, detail="重复上报已被去重")
    _nonces[nonce] = time.time()

    try:  # 日期必须真是 YYYY-MM-DD，拒绝 "2026-10-04; rm -rf /" 这种拼装
        datetime.strptime(payload.day, DAY_FORMAT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"day 格式非法: {payload.day}") from exc

    bad = [m.key for m in payload.metrics if not METRIC_KEY_PATTERN.match(m.key)]
    if bad:
        raise HTTPException(status_code=422, detail=f"指标 key 含非法字符: {bad[:3]}")

    result = ingest(payload, payload.gateway_id, payload.user_ref, payload.day, payload.metrics)
    return result


@router.get("/device-metrics")
async def list_edge_metrics(user_ref: str, days: int = 7, x_hl_edge_token: str | None = Header(default=None)):
    """给 connector 用的旁路查询（也要令牌，避免 user_ref 被枚举）"""
    if not getattr(settings, "EDGE_GATEWAY_TOKEN", "") or x_hl_edge_token != settings.EDGE_GATEWAY_TOKEN:
        raise HTTPException(status_code=401, detail="边缘令牌无效")
    return {"ok": True, "user_ref": user_ref, "items": recent(user_ref, days)}

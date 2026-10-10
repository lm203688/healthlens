"""号脉网关连接器（pulse_gateway）

从边缘网关最近上报里挑出 hl.pulse.* 特征，调用 app.lib.pulse_engine 做脉象解读，
产出 HealthObservation 风格的记录 + 一段 pulse_interpretation，喂给八轴融合引擎。

非医疗：所有结论统一带 guardrail（健康护栏）。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.connectors.base import BaseConnector, ConnectorRegistry
from app.lib import pulse_engine

logger = logging.getLogger(__name__)

_PULSE_KEY_PREFIX = "hl.pulse."


def extract_pulse_features(payloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从若干 device-metrics 上报里抽取最新一份 hl.pulse.* 特征。"""
    features: dict[str, Any] = {}
    day = ""
    for payload in payloads:
        for metric in payload.get("metrics") or []:
            key = str(metric.get("key", ""))
            if not key.startswith(_PULSE_KEY_PREFIX):
                continue
            val = metric.get("value")
            if val is None or val == "":
                continue
            features[key] = val
            d = str(payload.get("day") or "")
            if d:
                day = d
    return {"features": features, "day": day} if features else None


def interpret_payloads(payloads: list[dict[str, Any]], user_ref: str) -> dict[str, Any]:
    extracted = extract_pulse_features(payloads)
    if not extracted:
        return {
            "items_count": 0,
            "items": [],
            "pulse_interpretation": None,
            "source": "pulse_gateway",
            "available": False,
        }
    features = extracted["features"]
    day = extracted["day"] or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        interp = pulse_engine.classify_pulse(features)
    except pulse_engine.PulseKnowledgeBaseError as exc:
        # 知识库不可用：显式标注 unavailable，而不是给一个标签名退化、八轴全空的假解读
        return {
            "items_count": 0,
            "items": [],
            "pulse_interpretation": None,
            "source": "pulse_gateway",
            "available": False,
            "reason": "pulse_knowledge_base_unavailable",
            "detail": str(exc),
        }
    observation = pulse_engine.build_pulse_observation(features, user_ref, day)
    return {
        "items_count": 1,
        "items": [observation],
        "pulse_interpretation": interp,
        "source": "pulse_gateway",
        "available": True,
    }


@ConnectorRegistry.register("pulse_gateway")
class PulseGatewayConnector(BaseConnector):
    """号脉网关连接器 - 从最近边缘上报读 hl.pulse.* 并解读"""

    SOURCE_TYPE = "pulse_gateway"
    DISPLAY_NAME = "HealthLens 号脉网关"

    def __init__(self):
        self.token = getattr(settings, "EDGE_GATEWAY_TOKEN", "")
        self._token_passthrough = True

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """access_token 此处是 user_ref（边缘不知道真实用户身份）"""
        try:
            from app.api.device_metrics import recent

            payloads = recent(access_token, days)
        except Exception as exc:
            logger.warning(f"[pulse_gateway] 读取边缘指标失败: {exc}")
            return {"items_count": 0, "items": [], "pulse_interpretation": None, "unavailable": str(exc)}
        return interpret_payloads(payloads, access_token)

    async def sync_data(self, access_token: str, user_id: str, since=None) -> dict:
        data = await self.fetch_health_data(access_token)
        return {
            "success": True,
            "records_count": data["items_count"],
            "errors": [],
            "synced_at": datetime.now(UTC),
            "raw_data": data.get("items", []),
        }

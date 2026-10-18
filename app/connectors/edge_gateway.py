"""边缘网关（healthgateway）连接器

边缘设备把「日粒度健康指标」推到 /api/v1/device-metrics，云端由本连接器
把这些指标转成 HealthObservation 风格的记录，喂给八轴融合引擎。

命名纪律（跟项目其它证据一样，不编造标准码）：
- 只有能给出真实 LOINC 码的字段才填 loinc_code（当前仅 resting_heart_rate -> 8867-4）；
- 领域特有的 EEG 频带比、α 不对称走 `hl.` 自有命名空间，loinc_code 为 None，
  loinc_name 写清是哪条指标，不冒充标准码。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.connectors.base import BaseConnector, ConnectorRegistry

logger = logging.getLogger(__name__)

# 真实 LOINC 映射：仅在确定有标准码时登记
LOINC_MAP: dict[str, tuple[str, str]] = {
    "resting_heart_rate": ("8867-4", "心率"),
    "heart_rate": ("8867-4", "心率"),
}

# 健康护栏：数值超出合理生理区间直接丢弃，不让脏数据进八轴
PHYSIO_BOUNDS: dict[str, tuple[float, float]] = {
    "resting_heart_rate": (30.0, 220.0),
    "hl.eeg.alpha_ratio": (0.0, 1.0),
    "hl.eeg.theta_ratio": (0.0, 1.0),
    "hl.eeg.beta_ratio": (0.0, 1.0),
    "hl.eeg.delta_ratio": (0.0, 1.0),
    "hl.eeg.alpha_asymmetry": (-5.0, 5.0),
}


def map_metrics_to_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """边缘指标 -> HealthObservation 记录

    payload 形如：{"gateway_id", "user_ref", "day", "device", "metrics", "stats"}
    产出沿用 HealthObservation 的列语义（loinc_code / value_numeric / recorded_at / source）。
    """
    day = str(payload.get("day") or "")
    gateway_id = str(payload.get("gateway_id") or "edge")
    source = f"edge_gateway:{gateway_id}"
    try:
        recorded_at = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).isoformat()
    except (ValueError, TypeError):
        recorded_at = datetime.now(UTC).isoformat()

    observations: list[dict[str, Any]] = []
    for metric in payload.get("metrics") or []:
        key = str(metric.get("key", ""))
        value = metric.get("value")
        if not key or not isinstance(value, (int, float)):
            continue
        bounds = PHYSIO_BOUNDS.get(key)
        if bounds and not (bounds[0] <= float(value) <= bounds[1]):
            logger.warning(f"[edge_gateway] 越界丢弃 {key}={value}")
            continue
        loinc_code, loinc_name = LOINC_MAP.get(key, (None, f"边缘网关指标 {key}"))
        observations.append(
            {
                "loinc_code": loinc_code,
                "loinc_name": loinc_name,
                "value_numeric": round(float(value), 5),
                "value_unit": metric.get("unit"),
                "value_string": None,
                "source": source,
                "recorded_at": recorded_at,
                "evidence": metric.get("evidence", "edge-derived"),
                "sample_count": metric.get("sample_count"),
            }
        )
    return observations


@ConnectorRegistry.register("edge_gateway")
class EdgeGatewayConnector(BaseConnector):
    """边缘网关连接器 - 从最近指标缓存读边缘上报"""

    SOURCE_TYPE = "edge_gateway"
    DISPLAY_NAME = "HealthLens 边缘网关"

    def __init__(self):
        self.api_url = getattr(settings, "PUBLIC_BASE_URL", "https://healthlens.cc").rstrip("/")
        self.token = getattr(settings, "EDGE_GATEWAY_TOKEN", "")
        self._token_passthrough = True

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """access_token 此处是 user_ref（边缘不知道真实用户身份）"""
        try:
            from app.api.device_metrics import recent

            payloads = recent(access_token, days)
        except Exception as exc:  # 路由未加载 / 缓存为空都算不可用，不拖垮主流程
            logger.warning(f"[edge_gateway] 读取边缘指标失败: {exc}")
            return {"items_count": 0, "items": [], "unavailable": str(exc)}

        items: list[dict[str, Any]] = []
        for payload in payloads:
            items.extend(map_metrics_to_observations(payload))
        return {
            "items_count": len(items),
            "items": items,
            "source": "edge_gateway",
            "days": days,
        }

    async def sync_data(self, access_token: str, user_id: str, since=None) -> dict:
        data = await self.fetch_health_data(access_token)
        return {
            "success": True,
            "records_count": data["items_count"],
            "errors": [],
            "synced_at": datetime.now(UTC),
            "raw_data": data["items"],
        }

"""HealthLens Powered-by SDK —— 对外部合作方暴露的异步 Python 客户端。

用法（示意）：
    from app.integrations.sdk import HealthLensClient

    async with HealthLensClient(base_url="https://api.healthlens.cc", api_key="hl_live_xxx") as c:
        r = await c.health_score(user_id="u_123", date="2026-10-15")
        r = await c.axis_assessment(user_id="u_123")
        r = await c.tcm_recommendations(user_id="u_123")
        r = await c.wellness_report(user_id="u_123")
        r = await c.config(partner_id="p_abc")
        r = await c.health_check()

wellness 边界
------------
本 SDK 只封装 wellness 平台公开 API，所有输出附 disclaimer 字段。合作方不得
用于医疗诊断/治疗/患者管理。参见各端点响应内的 `disclaimer`。
"""
from .client import (
    HealthLensClient,
    HealthLensAPIError,
    HealthLensAuthError,
)

__all__ = [
    "HealthLensClient",
    "HealthLensAPIError",
    "HealthLensAuthError",
]

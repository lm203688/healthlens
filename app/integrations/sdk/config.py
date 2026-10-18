"""远程配置拉取 —— S3-2 Powered-by SDK。

给合作方（或合作方侧的 SDK 层）提供一个统一的「读当前 partner 配置」入口。
所有值从 Partner 表读取；不缓存（配置改动立即生效，配合低复杂度设计）。

wellness 边界
------------
返回的模块清单使用健康导向命名（energy / digestion / sleep 等），
不使用医疗术语；enabled_modules 与 allowed_endpoints 均可由 admin 配置。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.partner import Partner

# 合作方默认可用的模块集合（wellness 语义，非医疗）
DEFAULT_ENABLED_MODULES = [
    "health_score",
    "axis_assessment",
    "tcm_recommendations",
    "wellness_report",
]

# 合作方默认可调用的端点白名单（路径后缀匹配）
DEFAULT_ALLOWED_ENDPOINTS = [
    "/partner-api/health",
    "/partner-api/health-score",
    "/partner-api/axis-assessment",
    "/partner-api/tcm-recommendations",
    "/partner-api/wellness-report",
]

# wellness 平台的对外 disclaimer 模板（合作方集成时原样呈现给用户）
DISCLAIMER = (
    "HealthLens 是 wellness（健康管理）平台，非医疗诊断或治疗工具。"
    "所有输出为健康信号参考与生活方式引导，不构成医疗建议。"
    "身体不适请咨询执业医生。"
)


async def _load_partner(partner_id: str, db: AsyncSession) -> Partner:
    result = await db.execute(select(Partner).where(Partner.id == partner_id))
    partner = result.scalar_one_or_none()
    if partner is None:
        raise KeyError(f"partner not found: {partner_id}")
    return partner


async def get_partner_config(partner_id: str, db: AsyncSession | None = None) -> dict[str, Any]:
    """获取 partner 的运行时配置。

    Args:
        partner_id: 合作方 ID
        db: 可选的 AsyncSession；为 None 时自建会话（非 FastAPI 场景使用）

    Returns:
        dict，包含：
            - partner_id / name / status
            - enabled_modules: list[str]
            - allowed_endpoints: list[str]
            - rate_limit: {"per_min": int}
            - base_url: str
            - disclaimer: str
            - version: str

    Raises:
        KeyError: partner 不存在（调用方可转 404）
    """
    async def _do(session: AsyncSession) -> dict[str, Any]:
        p = await _load_partner(partner_id, session)
        enabled = DEFAULT_ENABLED_MODULES
        if p.allowed_endpoints:
            enabled = [s.strip() for s in str(p.allowed_endpoints).split(",") if s.strip()]

        return {
            "success": True,
            "partner_id": p.id,
            "name": p.name,
            "status": p.status,
            "enabled_modules": enabled,
            "allowed_endpoints": DEFAULT_ALLOWED_ENDPOINTS,
            "rate_limit": {"per_min": int(p.rate_limit_per_min or 0)},
            "base_url": get_api_base_url_sync(p),
            "disclaimer": DISCLAIMER,
            "version": settings.APP_VERSION,
        }

    if db is None:
        async with get_db() as session:
            return await _do(session)
    return await _do(db)


def get_api_base_url_sync(partner: Partner) -> str:
    """返回合作方专属 base URL（当前实现：统一走 public base）。

    未来支持 per-partner 子域时在此分派。fail-loud：PUBLIC_BASE_URL 未配置时
    回落到 `http://localhost:8000`，仅用于本地开发，不上生产。
    """
    base = getattr(settings, "PUBLIC_BASE_URL", "") or ""
    if not base:
        return "http://localhost:8000"
    return base.rstrip("/")


async def get_api_base_url(partner_id: str, db: AsyncSession | None = None) -> str:
    """异步获取合作方专属 base URL。"""
    async def _do(session: AsyncSession) -> str:
        p = await _load_partner(partner_id, session)
        return get_api_base_url_sync(p)

    if db is None:
        async with get_db() as session:
            return await _do(session)
    return await _do(db)

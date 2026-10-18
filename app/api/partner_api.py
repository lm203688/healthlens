"""合作方对外 API —— S3-2 Powered-by SDK。

所有端点除 `/health` 外均要求 `X-API-Key` 认证（非 JWT）。

端点
----
- GET  /api/v1/partner-api/health           公开健康检查
- GET  /api/v1/partner-api/config           获取 partner 配置
- POST /api/v1/partner-api/health-score     用户健康评分
- POST /api/v1/partner-api/axis-assessment  八轴评估
- POST /api/v1/partner-api/tcm-recommendations  TCM 推荐
- POST /api/v1/partner-api/wellness-report  综合 wellness 报告

wellness 边界
------------
所有响应带 `disclaimer` 字段，不含诊断/治疗/疾病术语；合作方集成时
必须原样呈现给终端用户。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.integrations.sdk.auth import api_key_header, hash_api_key
from app.integrations.sdk.config import DISCLAIMER, get_partner_config
from app.integrations.sdk.health_check import check_health
from app.models.user import User

router = APIRouter(tags=["合作方API"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class UserIdIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)


class HealthScoreIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    date: Optional[str] = Field(
        default=None,
        description="YYYY-MM-DD 格式日期，缺省为当日",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Wellness 输出构造（无真实个体数据时的确定性合成占位）
# ─────────────────────────────────────────────────────────────────────────────

# 八轴中文标签（与 wellness_simulator 保持一致）
AXIS_LABELS: dict[str, str] = {
    "A": "气化/自噬",
    "B": "气血-线粒体",
    "C": "络脉-清瘀",
    "D": "阴阳-昼夜",
    "E": "脏腑-神经内分泌",
    "F": "正邪-炎症",
    "G": "神-情志",
    "H": "先天-肾精",
}


def _deterministic_score(user_id: str, axis: str, date: str | None = None) -> float:
    """基于 user_id + axis 的确定性 wellness 信号分（0-100，非临床值）。"""
    seed_str = f"{user_id}:{axis}:{date or 'today'}"
    n = sum(ord(c) for c in seed_str)
    # 映射到 [40, 90] 之间，避免极端值造成合作方 UI 抖动
    return round(40.0 + (n % 51), 1)


def _axis_scores(user_id: str, date: str | None = None) -> dict[str, float]:
    return {ax: _deterministic_score(user_id, ax, date) for ax in AXIS_LABELS}


def _composite_score(user_id: str, date: str | None = None) -> float:
    axes = _axis_scores(user_id, date)
    return round(sum(axes.values()) / len(axes), 1)


async def _ensure_user_exists(user_id: str, db: AsyncSession) -> User:
    """确保 user_id 存在。不存在返回 404。

    fail-loud：合作方传入不存在的 user_id 不做静默兜底（否则合作方会拿到
    「看起来正常」的合成数据但无法溯源）。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user not found: {user_id}",
        )
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health")
async def partner_health_check(db: AsyncSession = Depends(get_db)):
    """公开健康检查端点（无需 API Key）。合作方监控使用。"""
    return await check_health(db)


@router.get("/config")
async def partner_config(
    partner_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    partner: dict[str, Any] = Depends(api_key_header),
):
    """获取合作方配置。

    - 若请求参数 `partner_id` 为空：使用认证 partner 的配置
    - 若指定 `partner_id`：允许跨 partner 查询（管理/迁移场景）；返回目标 partner
      的完整配置（不返回未授权敏感字段，如 api_key_hash）
    """
    target_id = partner_id or partner["partner_id"]
    try:
        cfg = await get_partner_config(target_id, db)
    except KeyError:
        raise HTTPException(status_code=404, detail="partner not found")
    return cfg


@router.post("/health-score")
async def partner_health_score(
    body: HealthScoreIn,
    db: AsyncSession = Depends(get_db),
    partner: dict[str, Any] = Depends(api_key_header),
):
    """用户健康评分。基于八轴均值，non-clinical wellness 参考值。"""
    await _ensure_user_exists(body.user_id, db)
    composite = _composite_score(body.user_id, body.date)
    return {
        "success": True,
        "user_id": body.user_id,
        "date": body.date or "today",
        "health_score": composite,
        "axis_scores": _axis_scores(body.user_id, body.date),
        "partner_id": partner["partner_id"],
        "disclaimer": DISCLAIMER,
    }


@router.post("/axis-assessment")
async def partner_axis_assessment(
    body: UserIdIn,
    db: AsyncSession = Depends(get_db),
    partner: dict[str, Any] = Depends(api_key_header),
):
    """八轴评估：返回 8 轴 wellness 信号分与中文标签。"""
    await _ensure_user_exists(body.user_id, db)
    scores = _axis_scores(body.user_id)
    return {
        "success": True,
        "user_id": body.user_id,
        "axes": [
            {
                "code": ax,
                "label": AXIS_LABELS[ax],
                "score": scores[ax],
            }
            for ax in AXIS_LABELS
        ],
        "partner_id": partner["partner_id"],
        "disclaimer": DISCLAIMER,
    }


@router.post("/tcm-recommendations")
async def partner_tcm_recommendations(
    body: UserIdIn,
    db: AsyncSession = Depends(get_db),
    partner: dict[str, Any] = Depends(api_key_header),
):
    """TCM 生活方式推荐（wellness 语义，非治疗建议）。"""
    await _ensure_user_exists(body.user_id, db)
    scores = _axis_scores(body.user_id)
    # 选分值最低的 3 轴作为关注重点（wellness 参考，非辨证）
    weakest = sorted(scores.items(), key=lambda kv: kv[1])[:3]
    recommendations = [
        {
            "axis": ax,
            "label": AXIS_LABELS[ax],
            "score": score,
            "focus": "重点关注",
            "note": "根据当前 wellness 信号提示的关注方向",
        }
        for ax, score in weakest
    ]
    return {
        "success": True,
        "user_id": body.user_id,
        "recommendations": recommendations,
        "partner_id": partner["partner_id"],
        "disclaimer": DISCLAIMER,
    }


@router.post("/wellness-report")
async def partner_wellness_report(
    body: UserIdIn,
    db: AsyncSession = Depends(get_db),
    partner: dict[str, Any] = Depends(api_key_header),
):
    """综合 wellness 报告：一次性汇总 health_score + axis + tcm 三合一。"""
    await _ensure_user_exists(body.user_id, db)
    scores = _axis_scores(body.user_id)
    composite = _composite_score(body.user_id)
    weakest = sorted(scores.items(), key=lambda kv: kv[1])[:3]
    return {
        "success": True,
        "user_id": body.user_id,
        "composite_score": composite,
        "axis_scores": scores,
        "focus_axes": [ax for ax, _ in weakest],
        "partner_id": partner["partner_id"],
        "disclaimer": DISCLAIMER,
    }

"""增强版推广 API
补充排行榜、渠道统计、GEO引用测量等缺失端点
路由前缀: /api/v1/growth (与 growth.py 合并注册)
"""
from fastapi import APIRouter, Depends, Query
from loguru import logger
from typing import Optional

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/leaderboard", summary="邀请排行榜")
async def get_leaderboard(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取邀请排行榜 Top N"""
    from app.services.referral_service import get_leaderboard

    leaderboard = await get_leaderboard(db, limit=limit)
    return {"success": True, "data": leaderboard}


@router.get("/channel-stats", summary="渠道来源统计")
async def get_channel_stats(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """获取各推广渠道的流量和转化统计"""
    from app.services.analytics_service import get_channel_stats

    stats = await get_channel_stats(db, days=days)
    return {"success": True, "data": stats}


@router.get("/funnel-stats", summary="转化漏斗统计")
async def get_funnel_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """获取注册→首次操作→付费的转化漏斗数据"""
    from app.services.analytics_service import get_funnel_stats

    funnel = await get_funnel_stats(db)
    return {"success": True, "data": funnel}

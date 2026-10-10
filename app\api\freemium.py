"""Freemium 积分门禁 API
路由前缀: /api/v1/freemium
暴露 FreemiumGate 服务给前端调用
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from loguru import logger

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class AccessExecuteRequest(BaseModel):
    """执行高级功能访问请求"""
    feature_code: str = Field(..., min_length=1, max_length=50)
    source_id: Optional[str] = None


class RoiCheckRequest(BaseModel):
    """ROI 评估请求"""
    feature_code: str = Field(..., min_length=1, max_length=50)


@router.get("/features", summary="获取功能列表")
async def list_features(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取所有功能列表（免费 + 高级）及积分费用"""
    from app.services.freemium_service import get_all_features, get_free_features
    return {
        "success": True,
        "data": {
            "free_features": get_free_features(),
            "premium_features": get_all_features(),
        },
    }


@router.get("/balance-info", summary="获取积分余额及门禁状态")
async def get_balance_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户积分余额及所有高级功能的可访问状态"""
    from app.services.freemium_service import FreemiumGate, get_points_balance
    from app.services.points_service import get_points_balance

    balance_info = await get_points_balance(db, current_user.id)

    # 检查每个高级功能的状态
    feature_statuses = []
    for code, rule in FreemiumGate.PREMIUM_RULES.items():
        status = await FreemiumGate.check_access(db, current_user.id, code)
        feature_statuses.append({
            "code": code,
            "name": rule["name"],
            "cost": rule["cost"],
            "allowed": status["allowed"],
            "shortfall": status.get("shortfall", 0),
        })

    return {
        "success": True,
        "data": {
            "balance": balance_info["balance"],
            "total_earned": balance_info["total_earned"],
            "total_spent": balance_info["total_spent"],
            "features": feature_statuses,
        },
    }


@router.post("/check", summary="检查功能访问权限")
async def check_access(
    feature_code: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查用户是否有足够积分访问指定高级功能（不扣减）"""
    from app.services.freemium_service import FreemiumGate

    result = await FreemiumGate.check_access(db, current_user.id, feature_code)
    result["success"] = True
    return result


@router.post("/access", summary="执行高级功能访问（扣减积分）")
async def execute_access(
    body: AccessExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """原子化执行访问：检查 + 扣减 + 记录"""
    from app.services.freemium_service import FreemiumGate

    result = await FreemiumGate.execute_access(
        db, current_user.id, body.feature_code, body.source_id
    )
    return result


@router.get("/earning-guide", summary="获取积分赚取指南")
async def earning_guide(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成个性化积分赚取指南，帮助用户规划如何解锁目标功能"""
    from app.services.freemium_service import FreemiumGate

    guide = await FreemiumGate.get_earning_guide(db, current_user.id)
    return {"success": True, "data": guide}


@router.post("/roi", summary="功能价值评估")
async def check_roi(
    body: RoiCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """评估某高级功能对当前用户的价值（ROI 分析）"""
    from app.services.freemium_service import calculate_roi

    roi = await calculate_roi(db, current_user.id, body.feature_code)
    return {"success": True, "data": roi}

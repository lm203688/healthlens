"""积分系统 API - 健康币查询、交易历史、积分任务"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.user import User
from app.models.points import PointRule
from app.api.deps import get_current_user
from app.services.points_service import (
    get_points_balance,
    get_transaction_history,
    award_points,
    spend_points,
    initialize_default_rules,
)
from loguru import logger

router = APIRouter(tags=["积分系统"])


# ============ Schemas ============

class PointEarnRequest(BaseModel):
    """积分获取请求（管理员/系统调用）"""
    rule_code: str
    source_id: str | None = None
    description: str | None = None


class PointSpendRequest(BaseModel):
    """积分消费请求"""
    rule_code: str
    source_id: str | None = None
    description: str | None = None
    quantity: int = Field(1, ge=1)


class PointRuleResponse(BaseModel):
    """积分规则响应"""
    rule_code: str
    rule_name: str
    description: str | None
    action_type: str
    base_points: float
    category: str | None
    daily_limit: int | None


# ============ Endpoints ============

@router.get("/balance", response_model=dict)
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户积分余额"""
    balance = await get_points_balance(db, str(current_user.id))
    return {"success": True, "data": balance}


@router.get("/transactions", response_model=dict)
async def list_transactions(
    tx_type: str | None = Query(None, description="交易类型: earn/spend/refund"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取积分交易历史"""
    result = await get_transaction_history(
        db, str(current_user.id), tx_type=tx_type, page=page, page_size=page_size
    )
    return {"success": True, "data": result["data"], "meta": result["meta"]}


@router.get("/rules", response_model=dict)
async def list_rules(
    category: str | None = Query(None, description="分类筛选"),
    action_type: str | None = Query(None, description="类型: earn/spend"),
    db: AsyncSession = Depends(get_db),
):
    """获取积分规则列表"""
    query = select(PointRule).where(PointRule.is_active == True)
    if category:
        query = query.where(PointRule.category == category)
    if action_type:
        query = query.where(PointRule.action_type == action_type)

    query = query.order_by(PointRule.priority.desc(), PointRule.created_at.asc())
    result = await db.execute(query)
    rules = result.scalars().all()

    data = []
    for r in rules:
        data.append({
            "rule_code": r.rule_code,
            "rule_name": r.rule_name,
            "description": r.description,
            "action_type": r.action_type,
            "base_points": float(r.base_points),
            "category": r.category,
            "daily_limit": r.daily_limit,
            "monthly_limit": r.monthly_limit,
        })

    return {"success": True, "data": data}


@router.post("/earn", response_model=dict)
async def earn_points(
    body: PointEarnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取积分（通过完成指定行为）
    - 客户端调用此接口报告用户完成了某个行为
    - 系统根据规则自动计算并发放积分
    - 统一返回 {"success": true/false, ...} 格式
    """
    result = await award_points(
        db,
        user_id=str(current_user.id),
        rule_code=body.rule_code,
        source_id=body.source_id,
        extra_description=body.description,
    )
    if result["success"]:
        return {"success": True, "data": result}
    # 业务逻辑失败，返回统一格式（HTTP 200）
    return {
        "success": False,
        "error": {
            "code": "POINTS_EARN_FAILED",
            "message": result.get("message", "Failed to award points"),
            "awarded": result.get("awarded", 0),
        },
    }


@router.post("/spend", response_model=dict)
async def spend_user_points(
    body: PointSpendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    消费积分（用于兑换服务/功能）
    - 在调用需要积分的服务前，先调用此接口扣减积分
    - 统一返回 {"success": true/false, ...} 格式
    """
    result = await spend_points(
        db,
        user_id=str(current_user.id),
        rule_code=body.rule_code,
        source_id=body.source_id,
        extra_description=body.description,
        quantity=body.quantity,
    )
    if result["success"]:
        return {"success": True, "data": result}
    # 业务逻辑失败，返回统一格式（HTTP 200）
    error_code = "INSUFFICIENT_POINTS" if "Insufficient" in result.get("message", "") else "POINTS_SPEND_FAILED"
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": result.get("message", "Failed to spend points"),
            "required": result.get("required"),
            "balance": result.get("balance"),
        },
    }


@router.get("/tasks/daily", response_model=dict)
async def get_daily_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取今日积分任务列表及完成状态
    """
    from app.models.points import PointTransaction

    today = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    tomorrow = today + timedelta(days=1)

    # 获取所有 earn 规则
    result = await db.execute(
        select(PointRule).where(
            and_(PointRule.action_type == "earn", PointRule.is_active == True)
        )
    )
    rules = result.scalars().all()

    tasks = []
    for rule in rules:
        # 查询今日已完成次数
        count_result = await db.execute(
            select(func.count())
            .select_from(PointTransaction)
            .where(
                and_(
                    PointTransaction.user_id == str(current_user.id),
                    PointTransaction.source == rule.rule_code,
                    PointTransaction.tx_type == "earn",
                    PointTransaction.created_at >= today,
                    PointTransaction.created_at < tomorrow,
                )
            )
        )
        completed = count_result.scalar() or 0
        limit = rule.daily_limit or 1

        tasks.append({
            "rule_code": rule.rule_code,
            "rule_name": rule.rule_name,
            "description": rule.description,
            "points": float(rule.base_points),
            "category": rule.category,
            "completed_count": completed,
            "daily_limit": limit,
            "is_available": completed < limit,
            "progress": f"{completed}/{limit}",
        })

    # 按分类分组
    grouped = {}
    for task in tasks:
        cat = task["category"] or "other"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(task)

    return {
        "success": True,
        "data": {
            "tasks": tasks,
            "by_category": grouped,
            "total_available": sum(1 for t in tasks if t["is_available"]),
        },
    }


@router.post("/admin/init-rules", response_model=dict)
async def init_point_rules(
    db: AsyncSession = Depends(get_db),
):
    """初始化默认积分规则（管理员接口）"""
    await initialize_default_rules(db)
    return {"success": True, "data": {"message": "Default rules initialized"}}

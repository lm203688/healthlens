"""健康目标 API - 目标设定、进度追踪、完成度分析"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models.user import User
from app.models.health_goal import HealthGoal, GoalProgress
from app.api.deps import get_current_user

router = APIRouter(tags=["goals"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GoalCreateInput(BaseModel):
    goal_type: str  # weight / steps / bp / glucose / exercise / sleep
    goal_name: str
    target_value: float
    current_value: float | None = None
    unit: str
    target_date: datetime
    notes: str | None = None
    is_reminder_enabled: bool = True


class GoalUpdateInput(BaseModel):
    goal_name: str | None = None
    target_value: float | None = None
    current_value: float | None = None
    target_date: datetime | None = None
    status: str | None = None
    notes: str | None = None
    is_reminder_enabled: bool | None = None


class ProgressCreateInput(BaseModel):
    value: float
    note: str | None = None


# ---------------------------------------------------------------------------
# Goals CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建健康目标"""
    goal = HealthGoal(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        goal_type=body.goal_type,
        goal_name=body.goal_name,
        target_value=body.target_value,
        current_value=body.current_value,
        unit=body.unit,
        start_date=datetime.now(timezone.utc),
        target_date=body.target_date,
        notes=body.notes,
        is_reminder_enabled=body.is_reminder_enabled,
    )

    # 计算初始进度
    if body.current_value is not None and body.target_value:
        goal.progress = _calculate_progress(body.current_value, body.target_value, body.goal_type)

    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    return {
        "success": True,
        "data": _serialize_goal(goal),
    }


@router.get("", response_model=dict)
async def list_goals(
    status_filter: str | None = Query(None, alias="status"),
    goal_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取健康目标列表"""
    query = select(HealthGoal).where(HealthGoal.user_id == current_user.id)
    count_query = select(func.count()).select_from(HealthGoal).where(
        HealthGoal.user_id == current_user.id
    )

    if status_filter:
        query = query.where(HealthGoal.status == status_filter)
        count_query = count_query.where(HealthGoal.status == status_filter)
    if goal_type:
        query = query.where(HealthGoal.goal_type == goal_type)
        count_query = count_query.where(HealthGoal.goal_type == goal_type)

    query = query.order_by(desc(HealthGoal.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    goals = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "success": True,
        "data": [_serialize_goal(g) for g in goals],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/{goal_id}", response_model=dict)
async def get_goal_detail(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取目标详情"""
    result = await db.execute(
        select(HealthGoal).where(
            HealthGoal.id == goal_id,
            HealthGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    # 获取进度历史
    progress_result = await db.execute(
        select(GoalProgress).where(GoalProgress.goal_id == goal_id).order_by(desc(GoalProgress.recorded_at)).limit(30)
    )
    progress_records = progress_result.scalars().all()

    goal_data = _serialize_goal(goal)
    goal_data["progress_history"] = [
        {
            "id": str(p.id),
            "value": float(p.value) if p.value else None,
            "recorded_at": p.recorded_at.isoformat() if p.recorded_at else None,
            "note": p.note,
        }
        for p in progress_records
    ]

    return {"success": True, "data": goal_data}


@router.put("/{goal_id}", response_model=dict)
async def update_goal(
    goal_id: str,
    body: GoalUpdateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新健康目标"""
    result = await db.execute(
        select(HealthGoal).where(
            HealthGoal.id == goal_id,
            HealthGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    if body.goal_name is not None:
        goal.goal_name = body.goal_name
    if body.target_value is not None:
        goal.target_value = body.target_value
    if body.current_value is not None:
        goal.current_value = body.current_value
    if body.target_date is not None:
        goal.target_date = body.target_date
    if body.status is not None:
        goal.status = body.status
    if body.notes is not None:
        goal.notes = body.notes
    if body.is_reminder_enabled is not None:
        goal.is_reminder_enabled = body.is_reminder_enabled

    # 重新计算进度
    if goal.current_value is not None and goal.target_value:
        goal.progress = _calculate_progress(float(goal.current_value), float(goal.target_value), goal.goal_type)

    await db.commit()
    await db.refresh(goal)

    return {"success": True, "data": _serialize_goal(goal)}


@router.delete("/{goal_id}", response_model=dict)
async def delete_goal(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除健康目标(标记为放弃)"""
    result = await db.execute(
        select(HealthGoal).where(
            HealthGoal.id == goal_id,
            HealthGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    goal.status = "abandoned"
    await db.commit()

    return {"success": True, "data": {"message": "Goal abandoned"}}


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

@router.post("/{goal_id}/progress", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_progress(
    goal_id: str,
    body: ProgressCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加目标进度记录"""
    result = await db.execute(
        select(HealthGoal).where(
            HealthGoal.id == goal_id,
            HealthGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    # 创建进度记录
    progress = GoalProgress(
        id=str(uuid.uuid4()),
        goal_id=goal_id,
        value=body.value,
        recorded_at=datetime.now(timezone.utc),
        note=body.note,
    )
    db.add(progress)

    # 更新目标当前值和进度
    goal.current_value = body.value
    goal.progress = _calculate_progress(body.value, float(goal.target_value), goal.goal_type)

    # 检查是否完成
    if goal.progress >= 100:
        goal.status = "completed"

    await db.commit()
    await db.refresh(progress)

    return {
        "success": True,
        "data": {
            "id": str(progress.id),
            "value": float(progress.value) if progress.value else None,
            "recorded_at": progress.recorded_at.isoformat() if progress.recorded_at else None,
            "goal_progress": float(goal.progress) if goal.progress else 0,
            "goal_status": goal.status,
        },
    }


@router.get("/summary/stats", response_model=dict)
async def get_goals_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取目标统计信息"""
    # 总目标数
    total_result = await db.execute(
        select(func.count()).select_from(HealthGoal).where(HealthGoal.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    # 活跃目标
    active_result = await db.execute(
        select(func.count()).select_from(HealthGoal).where(
            HealthGoal.user_id == current_user.id,
            HealthGoal.status == "active",
        )
    )
    active = active_result.scalar() or 0

    # 已完成
    completed_result = await db.execute(
        select(func.count()).select_from(HealthGoal).where(
            HealthGoal.user_id == current_user.id,
            HealthGoal.status == "completed",
        )
    )
    completed = completed_result.scalar() or 0

    # 平均完成度
    avg_result = await db.execute(
        select(func.avg(HealthGoal.progress)).where(
            HealthGoal.user_id == current_user.id,
            HealthGoal.status == "active",
        )
    )
    avg_progress = float(avg_result.scalar() or 0)

    return {
        "success": True,
        "data": {
            "total_goals": total,
            "active_goals": active,
            "completed_goals": completed,
            "average_progress": round(avg_progress, 1),
            "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calculate_progress(current: float, target: float, goal_type: str) -> float:
    """计算目标完成进度 (0-100)"""
    if target == 0:
        return 0.0

    if goal_type in ("weight", "bp", "glucose", "ldl_c"):
        # 下降型目标: 当前值越低越好
        if current <= target:
            return 100.0
        # 假设初始值比目标高 20%
        initial = target * 1.2
        progress = (initial - current) / (initial - target) * 100
        return max(0.0, min(100.0, round(progress, 1)))
    else:
        # 上升型目标: 步数、运动时长
        if current >= target:
            return 100.0
        progress = current / target * 100
        return max(0.0, min(100.0, round(progress, 1)))


def _serialize_goal(goal: HealthGoal) -> dict:
    return {
        "id": str(goal.id),
        "goal_type": goal.goal_type,
        "goal_name": goal.goal_name,
        "target_value": float(goal.target_value) if goal.target_value else None,
        "current_value": float(goal.current_value) if goal.current_value else None,
        "unit": goal.unit,
        "progress": float(goal.progress) if goal.progress else 0,
        "status": goal.status,
        "start_date": goal.start_date.isoformat() if goal.start_date else None,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "notes": goal.notes,
        "is_reminder_enabled": goal.is_reminder_enabled,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }

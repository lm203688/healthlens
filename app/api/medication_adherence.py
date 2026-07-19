"""用药依从性 API - 追踪用户服药记录、依从性统计"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from app.database import get_db
from app.models.user import User
from app.models.medication_adherence import MedicationAdherence
from app.api.deps import get_current_user

router = APIRouter(tags=["medication_adherence"])


class AdherenceCreateInput(BaseModel):
    """创建服药计划"""
    medication_name: str
    prescribed_dose: str | None = None
    scheduled_at: datetime
    note: str | None = None


class AdherenceRecordInput(BaseModel):
    """记录实际服药"""
    status: str  # taken / missed / skipped
    note: str | None = None


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_adherence_plan(
    body: AdherenceCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建服药计划记录"""
    record = MedicationAdherence(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        medication_name=body.medication_name,
        prescribed_dose=body.prescribed_dose,
        scheduled_at=body.scheduled_at,
        note=body.note,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {"success": True, "data": _serialize_adherence(record)}


@router.get("", response_model=dict)
async def list_adherence(
    status_filter: str | None = Query(None, alias="status"),
    days: int = Query(30, ge=1, le=365, description="查询最近N天"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取服药记录列表"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(MedicationAdherence).where(
        MedicationAdherence.user_id == current_user.id,
        MedicationAdherence.scheduled_at >= since,
    )
    count_query = select(func.count()).select_from(MedicationAdherence).where(
        MedicationAdherence.user_id == current_user.id,
        MedicationAdherence.scheduled_at >= since,
    )

    if status_filter:
        query = query.where(MedicationAdherence.status == status_filter)
        count_query = count_query.where(MedicationAdherence.status == status_filter)

    query = query.order_by(desc(MedicationAdherence.scheduled_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    records = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "success": True,
        "data": [_serialize_adherence(r) for r in records],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.put("/{record_id}", response_model=dict)
async def record_medication_intake(
    record_id: str,
    body: AdherenceRecordInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记录实际服药情况"""
    result = await db.execute(
        select(MedicationAdherence).where(
            MedicationAdherence.id == record_id,
            MedicationAdherence.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    record.status = body.status
    if body.status == "taken":
        now = datetime.now(timezone.utc)
        record.taken_at = now
        # 检查是否延误 (超过计划时间 30 分钟)
        if record.scheduled_at:
            # 统一时区: 若 scheduled_at 无时区信息，补上 UTC
            scheduled = record.scheduled_at
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            if now > scheduled + timedelta(minutes=30):
                record.is_late = True
    if body.note:
        record.note = body.note

    await db.commit()
    await db.refresh(record)

    return {"success": True, "data": _serialize_adherence(record)}


@router.get("/stats/summary", response_model=dict)
async def get_adherence_stats(
    days: int = Query(30, ge=1, le=365, description="统计最近N天"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用药依从性统计"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 总计划数
    total_result = await db.execute(
        select(func.count()).select_from(MedicationAdherence).where(
            MedicationAdherence.user_id == current_user.id,
            MedicationAdherence.scheduled_at >= since,
        )
    )
    total = total_result.scalar() or 0

    # 已服数
    taken_result = await db.execute(
        select(func.count()).select_from(MedicationAdherence).where(
            MedicationAdherence.user_id == current_user.id,
            MedicationAdherence.scheduled_at >= since,
            MedicationAdherence.status == "taken",
        )
    )
    taken = taken_result.scalar() or 0

    # 漏服数
    missed_result = await db.execute(
        select(func.count()).select_from(MedicationAdherence).where(
            MedicationAdherence.user_id == current_user.id,
            MedicationAdherence.scheduled_at >= since,
            MedicationAdherence.status == "missed",
        )
    )
    missed = missed_result.scalar() or 0

    # 延误数
    late_result = await db.execute(
        select(func.count()).select_from(MedicationAdherence).where(
            MedicationAdherence.user_id == current_user.id,
            MedicationAdherence.scheduled_at >= since,
            MedicationAdherence.is_late == True,
        )
    )
    late = late_result.scalar() or 0

    # 依从率 = 已服 / (已服 + 漏服) * 100
    adherence_rate = (taken / (taken + missed) * 100) if (taken + missed) > 0 else 0

    return {
        "success": True,
        "data": {
            "period_days": days,
            "total_planned": total,
            "total_taken": taken,
            "total_missed": missed,
            "total_late": late,
            "adherence_rate": round(adherence_rate, 1),
            "on_time_rate": round((taken - late) / taken * 100, 1) if taken > 0 else 0,
        },
    }


def _serialize_adherence(r: MedicationAdherence) -> dict:
    return {
        "id": str(r.id),
        "medication_name": r.medication_name,
        "prescribed_dose": r.prescribed_dose,
        "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
        "taken_at": r.taken_at.isoformat() if r.taken_at else None,
        "status": r.status,
        "is_late": r.is_late,
        "note": r.note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

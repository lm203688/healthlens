"""用户 wellness 自测闭环 API（SIIV 的 V 端）

- POST /api/v1/checkin          创建一次自测（能量/消化/睡眠 1-5 分 + 备注）
- GET  /api/v1/checkin/history  查看本人历史自测
- GET  /api/v1/checkin/summary  近 N 次自测的均值与趋势（数据飞轮反馈）

定位：主观健康感受记录，非医疗评估、非诊断。
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.wellness_checkin import WellnessCheckin

router = APIRouter(tags=["自测闭环"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CheckinInput(BaseModel):
    energy_score: int = Field(..., ge=1, le=5, description="精力/活力自评 (1-5)")
    digestion_score: int = Field(..., ge=1, le=5, description="消化/肠胃舒适自评 (1-5)")
    sleep_score: int = Field(..., ge=1, le=5, description="睡眠/休息质量自评 (1-5)")
    note: str | None = Field(None, max_length=500, description="当日主观备注（可选）")
    checkin_date: datetime | None = Field(None, description="自测日期（可回溯补填，默认今天）")


class CheckinOutput(BaseModel):
    id: str
    energy_score: int
    digestion_score: int
    sleep_score: int
    note: str | None
    checkin_date: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=dict)
async def create_checkin(
    body: CheckinInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记录一次 wellness 自测。"""
    record = WellnessCheckin(
        user_id=str(current_user.id),
        energy_score=body.energy_score,
        digestion_score=body.digestion_score,
        sleep_score=body.sleep_score,
        note=body.note,
        checkin_date=body.checkin_date or datetime.utcnow(),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        "success": True,
        "data": {
            "id": str(record.id),
            "energy_score": record.energy_score,
            "digestion_score": record.digestion_score,
            "sleep_score": record.sleep_score,
            "note": record.note,
            "checkin_date": record.checkin_date.isoformat(),
            "created_at": record.created_at.isoformat(),
        },
        "message": "自测已记录。长期记录可帮助观察自身精力/消化/睡眠变化趋势。",
    }


@router.get("/history", response_model=dict)
async def checkin_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看本人最近的自测记录。"""
    limit = max(1, min(limit, 50))
    result = await db.execute(
        select(WellnessCheckin)
        .where(WellnessCheckin.user_id == str(current_user.id))
        .order_by(WellnessCheckin.checkin_date.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return {
        "success": True,
        "data": {
            "count": len(rows),
            "items": [
                {
                    "id": str(r.id),
                    "energy_score": r.energy_score,
                    "digestion_score": r.digestion_score,
                    "sleep_score": r.sleep_score,
                    "note": r.note,
                    "checkin_date": r.checkin_date.isoformat(),
                }
                for r in rows
            ],
        },
    }


@router.get("/summary", response_model=dict)
async def checkin_summary(
    window: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """近 N 次自测的均值与趋势（数据飞轮反馈）。"""
    window = max(1, min(window, 50))
    result = await db.execute(
        select(WellnessCheckin)
        .where(WellnessCheckin.user_id == str(current_user.id))
        .order_by(WellnessCheckin.checkin_date.desc())
        .limit(window)
    )
    rows = result.scalars().all()

    if not rows:
        return {
            "success": True,
            "data": {
                "count": 0,
                "averages": None,
                "trend": None,
                "message": "暂无自测记录，开始每周自评以观察变化趋势。",
            },
        }

    # 按时间正序计算趋势（最早→最近）
    asc = list(reversed(rows))
    n = len(asc)
    avg_energy = sum(r.energy_score for r in asc) / n
    avg_digestion = sum(r.digestion_score for r in asc) / n
    avg_sleep = sum(r.sleep_score for r in asc) / n

    # 趋势：前半段均值 vs 后半段均值（样本>=4 才给趋势）
    trend = None
    if n >= 4:
        half = n // 2
        early = asc[:half]
        late = asc[half:]
        trend = {
            "energy": round(sum(r.energy_score for r in late) / len(late) - sum(r.energy_score for r in early) / len(early), 2),
            "digestion": round(sum(r.digestion_score for r in late) / len(late) - sum(r.digestion_score for r in early) / len(early), 2),
            "sleep": round(sum(r.sleep_score for r in late) / len(late) - sum(r.sleep_score for r in early) / len(early), 2),
        }

    return {
        "success": True,
        "data": {
            "count": n,
            "averages": {
                "energy": round(avg_energy, 2),
                "digestion": round(avg_digestion, 2),
                "sleep": round(avg_sleep, 2),
                "overall": round((avg_energy + avg_digestion + avg_sleep) / 3, 2),
            },
            "trend": trend,
            "latest_checkin_date": rows[0].checkin_date.isoformat(),
        },
    }

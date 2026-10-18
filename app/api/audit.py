"""运行时审计巡检 API（简化版 wellness 安全护栏）

- GET /api/v1/audit/recent  最近审计事件（admin）
- GET /api/v1/audit/status  近 7 天各类型事件计数与风险评分（admin）

仅 admin 可访问；用于事后巡检与「安全状态灯」数据源。
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.models.audit_event import AuditEvent

router = APIRouter(tags=["运行时审计"])


@router.get("/recent", response_model=dict)
async def audit_recent(
    limit: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """最近审计事件（admin）。"""
    limit = max(1, min(limit, 100))
    result = await db.execute(
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc())
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
                    "user_id": r.user_id,
                    "endpoint": r.endpoint,
                    "event_type": r.event_type,
                    "severity": r.severity,
                    "detail": r.detail,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        },
    }


@router.get("/status", response_model=dict)
async def audit_status(
    days: int = 7,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """近 N 天审计事件计数 + 风险评分（admin）。

    风险评分 = Σ(事件严重度) / 天数，归一化到 0-100（越高越需关注）。
    """
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(
            AuditEvent.event_type,
            func.count(AuditEvent.id),
            func.sum(AuditEvent.severity),
        ).where(AuditEvent.created_at >= since)
        .group_by(AuditEvent.event_type)
    )
    rows = result.all()

    by_type = {r[0]: {"count": r[1], "severity_sum": r[2] or 0} for r in rows}
    total_severity = sum(v["severity_sum"] for v in by_type.values())
    # 风险评分：日均严重度 × 20，封顶 100
    risk_score = min(100, round(total_severity / max(days, 1) * 20, 1))

    return {
        "success": True,
        "data": {
            "window_days": days,
            "by_type": by_type,
            "total_events": sum(v["count"] for v in by_type.values()),
            "total_severity": total_severity,
            "risk_score": risk_score,
            "level": "safe" if risk_score < 20 else ("watch" if risk_score < 50 else "alert"),
        },
    }

"""通知中心 API - 站内通知、健康提醒、用药提醒"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.api.deps import get_current_user

router = APIRouter(tags=["notifications"])


class NotificationCreateInput(BaseModel):
    """系统创建通知 (管理员/系统调用)"""
    category: str  # health_alert / medication / appointment / system / tcm
    title: str
    content: str
    severity: str = "info"  # info / warning / critical
    action_url: str | None = None
    action_label: str | None = None


@router.get("", response_model=dict)
async def list_notifications(
    category: str | None = Query(None, description="按分类筛选"),
    is_read: bool | None = Query(None, description="按已读状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取通知列表"""
    query = select(Notification).where(Notification.user_id == current_user.id)
    count_query = select(func.count()).select_from(Notification).where(
        Notification.user_id == current_user.id
    )

    if category:
        query = query.where(Notification.category == category)
        count_query = count_query.where(Notification.category == category)
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)
        count_query = count_query.where(Notification.is_read == is_read)

    query = query.order_by(desc(Notification.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    notifications = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # 未读数
    unread_result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    unread_count = unread_result.scalar() or 0

    return {
        "success": True,
        "data": [_serialize_notification(n) for n in notifications],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "unread_count": unread_count,
        },
    }


@router.get("/unread/count", response_model=dict)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取未读通知数量"""
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    count = result.scalar() or 0
    return {"success": True, "data": {"unread_count": count}}


@router.put("/{notification_id}/read", response_model=dict)
async def mark_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记单条通知为已读"""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    await db.commit()

    return {"success": True, "data": {"message": "Marked as read"}}


@router.put("/read-all", response_model=dict)
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """标记所有通知为已读"""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.commit()

    return {"success": True, "data": {"message": "All notifications marked as read"}}


@router.delete("/{notification_id}", response_model=dict)
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除通知"""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    await db.delete(notification)
    await db.commit()

    return {"success": True, "data": {"message": "Notification deleted"}}


def _serialize_notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "category": n.category,
        "title": n.title,
        "content": n.content,
        "severity": n.severity,
        "is_read": n.is_read,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "action_url": n.action_url,
        "action_label": n.action_label,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }

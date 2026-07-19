"""通知服务单元测试"""
import pytest
import uuid
from unittest.mock import patch
from sqlalchemy import select

from app.services.notification_service import (
    NotificationMessage,
    send_notification,
    notify_diagnosis_ready,
    notify_abnormal_detected,
)
from app.models.notification import Notification


def _make_async_persist(db_session):
    """创建一个使用测试 db_session 的 _persist_notification 替代函数。

    原始 _persist_notification 使用同步 SessionLocal，与测试的异步
    in-memory SQLite 不共享数据库。通过替换实现，使通知写入测试 session。
    """

    async def _persist(message: NotificationMessage) -> bool:
        notification = Notification(
            id=str(uuid.uuid4()),
            user_id=message.user_id,
            category=message.category,
            title=message.title,
            content=message.body,
            severity=message.severity,
            action_url=message.link,
            action_label="查看详情" if message.link else None,
        )
        db_session.add(notification)
        await db_session.commit()
        return True

    return _persist


@pytest.mark.asyncio
async def test_persist_notification(db_session):
    """创建 NotificationMessage, 调用 send_notification, 验证写入数据库"""
    user_id = str(uuid.uuid4())
    msg = NotificationMessage(
        user_id=user_id,
        title="测试通知",
        body="这是一条测试通知",
    )

    with patch(
        "app.services.notification_service._persist_notification",
        side_effect=_make_async_persist(db_session),
    ):
        result = await send_notification(msg)
        assert result is True

    # 验证数据库中有记录
    result = await db_session.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    notifications = result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].title == "测试通知"
    assert notifications[0].severity == "info"


@pytest.mark.asyncio
async def test_notify_diagnosis_ready(db_session):
    """调用 notify_diagnosis_ready, 验证 Notification 表有记录"""
    user_id = str(uuid.uuid4())

    with patch(
        "app.services.notification_service._persist_notification",
        side_effect=_make_async_persist(db_session),
    ):
        await notify_diagnosis_ready(user_id, diagnosis_count=3)

    result = await db_session.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    notifications = result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].title == "诊断报告已生成"
    assert notifications[0].category == "health_alert"


@pytest.mark.asyncio
async def test_notify_abnormal_detected(db_session):
    """调用 notify_abnormal_detected, 验证 severity 为 warning"""
    user_id = str(uuid.uuid4())

    with patch(
        "app.services.notification_service._persist_notification",
        side_effect=_make_async_persist(db_session),
    ):
        await notify_abnormal_detected(user_id, abnormal_count=2)

    result = await db_session.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    notifications = result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].severity == "warning"
    assert "2项异常指标" in notifications[0].title
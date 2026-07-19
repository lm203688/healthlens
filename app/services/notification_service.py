"""通知服务 - 多渠道消息推送
Phase 1: 站内通知持久化 + 日志
Phase 2: 飞书/微信/短信
"""
import uuid
from datetime import datetime, timezone
from loguru import logger
from dataclasses import dataclass


@dataclass
class NotificationMessage:
    user_id: str
    title: str
    body: str
    channel: str = "in_app"  # in_app / wechat / sms / feishu
    link: str | None = None
    severity: str = "info"  # info / warning / critical
    category: str = "system"  # health_alert / medication / appointment / system / tcm


async def _persist_notification(message: NotificationMessage) -> bool:
    """将站内通知写入数据库"""
    try:
        from app.database import SessionLocal
        from app.models.notification import Notification

        db = SessionLocal()
        try:
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
            db.add(notification)
            db.commit()
            logger.debug(f"Notification persisted: id={notification.id}, user={message.user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to persist notification: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Notification persistence unavailable: {e}")
        return False


async def send_notification(message: NotificationMessage) -> bool:
    """发送通知"""
    logger.info(f"[Notification] {message.channel} -> user={message.user_id}: {message.title}")

    if message.channel == "in_app":
        return await _persist_notification(message)
    elif message.channel == "feishu":
        # Phase 2: 飞书 webhook
        logger.info(f"  Feishu notification not yet implemented")
        # 同时也持久化到站内
        await _persist_notification(message)
        return True
    elif message.channel == "wechat":
        # Phase 2: 微信模板消息
        logger.info(f"  WeChat notification not yet implemented")
        await _persist_notification(message)
        return True
    elif message.channel == "sms":
        # Phase 2: 短信
        logger.info(f"  SMS notification not yet implemented")
        return True

    return True


async def notify_diagnosis_ready(user_id: str, diagnosis_count: int) -> None:
    """诊断完成通知"""
    await send_notification(NotificationMessage(
        user_id=user_id,
        title="诊断报告已生成",
        body=f"AI已完成{diagnosis_count}项诊断分析，请前往查看。",
        channel="in_app",
        category="health_alert",
        severity="info",
    ))


async def notify_tcm_formula_ready(user_id: str, formula_name: str) -> None:
    """中医方剂推荐通知"""
    await send_notification(NotificationMessage(
        user_id=user_id,
        title="方剂推荐已生成",
        body=f"已为您推荐方剂「{formula_name}」，请查看详情。",
        channel="in_app",
        category="tcm",
        severity="info",
    ))


async def notify_order_shipped(user_id: str, order_id: str, tracking: str | None = None) -> None:
    """配送发货通知"""
    body = f"您的中药配方颗粒已发货。"
    if tracking:
        body += f"快递单号：{tracking}"
    await send_notification(NotificationMessage(
        user_id=user_id,
        title="中药配送已发货",
        body=body,
        channel="in_app",
        category="tcm",
        severity="info",
        link=f"/api/v1/tcm/orders/{order_id}",
    ))


async def notify_abnormal_detected(user_id: str, abnormal_count: int) -> None:
    """异常指标预警通知"""
    await send_notification(NotificationMessage(
        user_id=user_id,
        title=f"检测到{abnormal_count}项异常指标",
        body="请查看最新健康分析报告，建议及时就医复查。",
        channel="in_app",
        category="health_alert",
        severity="warning",
        link="/api/v1/dashboard/overview",
    ))


async def notify_medication_reminder(user_id: str, medication_name: str, scheduled_at: datetime) -> None:
    """用药提醒"""
    time_str = scheduled_at.strftime("%H:%M") if scheduled_at else ""
    await send_notification(NotificationMessage(
        user_id=user_id,
        title=f"用药提醒: {medication_name}",
        body=f"请在{time_str}服用{medication_name}。按时服药有助于治疗效果。",
        channel="in_app",
        category="medication",
        severity="info",
    ))


async def notify_risk_assessment_ready(user_id: str, risk_level: str) -> None:
    """风险评估完成通知"""
    severity = "warning" if risk_level in ("high", "very_high") else "info"
    await send_notification(NotificationMessage(
        user_id=user_id,
        title="慢病风险评估已完成",
        body=f"您的综合风险等级为: {risk_level}。请前往健康仪表盘查看详情。",
        channel="in_app",
        category="health_alert",
        severity=severity,
        link="/api/v1/dashboard/overview",
    ))

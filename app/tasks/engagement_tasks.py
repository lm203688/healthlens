"""用户激活 & 留存自动化任务
调度方式: celery -A app.worker.celery_app beat --loglevel=info
"""
from loguru import logger
from app.worker import celery_app
import asyncio


@celery_app.task(bind=True, max_retries=2, default_retry_delay=300)
def reactivate_silent_users(task_self, inactive_days: int = 3):
    """沉默用户自动唤醒

    查找 N 天未活跃的注册用户，发送个性化唤醒邮件。
    - 3天未活跃：轻度唤醒（健康数据提醒）
    - 7天未活跃：深度唤醒（新功能/积分奖励）
    - 14天未活跃：止损（最后机会 + 积分赠送）

    Args:
        inactive_days: 沉默天数阈值
    """
    async def _run():
        from app.database import SessionLocal
        from app.models.user import User
        from app.models.analytics import AnalyticsSession
        from sqlalchemy import select, func, and_, or_, desc
        from datetime import datetime, timedelta

        db = SessionLocal()
        try:
            # 查找沉默用户（有最近活动记录但超过 N 天未活跃）
            cutoff = datetime.utcnow() - timedelta(days=inactive_days)

            # 子查询：获取每个用户最后活跃时间
            last_activity = (
                select(
                    AnalyticsSession.user_id,
                    func.max(AnalyticsSession.created_at).label("last_active")
                )
                .where(AnalyticsSession.user_id.isnot(None))
                .group_by(AnalyticsSession.user_id)
                .subquery()
            )

            # 主查询：注册用户 + 最后活跃在 N 天前
            # 或逻辑：无活动记录(null) 或 最后活动早于截止时间
            result = await db.execute(
                select(User.id, User.email, User.nickname, last_activity.c.last_active)
                .join(last_activity, User.id == last_activity.c.user_id, isouter=True)
                .where(
                    and_(
                        User.is_active == True,
                        or_(
                            last_activity.c.last_active.is_(None),
                            last_activity.c.last_active < cutoff,
                        ),
                        # 排除今天刚注册的
                        User.created_at < datetime.utcnow() - timedelta(days=1),
                    )
                )
                .limit(50)  # 每次最多处理50人
            )

            silent_users = result.all()

            if not silent_users:
                logger.info(f"[Reactivation] No silent users for {inactive_days}d threshold")
                return {"success": True, "sent": 0, "threshold": inactive_days}

            sent = 0
            failed = 0
            for user_id, email, nickname, last_active in silent_users:
                if not email:
                    continue
                try:
                    from app.services.email_service import EmailService
                    mail = EmailService()

                    if inactive_days <= 3:
                        await mail.send_reactivation(email, nickname or "用户", 3)
                    elif inactive_days <= 7:
                        await mail.send_reactivation(email, nickname or "用户", 7)
                    else:
                        await mail.send_reactivation(email, nickname or "用户", 14)

                    sent += 1
                except Exception as e:
                    logger.warning(f"[Reactivation] Failed to send to {email}: {e}")
                    failed += 1

                # 避免短时间内大量发送
                await asyncio.sleep(0.5)

            logger.info(
                f"[Reactivation] threshold={inactive_days}d, "
                f"found={len(silent_users)}, sent={sent}, failed={failed}"
            )
            return {
                "success": True,
                "sent": sent,
                "failed": failed,
                "threshold": inactive_days,
            }
        except Exception as e:
            logger.error(f"[Reactivation] Failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"reactivate_silent_users failed: {exc}")
        raise task_self.retry(exc=exc)

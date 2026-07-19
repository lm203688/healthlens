"""异步健康分析和诊断任务"""
from loguru import logger
from app.worker import celery_app


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def analyze_health_async(self, user_id: str):
    """异步健康分析任务"""
    import asyncio
    from app.database import SessionLocal
    from app.services.analysis_service import analyze_user_observations

    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        try:
            analysis = loop.run_until_complete(analyze_user_observations(db, user_id))
        finally:
            loop.close()
        logger.info(f"Health analysis complete for user {user_id}")
        return analysis
    except Exception as exc:
        logger.error(f"Analysis task failed: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def diagnosis_async(self, user_id: str):
    """异步诊断任务"""
    import asyncio
    from app.database import SessionLocal
    from app.services.diagnosis_service import trigger_diagnosis

    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(trigger_diagnosis(db, user_id))
        finally:
            loop.close()

        # 通知用户
        try:
            from app.services.notification_service import notify_diagnosis_ready
            loop2 = asyncio.new_event_loop()
            try:
                loop2.run_until_complete(
                    notify_diagnosis_ready(user_id, result.get("total_findings", 0))
                )
            finally:
                loop2.close()
        except Exception:
            pass

        logger.info(f"Diagnosis complete for user {user_id}: {result.get('total_findings', 0)} findings")
        return result
    except Exception as exc:
        logger.error(f"Diagnosis task failed: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()

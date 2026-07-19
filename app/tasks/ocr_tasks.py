"""异步 OCR 任务"""
import uuid
import json
from datetime import datetime, timezone
from decimal import Decimal
from loguru import logger
from app.worker import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_report_async(self, record_id: str, user_id: str, file_path: str):
    """异步 OCR 解析任务

    1. 读取文件内容
    2. 调用 OCR 引擎解析
    3. 将结果写入数据库
    4. 更新 HealthRecord 状态
    """
    try:
        from app.database import SessionLocal
        from app.config import settings
        from app.core.ocr_engine import get_ocr_engine
        from app.models.observation import HealthObservation
        from app.models.record import HealthRecord

        # 读取文件
        with open(file_path, "rb") as f:
            content = f.read()

        # 获取 OCR 引擎
        engine = get_ocr_engine(settings.OCR_ENGINE)

        # 同步调用 OCR（Celery worker 是同步上下文）
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            ocr_result = loop.run_until_complete(engine.parse(content))
        finally:
            loop.close()

        # 提取指标
        observations_data = ocr_result.structured_data.get("observations", [])

        # 写入数据库
        db = SessionLocal()
        try:
            created_count = 0
            for obs_item in observations_data:
                try:
                    observation = HealthObservation(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        loinc_code=obs_item.get("loinc_code"),
                        loinc_name=obs_item.get("loinc_name"),
                        value_numeric=Decimal(str(obs_item["value_numeric"])) if obs_item.get("value_numeric") is not None else None,
                        value_string=obs_item.get("value_string"),
                        value_unit=obs_item.get("value_unit"),
                        reference_range_low=Decimal(str(obs_item["reference_range_low"])) if obs_item.get("reference_range_low") is not None else None,
                        reference_range_high=Decimal(str(obs_item["reference_range_high"])) if obs_item.get("reference_range_high") is not None else None,
                        source="ocr",
                        recorded_at=datetime.now(timezone.utc),
                    )
                    db.add(observation)
                    created_count += 1
                except Exception as e:
                    logger.error(f"Failed to create observation: {e}")
                    continue

            # 更新 HealthRecord 状态
            from sqlalchemy import select
            result = db.execute(
                select(HealthRecord).where(HealthRecord.id == record_id)
            )
            record = result.scalar_one_or_none()
            if record:
                record.status = "completed"
                record.observations_count = created_count
                record.parse_result = json.dumps({
                    "message": f"Parsed by OCR, extracted {created_count} observations",
                    "observations_preview": observations_data[:5],
                })

            db.commit()
            logger.info(f"Async OCR complete: record={record_id}, extracted={created_count}")

            # 发送通知
            try:
                from app.services.notification_service import notify_abnormal_detected
                # 检查是否有异常值
                abnormal_count = sum(
                    1 for o in observations_data
                    if o.get("value_numeric") and o.get("reference_range_high")
                    and o["value_numeric"] > o["reference_range_high"]
                )
                if abnormal_count > 0:
                    import asyncio as _loop
                    _loop.new_event_loop().run_until_complete(
                        notify_abnormal_detected(user_id, abnormal_count)
                    )
            except Exception:
                pass

            return {
                "status": "completed",
                "record_id": record_id,
                "extracted_items": created_count,
            }
        finally:
            db.close()

    except Exception as exc:
        logger.error(f"OCR task failed: {exc}")
        # 更新 record 状态为 failed
        try:
            from app.database import SessionLocal
            from app.models.record import HealthRecord
            from sqlalchemy import select
            db = SessionLocal()
            try:
                result = db.execute(select(HealthRecord).where(HealthRecord.id == record_id))
                record = result.scalar_one_or_none()
                if record:
                    record.status = "failed"
                    record.error_message = str(exc)[:500]
                db.commit()
            finally:
                db.close()
        except Exception:
            pass

        raise self.retry(exc=exc)

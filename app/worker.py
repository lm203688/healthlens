"""Celery 异步任务 worker
启动方式: celery -A app.worker.celery_app worker --loglevel=info
"""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "healthlens",
    broker=settings.CELERY_BROKER_URL or "redis://localhost:6379/0",
    backend=settings.CELERY_RESULT_BACKEND or "redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,  # 结果保留1小时
)

# 自动发现任务模块
celery_app.autodiscover_tasks(["app.tasks"])

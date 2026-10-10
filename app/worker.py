"""Celery 异步任务 worker

启动方式:
    worker: celery -A app.worker.celery_app worker --loglevel=info --concurrency=2
    beat:   celery -A app.worker.celery_app beat  --loglevel=info

修订记录 (2026-08-04)
---------------------
1. day_of_week 全部改为字符串缩写。原代码用整数且按「0=周一」理解，
   而 Celery crontab 的约定是 0=周日，导致 9 个任务里 6 个整体偏移一天。
   用 "mon"/"wed" 这类字面量后不再存在解释歧义。
2. 删除 `beat_schedule_timezone` —— 这不是 Celery 的合法配置项，赋值不报错
   但完全不生效，是误导性死配置。真正生效的是 conf.timezone（已正确设置为
   Asia/Shanghai，因此历史上并不存在 8 小时偏移，只有星期偏移）。
3. 每个定时任务补 expires，防止 beat 停机重启后补投一堆陈旧任务造成雪崩。
4. 新增 broker 断线重连、任务超时护栏、worker 丢失重入队。
5. 新增 pipeline-heartbeat 心跳任务，供外部看门狗判定 beat 是否存活。
"""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# 任务模块必须显式 include。
# 原代码只有 autodiscover_tasks(["app.tasks"])，而 autodiscover 默认查找的是
# `app.tasks.tasks` 这个子模块——它并不存在，且 app/tasks/__init__.py 是空文件，
# 因此所有任务实际从未注册到 worker。即使 beat 跑起来，也只会报
# "Received unregistered task"。include 在 finalize 阶段导入，不会循环引用。
TASK_MODULES = [
    "app.tasks.acquisition_tasks",
    "app.tasks.analysis_tasks",
    "app.tasks.engagement_tasks",
    "app.tasks.ocr_tasks",
    "app.tasks.ops_tasks",
]

celery_app = Celery(
    "healthlens",
    broker=settings.CELERY_BROKER_URL or "redis://localhost:6379/0",
    backend=settings.CELERY_RESULT_BACKEND or "redis://localhost:6379/1",
    include=TASK_MODULES,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # crontab 按此时区解释。Celery 唯一合法的时区配置项就是 timezone。
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,  # 结果保留1小时
    # ---- 可靠性配置 ----
    # redis 抖动时持续重连，避免 worker/beat 直接退出
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    # worker 被强杀时任务重新入队（配合 task_acks_late 防丢任务）
    task_reject_on_worker_lost=True,
    # 超时护栏：软超时先抛异常让任务自己收尾，硬超时兜底
    task_soft_time_limit=1800,   # 30 分钟
    task_time_limit=2100,        # 35 分钟
    # beat 调度状态落盘到挂载卷，容器重建后不重复补投
    beat_schedule_filename="/app/data/celerybeat-schedule",
)

# 保留 autodiscover 作为补充（未来新增 app/tasks/tasks.py 时自动生效），
# 真正保证注册的是上面的 include=TASK_MODULES。
celery_app.autodiscover_tasks(["app.tasks"])

# 任务过期时间（秒）。beat 若停机超过该时长，重启后不再补投这些任务。
_EXPIRES_DAILY = 6 * 3600      # 日任务：6 小时内没被消费就作废
_EXPIRES_WEEKLY = 24 * 3600    # 周任务：24 小时内没被消费就作废

# Celery Beat 定时调度配置
# 注意：day_of_week 使用字符串缩写，Celery 内部 0=Sunday，用缩写规避歧义。
celery_app.conf.beat_schedule = {
    # ========== SEO 内容工厂（后半夜运行） ==========
    # SEO 知识页面批量生成 - conditions 类型（周三 03:00）
    "seo-generate-conditions": {
        "task": "app.tasks.acquisition_tasks.seo_batch_generate",
        "schedule": crontab(hour=3, minute=0, day_of_week="wed"),
        "args": [10, "conditions"],
        "options": {"expires": _EXPIRES_WEEKLY},
    },
    # SEO 知识页面批量生成 - herbs 类型（周六 03:00）
    "seo-generate-herbs": {
        "task": "app.tasks.acquisition_tasks.seo_batch_generate",
        "schedule": crontab(hour=3, minute=0, day_of_week="sat"),
        "args": [10, "herbs"],
        "options": {"expires": _EXPIRES_WEEKLY},
    },
    # SEO 自动审核发布 - 每日 04:00
    "seo-auto-publish": {
        "task": "app.tasks.acquisition_tasks.seo_auto_publish",
        "schedule": crontab(hour=4, minute=0),
        "args": [10],
        "options": {"expires": _EXPIRES_DAILY},
    },
    # 用户教育内容生成 - 每周五 03:00
    "user-education-push": {
        "task": "app.tasks.acquisition_tasks.user_education_push",
        "schedule": crontab(hour=3, minute=0, day_of_week="fri"),
        "args": [],
        "options": {"expires": _EXPIRES_WEEKLY},
    },
    # ========== 数据清理 ==========
    # 过期邀请码清理 - 每日 05:00
    "cleanup-expired-invites": {
        "task": "app.tasks.acquisition_tasks.cleanup_expired_invites",
        "schedule": crontab(hour=5, minute=0),
        "args": [],
        "options": {"expires": _EXPIRES_DAILY},
    },
    # 过期分析数据清理 - 每周日 05:00
    "cleanup-old-analytics": {
        "task": "app.tasks.acquisition_tasks.cleanup_old_analytics",
        "schedule": crontab(hour=5, minute=0, day_of_week="sun"),
        "args": [90],
        "options": {"expires": _EXPIRES_WEEKLY},
    },
    # ========== 用户激活 & 唤醒 ==========
    # 沉默用户唤醒（3天未活跃）- 每日 06:00
    "reactivate-silent-users": {
        "task": "app.tasks.engagement_tasks.reactivate_silent_users",
        "schedule": crontab(hour=6, minute=0),
        "args": [3],
        "options": {"expires": _EXPIRES_DAILY},
    },
    # 沉默用户深度唤醒（7天未活跃）- 每周二 06:00
    "reactivate-deep-silent": {
        "task": "app.tasks.engagement_tasks.reactivate_silent_users",
        "schedule": crontab(hour=6, minute=0, day_of_week="tue"),
        "args": [7],
        "options": {"expires": _EXPIRES_WEEKLY},
    },
    # ========== 监控 & 报告 ==========
    # 获客数据周报 - 每周一 04:00
    "acquisition-weekly-report": {
        "task": "app.tasks.acquisition_tasks.acquisition_weekly_report",
        "schedule": crontab(hour=4, minute=0, day_of_week="mon"),
        "args": [],
        "options": {"expires": _EXPIRES_WEEKLY},
    },
    # ========== 心跳 & 自检（供看门狗判活） ==========
    # 每 10 分钟写一次心跳。心跳断了 = beat 死了，看门狗据此告警。
    "pipeline-heartbeat": {
        "task": "app.tasks.ops_tasks.write_heartbeat",
        "schedule": crontab(minute="*/10"),
        "args": [],
        "options": {"expires": 540},  # 9 分钟，绝不补投
    },
    # 每小时自检数据库/Redis/worker 连通性
    "ops-selfcheck": {
        "task": "app.tasks.ops_tasks.run_selfcheck",
        "schedule": crontab(minute=5),
        "args": [],
        "options": {"expires": 3000},
    },
    # ========== 数据备份（T3） ==========
    # 每日 02:00 逻辑备份数据库（pg_dump -> gzip），保留最近 7 份
    "ops-db-backup": {
        "task": "app.tasks.ops_tasks.backup_database",
        "schedule": crontab(hour=2, minute=0),
        "args": [],
        "options": {"expires": _EXPIRES_DAILY},
    },
}

"""Celery 任务包。

此前本文件为空，且 worker 只调用 autodiscover_tasks(["app.tasks"])
（它查找的是不存在的 app.tasks.tasks），导致任务全部未注册。
现在注册以 app/worker.py 的 include=TASK_MODULES 为准，
这里的显式导入作为第二重保险，便于 `python -c "import app.tasks"` 快速验证。
"""

__all__ = [
    "acquisition_tasks",
    "analysis_tasks",
    "engagement_tasks",
    "ocr_tasks",
    "ops_tasks",
]

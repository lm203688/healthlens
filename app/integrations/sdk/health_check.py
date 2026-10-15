"""合作方健康检查 —— S3-2 Powered-by SDK。

对外端点返回：
    {
      "status": "ok" | "degraded",
      "version": "0.26.2",
      "engines": {"fusion": bool, "tcm": bool, "pulse": bool},
      "database": bool,
      "timestamp": "ISO-8601 UTC"
    }

fail-loud 原则
--------------
- DB 连接失败 → database=False，整体 status=degraded
- 引擎导入失败 → 对应引擎=False，整体 status=degraded
- 任何异常不静默降级为 True；宁可报告 degraded 也不谎报 ok
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text


async def check_health(db_session=None) -> dict[str, Any]:
    """检查 DB 连接与引擎可用性。

    Args:
        db_session: 可选的 AsyncSession（由 FastAPI 依赖注入时传入）；
                    为 None 时自建会话。

    Returns:
        dict 见模块 docstring。
    """
    from app.config import settings

    result: dict[str, Any] = {
        "status": "ok",
        "version": settings.APP_VERSION,
        "engines": {"fusion": False, "tcm": False, "pulse": False},
        "database": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 1. DB 检查
    try:
        if db_session is not None:
            await db_session.execute(text("SELECT 1"))
        else:
            from app.database import async_session_factory
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        result["database"] = True
    except Exception:  # noqa: BLE001 - 引擎探测必须 fail-loud
        result["database"] = False

    # 2. 引擎可用性检查（import 失败即视为不可用）
    try:
        from app.lib import fusion_engine  # noqa: F401
        result["engines"]["fusion"] = True
    except Exception:  # noqa: BLE001
        result["engines"]["fusion"] = False

    try:
        from app.lib import wellness_simulator  # noqa: F401 - TCM 侧 wellness 引擎
        result["engines"]["tcm"] = True
    except Exception:  # noqa: BLE001
        result["engines"]["tcm"] = False

    try:
        from app.lib import pulse_engine  # noqa: F401
        result["engines"]["pulse"] = True
    except Exception:  # noqa: BLE001
        result["engines"]["pulse"] = False

    # 汇总
    if not result["database"] or not all(result["engines"].values()):
        result["status"] = "degraded"

    result["disclaimer"] = (
        "HealthLens 是 wellness（健康管理）平台，非医疗诊断或治疗工具。"
        "身体不适请咨询执业医生。"
    )
    return result

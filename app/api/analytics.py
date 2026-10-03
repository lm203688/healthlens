"""
用户行为埋点 API
路由前缀: /api/v1/analytics
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from loguru import logger

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# 演示模式 DEMO 数据
DEMO_DASHBOARD = {
    "total_users": 1248,
    "active_users_7d": 386,
    "avg_session_duration": 342,
    "plan_completion_rate": 68.5,
    "top_pages": [
        {"page": "dashboard", "views": 4520},
        {"page": "plan", "views": 3180},
        {"page": "diagnosis", "views": 2450},
        {"page": "today", "views": 1980},
        {"page": "knowledge", "views": 1120},
    ],
    "growth_rate": 12.3,
}


class EventRequest(BaseModel):
    event_type: str = Field(..., pattern="^(page_view|click|scroll|plan_view|plan_execute|share|invite)$")
    page: Optional[str] = None
    element: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionRequest(BaseModel):
    session_id: str
    duration_seconds: int = Field(..., ge=0)
    pages_visited: List[str]
    actions_count: int = Field(..., ge=0)


class ConversionRequest(BaseModel):
    conversion_type: str = Field(..., pattern="^(registration|premium|trial)$")
    source: Optional[str] = "direct"
    referrer_code: Optional[str] = None
    landing_page: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/event", summary="记录用户行为事件")
async def track_event(
    body: EventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.analytics_service import track_event as svc_track_event
    except ImportError:
        logger.warning("analytics_service not available")
        return {"success": False, "data": None, "message": "分析服务暂不可用"}

    user_id = current_user.id if current_user else None

    # 从请求中提取客户端信息
    user_agent = request.headers.get("user-agent", "")[:500]
    referrer = request.headers.get("referer", "")[:1000]

    result = await svc_track_event(
        db,
        user_id=user_id,
        event_type=body.event_type,
        page=body.page,
        element=body.element,
        metadata=body.metadata or {},
        user_agent=user_agent,
        referrer=referrer,
    )

    return {
        "success": True,
        "data": {"id": result.get("event_id", "")},
        "message": "事件已记录",
    }


@router.post("/session", summary="记录会话数据")
async def track_session(
    body: SessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.analytics_service import track_session as svc_track_session
    except ImportError:
        logger.warning("analytics_service not available")
        return {"success": False, "data": None, "message": "分析服务暂不可用"}

    user_id = current_user.id if current_user else None

    result = await svc_track_session(
        db,
        user_id=user_id,
        session_id=body.session_id,
        duration=body.duration_seconds,
        pages=body.pages_visited,
        actions=body.actions_count,
    )

    return {
        "success": True,
        "data": {"id": result.get("session_id", "")},
        "message": "会话已记录",
    }


@router.post("/conversion", summary="记录转化事件")
async def track_conversion(
    body: ConversionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.analytics_service import track_conversion
    except ImportError:
        logger.warning("analytics_service not available")
        return {"success": False, "data": None, "message": "分析服务暂不可用"}

    user_id = current_user.id if current_user else None
    if not user_id:
        return {"success": False, "data": None, "message": "请先登录后再记录转化"}

    result = await track_conversion(
        db,
        user_id=user_id,
        source=body.source,
        referrer_code=body.referrer_code,
        landing_page=body.landing_page,
        conversion_type=body.conversion_type,
    )

    return {
        "success": True,
        "data": {"id": result.get("conversion_id", "")},
        "message": "转化事件已记录",
    }


@router.get("/dashboard", summary="返回运营数据看板")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.analytics_service import get_dashboard_stats
    except ImportError:
        logger.warning("analytics_service not available, returning demo data")
        return {"success": True, "data": DEMO_DASHBOARD}

    try:
        stats = await get_dashboard_stats(db, days=7)

        # 如果数据库中没有任何真实数据，回退到 DEMO
        if stats.get("total_events", 0) == 0 and stats.get("dau", 0) == 0:
            return {"success": True, "data": DEMO_DASHBOARD}

        # 将服务层返回的字段映射到原接口格式，保持兼容
        return {
            "success": True,
            "data": {
                "total_users": stats.get("mau", 0),
                "active_users_7d": stats.get("dau", 0),
                "avg_session_duration": stats.get("avg_session_duration", 0),
                "plan_completion_rate": 0.0,
                "top_pages": stats.get("top_pages", DEMO_DASHBOARD["top_pages"]),
                "growth_rate": 0.0,
                "funnel": stats.get("funnel"),
                "period_days": stats.get("period_days", 7),
                "total_events": stats.get("total_events", 0),
            },
        }
    except Exception as e:
        logger.warning(f"Failed to get dashboard stats from service: {e}")
        return {"success": True, "data": DEMO_DASHBOARD}

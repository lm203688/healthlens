"""行为分析服务 - 持久化存储"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, distinct, desc
from loguru import logger

from app.models.analytics import AnalyticsEvent, AnalyticsSession, ConversionRecord


async def track_event(
    db: AsyncSession,
    user_id: Optional[str] = None,
    event_type: str = "page_view",
    page: Optional[str] = None,
    element: Optional[str] = None,
    session_id: Optional[str] = None,
    ip_hash: Optional[str] = None,
    user_agent: Optional[str] = None,
    referrer: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    """记录用户行为事件"""
    event = AnalyticsEvent(
        user_id=user_id,
        event_type=event_type,
        page=page,
        element=element,
        session_id=session_id,
        ip_hash=ip_hash,
        user_agent=user_agent,
        referrer=referrer,
        metadata_=metadata or {},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {"success": True, "event_id": str(event.id)}


async def track_session(
    db: AsyncSession,
    user_id: Optional[str] = None,
    session_id: str = "",
    duration_seconds: int = 0,
    pages_visited: Optional[List[str]] = None,
    actions_count: int = 0,
    device_type: Optional[str] = None,
) -> dict:
    """记录会话数据"""
    session = AnalyticsSession(
        user_id=user_id,
        session_id=session_id,
        duration_seconds=duration_seconds,
        pages_visited=pages_visited or [],
        actions_count=actions_count,
        device_type=device_type or "unknown",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"success": True, "session_id": str(session.id)}


async def track_conversion(
    db: AsyncSession,
    user_id: str,
    source: Optional[str] = None,
    referrer_code: Optional[str] = None,
    landing_page: Optional[str] = None,
    conversion_type: str = "registration",
) -> dict:
    """记录转化事件"""
    record = ConversionRecord(
        user_id=user_id,
        source=source or "direct",
        referrer_code=referrer_code,
        landing_page=landing_page,
        conversion_type=conversion_type,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(f"Conversion: user={user_id}, type={conversion_type}, source={source}")
    return {"success": True, "conversion_id": str(record.id)}


async def get_dashboard_stats(db: AsyncSession, days: int = 7) -> dict:
    """获取仪表盘统计数据"""
    since = datetime.utcnow() - timedelta(days=days)

    # DAU
    dau_q = await db.execute(
        select(func.count(distinct(AnalyticsEvent.user_id))).where(
            and_(
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.user_id.isnot(None),
            )
        )
    )
    dau = dau_q.scalar() or 0

    # MAU
    mau_since = datetime.utcnow() - timedelta(days=30)
    mau_q = await db.execute(
        select(func.count(distinct(AnalyticsEvent.user_id))).where(
            and_(
                AnalyticsEvent.created_at >= mau_since,
                AnalyticsEvent.user_id.isnot(None),
            )
        )
    )
    mau = mau_q.scalar() or 0

    # Top pages
    pages_q = await db.execute(
        select(AnalyticsEvent.page, func.count().label("views"))
        .where(and_(AnalyticsEvent.created_at >= since, AnalyticsEvent.page.isnot(None)))
        .group_by(AnalyticsEvent.page)
        .order_by(desc("views"))
        .limit(10)
    )
    top_pages = [{"page": r.page, "views": r.views} for r in pages_q]

    # Avg session duration
    dur_q = await db.execute(
        select(func.avg(AnalyticsSession.duration_seconds)).where(AnalyticsSession.created_at >= since)
    )
    avg_session = round(dur_q.scalar() or 0)

    # Total events
    evt_q = await db.execute(
        select(func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.created_at >= since)
    )
    total_events = evt_q.scalar() or 0

    funnel = await get_funnel_stats(db)

    return {
        "dau": dau,
        "mau": mau,
        "top_pages": top_pages,
        "avg_session_duration": avg_session,
        "total_events": total_events,
        "period_days": days,
        "funnel": funnel,
    }


async def get_funnel_stats(db: AsyncSession) -> dict:
    """获取转化漏斗数据"""
    reg_q = await db.execute(
        select(func.count()).select_from(ConversionRecord)
        .where(ConversionRecord.conversion_type == "registration")
    )
    registrations = reg_q.scalar() or 0

    action_q = await db.execute(
        select(func.count(distinct(AnalyticsSession.user_id))).where(
            and_(
                AnalyticsSession.user_id.isnot(None),
                AnalyticsSession.actions_count > 0,
            )
        )
    )
    first_actions = action_q.scalar() or 0

    prem_q = await db.execute(
        select(func.count()).select_from(ConversionRecord)
        .where(ConversionRecord.conversion_type == "premium")
    )
    premium_users = prem_q.scalar() or 0

    def _rate(num, denom):
        return round(num / denom * 100, 2) if denom else 0.0

    return {
        "registrations": registrations,
        "first_actions": first_actions,
        "premium_users": premium_users,
        "registration_to_action_rate": _rate(first_actions, registrations),
        "action_to_premium_rate": _rate(premium_users, first_actions),
        "overall_conversion_rate": _rate(premium_users, registrations),
    }


async def get_channel_stats(db: AsyncSession) -> dict:
    """获取流量来源分布"""
    seo_q = await db.execute(
        select(func.count()).select_from(AnalyticsEvent).where(
            and_(
                AnalyticsEvent.referrer.isnot(None),
                or_(
                    AnalyticsEvent.referrer.ilike("%google%"),
                    AnalyticsEvent.referrer.ilike("%bing%"),
                    AnalyticsEvent.referrer.ilike("%baidu%"),
                    AnalyticsEvent.referrer.ilike("%sogou%"),
                    AnalyticsEvent.referrer.ilike("%healthlens.cc/knowledge%"),
                    AnalyticsEvent.referrer.ilike("%healthlens.cc/health%"),
                ),
            )
        )
    )
    seo_count = seo_q.scalar() or 0

    ref_q = await db.execute(
        select(func.count()).select_from(AnalyticsEvent)
        .where(AnalyticsEvent.referrer.ilike("%ref=%"))
    )
    referral_count = ref_q.scalar() or 0

    social_q = await db.execute(
        select(func.count()).select_from(AnalyticsEvent).where(
            and_(
                AnalyticsEvent.referrer.isnot(None),
                or_(
                    AnalyticsEvent.referrer.ilike("%weibo%"),
                    AnalyticsEvent.referrer.ilike("%wechat%"),
                    AnalyticsEvent.referrer.ilike("%douyin%"),
                    AnalyticsEvent.referrer.ilike("%xiaohongshu%"),
                    AnalyticsEvent.referrer.ilike("%t.co%"),
                    AnalyticsEvent.referrer.ilike("%facebook%"),
                ),
            )
        )
    )
    social_count = social_q.scalar() or 0

    wake_q = await db.execute(
        select(func.count()).select_from(AnalyticsEvent)
        .where(AnalyticsEvent.referrer == "wake_up")
    )
    wake_up_count = wake_q.scalar() or 0

    total_q = await db.execute(select(func.count()).select_from(AnalyticsEvent))
    total_count = total_q.scalar() or 0

    direct_count = max(0, total_count - seo_count - referral_count - social_count - wake_up_count)

    return {
        "seo": seo_count,
        "referral": referral_count,
        "direct": direct_count,
        "social": social_count,
        "wake_up": wake_up_count,
        "total": total_count,
    }


async def cleanup_old_events(db: AsyncSession, days: int = 90) -> dict:
    """清理过期事件记录"""
    cutoff = datetime.utcnow() - timedelta(days=days)

    evts = (await db.execute(select(AnalyticsEvent).where(AnalyticsEvent.created_at < cutoff))).scalars().all()
    sessions = (await db.execute(select(AnalyticsSession).where(AnalyticsSession.created_at < cutoff))).scalars().all()

    for e in evts:
        await db.delete(e)
    for s in sessions:
        await db.delete(s)

    await db.commit()
    logger.info(f"Cleaned up {len(evts)} events and {len(sessions)} sessions older than {days} days")

    return {
        "success": True,
        "events_deleted": len(evts),
        "sessions_deleted": len(sessions),
        "cutoff_date": cutoff.isoformat(),
    }

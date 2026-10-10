"""持久化分析模型 - 事件、会话、转化记录"""
from sqlalchemy import String, ForeignKey, DateTime, JSON, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin


class AnalyticsEvent(UUIDPrimaryKeyMixin, Base):
    """用户行为事件"""
    __tablename__ = "analytics_events"

    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    page: Mapped[str] = mapped_column(String(500))
    element: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict | None] = mapped_column(JSON)
    session_id: Mapped[str | None] = mapped_column(String(100), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    referrer: Mapped[str | None] = mapped_column(String(1000))
    created_at = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("ix_analytics_events_event_type_created", "event_type", "created_at"),
        Index("ix_analytics_events_session_created", "session_id", "created_at"),
    )


class AnalyticsSession(UUIDPrimaryKeyMixin, Base):
    """用户会话"""
    __tablename__ = "analytics_sessions"

    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    duration: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_visited: Mapped[list | None] = mapped_column(JSON)
    actions_count: Mapped[int] = mapped_column(Integer, default=0)
    device_type: Mapped[str | None] = mapped_column(String(50))
    created_at = mapped_column(DateTime, index=True)


class ConversionRecord(UUIDPrimaryKeyMixin, Base):
    """转化记录"""
    __tablename__ = "conversion_records"

    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # register / seo / referral / direct / social / wake_up
    referrer_code: Mapped[str | None] = mapped_column(String(255))
    landing_page: Mapped[str | None] = mapped_column(String(500))
    conversion_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # signup / first_action / premium
    metadata_: Mapped[dict | None] = mapped_column(JSON)
    created_at = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("ix_conversion_records_source_type", "source", "conversion_type"),
    )

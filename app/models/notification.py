"""通知模型 - 站内通知中心"""
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """站内通知"""
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(50))  # health_alert / medication / appointment / system / tcm
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info / warning / critical
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string (原 metadata, 避开 SQLAlchemy 保留字)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

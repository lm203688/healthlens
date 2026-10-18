"""GDPR 用户同意记录 — 持久化到数据库，替代内存 dict"""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class GDPRConsent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "gdpr_consents"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_at: Mapped[str | None] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(10), default="2.0", nullable=False)
    purposes: Mapped[str | None] = mapped_column(Text)  # JSON array as text
    note: Mapped[str | None] = mapped_column(Text)

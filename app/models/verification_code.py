"""短信验证码模型 —— 用于存储手机验证码（登录/注册场景）"""
from datetime import datetime, timedelta

from sqlalchemy import String, Boolean, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class VerificationCode(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "verification_codes"
    __table_args__ = (
        Index("ix_verification_codes_phone_purpose", "phone", "purpose"),
    )

    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), default="login", nullable=False)  # login / register
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

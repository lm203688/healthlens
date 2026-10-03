"""邀请/分享增长模型 - 邀请码、分享记录"""
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class InviteCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """邀请码"""
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    inviter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    claimant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )  # active / claimed / expired
    is_claimed: Mapped[bool] = mapped_column(default=False, server_default="0")
    reward_points: Mapped[int] = mapped_column(Integer, default=200)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class ShareRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """分享记录"""
    __tablename__ = "share_records"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(36))
    share_url: Mapped[str | None] = mapped_column(String(1000))
    platform: Mapped[str] = mapped_column(
        String(20)
    )  # web / wechat / xiaohongshu / other
    click_count: Mapped[int] = mapped_column(Integer, default=0)

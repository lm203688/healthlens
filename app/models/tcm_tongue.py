from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class TongueImage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tongue_images"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    tongue_color: Mapped[str | None] = mapped_column(String(50))
    tongue_shape: Mapped[str | None] = mapped_column(String(50))
    coating_color: Mapped[str | None] = mapped_column(String(50))
    coating_quality: Mapped[str | None] = mapped_column(String(50))
    sublingual_vein: Mapped[str | None] = mapped_column(String(50))
    ai_analysis: Mapped[dict | None] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class TcmProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tcm_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True
    )
    constitution_type: Mapped[str | None] = mapped_column(String(20))
    constitution_score: Mapped[dict | None] = mapped_column(JSON)
    questionnaire_data: Mapped[dict | None] = mapped_column(JSON)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime)
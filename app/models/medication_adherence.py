"""用药依从性模型"""
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class MedicationAdherence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用药记录 - 追踪用户是否按时服药"""
    __tablename__ = "medication_adherence"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    medication_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("medication_recommendations.id"), nullable=True)
    medication_name: Mapped[str] = mapped_column(String(200))
    prescribed_dose: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)  # 计划服药时间
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 实际服药时间
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / taken / missed / skipped
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否延误

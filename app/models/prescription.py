"""处方模型 - 记录医生开具的处方"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Prescription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prescriptions"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    diagnosis_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("diagnosis_results.id"), nullable=True)
    prescription_no: Mapped[str | None] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")  # draft/active/discontinued
    medications: Mapped[dict | None] = mapped_column(JSON)  # 处方药物列表
    notes: Mapped[str | None] = mapped_column(Text)
    prescribed_at: Mapped[datetime | None] = mapped_column(DateTime)
    prescribed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
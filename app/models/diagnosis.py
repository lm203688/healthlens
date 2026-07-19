from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class DiagnosisResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnosis_results"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    diagnosis_text: Mapped[str | None] = mapped_column(Text)
    icd_code: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    severity: Mapped[str | None] = mapped_column(String(50))
    is_ai_generated: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
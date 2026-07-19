from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class TcmSyndromeDiagnosis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tcm_syndrome_diagnoses"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    syndrome_code: Mapped[str | None] = mapped_column(String(50))  # TCD code
    syndrome_name: Mapped[str | None] = mapped_column(String(100))
    principle: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    evidence: Mapped[dict | None] = mapped_column(JSON)
    is_ai_generated: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    diagnosis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("diagnosis_results.id"), nullable=True
    )
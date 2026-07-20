from sqlalchemy import String, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class MedicationRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "medication_recommendations"

    diagnosis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("diagnosis_results.id"), index=True
    )
    drug_name: Mapped[str] = mapped_column(String(255), nullable=False)
    drug_code: Mapped[str | None] = mapped_column(String(50))  # ATC code
    dosage: Mapped[str | None] = mapped_column(String(100))
    dosage_unit: Mapped[str | None] = mapped_column(String(50))
    frequency: Mapped[str | None] = mapped_column(String(100))
    route: Mapped[str | None] = mapped_column(String(50))
    pgx_evidence: Mapped[bool | None] = mapped_column(Boolean)
from datetime import date
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class HealthProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "health_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True
    )
    fhir_patient_id: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[str | None] = mapped_column(String(10))
    birth_date: Mapped[date | None] = mapped_column(Date)
    blood_type: Mapped[str | None] = mapped_column(String(10))
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
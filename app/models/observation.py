from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class HealthObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "health_observations"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    loinc_code: Mapped[str | None] = mapped_column(String(50))
    loinc_name: Mapped[str | None] = mapped_column(String(500))
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(15, 5))
    value_string: Mapped[str | None] = mapped_column(Text)
    value_unit: Mapped[str | None] = mapped_column(String(50))
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(15, 5))
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(15, 5))
    source: Mapped[str | None] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # TimescaleDB hypertable 将在迁移中创建
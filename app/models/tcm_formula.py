from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class TcmFormulaRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tcm_formula_recommendations"

    syndrome_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tcm_syndrome_diagnoses.id")
    )
    formula_name: Mapped[str | None] = mapped_column(String(100))
    formula_source: Mapped[str | None] = mapped_column(String(200))
    original_composition: Mapped[dict | None] = mapped_column(JSON)
    modified_composition: Mapped[dict | None] = mapped_column(JSON)
    additions: Mapped[dict | None] = mapped_column(JSON)
    subtractions: Mapped[dict | None] = mapped_column(JSON)
    dosage_instructions: Mapped[str | None] = mapped_column(Text)
    formula_analysis: Mapped[dict | None] = mapped_column(JSON)


class TcmFormulaLibrary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tcm_formula_library"

    formula_name: Mapped[str] = mapped_column(String(100), nullable=False)
    formula_name_en: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    composition: Mapped[dict | None] = mapped_column(JSON)
    dosage: Mapped[str | None] = mapped_column(Text)
    indications: Mapped[str | None] = mapped_column(Text)
    syndrome_code: Mapped[str | None] = mapped_column(String(50))
    modifications: Mapped[dict | None] = mapped_column(JSON)
    contraindications: Mapped[str | None] = mapped_column(Text)
    modern_evidence: Mapped[dict | None] = mapped_column(JSON)


class TcmHerb(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tcm_herbs"

    herb_name: Mapped[str] = mapped_column(String(100), nullable=False)
    herb_name_en: Mapped[str | None] = mapped_column(String(200))
    pinyin: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    property: Mapped[str | None] = mapped_column(String(50))
    flavor: Mapped[str | None] = mapped_column(String(100))
    meridian: Mapped[str | None] = mapped_column(String(200))
    efficacy: Mapped[str | None] = mapped_column(Text)
    usage_dosage: Mapped[str | None] = mapped_column(Text)
    contraindications: Mapped[str | None] = mapped_column(Text)
    chemical_components: Mapped[dict | None] = mapped_column(JSON)
    cyp450_metabolism: Mapped[dict | None] = mapped_column(JSON)


class TcmDeliveryOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tcm_delivery_orders"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    formula_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tcm_formula_recommendations.id"), nullable=True
    )
    pharmacy_name: Mapped[str | None] = mapped_column(String(200))
    order_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    total_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    doctor_signature: Mapped[str | None] = mapped_column(String(100))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
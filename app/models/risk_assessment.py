"""风险评估记录模型"""
from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class RiskAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """风险评估记录"""
    __tablename__ = "risk_assessments"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    risk_type: Mapped[str] = mapped_column(String(50))  # ascvd / diabetes / metabolic_syndrome
    risk_level: Mapped[str] = mapped_column(String(20))  # low / moderate / high / very_high
    risk_score: Mapped[float] = mapped_column(Numeric(10, 2))
    risk_probability: Mapped[float] = mapped_column(Numeric(5, 2))
    risk_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    references: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    input_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 输入快照
    assessed_at: Mapped[datetime] = mapped_column(DateTime)

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class PharmacogenomicProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pharmacogenomic_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    gene_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    phenotype: Mapped[str | None] = mapped_column(String(100))
    variant_rsid: Mapped[str | None] = mapped_column(String(50))
    genotype: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(100))
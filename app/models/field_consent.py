"""字段级×法域级同意模型 — M13 差异化能力

当前 GDPRConsent 只记录「用户是否同意」，无法回答：
- 用户是否同意分享「心率」字段用于「分析」目的？
- 用户是否同意在 EU 法域处理「基因组」数据？

本模型记录 (user, field, jurisdiction, purpose) 四维同意，
支持 GDPR Article 7「具体、知情、明确」同意要求，
以及各国数据保护法的字段级同意需求。

设计要点：
- 字段路径用点分路径（如 heart_rate、genome.CYP2C19）
- 法域与 ClaimsEngine 共享 SUPPORTED_JURISDICTIONS
- 每个同意记录有独立的 accepted_at 和 version（同意版本管理）
- 全局撤回（GDPRConsent.accepted=false）自动覆盖所有字段级同意
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class FieldConsent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """字段级×法域级同意记录"""
    __tablename__ = "field_consents"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # 字段路径：点分路径（如 "heart_rate"、"genome.CYP2C19"、"sleep.duration"）
    field_path: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # 法域：cn/us/uk/au/eu
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, default="cn", index=True)
    # 同意目的：analysis/training/share/export/none
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, default="analysis", index=True)
    # 是否同意
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 同意时间
    accepted_at: Mapped[str | None] = mapped_column(String(50))
    # 同意版本（与全局 GDPRConsent 版本独立管理）
    version: Mapped[str] = mapped_column(String(10), default="2.0", nullable=False)
    # 备注
    note: Mapped[str | None] = mapped_column(Text)

    # 复合唯一索引：同一用户同一字段同一法域同一目的只有一条记录
    __table_args__ = (
        Index(
            "uq_field_consent_unique",
            "user_id", "field_path", "jurisdiction", "purpose",
            unique=True,
        ),
        Index("ix_field_consent_user_jurisdiction", "user_id", "jurisdiction"),
    )

"""合作方（Partner）与 API Key 模型 — S3-2 Powered-by SDK

wellness 平台向外部合作方（可穿戴设备厂、企业健康 App、健康保险等）
开放 Powered-by 接入。所有对外 API 走 API Key 认证（非 JWT），Key 只
存 SHA256 摘要——明文仅生成时返回一次，落库后不可反推。

字段边界
--------
- Partner.status: pending（新创建） / active（激活可调用） / inactive（停用）
- PartnerApiKey.status: active / revoked（吊销后不可再认证）
- PartnerApiKey.expires_at 为空表示长期有效；非空且过期后认证失败
- last_used_at 用于风控观察（Key 长期未使用或异常频次可人工吊销）
"""
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Partner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """合作方主表。"""

    __tablename__ = "partners"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
    )  # pending / active / inactive
    # 描述性元数据，纯文本，不做结构化承诺
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 该合作方专属的外部回调/展示名（如嵌入品牌时的 logo 名），非必填
    brand_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 允许调用的端点白名单，逗号分隔；空字符串或 None 表示启用默认全集
    allowed_endpoints: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 每分钟请求上限（简单限速，配合 slowapi 或直接内存令牌桶）
    rate_limit_per_min: Mapped[int] = mapped_column(
        default=600, nullable=False
    )

    # 关系
    api_keys: Mapped[list["PartnerApiKey"]] = relationship(
        "PartnerApiKey",
        back_populates="partner",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_partners_status", "status"),
        Index("ix_partners_email", "contact_email"),
    )


class PartnerApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """合作方 API Key。明文 Key 仅在生成时返回一次；落库只存 SHA256 摘要。"""

    __tablename__ = "partner_api_keys"

    partner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("partners.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # SHA256(key_plain).hexdigest() —— 64 字符小写十六进制
    key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    # 生成时的可读前缀（如 hl_live_abc12345），便于人肉识别，非敏感
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False,
    )  # active / revoked
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 备注（如「iOS 生产」/「staging」）
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    partner: Mapped["Partner"] = relationship(
        "Partner", back_populates="api_keys"
    )

    __table_args__ = (
        Index("ix_partner_api_keys_partner_status", "partner_id", "status"),
    )

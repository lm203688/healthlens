"""积分系统模型 - 健康币体系"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text, JSON, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class UserPoints(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用户积分账户"""
    __tablename__ = "user_points"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, index=True
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0")
    )  # 当前余额
    total_earned: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0")
    )  # 累计获得
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0")
    )  # 累计消费
    lifetime_value: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0")
    )  # 生命周期价值估算


class PointTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """积分交易记录"""
    __tablename__ = "point_transactions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    tx_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # earn / spend / refund / adjustment
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 来源/用途标识
    source_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # 关联业务ID
    description: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JSON)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime)


class PointRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """积分规则配置"""
    __tablename__ = "point_rules"

    rule_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )  # 规则编码
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # earn / spend
    base_points: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0")
    )
    multiplier_formula: Mapped[str | None] = mapped_column(
        String(200)
    )  # 倍数公式，如 "x2" 或复杂表达式
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    monthly_limit: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=0)
    category: Mapped[str | None] = mapped_column(
        String(50)
    )  # onboarding / daily / referral / api / premium

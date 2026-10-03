"""阶梯邀请奖励模型 - 多级邀请关系 + 阶梯奖励配置"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text, JSON, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class ReferralTier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """邀请阶梯奖励配置
    定义邀请第N个人时的奖励倍数
    例如：第1-3人 1x，第4-10人 1.5x，第11+人 2x
    """
    __tablename__ = "referral_tiers"

    tier_level: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # 阶梯等级 1,2,3...
    tier_name: Mapped[str] = mapped_column(String(50), nullable=False)  # 阶梯名称: 青铜/白银/黄金/钻石
    min_invites: Mapped[int] = mapped_column(Integer, nullable=False)  # 最少邀请人数
    max_invites: Mapped[int | None] = mapped_column(Integer)  # 最多邀请人数，NULL表示无上限
    reward_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("1.0")
    )  # 奖励倍数
    bonus_points: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 达到该阶梯时的额外一次性奖励
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    description: Mapped[str | None] = mapped_column(Text)


class ReferralRelationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """多级邀请关系
    记录每一层的邀请关系，支持多级分销追踪
    level 1 = 直接邀请
    level 2 = 间接邀请（被邀请人邀请的人）
    """
    __tablename__ = "referral_relationships"

    inviter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )  # 邀请人
    invitee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True, unique=True
    )  # 被邀请人（每人只能有一个直接邀请人）
    level: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )  # 关系层级：1=直接邀请
    reward_claimed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )  # 邀请奖励是否已发放
    reward_amount: Mapped[int] = mapped_column(Integer, default=0)  # 实际奖励积分
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    invite_code_used: Mapped[str | None] = mapped_column(String(12))  # 使用的邀请码

    __mapper_args__ = {
        "confirm_deleted_rows": False,
    }


class ReferralRebate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """邀请返利记录
    被邀请人消费积分时，邀请人获得一定比例的返利
    """
    __tablename__ = "referral_rebates"

    inviter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    invitee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1)  # 返利层级
    source_tx_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("point_transactions.id")
    )  # 触发返利的消费交易ID
    rebate_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )  # 返利比例（百分比）
    rebate_points: Mapped[int] = mapped_column(Integer, nullable=False)  # 返利积分数
    description: Mapped[str | None] = mapped_column(String(200))
    is_processed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )  # 是否已发放


class PointPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """积分包商品 - 可购买的积分套餐"""
    __tablename__ = "point_packages"

    package_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )  # 套餐编码
    package_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 套餐名称
    points_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 包含积分数
    bonus_points: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 赠送积分
    price_cny: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )  # 价格（人民币）
    original_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2)
    )  # 原价（用于显示折扣）
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    is_popular: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )  # 是否热门推荐
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JSON)


class PointOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """积分购买订单"""
    __tablename__ = "point_orders"

    order_no: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )  # 订单号
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("point_packages.id"), nullable=False
    )
    package_code: Mapped[str] = mapped_column(String(50), nullable=False)
    points_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 购买积分数
    bonus_points: Mapped[int] = mapped_column(Integer, default=0)  # 赠送积分
    total_points: Mapped[int] = mapped_column(Integer, nullable=False)  # 总积分数
    price_cny: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(20), default="mock"
    )  # mock / wechat / alipay / stripe
    payment_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending / paid / failed / refunded
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    transaction_id: Mapped[str | None] = mapped_column(
        String(100)
    )  # 第三方支付流水号
    points_credited: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )  # 积分是否已到账
    credited_at: Mapped[datetime | None] = mapped_column(DateTime)
    credited_tx_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("point_transactions.id")
    )
    extra_data: Mapped[dict | None] = mapped_column(JSON)

"""阶梯邀请奖励服务 - 多级关系、阶梯奖励、消费返利"""
import uuid
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.tiered_referral import (
    ReferralTier,
    ReferralRelationship,
    ReferralRebate,
    PointPackage,
    PointOrder,
)
from app.services.points_service import award_points, ensure_user_points_account


# ==================== 阶梯奖励配置 ====================

DEFAULT_TIERS = [
    {
        "tier_level": 1,
        "tier_name": "青铜邀请者",
        "min_invites": 0,
        "max_invites": 3,
        "reward_multiplier": "1.0",
        "bonus_points": 0,
        "description": "邀请前3位好友，每人奖励200积分",
    },
    {
        "tier_level": 2,
        "tier_name": "白银邀请者",
        "min_invites": 3,
        "max_invites": 10,
        "reward_multiplier": "1.5",
        "bonus_points": 200,
        "description": "邀请第4-10位好友，每人奖励300积分（1.5x），额外奖励200积分",
    },
    {
        "tier_level": 3,
        "tier_name": "黄金邀请者",
        "min_invites": 10,
        "max_invites": 30,
        "reward_multiplier": "2.0",
        "bonus_points": 500,
        "description": "邀请第11-30位好友，每人奖励400积分（2x），额外奖励500积分",
    },
    {
        "tier_level": 4,
        "tier_name": "钻石邀请者",
        "min_invites": 30,
        "max_invites": None,
        "reward_multiplier": "3.0",
        "bonus_points": 1000,
        "description": "邀请第31位及以上好友，每人奖励600积分（3x），额外奖励1000积分",
    },
]

# 返利比例（按层级）
REBATE_PERCENT_BY_LEVEL = {
    1: Decimal("10"),   # 直接邀请：被邀请人消费的10%返利
    2: Decimal("5"),    # 间接邀请：5%返利
}

MAX_REBATE_LEVEL = 2  # 最多追踪2级返利


# ==================== 阶梯配置管理 ====================

async def initialize_default_tiers(db: AsyncSession) -> int:
    """初始化默认阶梯配置"""
    count = 0
    for tier_data in DEFAULT_TIERS:
        existing = await db.execute(
            select(ReferralTier).where(
                ReferralTier.tier_level == tier_data["tier_level"]
            )
        )
        if existing.scalar_one_or_none():
            continue

        tier = ReferralTier(
            id=str(uuid.uuid4()),
            **tier_data,
            is_active=True,
        )
        db.add(tier)
        count += 1

    if count > 0:
        await db.commit()
        logger.info(f"[ReferralTier] Initialized {count} default tiers")

    return count


async def get_all_tiers(db: AsyncSession) -> list[ReferralTier]:
    """获取所有激活的阶梯配置"""
    result = await db.execute(
        select(ReferralTier)
        .where(ReferralTier.is_active == True)
        .order_by(ReferralTier.tier_level.asc())
    )
    return list(result.scalars().all())


async def get_tier_by_invite_count(
    db: AsyncSession,
    invite_count: int,
) -> ReferralTier | None:
    """根据邀请人数获取对应阶梯"""
    tiers = await get_all_tiers(db)
    for tier in tiers:
        if tier.min_invites <= invite_count:
            if tier.max_invites is None or invite_count < tier.max_invites:
                return tier
    return tiers[-1] if tiers else None


async def get_user_current_tier(
    db: AsyncSession,
    user_id: str,
) -> tuple[ReferralTier | None, int]:
    """获取用户当前所在阶梯

    Returns:
        (当前阶梯, 已邀请人数)
    """
    result = await db.execute(
        select(func.count()).where(
            ReferralRelationship.inviter_id == user_id,
            ReferralRelationship.level == 1,
        )
    )
    invite_count = result.scalar_one() or 0

    tier = await get_tier_by_invite_count(db, invite_count)
    return tier, invite_count


# ==================== 邀请关系管理 ====================

async def create_referral_relationship(
    db: AsyncSession,
    inviter_id: str,
    invitee_id: str,
    invite_code_used: str | None = None,
) -> ReferralRelationship | None:
    """创建邀请关系（同时处理多级关系链）

    Returns:
        新建的直接邀请关系，如果已存在则返回None
    """
    # 检查被邀请人是否已有直接邀请人
    existing = await db.execute(
        select(ReferralRelationship).where(
            ReferralRelationship.invitee_id == invitee_id,
            ReferralRelationship.level == 1,
        )
    )
    if existing.scalar_one_or_none():
        logger.warning(f"[Referral] invitee={invitee_id} already has inviter")
        return None

    # 创建直接邀请关系
    direct_rel = ReferralRelationship(
        id=str(uuid.uuid4()),
        inviter_id=inviter_id,
        invitee_id=invitee_id,
        level=1,
        invite_code_used=invite_code_used,
    )
    db.add(direct_rel)

    # 创建多级关系：向上追溯邀请人的邀请人
    # level 2 = 邀请人的邀请人（间接邀请）
    ancestor_rels = await db.execute(
        select(ReferralRelationship).where(
            ReferralRelationship.invitee_id == inviter_id,
        )
    )

    for ancestor in ancestor_rels.scalars().all():
        if ancestor.level + 1 > MAX_REBATE_LEVEL:
            continue
        # 为更高层级的邀请者也创建关系记录
        upper_rel = ReferralRelationship(
            id=str(uuid.uuid4()),
            inviter_id=ancestor.inviter_id,
            invitee_id=invitee_id,
            level=ancestor.level + 1,
        )
        db.add(upper_rel)

    await db.commit()
    await db.refresh(direct_rel)

    logger.info(
        f"[Referral] Relationship created: "
        f"inviter={inviter_id} -> invitee={invitee_id} (level 1)"
    )
    return direct_rel


async def get_user_referral_stats(
    db: AsyncSession,
    user_id: str,
) -> dict:
    """获取用户邀请统计

    Returns:
        {
            "total_invited": int,       # 总直接邀请人数
            "total_reward": int,        # 累计邀请奖励
            "current_tier": dict,       # 当前阶梯信息
            "next_tier": dict | None,   # 下一阶梯信息
            "invites_to_next": int,     # 距离下一阶梯还需邀请人数
            "level2_count": int,        # 间接邀请人数
            "total_rebate": int,        # 累计返利积分
        }
    """
    # 直接邀请人数
    result = await db.execute(
        select(func.count()).where(
            ReferralRelationship.inviter_id == user_id,
            ReferralRelationship.level == 1,
        )
    )
    total_invited = result.scalar_one() or 0

    # 累计邀请奖励
    result = await db.execute(
        select(func.coalesce(func.sum(ReferralRelationship.reward_amount), 0)).where(
            ReferralRelationship.inviter_id == user_id,
            ReferralRelationship.level == 1,
            ReferralRelationship.reward_claimed == True,
        )
    )
    total_reward = int(result.scalar_one() or 0)

    # 间接邀请人数
    result = await db.execute(
        select(func.count()).where(
            ReferralRelationship.inviter_id == user_id,
            ReferralRelationship.level == 2,
        )
    )
    level2_count = result.scalar_one() or 0

    # 累计返利
    result = await db.execute(
        select(func.coalesce(func.sum(ReferralRebate.rebate_points), 0)).where(
            ReferralRebate.inviter_id == user_id,
            ReferralRebate.is_processed == True,
        )
    )
    total_rebate = int(result.scalar_one() or 0)

    # 当前阶梯
    tiers = await get_all_tiers(db)
    current_tier = None
    next_tier = None
    invites_to_next = 0

    for i, tier in enumerate(tiers):
        if tier.min_invites <= total_invited:
            if tier.max_invites is None or total_invited < tier.max_invites:
                current_tier = tier
                if i + 1 < len(tiers):
                    next_tier = tiers[i + 1]
                    invites_to_next = max(0, next_tier.min_invites - total_invited)
                break

    return {
        "total_invited": total_invited,
        "total_reward": total_reward,
        "current_tier": {
            "tier_level": current_tier.tier_level,
            "tier_name": current_tier.tier_name,
            "reward_multiplier": float(current_tier.reward_multiplier),
            "bonus_points": current_tier.bonus_points,
            "description": current_tier.description,
        } if current_tier else None,
        "next_tier": {
            "tier_level": next_tier.tier_level,
            "tier_name": next_tier.tier_name,
            "reward_multiplier": float(next_tier.reward_multiplier),
            "bonus_points": next_tier.bonus_points,
            "description": next_tier.description,
        } if next_tier else None,
        "invites_to_next": invites_to_next,
        "level2_count": level2_count,
        "total_rebate": total_rebate,
    }


async def process_tiered_referral_reward(
    db: AsyncSession,
    inviter_id: str,
    invitee_id: str,
    base_reward: int = 200,
) -> int:
    """处理阶梯式邀请奖励

    根据邀请人当前已邀请人数确定奖励倍数，发放奖励。

    Returns:
        实际发放的积分数量
    """
    # 获取当前已邀请人数（不包括本次）
    result = await db.execute(
        select(func.count()).where(
            ReferralRelationship.inviter_id == inviter_id,
            ReferralRelationship.level == 1,
            ReferralRelationship.reward_claimed == True,
        )
    )
    current_count = result.scalar_one() or 0

    # 获取对应阶梯
    tier = await get_tier_by_invite_count(db, current_count)
    if not tier:
        multiplier = Decimal("1.0")
        bonus = 0
    else:
        multiplier = tier.reward_multiplier
        bonus = tier.bonus_points if current_count == tier.min_invites else 0

    # 计算实际奖励
    actual_reward = int(base_reward * float(multiplier)) + bonus

    # 发放积分
    await award_points(
        db,
        inviter_id,
        "invite_friend",
        source_id=invitee_id,
        extra_description=f"邀请好友注册（{current_count + 1}人，{tier.tier_name if tier else '基础'}）",
    )

    # 额外阶梯奖励
    if bonus > 0:
        await award_points(
            db,
            inviter_id,
            "invite_friend",
            source_id=f"tier_bonus_{tier.tier_level}",
            extra_description=f"达成{tier.tier_name}里程碑奖励",
        )

    # 更新关系记录
    rel_result = await db.execute(
        select(ReferralRelationship).where(
            ReferralRelationship.inviter_id == inviter_id,
            ReferralRelationship.invitee_id == invitee_id,
            ReferralRelationship.level == 1,
        )
    )
    rel = rel_result.scalar_one_or_none()
    if rel:
        rel.reward_claimed = True
        rel.reward_amount = actual_reward
        rel.claimed_at = datetime.utcnow()
        await db.commit()

    logger.info(
        f"[ReferralReward] inviter={inviter_id}, invitee={invitee_id}, "
        f"base={base_reward}, multiplier={multiplier}, bonus={bonus}, "
        f"total={actual_reward}"
    )
    return actual_reward


async def process_referral_rebate(
    db: AsyncSession,
    invitee_id: str,
    spend_points: int,
    source_tx_id: str | None = None,
) -> int:
    """处理邀请返利

    当被邀请人消费积分时，向上级邀请人发放返利。

    Returns:
        总返利积分数量
    """
    # 查找所有层级的邀请关系
    result = await db.execute(
        select(ReferralRelationship).where(
            ReferralRelationship.invitee_id == invitee_id,
        )
    )
    relationships = result.scalars().all()

    total_rebate = 0

    for rel in relationships:
        level = rel.level
        if level > MAX_REBATE_LEVEL:
            continue

        rebate_percent = REBATE_PERCENT_BY_LEVEL.get(level, Decimal("0"))
        if rebate_percent <= 0:
            continue

        rebate_points = int(spend_points * float(rebate_percent) / 100)
        if rebate_points <= 0:
            continue

        # 创建返利记录
        rebate = ReferralRebate(
            id=str(uuid.uuid4()),
            inviter_id=rel.inviter_id,
            invitee_id=invitee_id,
            level=level,
            source_tx_id=source_tx_id,
            rebate_percent=rebate_percent,
            rebate_points=rebate_points,
            description=f"{'直接' if level == 1 else '间接'}邀请返利（{rebate_percent}%）",
            is_processed=False,
        )
        db.add(rebate)

        # 发放返利积分
        try:
            await award_points(
                db,
                rel.inviter_id,
                "invite_friend",
                source_id=f"rebate_{invitee_id}",
                extra_description=f"邀请返利：被邀请人消费{spend_points}积分，返{rebate_points}积分（{rebate_percent}%）",
            )
            rebate.is_processed = True
            total_rebate += rebate_points
        except Exception as e:
            logger.error(f"[ReferralRebate] Failed: inviter={rel.inviter_id}, error={e}")

    if total_rebate > 0:
        await db.commit()
        logger.info(
            f"[ReferralRebate] invitee={invitee_id}, "
            f"spend={spend_points}, total_rebate={total_rebate}"
        )

    return total_rebate


# ==================== 积分购买 ====================

DEFAULT_PACKAGES = [
    {
        "package_code": "starter",
        "package_name": "入门套餐",
        "points_amount": 100,
        "bonus_points": 0,
        "price_cny": "9.9",
        "original_price": None,
        "is_popular": False,
        "sort_order": 1,
        "description": "适合首次体验，解锁基础高级功能",
    },
    {
        "package_code": "basic",
        "package_name": "基础套餐",
        "points_amount": 500,
        "bonus_points": 50,
        "price_cny": "39.9",
        "original_price": "49.9",
        "is_popular": True,
        "sort_order": 2,
        "description": "热门推荐，赠送50积分，可做5次深度分析",
    },
    {
        "package_code": "pro",
        "package_name": "专业套餐",
        "points_amount": 2000,
        "bonus_points": 300,
        "price_cny": "129.9",
        "original_price": "199.9",
        "is_popular": False,
        "sort_order": 3,
        "description": "深度用户首选，赠送300积分，性价比最高",
    },
    {
        "package_code": "ultimate",
        "package_name": "至尊套餐",
        "points_amount": 5000,
        "bonus_points": 1000,
        "price_cny": "299.9",
        "original_price": "499.9",
        "is_popular": False,
        "sort_order": 4,
        "description": "健康管理达人必备，赠送1000积分，全功能畅用",
    },
]


async def initialize_default_packages(db: AsyncSession) -> int:
    """初始化默认积分套餐"""
    count = 0
    for pkg_data in DEFAULT_PACKAGES:
        existing = await db.execute(
            select(PointPackage).where(
                PointPackage.package_code == pkg_data["package_code"]
            )
        )
        if existing.scalar_one_or_none():
            continue

        pkg = PointPackage(
            id=str(uuid.uuid4()),
            **pkg_data,
            is_active=True,
        )
        db.add(pkg)
        count += 1

    if count > 0:
        await db.commit()
        logger.info(f"[PointPackage] Initialized {count} default packages")

    return count


async def get_all_packages(db: AsyncSession) -> list[PointPackage]:
    """获取所有激活的积分套餐"""
    result = await db.execute(
        select(PointPackage)
        .where(PointPackage.is_active == True)
        .order_by(PointPackage.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_package_by_code(
    db: AsyncSession,
    package_code: str,
) -> PointPackage | None:
    """根据编码获取套餐"""
    result = await db.execute(
        select(PointPackage).where(
            PointPackage.package_code == package_code,
            PointPackage.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def create_point_order(
    db: AsyncSession,
    user_id: str,
    package_code: str,
    payment_method: str = "mock",
) -> PointOrder | None:
    """创建积分购买订单"""
    pkg = await get_package_by_code(db, package_code)
    if not pkg:
        return None

    order_no = f"HL{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"
    total_points = pkg.points_amount + pkg.bonus_points

    order = PointOrder(
        id=str(uuid.uuid4()),
        order_no=order_no,
        user_id=user_id,
        package_id=pkg.id,
        package_code=pkg.package_code,
        points_amount=pkg.points_amount,
        bonus_points=pkg.bonus_points,
        total_points=total_points,
        price_cny=pkg.price_cny,
        payment_method=payment_method,
        payment_status="pending",
        points_credited=False,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    logger.info(f"[PointOrder] Created: user={user_id}, package={package_code}, order_no={order_no}")
    return order


async def process_payment_mock(
    db: AsyncSession,
    order_id: str,
    user_id: str,
) -> PointOrder | None:
    """模拟支付成功（用于测试和开发环境）"""
    result = await db.execute(
        select(PointOrder).where(
            PointOrder.id == order_id,
            PointOrder.user_id == user_id,
        )
    )
    order = result.scalar_one_or_none()

    if not order or order.payment_status != "pending":
        return None

    # 标记支付成功
    order.payment_status = "paid"
    order.paid_at = datetime.utcnow()
    order.transaction_id = f"MOCK{secrets.token_hex(8).upper()}"

    # 确保用户有积分账户
    await ensure_user_points_account(db, user_id)

    # 发放积分（失败必须 fail-loud，绝不允许「已付款却未到账」）
    from app.services.points_service import award_points as _award

    award_result = await _award(
        db,
        user_id,
        "point_purchase",
        source_id=order.id,
        extra_description=f"购买{order.package_code}套餐：{order.points_amount}积分 + {order.bonus_points}赠送积分",
        multiplier=Decimal(order.total_points),  # 使用multiplier来指定实际发放数量
    )

    if not award_result.get("success"):
        # 发分失败：保留订单为 paid 但明确未到账，并抛出异常让上层感知（不再静默成功）
        order.points_credited = False
        await db.commit()
        logger.error(
            f"[PointOrder] 积分发放失败（订单保留 paid 但未到账，待人工/对账补发）: "
            f"order_no={order.order_no}, user={user_id}, reason={award_result.get('message')}"
        )
        raise RuntimeError(f"积分发放失败: {award_result.get('message')}")

    # 标记积分已到账
    order.points_credited = True
    order.credited_at = datetime.utcnow()
    # 从交易记录中获取最新的tx_id
    from app.models.points import PointTransaction
    from sqlalchemy import desc
    tx_result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.user_id == user_id,
            PointTransaction.source == "point_purchase",
            PointTransaction.source_id == order.id,
        ).order_by(desc(PointTransaction.created_at)).limit(1)
    )
    tx = tx_result.scalar_one_or_none()
    order.credited_tx_id = tx.id if tx else None

    await db.commit()
    await db.refresh(order)

    logger.info(
        f"[PointOrder] Paid: order_no={order.order_no}, "
        f"user={user_id}, points={order.total_points}"
    )
    return order


async def get_user_orders(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PointOrder], int]:
    """获取用户的积分购买订单"""
    query = select(PointOrder).where(PointOrder.user_id == user_id).order_by(
        PointOrder.created_at.desc()
    )

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    orders = result.scalars().all()

    return list(orders), total

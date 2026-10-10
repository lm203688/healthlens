"""积分服务 - 核心积分操作"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from loguru import logger

from app.models.points import UserPoints, PointTransaction, PointRule


# 默认积分规则（启动时自动初始化）
DEFAULT_POINT_RULES = [
    {
        "rule_code": "register_complete",
        "rule_name": "完成注册",
        "description": "新用户完成注册",
        "action_type": "earn",
        "base_points": Decimal("100"),
        "category": "onboarding",
        "daily_limit": 1,
    },
    {
        "rule_code": "profile_complete",
        "rule_name": "完善健康档案",
        "description": "填写完整健康档案信息",
        "action_type": "earn",
        "base_points": Decimal("50"),
        "category": "onboarding",
        "daily_limit": 1,
    },
    {
        "rule_code": "report_upload",
        "rule_name": "上传体检报告",
        "description": "上传并解析体检/健康报告",
        "action_type": "earn",
        "base_points": Decimal("100"),
        "category": "onboarding",
        "daily_limit": 3,
    },
    {
        "rule_code": "constitution_survey",
        "rule_name": "完成体质问卷",
        "description": "完成中医体质辨识问卷",
        "action_type": "earn",
        "base_points": Decimal("50"),
        "category": "onboarding",
        "daily_limit": 1,
    },
    {
        "rule_code": "daily_sleep_checkin",
        "rule_name": "每日睡眠打卡",
        "description": "记录每日睡眠数据",
        "action_type": "earn",
        "base_points": Decimal("10"),
        "category": "daily",
        "daily_limit": 1,
    },
    {
        "rule_code": "daily_nutrition_log",
        "rule_name": "每日饮食记录",
        "description": "记录每日饮食情况",
        "action_type": "earn",
        "base_points": Decimal("5"),
        "category": "daily",
        "daily_limit": 3,
    },
    {
        "rule_code": "invite_friend",
        "rule_name": "邀请好友注册",
        "description": "邀请新用户成功注册",
        "action_type": "earn",
        "base_points": Decimal("200"),
        "category": "referral",
        "daily_limit": 10,
    },
    {
        "rule_code": "risk_assessment",
        "rule_name": "完成风险评估",
        "description": "完成慢病风险评估",
        "action_type": "earn",
        "base_points": Decimal("30"),
        "category": "onboarding",
        "daily_limit": 1,
    },
    {
        "rule_code": "deep_analysis_report",
        "rule_name": "深度分析报告",
        "description": "生成深度健康分析报告",
        "action_type": "spend",
        "base_points": Decimal("50"),
        "category": "premium",
    },
    {
        "rule_code": "personalized_plan",
        "rule_name": "个性化健康方案",
        "description": "获取个性化健康改善方案",
        "action_type": "spend",
        "base_points": Decimal("100"),
        "category": "premium",
    },
    {
        "rule_code": "tcm_diagnosis",
        "rule_name": "中医辨证分析",
        "description": "进行中医体质与辨证分析",
        "action_type": "spend",
        "base_points": Decimal("30"),
        "category": "premium",
    },
    {
        "rule_code": "food_medicine_plan",
        "rule_name": "药食同源方案",
        "description": "获取药食同源调理方案",
        "action_type": "spend",
        "base_points": Decimal("20"),
        "category": "premium",
    },
    {
        "rule_code": "api_call",
        "rule_name": "API调用",
        "description": "开发者API调用扣费",
        "action_type": "spend",
        "base_points": Decimal("1"),
        "category": "api",
    },
    {
        # 关键：付费购买积分的发放规则。
        # base_points 必须为 1——实际到账 = base_points × multiplier(=订单总积分)。
        # 且**绝不能设 daily_limit**，否则用户当天二次购买将拿不到积分。
        "rule_code": "point_purchase",
        "rule_name": "购买积分套餐",
        "description": "用户付费购买积分套餐后发放（含赠送积分）",
        "action_type": "earn",
        "base_points": Decimal("1"),
        "category": "purchase",
        "daily_limit": None,
        "monthly_limit": None,
        "priority": 100,
    },
]


async def ensure_user_points_account(db: AsyncSession, user_id: str) -> UserPoints:
    """确保用户积分账户存在"""
    result = await db.execute(
        select(UserPoints).where(UserPoints.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        account = UserPoints(
            user_id=user_id,
            balance=Decimal("0"),
            total_earned=Decimal("0"),
            total_spent=Decimal("0"),
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        logger.info(f"Created points account for user {user_id}")
    return account


async def award_points(
    db: AsyncSession,
    user_id: str,
    rule_code: str,
    source_id: Optional[str] = None,
    extra_description: Optional[str] = None,
    multiplier: Decimal = Decimal("1"),
) -> dict:
    """
    根据规则给用户奖励积分
    """
    # 1. 查找规则
    result = await db.execute(
        select(PointRule).where(
            and_(PointRule.rule_code == rule_code, PointRule.is_active == True)
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        logger.warning(f"Point rule not found or inactive: {rule_code}")
        return {"success": False, "message": f"Rule '{rule_code}' not found"}

    # 2. 检查日/月限额
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if rule.daily_limit:
        today_count = await _count_transactions_today(
            db, user_id, rule_code, today
        )
        if today_count >= rule.daily_limit:
            logger.info(f"Daily limit reached for rule {rule_code}, user {user_id}")
            return {
                "success": False,
                "message": f"Daily limit ({rule.daily_limit}) reached",
                "awarded": 0,
            }

    # 3. 计算积分
    points = rule.base_points * multiplier

    # 4. 确保账户存在并更新
    account = await ensure_user_points_account(db, user_id)
    old_balance = account.balance
    account.balance += points
    account.total_earned += points
    account.lifetime_value += points * Decimal("0.1")  # LTV估算

    # 5. 创建交易记录
    tx = PointTransaction(
        user_id=user_id,
        tx_type="earn",
        amount=points,
        balance_after=account.balance,
        source=rule_code,
        source_id=source_id,
        description=extra_description or rule.rule_name,
    )
    db.add(tx)
    await db.commit()

    logger.info(
        f"Points awarded: user={user_id}, rule={rule_code}, points={points}, "
        f"balance={old_balance} -> {account.balance}"
    )

    return {
        "success": True,
        "awarded": float(points),
        "balance": float(account.balance),
        "rule": rule.rule_name,
    }


async def spend_points(
    db: AsyncSession,
    user_id: str,
    rule_code: str,
    source_id: Optional[str] = None,
    extra_description: Optional[str] = None,
    quantity: int = 1,
) -> dict:
    """
    消费积分
    """
    # 1. 查找规则
    result = await db.execute(
        select(PointRule).where(
            and_(PointRule.rule_code == rule_code, PointRule.is_active == True)
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return {"success": False, "message": f"Rule '{rule_code}' not found"}

    # 2. 计算消费额
    points = rule.base_points * Decimal(str(quantity))

    # 3. 检查余额
    account = await ensure_user_points_account(db, user_id)
    if account.balance < points:
        return {
            "success": False,
            "message": "Insufficient points",
            "required": float(points),
            "balance": float(account.balance),
        }

    # 4. 扣减积分
    old_balance = account.balance
    account.balance -= points
    account.total_spent += points

    # 5. 创建交易记录
    tx = PointTransaction(
        user_id=user_id,
        tx_type="spend",
        amount=-points,
        balance_after=account.balance,
        source=rule_code,
        source_id=source_id,
        description=extra_description or rule.rule_name,
    )
    db.add(tx)
    await db.commit()

    logger.info(
        f"Points spent: user={user_id}, rule={rule_code}, points={points}, "
        f"balance={old_balance} -> {account.balance}"
    )

    return {
        "success": True,
        "spent": float(points),
        "balance": float(account.balance),
        "rule": rule.rule_name,
    }


async def get_points_balance(db: AsyncSession, user_id: str) -> dict:
    """获取用户积分余额"""
    account = await ensure_user_points_account(db, user_id)
    return {
        "balance": float(account.balance),
        "total_earned": float(account.total_earned),
        "total_spent": float(account.total_spent),
        "lifetime_value": float(account.lifetime_value),
    }


async def get_transaction_history(
    db: AsyncSession,
    user_id: str,
    tx_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """获取积分交易历史"""
    query = select(PointTransaction).where(PointTransaction.user_id == user_id)
    count_query = select(func.count()).select_from(PointTransaction).where(
        PointTransaction.user_id == user_id
    )

    if tx_type:
        query = query.where(PointTransaction.tx_type == tx_type)
        count_query = count_query.where(PointTransaction.tx_type == tx_type)

    query = query.order_by(PointTransaction.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    transactions = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for tx in transactions:
        data.append({
            "id": str(tx.id),
            "tx_type": tx.tx_type,
            "amount": float(tx.amount),
            "balance_after": float(tx.balance_after),
            "source": tx.source,
            "description": tx.description,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })

    return {
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


async def initialize_default_rules(db: AsyncSession) -> dict:
    """
    初始化默认积分规则（幂等，可重复执行）。

    除了补齐缺失规则，还会「自愈」关键计费规则的错误配置：
    point_purchase 若被误设 daily_limit 或 base_points≠1，会导致
    用户付费后拿不到积分（资损），因此强制纠正。
    """
    created: list[str] = []
    repaired: list[str] = []

    for rule_data in DEFAULT_POINT_RULES:
        code = rule_data["rule_code"]
        result = await db.execute(select(PointRule).where(PointRule.rule_code == code))
        rule = result.scalar_one_or_none()

        if rule is None:
            db.add(PointRule(**rule_data))
            created.append(code)
            logger.info(f"Created point rule: {code}")
            continue

        if code == "point_purchase":
            need_fix = (
                rule.daily_limit is not None
                or rule.monthly_limit is not None
                or rule.base_points != Decimal("1")
                or not rule.is_active
            )
            if need_fix:
                rule.daily_limit = None
                rule.monthly_limit = None
                rule.base_points = Decimal("1")
                rule.is_active = True
                repaired.append(code)
                logger.warning(f"Repaired critical point rule: {code}")

    await db.commit()

    if created or repaired:
        logger.info(f"积分规则初始化完成 | created={created} | repaired={repaired}")

    return {"created": created, "repaired": repaired, "total": len(DEFAULT_POINT_RULES)}


# 进程内缓存，避免每次注册/下单都重复扫描规则表
_rules_seeded = False


async def ensure_rules_seeded(db: AsyncSession) -> None:
    """
    确保积分规则已存在（进程内只执行一次实际写入检查）。

    在注册赠分、购买积分等关键路径前调用，避免因为忘记跑 seed 脚本
    导致「注册不赠分」「付款不到账」这类线上事故。

    注意：进程内缓存仅作快速通道，命中后仍会做一次存在性校验，
    避免「测试库/多库重建后缓存误判」导致规则缺失（注册不赠分）。
    """
    global _rules_seeded
    if _rules_seeded:
        try:
            r = await db.execute(
                select(PointRule.rule_code).where(PointRule.rule_code == "register_complete")
            )
            if r.scalar_one_or_none():
                return
        except Exception:
            # 校验失败不阻断，进入下面的自愈逻辑
            pass
    try:
        await initialize_default_rules(db)
        _rules_seeded = True
    except Exception as exc:  # 不阻断主流程，但必须留痕
        logger.error(f"积分规则自动初始化失败: {exc}")


async def _count_transactions_today(
    db: AsyncSession, user_id: str, source: str, today: datetime
) -> int:
    """统计今日某来源的交易次数"""
    tomorrow = today + timedelta(days=1)
    result = await db.execute(
        select(func.count())
        .select_from(PointTransaction)
        .where(
            and_(
                PointTransaction.user_id == user_id,
                PointTransaction.source == source,
                PointTransaction.tx_type == "earn",
                PointTransaction.created_at >= today,
                PointTransaction.created_at < tomorrow,
            )
        )
    )
    return result.scalar() or 0

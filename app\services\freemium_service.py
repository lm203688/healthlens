"""Freemium 积分门禁服务
自动化的付费墙逻辑：在用户触及高级功能边界时自动检查积分并触发转化引导
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from loguru import logger

from app.models.points import UserPoints, PointTransaction
from app.services.points_service import (
    spend_points,
    get_points_balance,
    ensure_user_points_account,
)
from app.services.analytics_service import track_conversion, track_event


# ---------------------------------------------------------------------------
# 免费功能清单（不消耗积分即可使用）
# ---------------------------------------------------------------------------
FREE_FEATURES: List[Dict[str, str]] = [
    {
        "code": "basic_report",
        "name": "基础健康报告",
        "description": "基于体检数据的基础健康概况",
    },
    {
        "code": "sleep_tracking",
        "name": "睡眠追踪",
        "description": "日常睡眠质量记录与趋势",
    },
    {
        "code": "daily_checkin",
        "name": "每日打卡",
        "description": "记录每日健康数据并获取积分",
    },
    {
        "code": "health_knowledge",
        "name": "健康知识库",
        "description": "浏览中医与现代医学知识",
    },
    {
        "code": "risk_screening",
        "name": "风险初筛",
        "description": "基础慢病风险快速筛查",
    },
]

# 每日可赚取积分的任务概览（用于 get_earning_guide）
DAILY_EARNING_TASKS: List[Dict[str, Any]] = [
    {
        "rule_code": "daily_sleep_checkin",
        "name": "每日睡眠打卡",
        "points": 10,
        "daily_limit": 1,
        "effort": "low",
    },
    {
        "rule_code": "daily_nutrition_log",
        "name": "每日饮食记录",
        "points": 5,
        "daily_limit": 3,
        "max_per_day": 15,
        "effort": "low",
    },
]

# 一次性赚取任务
ONCE_EARNING_TASKS: List[Dict[str, Any]] = [
    {
        "rule_code": "register_complete",
        "name": "完成注册",
        "points": 100,
        "effort": "none",
    },
    {
        "rule_code": "profile_complete",
        "name": "完善健康档案",
        "points": 50,
        "effort": "medium",
    },
    {
        "rule_code": "report_upload",
        "name": "上传体检报告",
        "points": 100,
        "daily_limit": 3,
        "max_total": 300,
        "effort": "medium",
    },
    {
        "rule_code": "constitution_survey",
        "name": "完成体质问卷",
        "points": 50,
        "effort": "medium",
    },
    {
        "rule_code": "risk_assessment",
        "name": "完成风险评估",
        "points": 30,
        "effort": "medium",
    },
]

# 推荐奖励
REFERRAL_EARNING: Dict[str, Any] = {
    "rule_code": "invite_friend",
    "name": "邀请好友注册",
    "points": 200,
    "daily_limit": 10,
    "effort": "high",
}

# ---------------------------------------------------------------------------
# FreemiumGate
# ---------------------------------------------------------------------------


class FreemiumGate:
    """积分门禁 -- 在用户触碰高级功能时自动检查积分、扣减、追踪转化

    转化优化策略：
    - 首次体验折扣：用户首次触碰某功能时享受50%积分折扣
    - 方案预览：积分不足时提供部分预览而非完全阻断
    - 渐进式引导：先推荐低成本功能再引导高价值功能
    """

    # 首次体验折扣配置
    FIRST_USE_DISCOUNT = 0.5  # 首次使用折扣50%
    PREVIEW_RATIO = 0.3  # 积分不足时展示30%内容作为预览

    PREMIUM_RULES: Dict[str, Dict[str, Any]] = {
        "deep_analysis": {
            "cost": 50,
            "name": "深度分析报告",
            "description": "生成多维度健康深度分析",
            "category": "analysis",
        },
        "personalized_plan": {
            "cost": 100,
            "name": "个性化健康方案",
            "description": "基于基因+体质的个性化方案",
            "category": "plan",
        },
        "tcm_diagnosis": {
            "cost": 30,
            "name": "中医辨证分析",
            "description": "AI中医体质与辨证分析",
            "category": "tcm",
        },
        "food_medicine_plan": {
            "cost": 20,
            "name": "药食同源方案",
            "description": "个性化药食同源调理方案",
            "category": "nutrition",
        },
        "frequency_prescription": {
            "cost": 15,
            "name": "频率疗法处方",
            "description": "个性化频率干预方案",
            "category": "frequency",
        },
        "genome_analysis": {
            "cost": 80,
            "name": "基因组分析报告",
            "description": "深度基因解读与代谢分析",
            "category": "genome",
        },
        "repair_score": {
            "cost": 10,
            "name": "修复评分详解",
            "description": "细胞修复评分详细解读",
            "category": "repair",
        },
    }

    # ------------------------------------------------------------------
    # 首次使用检查
    # ------------------------------------------------------------------

    @classmethod
    async def _is_first_use(
        cls, db: AsyncSession, user_id: str, feature_code: str
    ) -> bool:
        """检查用户是否首次使用某高级功能（未曾成功扣减过积分）"""
        result = await db.execute(
            select(func.count())
            .select_from(PointTransaction)
            .where(
                and_(
                    PointTransaction.user_id == user_id,
                    PointTransaction.source == feature_code,
                    PointTransaction.tx_type == "spend",
                )
            )
        )
        count = result.scalar() or 0
        return count == 0

    # ------------------------------------------------------------------
    # 核心：检查访问权限
    # ------------------------------------------------------------------

    @classmethod
    async def check_access(
        cls, db: AsyncSession, user_id: str, feature_code: str
    ) -> dict:
        """检查用户是否有足够积分访问指定高级功能

        Returns:
            允许: {"allowed": True, "cost": N, "balance": M}
            拒绝: {"allowed": False, "cost": N, "balance": M,
                    "shortfall": S, "message": "..."}
        """
        rule = cls.PREMIUM_RULES.get(feature_code)
        if not rule:
            logger.warning(f"Unknown premium feature: {feature_code}")
            return {
                "allowed": False,
                "cost": 0,
                "balance": 0,
                "shortfall": 0,
                "message": f"未知的高级功能: {feature_code}",
            }

        # 检查是否首次使用该功能（享受折扣）
        is_first_use = await cls._is_first_use(db, user_id, feature_code)
        original_cost = Decimal(str(rule["cost"]))
        if is_first_use:
            cost = (original_cost * Decimal(str(cls.FIRST_USE_DISCOUNT))).quantize(Decimal("1"))
            cost = max(cost, Decimal("1"))  # 至少1积分
        else:
            cost = original_cost

        account = await ensure_user_points_account(db, user_id)
        balance = account.balance

        # 无论是否通过，都记录门禁触碰事件（用于转化漏斗）
        await cls.track_gate_touch(db, user_id, feature_code, source="check_access")

        if balance >= cost:
            return {
                "allowed": True,
                "cost": float(cost),
                "original_cost": float(original_cost),
                "is_first_use_discount": is_first_use,
                "balance": float(balance),
                "feature": feature_code,
                "feature_name": rule["name"],
            }

        shortfall = cost - balance
        return {
            "allowed": False,
            "cost": float(cost),
            "original_cost": float(original_cost),
            "is_first_use_discount": is_first_use,
            "balance": float(balance),
            "shortfall": float(shortfall),
            "preview_available": True,
            "preview_message": (
                f"您的积分余额不足，但可以先预览部分内容。"
                f"完整功能需要 {cost} 积分"
                f"{'（首次体验价）' if is_first_use else ''}，"
                f"当前余额 {balance} 积分。"
                f"完成以下任务即可解锁完整内容。"
            ),
            "message": (
                f"积分不足，无法使用「{rule['name']}」。"
                f"需要 {cost} 积分"
                f"{'（首次体验价，原价' + str(int(original_cost)) + '积分）' if is_first_use else ''}，"
                f"当前余额 {balance} 积分，"
                f"还差 {shortfall} 积分。"
            ),
            "feature": feature_code,
            "feature_name": rule["name"],
        }

    # ------------------------------------------------------------------
    # 核心：原子化访问执行（检查 + 扣减一步完成）
    # ------------------------------------------------------------------

    @classmethod
    async def execute_access(
        cls,
        db: AsyncSession,
        user_id: str,
        feature_code: str,
        source_id: Optional[str] = None,
    ) -> dict:
        """原子化执行访问：检查积分 + 扣减 + 记录收据

        Returns:
            成功: {"success": True, "feature": ..., "cost": N,
                   "balance": M, "receipt": {...}}
            失败: {"success": False, "feature": ..., "cost": N,
                   "balance": M, "shortfall": S, "message": "..."}
        """
        rule = cls.PREMIUM_RULES.get(feature_code)
        if not rule:
            return {
                "success": False,
                "feature": feature_code,
                "cost": 0,
                "balance": 0,
                "shortfall": 0,
                "message": f"未知的高级功能: {feature_code}",
            }

        # 首次使用折扣
        is_first_use = await cls._is_first_use(db, user_id, feature_code)
        original_cost = Decimal(str(rule["cost"]))
        if is_first_use:
            cost = (original_cost * Decimal(str(cls.FIRST_USE_DISCOUNT))).quantize(Decimal("1"))
            cost = max(cost, Decimal("1"))
        else:
            cost = original_cost

        # 1. 记录门禁触碰
        await cls.track_gate_touch(db, user_id, feature_code, source="execute_access")

        # 2. 检查余额
        account = await ensure_user_points_account(db, user_id)
        balance = account.balance

        if balance < cost:
            shortfall = cost - balance
            return {
                "success": False,
                "feature": feature_code,
                "feature_name": rule["name"],
                "cost": float(cost),
                "balance": float(balance),
                "shortfall": float(shortfall),
                "message": (
                    f"积分不足，无法使用「{rule['name']}」。"
                    f"需要 {cost} 积分，当前余额 {balance} 积分，"
                    f"还差 {shortfall} 积分。"
                ),
            }

        # 3. 扣减积分（使用 points_service 的 spend_points）
        spend_result = await spend_points(
            db,
            user_id,
            rule_code=feature_code,
            source_id=source_id,
            extra_description=f"使用高级功能: {rule['name']}",
            quantity=1,
        )

        if not spend_result.get("success"):
            return {
                "success": False,
                "feature": feature_code,
                "feature_name": rule["name"],
                "cost": float(cost),
                "balance": float(balance),
                "shortfall": float(cost - balance),
                "message": spend_result.get("message", "积分扣减失败，请稍后重试"),
            }

        # 4. 构建收据
        receipt = {
            "feature_code": feature_code,
            "feature_name": rule["name"],
            "category": rule["category"],
            "cost": float(cost),
            "balance_before": float(balance),
            "balance_after": spend_result["balance"],
            "source_id": source_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 5. 记录转化事件（premium 转化）
        try:
            await track_conversion(
                db,
                user_id=user_id,
                source="freemium_gate",
                conversion_type="premium_feature_access",
            )
        except Exception as e:
            logger.warning(f"Failed to track premium conversion: {e}")

        # 6. 记录行为事件
        try:
            await track_event(
                db,
                user_id=user_id,
                event_type="premium_feature_used",
                metadata={
                    "feature_code": feature_code,
                    "feature_name": rule["name"],
                    "cost": float(cost),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to track feature usage event: {e}")

        logger.info(
            f"Premium access granted: user={user_id}, "
            f"feature={feature_code}, cost={cost}"
        )

        return {
            "success": True,
            "feature": feature_code,
            "feature_name": rule["name"],
            "cost": float(cost),
            "balance": spend_result["balance"],
            "receipt": receipt,
        }

    # ------------------------------------------------------------------
    # 赚取积分引导
    # ------------------------------------------------------------------

    @classmethod
    async def get_earning_guide(cls, db: AsyncSession, user_id: str) -> dict:
        """生成个性化积分赚取指南

        根据用户当前余额和最近的触碰功能，推荐最高效的积分获取方式，
        并计算需要多少操作才能解锁目标功能。
        """
        balance_info = await get_points_balance(db, user_id)
        current_balance = balance_info["balance"]
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # --- 1. 查询用户最近触碰的高级功能（取最近一个） ---
        last_gate_result = await db.execute(
            select(PointTransaction)
            .where(
                and_(
                    PointTransaction.user_id == user_id,
                    PointTransaction.source == "gate_touch",
                )
            )
            .order_by(PointTransaction.created_at.desc())
            .limit(1)
        )
        last_gate = last_gate_result.scalar_one_or_none()
        target_feature = None
        target_cost = 0
        if last_gate and last_gate.extra_data:
            target_feature = last_gate.extra_data.get("feature_code")
            if target_feature:
                rule = cls.PREMIUM_RULES.get(target_feature)
                if rule:
                    target_cost = rule["cost"]

        # --- 2. 每日任务完成情况 ---
        incomplete_daily = []
        for task in DAILY_EARNING_TASKS:
            today_count = await _count_transactions_today(
                db, user_id, task["rule_code"], today
            )
            remaining = task.get("daily_limit", 1) - today_count
            if remaining > 0:
                points_possible = task["points"] * remaining
                incomplete_daily.append({
                    "rule_code": task["rule_code"],
                    "name": task["name"],
                    "points_per_action": task["points"],
                    "remaining_today": remaining,
                    "points_possible": points_possible,
                    "effort": task["effort"],
                })

        daily_total_possible = sum(t["points_possible"] for t in incomplete_daily)

        # --- 3. 一次性任务完成情况 ---
        incomplete_once = []
        for task in ONCE_EARNING_TASKS:
            count_result = await db.execute(
                select(func.count())
                .select_from(PointTransaction)
                .where(
                    and_(
                        PointTransaction.user_id == user_id,
                        PointTransaction.source == task["rule_code"],
                        PointTransaction.tx_type == "earn",
                    )
                )
            )
            done_count = count_result.scalar() or 0
            limit = task.get("max_total") or task.get("daily_limit") or 1
            if done_count < limit:
                incomplete_once.append({
                    "rule_code": task["rule_code"],
                    "name": task["name"],
                    "points": task["points"],
                    "effort": task["effort"],
                })

        once_total_possible = sum(t["points"] for t in incomplete_once)

        # --- 4. 推荐奖励 ---
        referral_info = {
            **REFERRAL_EARNING,
            "daily_limit_remaining": REFERRAL_EARNING["daily_limit"],
        }
        # 查今日已邀请次数
        referral_today_count = await _count_transactions_today(
            db, user_id, REFERRAL_EARNING["rule_code"], today
        )
        referral_info["remaining_today"] = max(
            0, REFERRAL_EARNING["daily_limit"] - referral_today_count
        )

        # --- 5. 计算解锁目标功能所需操作 ---
        unlock_guide = None
        if target_feature and target_cost > 0:
            total_available = daily_total_possible + once_total_possible
            if current_balance + total_available >= target_cost:
                still_need = max(0, target_cost - current_balance)
                # 优先用每日任务覆盖
                daily_cover = min(daily_total_possible, still_need)
                once_cover = min(once_total_possible, still_need - daily_cover)
                referral_cover = max(0, still_need - daily_cover - once_cover)

                unlock_guide = {
                    "target_feature": target_feature,
                    "target_feature_name": cls.PREMIUM_RULES.get(
                        target_feature, {}
                    ).get("name", target_feature),
                    "target_cost": target_cost,
                    "current_balance": current_balance,
                    "still_need": still_need,
                    "strategy": {
                        "complete_daily_tasks": {
                            "points_needed": daily_cover,
                            "actions_estimated": _estimate_actions(
                                daily_cover, incomplete_daily
                            ),
                        },
                        "complete_once_tasks": {
                            "points_needed": once_cover,
                            "tasks_to_do": _select_once_tasks(
                                once_cover, incomplete_once
                            ),
                        },
                        "referral_needed": {
                            "points_needed": referral_cover,
                            "invites_needed": max(
                                1,
                                (referral_cover + REFERRAL_EARNING["points"] - 1)
                                // REFERRAL_EARNING["points"],
                            ),
                        },
                    },
                    "can_unlock_today": (
                        current_balance + daily_total_possible >= target_cost
                    ),
                }
            else:
                # 即使做完所有任务也不够，需要推荐
                still_need = max(0, target_cost - current_balance - total_available)
                unlock_guide = {
                    "target_feature": target_feature,
                    "target_feature_name": cls.PREMIUM_RULES.get(
                        target_feature, {}
                    ).get("name", target_feature),
                    "target_cost": target_cost,
                    "current_balance": current_balance,
                    "still_need": target_cost - current_balance,
                    "strategy": {
                        "complete_daily_tasks": {
                            "points_needed": daily_total_possible,
                            "actions_estimated": _estimate_actions(
                                daily_total_possible, incomplete_daily
                            ),
                        },
                        "complete_once_tasks": {
                            "points_needed": once_total_possible,
                            "tasks_to_do": [t["name"] for t in incomplete_once],
                        },
                        "referral_needed": {
                            "points_needed": still_need,
                            "invites_needed": max(
                                1,
                                (still_need + REFERRAL_EARNING["points"] - 1)
                                // REFERRAL_EARNING["points"],
                            ),
                        },
                    },
                    "can_unlock_today": False,
                }

        # 记录查看赚取引导事件
        try:
            await track_event(
                db,
                user_id=user_id,
                event_type="view_earning_guide",
                metadata={
                    "current_balance": current_balance,
                    "target_feature": target_feature,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to track earning guide view: {e}")

        return {
            "current_balance": current_balance,
            "daily_tasks": incomplete_daily,
            "daily_points_possible": daily_total_possible,
            "once_tasks": incomplete_once,
            "once_points_possible": once_total_possible,
            "referral": referral_info,
            "target_feature": target_feature,
            "unlock_guide": unlock_guide,
        }

    # ------------------------------------------------------------------
    # 门禁触碰追踪
    # ------------------------------------------------------------------

    @classmethod
    async def track_gate_touch(
        cls,
        db: AsyncSession,
        user_id: str,
        feature_code: str,
        source: str = "direct",
    ) -> dict:
        """记录用户触碰付费墙的事件（转化漏斗起点）

        Args:
            db: 异步数据库会话
            user_id: 用户ID
            feature_code: 用户试图访问的高级功能编码
            source: 触碰来源 (direct / check_access / execute_access / recommendation)

        Returns:
            {"success": True, "touch_id": str}
        """
        rule = cls.PREMIUM_RULES.get(feature_code, {})

        # 写入积分交易表作为触碰记录
        touch_record = PointTransaction(
            user_id=user_id,
            tx_type="earn",  # earn 类型仅作为记录，amount=0
            amount=Decimal("0"),
            balance_after=Decimal("0"),
            source="gate_touch",
            source_id=None,
            description=f"触碰付费墙: {rule.get('name', feature_code)}",
            extra_data={
                "feature_code": feature_code,
                "feature_name": rule.get("name", feature_code),
                "feature_cost": rule.get("cost", 0),
                "category": rule.get("category", "unknown"),
                "source": source,
            },
        )
        db.add(touch_record)
        await db.commit()

        # 同步写入分析事件表
        try:
            await track_event(
                db,
                user_id=user_id,
                event_type="gate_touch",
                metadata={
                    "feature_code": feature_code,
                    "feature_name": rule.get("name", feature_code),
                    "feature_cost": rule.get("cost", 0),
                    "category": rule.get("category", "unknown"),
                    "source": source,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to track gate_touch event: {e}")

        logger.info(
            f"Gate touch recorded: user={user_id}, "
            f"feature={feature_code}, source={source}"
        )

        return {
            "success": True,
            "touch_id": str(touch_record.id),
        }


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def get_all_features() -> List[Dict[str, Any]]:
    """返回所有高级功能列表及其积分费用

    Returns:
        [{"code": ..., "name": ..., "description": ..., "cost": ..., "category": ...}, ...]
    """
    return [
        {
            "code": code,
            "name": rule["name"],
            "description": rule["description"],
            "cost": rule["cost"],
            "category": rule["category"],
            "is_premium": True,
        }
        for code, rule in sorted(
            FreemiumGate.PREMIUM_RULES.items(), key=lambda x: x[1]["cost"]
        )
    ]


def get_free_features() -> List[Dict[str, Any]]:
    """返回所有免费功能列表

    Returns:
        [{"code": ..., "name": ..., "description": ..., "is_premium": False}, ...]
    """
    return [
        {
            "code": f["code"],
            "name": f["name"],
            "description": f["description"],
            "is_premium": False,
        }
        for f in FREE_FEATURES
    ]


async def calculate_roi(
    db: AsyncSession, user_id: str, feature_code: str
) -> dict:
    """计算某高级功能对特定用户的价值主张（ROI）

    通过对比用户历史使用数据和功能价格，帮助用户判断是否值得消费积分。

    Returns:
        {
            "feature_code": ...,
            "feature_name": ...,
            "cost": ...,
            "value_score": 0.0~1.0,
            "rationale": "...",
            "alternatives": [...],
        }
    """
    rule = FreemiumGate.PREMIUM_RULES.get(feature_code)
    if not rule:
        return {
            "feature_code": feature_code,
            "value_score": 0.0,
            "rationale": "未知功能，无法评估价值。",
        }

    cost = rule["cost"]
    balance_info = await get_points_balance(db, user_id)
    current_balance = balance_info["balance"]
    total_earned = balance_info["total_earned"]

    # 基础价值评分 (0~1)
    # 维度1: 用户使用频率（该功能被触碰次数）
    gate_touch_count_result = await db.execute(
        select(func.count())
        .select_from(PointTransaction)
        .where(
            and_(
                PointTransaction.user_id == user_id,
                PointTransaction.source == "gate_touch",
                PointTransaction.extra_data.isnot(None),
            )
        )
    )
    gate_touch_count = gate_touch_count_result.scalar() or 0

    # 维度2: 可负担性（余额 / 费用 比率）
    affordability = min(1.0, current_balance / cost) if cost > 0 else 1.0

    # 维度3: 活跃度（总赚取积分越高，用户越活跃，功能价值越大）
    engagement = min(1.0, total_earned / 500) if total_earned > 0 else 0.0

    # 维度4: 类别相关性（基于功能类别赋予基础权重）
    category_weights = {
        "analysis": 0.8,
        "plan": 0.9,
        "tcm": 0.7,
        "nutrition": 0.75,
        "frequency": 0.6,
        "genome": 0.85,
        "repair": 0.65,
    }
    category_weight = category_weights.get(rule["category"], 0.5)

    # 综合价值评分
    value_score = round(
        (affordability * 0.3 + engagement * 0.3 + category_weight * 0.4) * 100,
        1,
    ) / 100

    # 推荐理由
    rationale_parts = []
    if affordability >= 1.0:
        rationale_parts.append(f"当前余额({current_balance}积分)足够支付费用({cost}积分)")
    elif affordability >= 0.5:
        rationale_parts.append(
            f"当前余额({current_balance}积分)接近费用({cost}积分)，"
            f"完成少量任务即可解锁"
        )
    else:
        rationale_parts.append(
            f"当前余额({current_balance}积分)不足以支付({cost}积分)，"
            f"建议先完成赚取任务"
        )

    if engagement > 0.5:
        rationale_parts.append("您是活跃用户，该功能将为您带来更高价值")
    if category_weight >= 0.8:
        rationale_parts.append(f"「{rule['name']}」属于高价值核心功能")

    # 推荐替代方案（如果太贵，推荐更便宜的同类功能）
    alternatives = []
    if affordability < 0.5:
        same_category = [
            (code, r)
            for code, r in FreemiumGate.PREMIUM_RULES.items()
            if r["category"] == rule["category"] and code != feature_code
        ]
        for code, r in same_category:
            if r["cost"] <= current_balance:
                alternatives.append({
                    "code": code,
                    "name": r["name"],
                    "cost": r["cost"],
                    "reason": "当前余额即可解锁",
                })
        # 如果同类无替代，推荐最便宜的入门功能
        if not alternatives:
            cheapest = min(
                FreemiumGate.PREMIUM_RULES.values(), key=lambda x: x["cost"]
            )
            alternatives.append({
                "code": next(
                    k
                    for k, v in FreemiumGate.PREMIUM_RULES.items()
                    if v["cost"] == cheapest["cost"]
                ),
                "name": cheapest["name"],
                "cost": cheapest["cost"],
                "reason": "最低费用的入门高级功能",
            })

    return {
        "feature_code": feature_code,
        "feature_name": rule["name"],
        "description": rule["description"],
        "category": rule["category"],
        "cost": cost,
        "current_balance": current_balance,
        "value_score": value_score,
        "rationale": "。".join(rationale_parts) + "。",
        "alternatives": alternatives,
    }


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


async def _count_transactions_today(
    db: AsyncSession, user_id: str, source: str, today: datetime
) -> int:
    """统计用户今日某来源的 earn 交易次数"""
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


def _estimate_actions(
    points_needed: float, daily_tasks: List[Dict[str, Any]]
) -> int:
    """估算需要多少次每日操作才能赚取指定积分（贪心策略）"""
    remaining = points_needed
    actions = 0
    # 按每次操作收益从高到低排序
    sorted_tasks = sorted(daily_tasks, key=lambda t: -t["points_per_action"])
    for task in sorted_tasks:
        if remaining <= 0:
            break
        max_from_task = task["points_possible"]
        use = min(max_from_task, remaining)
        actions += max(1, (use + task["points_per_action"] - 1) // task["points_per_action"])
        remaining -= use
    # 如果还有剩余，按最低收益估算
    if remaining > 0 and sorted_tasks:
        min_points = sorted_tasks[-1]["points_per_action"]
        actions += max(1, (remaining + min_points - 1) // min_points)
    return actions


def _select_once_tasks(
    points_needed: float, once_tasks: List[Dict[str, Any]]
) -> List[str]:
    """选择能达到指定积分的一次性任务列表（贪心策略）"""
    selected = []
    remaining = points_needed
    sorted_tasks = sorted(once_tasks, key=lambda t: -t["points"])
    for task in sorted_tasks:
        if remaining <= 0:
            break
        selected.append(task["name"])
        remaining -= task["points"]
    return selected

"""推广裂变服务 - 持久化存储"""
import random
import string
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from loguru import logger

from app.models.referral import InviteCode, ShareRecord
from app.config import settings


async def generate_invite_code(db: AsyncSession, user_id: str) -> dict:
    """生成唯一 8 字符邀请码，30 天有效期"""
    # 检查是否已有未使用的有效邀请码
    existing_result = await db.execute(
        select(InviteCode).where(
            and_(
                InviteCode.inviter_id == user_id,
                InviteCode.status == "active",
                InviteCode.expires_at > datetime.utcnow(),
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {
            "success": True,
            "invite_code": existing.code,
            "expires_at": existing.expires_at.isoformat() if existing.expires_at else None,
        }

    # 生成唯一码（最多尝试 10 次）
    code = None
    for _ in range(10):
        candidate = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        # 检查唯一性
        check = await db.execute(
            select(InviteCode).where(InviteCode.code == candidate)
        )
        if not check.scalar_one_or_none():
            code = candidate
            break

    if not code:
        logger.warning(f"Failed to generate unique invite code for user {user_id}")
        return {"success": False, "message": "生成邀请码失败，请稍后重试"}

    expires_at = datetime.utcnow() + timedelta(days=30)
    invite = InviteCode(
        code=code,
        inviter_id=user_id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    logger.info(f"Invite code generated: user={user_id}, code={code}, expires={expires_at}")

    return {
        "success": True,
        "invite_code": code,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
    }


async def claim_invite_code(
    db: AsyncSession,
    claimant_id: str,
    code: str,
) -> dict:
    """验证并使用邀请码，双方各获得积分奖励"""
    code = code.upper().strip()

    result = await db.execute(
        select(InviteCode).where(InviteCode.code == code)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        return {"success": False, "message": "邀请码无效或不存在"}

    if invite.status != "active":
        return {"success": False, "message": "该邀请码已被使用或已过期"}

    if invite.expires_at and invite.expires_at < datetime.utcnow():
        return {"success": False, "message": "该邀请码已过期"}

    if invite.inviter_id == claimant_id:
        return {"success": False, "message": "不能使用自己的邀请码"}

    # 标记为已使用
    invite.status = "claimed"
    invite.claimant_id = claimant_id
    invite.claimed_at = datetime.utcnow()

    # 积分奖励通过 points_service 发放
    reward_points = 50
    try:
        from app.services.points_service import award_points
        # 邀请人奖励
        await award_points(
            db, invite.inviter_id, "invite_friend",
            source_id=claimant_id,
            extra_description=f"邀请用户 {claimant_id[:8]} 注册奖励",
        )
        # 被邀请人奖励
        await award_points(
            db, claimant_id, "register_complete",
            source_id=invite.id,
            extra_description=f"使用邀请码 {code} 注册奖励",
        )
    except Exception as e:
        logger.warning(f"Failed to award referral points: {e}")
        reward_points = 0

    await db.commit()

    logger.info(f"Invite code claimed: code={code}, inviter={invite.inviter_id}, claimant={claimant_id}")

    return {
        "success": True,
        "message": f"邀请码使用成功，双方各获得 {reward_points} 积分奖励",
        "reward": reward_points,
    }


async def record_share(
    db: AsyncSession,
    user_id: str,
    content_type: str,
    content_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> dict:
    """记录分享动作"""
    record = ShareRecord(
        user_id=user_id,
        content_type=content_type,
        content_id=content_id,
        platform=platform,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    logger.info(f"Share recorded: user={user_id}, type={content_type}, platform={platform}")

    return {
        "success": True,
        "share_id": str(record.id),
        "share_url": f"{settings.PUBLIC_BASE_URL}/register?ref={user_id[:8]}",
    }


async def increment_share_clicks(db: AsyncSession, share_id: str) -> dict:
    """追踪分享链接点击"""
    result = await db.execute(
        select(ShareRecord).where(ShareRecord.id == share_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return {"success": False, "message": "分享记录不存在"}

    record.click_count = (record.click_count or 0) + 1
    await db.commit()

    return {"success": True, "click_count": record.click_count}


async def get_referral_stats(db: AsyncSession, user_id: str) -> dict:
    """获取用户邀请统计

    返回: 邀请数、获得奖励、点击率等
    """
    # 邀请码总数（该用户生成的）
    total_codes_result = await db.execute(
        select(func.count()).select_from(InviteCode)
        .where(InviteCode.inviter_id == user_id)
    )
    total_codes = total_codes_result.scalar() or 0

    # 已被使用的邀请码
    claimed_result = await db.execute(
        select(func.count()).select_from(InviteCode)
        .where(and_(
            InviteCode.inviter_id == user_id,
            InviteCode.status == "claimed",
        ))
    )
    claimed_count = claimed_result.scalar() or 0

    # 该用户的分享总数
    share_count_result = await db.execute(
        select(func.count()).select_from(ShareRecord)
        .where(ShareRecord.user_id == user_id)
    )
    share_count = share_count_result.scalar() or 0

    # 分享链接总点击数
    clicks_result = await db.execute(
        select(func.coalesce(func.sum(ShareRecord.click_count), 0))
        .select_from(ShareRecord)
        .where(ShareRecord.user_id == user_id)
    )
    total_clicks = clicks_result.scalar() or 0

    # 点击率
    click_through_rate = 0.0
    if share_count > 0:
        click_through_rate = round(total_clicks / share_count * 100, 2)

    # 获得的奖励积分（通过积分交易记录计算）
    rewards_earned = 0
    try:
        from app.models.points import PointTransaction
        reward_result = await db.execute(
            select(func.coalesce(func.sum(PointTransaction.amount), 0))
            .select_from(PointTransaction)
            .where(and_(
                PointTransaction.user_id == user_id,
                PointTransaction.source == "invite_friend",
            ))
        )
        rewards_earned = float(reward_result.scalar() or 0)
    except Exception:
        pass

    return {
        "total_codes": total_codes,
        "claimed_count": claimed_count,
        "share_count": share_count,
        "total_clicks": total_clicks,
        "click_through_rate": click_through_rate,
        "rewards_earned": rewards_earned,
    }


async def get_leaderboard(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
    """获取邀请排行榜

    返回 Top N 邀请人列表
    """
    result = await db.execute(
        select(
            InviteCode.inviter_id,
            func.count().label("invitation_count"),
        )
        .where(InviteCode.status == "claimed")
        .group_by(InviteCode.inviter_id)
        .order_by(desc("invitation_count"))
        .limit(limit)
    )

    leaderboard = []
    for row in result:
        leaderboard.append({
            "user_id": row.inviter_id,
            "invitation_count": row.invitation_count,
        })

    # 附加用户名信息
    try:
        from app.models.user import User
        for entry in leaderboard:
            user_result = await db.execute(
                select(User.email).where(User.id == entry["user_id"])
            )
            user = user_result.scalar_one_or_none()
            entry["email_hint"] = (user[:4] + "***") if user and len(user) > 4 else "***"
    except Exception:
        pass

    return leaderboard


async def cleanup_expired_codes(db: AsyncSession) -> dict:
    """标记过期邀请码"""
    now = datetime.utcnow()

    result = await db.execute(
        select(InviteCode).where(
            and_(
                InviteCode.status == "active",
                InviteCode.expires_at < now,
                InviteCode.expires_at.isnot(None),
            )
        )
    )
    expired = result.scalars().all()

    count = 0
    for code in expired:
        code.status = "expired"
        count += 1

    await db.commit()

    if count > 0:
        logger.info(f"Marked {count} invite codes as expired")

    return {"success": True, "expired_count": count}

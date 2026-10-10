"""
推广系统 API
路由前缀: /api/v1/growth
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional
from loguru import logger

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# 分享/邀请链接统一使用 config.PUBLIC_BASE_URL（线上为 https://healthlens.cc），
# 不再硬编码已失效的 healthlens.app 域名（P0-18）。绝不返回编造的邀请统计。


class ShareRequest(BaseModel):
    content_type: str = Field(..., pattern="^(plan|knowledge|app)$")
    content_id: Optional[str] = None


class InviteClaimRequest(BaseModel):
    invite_code: str = Field(..., min_length=6, max_length=12)


@router.post("/share", summary="生成分享链接")
async def generate_share(
    body: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.referral_service import record_share
    except ImportError:
        logger.warning("referral_service not available, returning fallback")
        return {"success": False, "data": None, "message": "推广服务暂不可用，请稍后重试"}

    base_url = settings.PUBLIC_BASE_URL
    user_ref = ""
    if current_user:
        user_ref = f"?ref={current_user.id}"

    if body.content_type == "plan":
        share_url = f"{base_url}/plan/{body.content_id or 'default'}{user_ref}"
        share_text = "我在 HealthLens 生成了专属健康修复方案，快来看看吧！"
    elif body.content_type == "knowledge":
        share_url = f"{base_url}/knowledge/{body.content_id or 'intro'}{user_ref}"
        share_text = "HealthLens 健康知识库，融合中医古籍与精准养生，推荐给你。"
    else:
        share_url = f"{base_url}{user_ref}"
        share_text = "推荐 HealthLens —— AI 驱动的健康全景平台，看清健康的每一个细节。"

    user_id = current_user.id if current_user else "anonymous"
    result = await record_share(
        db, user_id=user_id,
        content_type=body.content_type,
        content_id=body.content_id,
        platform="web",
    )

    if not result.get("success"):
        return {"success": False, "data": None, "message": result.get("message", "分享记录失败")}

    # 返回与原接口一致的响应格式，使用 API 生成的完整链接
    return {
        "success": True,
        "data": {
            "share_url": share_url,
            "share_text": share_text,
        },
    }


@router.post("/invite", summary="生成邀请码")
async def generate_invite(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.referral_service import generate_invite_code
    except ImportError:
        logger.warning("referral_service not available, returning fallback")
        return {"success": False, "data": None, "message": "推广服务暂不可用，请稍后重试"}

    user_id = current_user.id if current_user else "anonymous"

    result = await generate_invite_code(db, user_id=user_id)

    if not result.get("success"):
        return {"success": False, "data": None, "message": result.get("message", "生成邀请码失败")}

    code = result["invite_code"]
    base_url = settings.PUBLIC_BASE_URL
    invite_url = f"{base_url}/register?invite={code}"

    return {
        "success": True,
        "data": {
            "invite_code": code,
            "invite_url": invite_url,
        },
    }


@router.post("/invite/claim", summary="使用邀请码")
async def claim_invite(
    body: InviteClaimRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.referral_service import claim_invite_code
    except ImportError:
        logger.warning("referral_service not available, returning fallback")
        return {"success": False, "data": None, "message": "推广服务暂不可用，请稍后重试"}

    claimant_id = current_user.id if current_user else None
    if not claimant_id:
        return {"success": False, "data": None, "message": "请先登录后再使用邀请码"}

    result = await claim_invite_code(db, claimant_id=claimant_id, code=body.invite_code)

    if not result.get("success"):
        return {"success": False, "data": None, "message": result.get("message", "邀请码使用失败")}

    return {
        "success": True,
        "data": {"reward": result.get("reward", 50)},
        "message": result.get("message", "邀请码使用成功，双方各获得 50 积分奖励"),
    }


@router.get("/referrals", summary="获取邀请统计")
async def get_referrals(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    try:
        from app.services.referral_service import get_referral_stats
    except ImportError:
        logger.warning("referral_service not available, returning demo data")

    user_id = current_user.id if current_user else None

    if not user_id:
        # 诚实空态：未登录时返回全零统计，绝不编造邀请数（P0-17）
        return {
            "success": True,
            "data": {
                "total_invited": 0,
                "rewards_earned": 0,
                "pending_rewards": 0,
                "share_count": 0,
                "total_clicks": 0,
                "click_through_rate": 0.0,
            },
            "message": "未登录，暂无邀请数据",
        }

    try:
        stats = await get_referral_stats(db, user_id=user_id)
        return {
            "success": True,
            "data": {
                "total_invited": stats.get("claimed_count", 0),
                "rewards_earned": stats.get("rewards_earned", 0),
                "pending_rewards": 0,
                "share_count": stats.get("share_count", 0),
                "total_clicks": stats.get("total_clicks", 0),
                "click_through_rate": stats.get("click_through_rate", 0.0),
            },
        }
    except Exception as e:
        logger.warning(f"Failed to get referral stats from service: {e}")
        # 失败上报诚实空态，不回退到任何编造数字（P0-17）
        return {
            "success": True,
            "data": {
                "total_invited": 0,
                "rewards_earned": 0,
                "pending_rewards": 0,
                "share_count": 0,
                "total_clicks": 0,
                "click_through_rate": 0.0,
            },
            "message": "邀请数据暂不可用",
        }

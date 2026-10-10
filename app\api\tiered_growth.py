"""阶梯邀请 + 积分购买 API
邀请阶梯奖励、消费返利、积分套餐购买
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.tiered_referral_service import (
    get_all_tiers,
    get_user_current_tier,
    get_user_referral_stats,
    process_tiered_referral_reward,
    initialize_default_tiers,
    get_all_packages,
    create_point_order,
    process_payment_mock,
    get_user_orders,
    initialize_default_packages,
)
from app.services.referral_service import claim_invite_code as original_claim
from app.services.tiered_referral_service import create_referral_relationship

router = APIRouter(tags=["阶梯邀请 & 积分购买"])


# ==================== 阶梯邀请 ====================

@router.get("/tiers")
async def get_referral_tiers(
    db: AsyncSession = Depends(get_db),
):
    """获取所有邀请阶梯配置"""
    # 确保有默认配置
    await initialize_default_tiers(db)

    tiers = await get_all_tiers(db)
    data = [
        {
            "tier_level": t.tier_level,
            "tier_name": t.tier_name,
            "min_invites": t.min_invites,
            "max_invites": t.max_invites,
            "reward_multiplier": float(t.reward_multiplier),
            "bonus_points": t.bonus_points,
            "description": t.description,
        }
        for t in tiers
    ]

    return {
        "success": True,
        "data": data,
    }


@router.get("/my-stats")
async def get_my_referral_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我的邀请统计（含阶梯信息）"""
    stats = await get_user_referral_stats(db, str(current_user.id))

    return {
        "success": True,
        "data": stats,
    }


@router.post("/invite/claim-tiered")
async def claim_invite_tiered(
    invite_code: str = Query(..., description="邀请码"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """使用邀请码（阶梯奖励版）

    升级版本：支持阶梯奖励倍数和多级关系追踪
    """
    # 先调用原有的邀请码领取逻辑（会发放基础奖励）
    try:
        result = await original_claim(db, str(current_user.id), invite_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 创建多级邀请关系
    inviter = result.get("inviter")
    if inviter:
        await create_referral_relationship(
            db,
            inviter_id=str(inviter.id),
            invitee_id=str(current_user.id),
            invite_code_used=invite_code,
        )

        # 重新计算阶梯奖励（在基础奖励基础上应用倍数）
        # 注意：original_claim 已经发放了 200 积分给邀请人
        # 这里计算差额并补发
        from app.services.tiered_referral_service import get_user_current_tier
        tier, invite_count = await get_user_current_tier(db, str(inviter.id))
        if tier and tier.reward_multiplier > 1:
            base_reward = 200
            multiplier = float(tier.reward_multiplier)
            extra = int(base_reward * (multiplier - 1))
            if extra > 0:
                from app.services.points_service import award_points
                await award_points(
                    db,
                    str(inviter.id),
                    "invite_friend",
                    source_id=f"tier_bonus_{current_user.id}",
                    extra_description=f"阶梯奖励加成（{tier.tier_name}，x{multiplier}）",
                    multiplier=extra,
                )

    return {
        "success": True,
        "data": {
            "reward": result.get("reward", 0),
            "message": result.get("message", ""),
        },
        "message": "邀请码使用成功，奖励已发放",
    }


# ==================== 积分购买 ====================

@router.get("/points/packages")
async def get_point_packages(
    db: AsyncSession = Depends(get_db),
):
    """获取积分套餐列表"""
    await initialize_default_packages(db)

    packages = await get_all_packages(db)
    data = [
        {
            "id": str(p.id),
            "package_code": p.package_code,
            "package_name": p.package_name,
            "points_amount": p.points_amount,
            "bonus_points": p.bonus_points,
            "total_points": p.points_amount + p.bonus_points,
            "price_cny": float(p.price_cny),
            "original_price": float(p.original_price) if p.original_price else None,
            "is_popular": p.is_popular,
            "description": p.description,
            "discount_pct": round((1 - float(p.price_cny) / float(p.original_price)) * 100, 0) if p.original_price else None,
        }
        for p in packages
    ]

    return {
        "success": True,
        "data": data,
    }


@router.post("/points/buy")
async def buy_points(
    package_code: str = Query(..., description="套餐编码"),
    payment_method: str = Query(
        "xunhu",
        description="支付方式: xunhu/wechat/alipay(国内虎皮椒 CNY) / creem(国际信用卡 USD) / mock(测试)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """购买积分（创建订单 + 发起支付）

    支付流程:
    - xunhu: 创建虎皮椒支付订单，返回支付链接/二维码，用户支付后回调自动发放积分
    - mock: 测试用，立即模拟支付成功

    前端流程:
    1. 调用本接口获取 pay_url 或 qrcode_url
    2. 手机端跳转 pay_url，PC端展示 qrcode_url 二维码
    3. 轮询 /api/v1/payment/status/{order_no} 检查支付状态
    4. 支付成功后积分自动到账
    """
    # 初始化套餐（首次调用时）
    await initialize_default_packages(db)

    # 确保积分发放规则已 seed（含 point_purchase），否则付款后积分不到账（资损）
    try:
        from app.services.points_service import ensure_rules_seeded
        await ensure_rules_seeded(db)
    except Exception as seed_err:
        logger.warning(f"积分规则自检失败（不阻断下单）: {seed_err}")

    # 创建订单
    order = await create_point_order(db, str(current_user.id), package_code, payment_method)
    if not order:
        raise HTTPException(status_code=404, detail="套餐不存在")

    # Mock 支付：立即模拟支付成功
    if payment_method == "mock":
        order = await process_payment_mock(db, str(order.id), str(current_user.id))
        if not order:
            raise HTTPException(status_code=500, detail="支付处理失败")

        return {
            "success": True,
            "data": {
                "order_id": str(order.id),
                "order_no": order.order_no,
                "package_code": order.package_code,
                "points_amount": order.points_amount,
                "bonus_points": order.bonus_points,
                "total_points": order.total_points,
                "price_cny": float(order.price_cny),
                "payment_status": order.payment_status,
                "payment_method": order.payment_method,
                "points_credited": order.points_credited,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            },
            "message": "购买成功，积分已到账",
        }

    # 虎皮椒支付：创建真实支付订单
    if payment_method in ("xunhu", "wechat", "alipay"):
        from app.services.xunhu_pay_service import create_payment

        # 构建支付参数
        title = f"HealthLens积分套餐-{order.package_code}（{order.total_points}积分）"
        attach = f"user_id={current_user.id},order_id={order.id}"

        pay_result = await create_payment(
            order_no=order.order_no,
            total_fee=order.price_cny,
            title=title,
            attach=attach,
        )

        if not pay_result["success"]:
            # 支付创建失败，更新订单状态
            order.payment_status = "failed"
            await db.commit()

            return {
                "success": False,
                "data": {
                    "order_id": str(order.id),
                    "order_no": order.order_no,
                    "payment_status": "failed",
                    "error": pay_result.get("errmsg", "支付创建失败"),
                    "errcode": pay_result.get("errcode", -1),
                },
                "message": f"支付创建失败: {pay_result.get('errmsg', '未知错误')}",
            }

        # 保存虎皮椒内部订单号
        order.transaction_id = str(pay_result.get("open_order_id", ""))
        await db.commit()

        return {
            "success": True,
            "data": {
                "order_id": str(order.id),
                "order_no": order.order_no,
                "package_code": order.package_code,
                "points_amount": order.points_amount,
                "bonus_points": order.bonus_points,
                "total_points": order.total_points,
                "price_cny": float(order.price_cny),
                "payment_status": order.payment_status,
                "payment_method": payment_method,
                "points_credited": order.points_credited,
                # 支付关键信息
                "pay_url": pay_result.get("pay_url", ""),
                "qrcode_url": pay_result.get("qrcode_url", ""),
                "open_order_id": pay_result.get("open_order_id", ""),
                # 前端轮询用
                "status_check_url": f"/api/v1/payment/status/{order.order_no}",
                "created_at": order.created_at.isoformat() if order.created_at else None,
            },
            "message": "订单已创建，请扫码或跳转支付",
        }

    # 国际信用卡支付（Creem，HealthLens 专属店铺，与其他业务店铺完全隔离）
    if payment_method in ("creem", "card", "international"):
        from app.services.creem_pay_service import (
            CreemNotConfigured,
            CreemStoreMismatch,
            create_checkout,
        )

        try:
            pay_result = await create_checkout(
                order_no=order.order_no,
                package_code=order.package_code,
                user_id=str(current_user.id),
                email=(getattr(current_user, "email", "") or ""),
            )
        except CreemStoreMismatch as exc:
            order.payment_status = "failed"
            await db.commit()
            logger.error(f"[Creem] 店铺隔离校验失败: {exc}")
            raise HTTPException(status_code=503, detail="国际支付配置异常，请联系客服")
        except CreemNotConfigured as exc:
            order.payment_status = "failed"
            await db.commit()
            raise HTTPException(
                status_code=503,
                detail=f"国际信用卡支付尚未开通：{exc}。国内用户可使用微信/支付宝。",
            )

        if not pay_result["success"]:
            order.payment_status = "failed"
            await db.commit()
            return {
                "success": False,
                "data": {
                    "order_id": str(order.id),
                    "order_no": order.order_no,
                    "payment_status": "failed",
                    "error": pay_result.get("error", "支付创建失败"),
                },
                "message": f"支付创建失败: {pay_result.get('error', '未知错误')}",
            }

        order.transaction_id = pay_result.get("checkout_id", "")
        await db.commit()

        return {
            "success": True,
            "data": {
                "order_id": str(order.id),
                "order_no": order.order_no,
                "package_code": order.package_code,
                "points_amount": order.points_amount,
                "bonus_points": order.bonus_points,
                "total_points": order.total_points,
                "price_cny": float(order.price_cny),
                "payment_status": order.payment_status,
                "payment_method": "creem",
                "points_credited": order.points_credited,
                # Creem 结账页（USD 计价，实际金额以 Creem 产品配置为准）
                "pay_url": pay_result["checkout_url"],
                "checkout_url": pay_result["checkout_url"],
                "checkout_id": pay_result.get("checkout_id", ""),
                "currency": "USD",
                "status_check_url": f"/api/v1/payment/status/{order.order_no}",
                "created_at": order.created_at.isoformat() if order.created_at else None,
            },
            "message": "订单已创建，请在新窗口完成信用卡支付",
        }

    raise HTTPException(status_code=400, detail=f"不支持的支付方式: {payment_method}")


@router.get("/points/orders")
async def get_my_point_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我的积分购买订单"""
    orders, total = await get_user_orders(
        db, str(current_user.id), page, page_size
    )

    data = [
        {
            "order_id": str(o.id),
            "order_no": o.order_no,
            "package_code": o.package_code,
            "total_points": o.total_points,
            "price_cny": float(o.price_cny),
            "payment_status": o.payment_status,
            "payment_method": o.payment_method,
            "points_credited": o.points_credited,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        }
        for o in orders
    ]

    return {
        "success": True,
        "data": {
            "items": data,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/admin/init-tiered-system")
async def init_tiered_system(
    db: AsyncSession = Depends(get_db),
):
    """初始化阶梯邀请和积分购买系统（首次部署使用）"""
    tiers_count = await initialize_default_tiers(db)
    packages_count = await initialize_default_packages(db)

    return {
        "success": True,
        "data": {
            "tiers_initialized": tiers_count,
            "packages_initialized": packages_count,
        },
        "message": f"初始化完成：{tiers_count}个阶梯配置，{packages_count}个积分套餐",
    }

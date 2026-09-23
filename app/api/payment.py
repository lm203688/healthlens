"""支付 API

- 国内：虎皮椒（微信 / 支付宝，CNY）—— /notify, /status/{order_no}
- 国际：Creem（信用卡，USD）—— /creem/webhook, /creem/setup-status
  Creem 使用 HealthLens **专属店铺**，与其他业务店铺完全隔离。
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from loguru import logger
from app.database import get_db
from app.models.user import User
from app.models.tiered_referral import PointOrder
from app.api.deps import get_current_user
from app.services.xunhu_pay_service import (
    create_payment,
    query_order as xunhu_query,
    verify_callback,
    parse_callback,
)
from app.services.tiered_referral_service import (
    process_payment_mock,
    get_user_orders,
)
from decimal import Decimal
from datetime import timezone

router = APIRouter(tags=["支付"])


@router.post("/notify")
async def payment_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """虎皮椒支付回调通知

    虎皮椒在用户支付成功后会向 notify_url 发送 POST 请求（form 表单）。
    服务器需返回 "success" 表示已收到，否则会重试6次。

    回调参数:
        trade_order_id: 商户订单号
        total_fee: 支付金额
        transaction_id: 交易号
        open_order_id: 虎皮椒内部订单号
        status: OD(已支付), CD(已退款), RD(退款中), UD(退款失败)
        hash: 签名
    """
    # 获取 form 表单数据
    form_data = await request.form()
    params = {k: v for k, v in form_data.items()}

    logger.info(f"[PaymentNotify] Received callback: {params}")

    # 验证签名
    if not verify_callback(params):
        logger.error(f"[PaymentNotify] Signature verification failed: {params}")
        return PlainTextResponse(content="fail", status_code=200)

    # 解析回调数据
    callback = parse_callback(params)
    order_no = callback["trade_order_id"]
    status_code = callback["status"]
    transaction_id = callback["transaction_id"]
    open_order_id = callback["open_order_id"]

    # 查找订单
    result = await db.execute(
        select(PointOrder).where(PointOrder.order_no == order_no)
    )
    order = result.scalar_one_or_none()

    if not order:
        logger.error(f"[PaymentNotify] Order not found: {order_no}")
        return PlainTextResponse(content="fail", status_code=200)

    # 已处理过的订单直接返回 success（防止重复处理）
    if order.payment_status == "paid" and order.points_credited:
        logger.info(f"[PaymentNotify] Order already processed: {order_no}")
        return PlainTextResponse(content="success", status_code=200)

    # 处理支付成功 (status = OD)
    if status_code == "OD":
        logger.info(f"[PaymentNotify] Payment success: order={order_no}, tx={transaction_id}")

        # 更新订单状态
        order.payment_status = "paid"
        order.paid_at = datetime.utcnow()
        order.transaction_id = transaction_id or open_order_id

        # 发放积分（失败必须 fail-loud：返回 fail 让虎皮椒重试，绝不静默成功）
        from app.services.points_service import award_points, ensure_user_points_account
        await ensure_user_points_account(db, str(order.user_id))

        award_result = await award_points(
            db,
            str(order.user_id),
            "point_purchase",
            source_id=str(order.id),
            extra_description=f"购买{order.package_code}套餐：{order.points_amount}积分 + {order.bonus_points}赠送积分",
            multiplier=Decimal(order.total_points),
        )

        if not award_result.get("success"):
            logger.error(
                f"[PaymentNotify] 积分发放失败: order={order_no}, "
                f"user={order.user_id}, reason={award_result.get('message')}"
            )
            await db.commit()  # 已置 paid，但未到账；返回 fail 触发虎皮椒重试
            return PlainTextResponse(content="fail", status_code=200)

        # 获取交易记录 ID
        from app.models.points import PointTransaction
        tx_result = await db.execute(
            select(PointTransaction).where(
                PointTransaction.user_id == str(order.user_id),
                PointTransaction.source == "point_purchase",
                PointTransaction.source_id == str(order.id),
            ).order_by(desc(PointTransaction.created_at)).limit(1)
        )
        tx = tx_result.scalar_one_or_none()

        order.points_credited = True
        order.credited_at = datetime.utcnow()
        order.credited_tx_id = tx.id if tx else None

        await db.commit()

        logger.info(
            f"[PaymentNotify] Points credited: order={order_no}, "
            f"user={order.user_id}, points={order.total_points}"
        )

        return PlainTextResponse(content="success", status_code=200)

    # 处理退款
    elif status_code in ("CD", "RD", "UD"):
        logger.info(f"[PaymentNotify] Refund status {status_code}: order={order_no}")
        order.payment_status = "refunded" if status_code == "CD" else "refund_pending"
        await db.commit()
        return PlainTextResponse(content="success", status_code=200)

    # 其他状态
    logger.warning(f"[PaymentNotify] Unknown status {status_code}: order={order_no}")
    return PlainTextResponse(content="success", status_code=200)


@router.get("/status/{order_no}")
async def check_payment_status(
    order_no: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询订单支付状态

    先查本地数据库，如果未支付则主动查询虎皮椒
    """
    # 查本地订单
    result = await db.execute(
        select(PointOrder).where(
            PointOrder.order_no == order_no,
            PointOrder.user_id == str(current_user.id),
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 如果本地已经是 paid 状态，直接返回
    if order.payment_status == "paid":
        return {
            "success": True,
            "data": {
                "order_no": order.order_no,
                "payment_status": order.payment_status,
                "points_credited": order.points_credited,
                "total_points": order.total_points,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            },
        }

    # 如果是 mock 支付，直接处理
    if order.payment_method == "mock" and order.payment_status == "pending":
        order = await process_payment_mock(db, str(order.id), str(current_user.id))
        if order:
            return {
                "success": True,
                "data": {
                    "order_no": order.order_no,
                    "payment_status": order.payment_status,
                    "points_credited": order.points_credited,
                    "total_points": order.total_points,
                    "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                },
            }

    # 主动查询虎皮椒
    if order.payment_method in ("wechat", "alipay", "xunhu"):
        query_result = await xunhu_query(order_no)

        if query_result["success"] and query_result["status"] == "OD":
            # 虎皮椒确认已支付，但本地未更新 -> 补发积分
            if order.payment_status != "paid":
                order.payment_status = "paid"
                order.paid_at = datetime.utcnow()
                order.transaction_id = query_result["data"].get("transaction_id", "")

                from app.services.points_service import award_points, ensure_user_points_account
                await ensure_user_points_account(db, str(order.user_id))

                award_result = await award_points(
                    db,
                    str(order.user_id),
                    "point_purchase",
                    source_id=str(order.id),
                    extra_description=f"购买{order.package_code}套餐（补发）",
                    multiplier=Decimal(order.total_points),
                )

                if not award_result.get("success"):
                    logger.error(
                        f"[PaymentQuery] 积分补发失败: order={order_no}, "
                        f"user={order.user_id}, reason={award_result.get('message')}"
                    )
                    await db.commit()
                    return {
                        "success": False,
                        "data": {
                            "order_no": order_no,
                            "points_credited": order.points_credited,
                            "error": award_result.get("message"),
                        },
                        "message": "支付已确认但积分发放失败，请联系客服补发",
                    }

                from app.models.points import PointTransaction
                tx_result = await db.execute(
                    select(PointTransaction).where(
                        PointTransaction.user_id == str(order.user_id),
                        PointTransaction.source == "point_purchase",
                        PointTransaction.source_id == str(order.id),
                    ).order_by(desc(PointTransaction.created_at)).limit(1)
                )
                tx = tx_result.scalar_one_or_none()

                order.points_credited = True
                order.credited_at = datetime.utcnow()
                order.credited_tx_id = tx.id if tx else None
                await db.commit()

                logger.info(f"[PaymentQuery] Points credited via query: order={order_no}")

            return {
                "success": True,
                "data": {
                    "order_no": order.order_no,
                    "payment_status": "paid",
                    "points_credited": order.points_credited,
                    "total_points": order.total_points,
                    "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                    "xunhu_status": query_result["status"],
                },
            }

        return {
            "success": True,
            "data": {
                "order_no": order.order_no,
                "payment_status": order.payment_status,
                "points_credited": order.points_credited,
                "total_points": order.total_points,
                "xunhu_status": query_result.get("status", "UNKNOWN"),
            },
        }

    # 主动查询 Creem（国际信用卡，回调丢失时的补偿路径）
    if order.payment_method in ("creem", "card", "international") and order.transaction_id:
        try:
            from app.services.creem_pay_service import query_checkout

            q = await query_checkout(order.transaction_id)
            if q.get("success") and q.get("paid") and order.payment_status != "paid":
                await _credit_order(db, order, order.transaction_id)
                logger.info(f"[PaymentQuery] Creem 补发积分成功: order={order_no}")
        except Exception as exc:  # 查询失败不影响状态返回
            logger.warning(f"[PaymentQuery] Creem 查询失败 order={order_no}: {exc}")

        return {
            "success": True,
            "data": {
                "order_no": order.order_no,
                "payment_status": order.payment_status,
                "points_credited": order.points_credited,
                "total_points": order.total_points,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            },
        }

    return {
        "success": True,
        "data": {
            "order_no": order.order_no,
            "payment_status": order.payment_status,
            "points_credited": order.points_credited,
            "total_points": order.total_points,
        },
    }


# ===========================================================================
# Creem 国际支付（HealthLens 专属店铺，禁止与其他店铺混用）
# ===========================================================================

async def _credit_order(db: AsyncSession, order: PointOrder, transaction_id: str = "") -> bool:
    """
    幂等发放订单积分。

    Returns:
        True 表示本次发放，False 表示此前已发放过（重复回调）
    """
    if order.payment_status == "paid" and order.points_credited:
        return False

    order.payment_status = "paid"
    order.paid_at = datetime.utcnow()
    if transaction_id:
        order.transaction_id = transaction_id

    from app.services.points_service import award_points, ensure_user_points_account
    await ensure_user_points_account(db, str(order.user_id))

    award_result = await award_points(
        db,
        str(order.user_id),
        "point_purchase",
        source_id=str(order.id),
        extra_description=(
            f"购买{order.package_code}套餐：{order.points_amount}积分 + {order.bonus_points}赠送积分"
        ),
        multiplier=Decimal(order.total_points),
    )

    if not award_result.get("success"):
        # 发分失败：fail-loud，不标记到账，抛出异常让回调方感知并告警
        logger.error(
            f"[CreditOrder] 积分发放失败: order_no={order.order_no}, "
            f"user={order.user_id}, reason={award_result.get('message')}"
        )
        await db.commit()
        raise RuntimeError(f"积分发放失败: {award_result.get('message')}")

    from app.models.points import PointTransaction
    tx_result = await db.execute(
        select(PointTransaction).where(
            PointTransaction.user_id == str(order.user_id),
            PointTransaction.source == "point_purchase",
            PointTransaction.source_id == str(order.id),
        ).order_by(desc(PointTransaction.created_at)).limit(1)
    )
    tx = tx_result.scalar_one_or_none()

    order.points_credited = True
    order.credited_at = datetime.utcnow()
    order.credited_tx_id = tx.id if tx else None

    await db.commit()
    return True


@router.post("/creem/webhook")
async def creem_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Creem 支付回调。

    安全链条（任一环失败即拒绝）：
    1. HMAC-SHA256 验签（使用本店铺的 CREEM_WEBHOOK_SECRET）
    2. 店铺隔离校验（store_id 必须等于 CREEM_STORE_ID）
    3. 订单归属校验 + 幂等发放
    """
    from app.services.creem_pay_service import (
        CreemStoreMismatch,
        parse_webhook,
        verify_webhook_signature,
    )

    raw = await request.body()
    signature = (
        request.headers.get("creem-signature")
        or request.headers.get("x-creem-signature")
        or ""
    )

    if not verify_webhook_signature(raw, signature):
        logger.error("[CreemWebhook] 签名校验失败，已拒绝")
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.error("[CreemWebhook] 请求体不是合法 JSON")
        raise HTTPException(status_code=400, detail="invalid payload")

    try:
        evt = parse_webhook(payload)
    except CreemStoreMismatch as exc:
        # 其他店铺的事件打进来了——绝不发积分
        logger.error(f"[CreemWebhook] 店铺隔离拒绝: {exc}")
        raise HTTPException(status_code=403, detail="store mismatch")

    logger.info(
        f"[CreemWebhook] event={evt['event_type']} order={evt['order_no']} paid={evt['paid']}"
    )

    if not evt["paid"]:
        return JSONResponse({"received": True, "ignored": evt["event_type"]})

    order_no = evt["order_no"]
    if not order_no:
        logger.error("[CreemWebhook] 回调缺少 order_no/request_id，无法定位订单")
        return JSONResponse({"received": True, "error": "missing order_no"})

    result = await db.execute(select(PointOrder).where(PointOrder.order_no == order_no))
    order = result.scalar_one_or_none()

    if not order:
        logger.error(f"[CreemWebhook] 订单不存在: {order_no}")
        return JSONResponse({"received": True, "error": "order not found"})

    # 订单归属二次校验（metadata 中的 user_id 必须与订单一致）
    meta_uid = str(evt.get("user_id") or "")
    if meta_uid and meta_uid != str(order.user_id):
        logger.error(
            f"[CreemWebhook] 用户不匹配 order={order_no} "
            f"meta_uid={meta_uid} order_uid={order.user_id}"
        )
        raise HTTPException(status_code=403, detail="user mismatch")

    credited = await _credit_order(db, order, evt.get("checkout_id", ""))
    if credited:
        logger.info(
            f"[CreemWebhook] 积分已发放 order={order_no} user={order.user_id} "
            f"points={order.total_points} amount={evt['amount']} {evt['currency']}"
        )
    else:
        logger.info(f"[CreemWebhook] 订单已处理过，幂等返回 order={order_no}")

    return JSONResponse({"received": True, "credited": credited})


@router.get("/creem/setup-status")
async def creem_setup_status():
    """Creem 配置自检（不返回密钥内容），用于部署后确认接线是否完整"""
    from app.services.creem_pay_service import setup_status
    return setup_status()


# ===========================================================================
# 套餐查询与创建订单（前端升级页面调用）
# ===========================================================================

@router.get("/packages")
async def list_packages(
    db: AsyncSession = Depends(get_db),
):
    """获取所有可用积分套餐"""
    from app.services.tiered_referral_service import get_all_packages

    packages = await get_all_packages(db)
    data = [
        {
            "code": p.package_code,
            "name": p.package_name,
            "points": p.points_amount,
            "bonus": p.bonus_points,
            "price_cny": float(p.price_cny),
            "original_price": float(p.original_price) if p.original_price else None,
            "is_popular": p.is_popular,
            "description": p.description,
        }
        for p in packages
    ]
    return {"success": True, "data": data}


@router.post("/create")
async def create_order(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建支付订单并返回支付链接

    body: { "package_code": "basic", "currency": "CNY" }
    """
    from uuid import uuid4
    import time
    from app.services.tiered_referral_service import get_package_by_code, create_point_order
    from app.services.xunhu_pay_service import create_payment as xunhu_create

    package_code = body.get("package_code", "basic")
    currency = body.get("currency", "CNY")

    pkg = await get_package_by_code(db, package_code)
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")

    order_no = f"HL{int(time.time())}{uuid4().hex[:8]}"

    # 创建本地订单
    order = await create_point_order(
        db,
        user_id=str(current_user.id),
        package_code=package_code,
        payment_method="xunhu" if currency == "CNY" else "creem",
    )

    if currency == "CNY":
        # 虎皮椒支付
        title = f"HealthLens {pkg.package_name}"
        result = await xunhu_create(
            order_no=order_no,
            total_fee=Decimal(pkg.price_cny),
            title=title,
            attach=str(order.id),
        )
        if result.get("success") and result.get("pay_url"):
            return {
                "success": True,
                "data": {
                    "order_no": order_no,
                    "checkout_url": result["pay_url"],
                    "package_code": package_code,
                },
            }
        return {
            "success": False,
            "data": {"order_no": order_no},
            "message": result.get("errmsg", "支付创建失败"),
        }
    else:
        # Creem 国际支付
        from app.services.creem_pay_service import create_checkout
        result = await create_checkout(
            order_no=order_no,
            amount=float(pkg.price_cny) * 7.2,  # 粗略汇率
            currency="USD",
            description=f"HealthLens {pkg.package_name}",
            user_id=str(current_user.id),
        )
        if result.get("success") and result.get("checkout_url"):
            return {
                "success": True,
                "data": {
                    "order_no": order_no,
                    "checkout_url": result["checkout_url"],
                    "package_code": package_code,
                },
            }
        return {
            "success": False,
            "data": {"order_no": order_no},
            "message": result.get("error", "支付创建失败"),
        }



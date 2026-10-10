"""
Creem 国际支付服务（信用卡 / Merchant of Record）

=========================== 店铺隔离原则 ===========================
本服务**必须**使用 HealthLens 专属的 Creem 店铺（store），
不得与任何其他业务的店铺混用。原因：

1. Creem 的 API Key 是**店铺级**凭证，混用会导致其他业务的订单/退款
   出现在 HealthLens 的对账里，财务无法拆分。
2. Webhook Secret 也是店铺级的，混用时其他店铺的事件会打到本服务，
   可能造成**错误发放积分**。
3. 产品(product)命名与定价互相污染，退款与客诉难以归属。

因此代码层面做了硬校验：所有 checkout 与 webhook 都会比对
`settings.CREEM_STORE_ID`，来源店铺不符一律拒绝（见 assert_store）。
====================================================================
"""
import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import httpx
from loguru import logger

from app.config import settings

_TIMEOUT = 30.0

# 套餐 -> 积分（与后端 PointPackage 的 starter/basic/pro/ultimate 对齐）
CREEM_PACKAGE_POINTS: dict[str, int] = {
    "starter": 100,
    "basic": 600,
    "pro": 2500,
    "ultimate": 6600,
}


class CreemNotConfigured(RuntimeError):
    """Creem 未启用或未配置完整"""


class CreemStoreMismatch(RuntimeError):
    """检测到非本店铺的数据——防止与其他店铺混用"""


# ---------------------------------------------------------------------------
# 配置与校验
# ---------------------------------------------------------------------------

def get_product_id(package_code: str) -> str:
    """取套餐对应的 Creem 产品 ID（在 HealthLens 专属店铺内创建）"""
    mapping = {
        "starter": settings.CREEM_PRODUCT_STARTER,
        "basic": settings.CREEM_PRODUCT_BASIC,
        "pro": settings.CREEM_PRODUCT_PRO,
        "ultimate": settings.CREEM_PRODUCT_ULTIMATE,
    }
    return mapping.get(package_code, "")


def ensure_configured() -> None:
    """下单前的前置校验：未配置就明确报错，绝不静默降级"""
    if not settings.CREEM_ENABLED:
        raise CreemNotConfigured("Creem 国际支付未启用（CREEM_ENABLED=false）")
    if not settings.CREEM_API_KEY:
        raise CreemNotConfigured("缺少 CREEM_API_KEY")
    if not settings.CREEM_STORE_ID:
        raise CreemNotConfigured(
            "缺少 CREEM_STORE_ID：必须显式指定 HealthLens 专属店铺，禁止与其他店铺混用"
        )


def assert_store(store_id: Any, context: str) -> None:
    """
    店铺隔离硬校验。

    只要返回数据里带了 store_id 且与配置不一致，立刻拒绝——
    这是防止「与其他店混在一起」导致错误发积分的最后一道闸。
    """
    if not store_id:
        return  # 部分接口不返回 store_id，跳过
    if str(store_id) != str(settings.CREEM_STORE_ID):
        logger.error(
            f"[Creem] 店铺不匹配 | context={context} | "
            f"got={store_id} | expected={settings.CREEM_STORE_ID}"
        )
        raise CreemStoreMismatch(
            f"来源店铺 {store_id} 与 HealthLens 专属店铺不符，已拒绝处理"
        )


def _headers() -> dict:
    return {
        "x-api-key": settings.CREEM_API_KEY,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# 创建 Checkout
# ---------------------------------------------------------------------------

async def create_checkout(
    order_no: str,
    package_code: str,
    user_id: str,
    email: str = "",
    success_url: str = "",
) -> dict:
    """
    在 HealthLens 专属店铺创建 Creem Checkout。

    Returns:
        {success, checkout_url, checkout_id, raw} 或 {success: False, error}
    """
    ensure_configured()

    product_id = get_product_id(package_code)
    if not product_id:
        return {
            "success": False,
            "error": f"套餐 {package_code} 未配置 Creem 产品 ID（请在专属店铺内创建产品并填入 .env）",
        }

    payload = {
        "product_id": product_id,
        "request_id": order_no,  # 幂等键，回调原样带回
        "metadata": {
            "order_no": order_no,
            "package_code": package_code,
            "user_id": str(user_id),
            "app": "healthlens",
            "store_id": settings.CREEM_STORE_ID,
        },
    }
    if email:
        payload["customer"] = {"email": email}
    if success_url or settings.PUBLIC_BASE_URL:
        payload["success_url"] = (
            success_url or f"{settings.PUBLIC_BASE_URL.rstrip('/')}/buy-points?status=success"
        )

    url = f"{settings.creem_api_base}/checkouts"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=_headers(), json=payload)
            if resp.status_code >= 400:
                logger.error(f"[Creem] 创建 checkout 失败 | {resp.status_code} | {resp.text[:400]}")
                return {
                    "success": False,
                    "error": f"Creem 返回 {resp.status_code}: {resp.text[:200]}",
                }
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.error(f"[Creem] 网络错误 | {exc}")
        return {"success": False, "error": f"Creem 网络错误: {exc}"}

    # 店铺隔离校验
    assert_store(data.get("store_id"), "create_checkout")

    checkout_url = data.get("checkout_url") or data.get("url") or ""
    if not checkout_url:
        logger.error(f"[Creem] 响应缺少 checkout_url | {json.dumps(data)[:300]}")
        return {"success": False, "error": "Creem 响应缺少 checkout_url"}

    logger.info(
        f"[Creem] Checkout 已创建 | order={order_no} | package={package_code} "
        f"| store={settings.CREEM_STORE_ID}"
    )
    return {
        "success": True,
        "checkout_url": checkout_url,
        "checkout_id": data.get("id", ""),
        "raw": data,
    }


# ---------------------------------------------------------------------------
# Webhook 验签与解析
# ---------------------------------------------------------------------------

def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """
    校验 Creem webhook 签名（HMAC-SHA256，密钥为**本店铺**的 webhook secret）。
    """
    secret = settings.CREEM_WEBHOOK_SECRET
    if not secret:
        logger.error("[Creem] 未配置 CREEM_WEBHOOK_SECRET，拒绝所有 webhook")
        return False
    if not signature:
        return False

    computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    # 兼容 "sha256=xxx" 前缀
    provided = signature.split("=", 1)[-1].strip() if "=" in signature else signature.strip()
    return hmac.compare_digest(computed, provided)


def parse_webhook(payload: dict) -> dict:
    """
    解析 Creem webhook 事件，抽取发放积分所需信息。

    Returns:
        {event_type, order_no, package_code, user_id, checkout_id, paid, amount, currency}
    """
    event_type = payload.get("eventType") or payload.get("type") or ""
    obj = payload.get("object") or payload.get("data") or {}

    # 店铺隔离校验（webhook 层，防止其他店铺事件打进来）
    assert_store(obj.get("store_id") or payload.get("store_id"), f"webhook:{event_type}")

    metadata = obj.get("metadata") or {}
    order_no = (
        metadata.get("order_no")
        or obj.get("request_id")
        or payload.get("request_id")
        or ""
    )

    order = obj.get("order") or {}
    amount = order.get("amount") or obj.get("amount") or 0
    currency = order.get("currency") or obj.get("currency") or "USD"

    paid_events = {"checkout.completed", "subscription.paid", "payment.succeeded"}
    status_ok = str(obj.get("status", "")).lower() in {"completed", "paid", "succeeded"}

    return {
        "event_type": event_type,
        "order_no": order_no,
        "package_code": metadata.get("package_code", ""),
        "user_id": metadata.get("user_id", ""),
        "checkout_id": obj.get("id", ""),
        "paid": event_type in paid_events or status_ok,
        # Creem 金额单位为「分」
        "amount": Decimal(str(amount)) / Decimal("100") if amount else Decimal("0"),
        "currency": currency,
    }


# ---------------------------------------------------------------------------
# 主动查询（对账用）
# ---------------------------------------------------------------------------

async def query_checkout(checkout_id: str) -> dict:
    """按 checkout_id 主动查询状态（用于回调丢失时补偿）"""
    ensure_configured()
    url = f"{settings.creem_api_base}/checkouts/{checkout_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers())
            if resp.status_code >= 400:
                return {"success": False, "error": f"{resp.status_code}: {resp.text[:200]}"}
            data = resp.json()
    except httpx.HTTPError as exc:
        return {"success": False, "error": str(exc)}

    assert_store(data.get("store_id"), "query_checkout")
    return {
        "success": True,
        "status": data.get("status", ""),
        "paid": str(data.get("status", "")).lower() in {"completed", "paid"},
        "raw": data,
    }


# ---------------------------------------------------------------------------
# 自检（供 /creem/setup-status 使用）
# ---------------------------------------------------------------------------

def setup_status() -> dict:
    """返回配置完整度，便于运维排查（不泄露密钥内容）"""
    products = {
        "starter": bool(settings.CREEM_PRODUCT_STARTER),
        "basic": bool(settings.CREEM_PRODUCT_BASIC),
        "pro": bool(settings.CREEM_PRODUCT_PRO),
        "ultimate": bool(settings.CREEM_PRODUCT_ULTIMATE),
    }
    missing = []
    if not settings.CREEM_API_KEY:
        missing.append("CREEM_API_KEY")
    if not settings.CREEM_STORE_ID:
        missing.append("CREEM_STORE_ID")
    if not settings.CREEM_WEBHOOK_SECRET:
        missing.append("CREEM_WEBHOOK_SECRET")
    missing += [f"CREEM_PRODUCT_{k.upper()}" for k, v in products.items() if not v]

    return {
        "enabled": settings.CREEM_ENABLED,
        "ready": settings.creem_ready,
        "test_mode": settings.CREEM_TEST_MODE,
        "api_base": settings.creem_api_base,
        "store_id": settings.CREEM_STORE_ID or None,
        "store_isolation": "enforced",
        "products_configured": products,
        "missing": missing,
    }

"""虎皮椒支付服务
对接虎皮椒 V3 个人支付接口，支持微信/支付宝收款
文档: https://www.xunhupay.com/doc/api/pay.html
"""
import hashlib
import time
import secrets
import httpx
from decimal import Decimal
from typing import Any
from loguru import logger
from app.config import settings


# 虎皮椒配置（从环境变量读取，不硬编码凭证）
XUNHU_APPID = getattr(settings, "XUNHU_APPID", "") or ""
XUNHU_SECRET = getattr(settings, "XUNHU_SECRET", "") or ""
XUNHU_GATEWAY = getattr(settings, "XUNHU_GATEWAY", "") or "https://api.xunhupay.com"
XUNHU_NOTIFY_URL = getattr(settings, "XUNHU_NOTIFY_URL", "") or "https://healthlens.cc/api/v1/payment/notify"
XUNHU_RETURN_URL = getattr(settings, "XUNHU_RETURN_URL", "") or "https://healthlens.cc/buy-points?status=success"


def _generate_hash(params: dict[str, Any], secret: str) -> str:
    """生成虎皮椒签名

    算法:
    1. 过滤空值和 hash 字段
    2. 按参数名 ASCII 字典序排序
    3. 拼接 key=value&key=value
    4. 末尾直接拼接 secret（无连接符）
    5. MD5 取 32 位小写
    """
    # 过滤
    filtered = {}
    for k, v in params.items():
        if k == "hash" or v is None or v == "":
            continue
        filtered[k] = str(v)

    # 排序
    sorted_keys = sorted(filtered.keys())

    # 拼接
    parts = [f"{k}={filtered[k]}" for k in sorted_keys]
    string_a = "&".join(parts)

    # 拼接 secret
    string_sign_temp = string_a + secret

    # MD5
    return hashlib.md5(string_sign_temp.encode("utf-8")).hexdigest()


def _verify_hash(params: dict[str, Any], secret: str) -> bool:
    """验证虎皮椒回调签名"""
    received_hash = params.get("hash", "")
    if not received_hash:
        return False
    calculated = _generate_hash(params, secret)
    return calculated.lower() == received_hash.lower()


async def create_payment(
    order_no: str,
    total_fee: Decimal,
    title: str,
    attach: str = "",
    return_url: str = "",
    notify_url: str = "",
) -> dict[str, Any]:
    """创建虎皮椒支付订单

    Args:
        order_no: 商户订单号（唯一）
        total_fee: 订单金额（元）
        title: 订单标题
        attach: 备注信息（回调原样返回）
        return_url: 支付成功跳转地址
        notify_url: 支付回调通知地址

    Returns:
        {
            "success": bool,
            "pay_url": str,        # 手机端支付链接
            "qrcode_url": str,     # PC端二维码链接
            "open_order_id": str,  # 虎皮椒内部订单号
            "errcode": int,
            "errmsg": str,
        }
    """
    # 格式化金额：虎皮椒接受 "39.9" 或 "39.90"
    fee_str = f"{total_fee:.2f}"

    params: dict[str, Any] = {
        "version": "1.1",
        "appid": XUNHU_APPID,
        "trade_order_id": order_no,
        "total_fee": fee_str,
        "title": title,
        "time": str(int(time.time())),
        "notify_url": notify_url or XUNHU_NOTIFY_URL,
        "nonce_str": secrets.token_hex(16),
        "plugins": "HealthLens",
    }

    if return_url:
        params["return_url"] = return_url
    else:
        params["return_url"] = XUNHU_RETURN_URL

    if attach:
        params["attach"] = attach

    # 生成签名
    params["hash"] = _generate_hash(params, XUNHU_SECRET)

    gateway_url = f"{XUNHU_GATEWAY}/payment/do.html"

    logger.info(
        f"[XunHuPay] Creating payment: order={order_no}, fee={fee_str}, "
        f"title={title}, gateway={gateway_url}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(gateway_url, json=params)
            data = resp.json()

        errcode = data.get("errcode", -1)
        errmsg = data.get("errmsg", "")

        if errcode == 0:
            result = {
                "success": True,
                "pay_url": data.get("url", ""),
                "qrcode_url": data.get("url_qrcode", ""),
                "open_order_id": str(data.get("openid", "")),  # 注意: 返回字段名是 openid，值是 orderid（整数）
                "errcode": errcode,
                "errmsg": errmsg,
            }
            logger.info(
                f"[XunHuPay] Payment created: order={order_no}, "
                f"open_order_id={result['open_order_id']}"
            )
            return result
        else:
            logger.error(
                f"[XunHuPay] Payment failed: order={order_no}, "
                f"errcode={errcode}, errmsg={errmsg}"
            )
            return {
                "success": False,
                "pay_url": "",
                "qrcode_url": "",
                "open_order_id": "",
                "errcode": errcode,
                "errmsg": errmsg,
            }

    except Exception as e:
        logger.error(f"[XunHuPay] Request error: order={order_no}, error={e}")
        return {
            "success": False,
            "pay_url": "",
            "qrcode_url": "",
            "open_order_id": "",
            "errcode": -1,
            "errmsg": str(e),
        }


async def query_order(order_no: str) -> dict[str, Any]:
    """查询虎皮椒订单状态

    Returns:
        {
            "success": bool,
            "status": str,  # OD(已支付), WP(待支付), CD(已取消)
            "data": dict,   # 完整返回数据
        }
    """
    params: dict[str, Any] = {
        "appid": XUNHU_APPID,
        "out_trade_order": order_no,
        "time": str(int(time.time())),
        "nonce_str": secrets.token_hex(16),
    }

    params["hash"] = _generate_hash(params, XUNHU_SECRET)

    query_url = f"{XUNHU_GATEWAY}/payment/query.html"

    logger.info(f"[XunHuPay] Querying order: {order_no}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(query_url, json=params)
            data = resp.json()

        errcode = data.get("errcode", -1)
        if errcode == 0:
            order_data = data.get("data", {})
            return {
                "success": True,
                "status": order_data.get("status", "UNKNOWN"),
                "data": order_data,
            }
        else:
            return {
                "success": False,
                "status": "UNKNOWN",
                "data": data,
                "errmsg": data.get("errmsg", ""),
            }
    except Exception as e:
        logger.error(f"[XunHuPay] Query error: order={order_no}, error={e}")
        return {
            "success": False,
            "status": "UNKNOWN",
            "data": {},
            "errmsg": str(e),
        }


def verify_callback(params: dict[str, Any]) -> bool:
    """验证虎皮椒支付回调签名

    回调参数是 form 表单 POST，需要验证 hash 签名
    """
    return _verify_hash(params, XUNHU_SECRET)


def parse_callback(params: dict[str, Any]) -> dict[str, Any]:
    """解析虎皮椒回调数据

    回调参数:
        trade_order_id: 商户订单号
        total_fee: 支付金额
        transaction_id: 交易号
        open_order_id: 虎皮椒内部订单号
        order_title: 订单标题
        status: OD(已支付), CD(已退款), RD(退款中), UD(退款失败)
        appid: 支付渠道ID
        time: 时间戳
        nonce_str: 随机字符串
        hash: 签名
    """
    return {
        "trade_order_id": params.get("trade_order_id", ""),
        "total_fee": params.get("total_fee", ""),
        "transaction_id": params.get("transaction_id", ""),
        "open_order_id": params.get("open_order_id", ""),
        "order_title": params.get("order_title", ""),
        "status": params.get("status", ""),
        "appid": params.get("appid", ""),
        "time": params.get("time", ""),
        "nonce_str": params.get("nonce_str", ""),
        "attach": params.get("attach", ""),
    }

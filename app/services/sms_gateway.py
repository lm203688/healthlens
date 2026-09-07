# -*- coding: utf-8 -*-
"""真实短信网关 —— 阿里云 (POP 签名) / 腾讯云 (TC3-HMAC-SHA256)

零 SDK 依赖：两种签名算法均用标准库实现，避免为一个发码功能引入重量级依赖。
未配置密钥时由调用方 (sms_service) 回退到 mock，本模块只负责"真的能发"。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import urllib.parse
import uuid
from datetime import datetime, timezone

import httpx

from app.config import settings

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 手机号用户入库时的占位邮箱后缀（users.email 唯一且非空）
PHONE_PLACEHOLDER_DOMAIN = "phone.healthlens.cc"


class SmsGatewayError(RuntimeError):
    """短信网关发送失败"""


def detect_channel(account: str) -> str:
    """判定账号类型: 含 @ 视为邮箱, 否则按中国大陆手机号校验"""
    account = (account or "").strip()
    if "@" in account:
        if not EMAIL_RE.match(account):
            raise ValueError("邮箱格式不正确")
        return "email"
    if not PHONE_RE.match(account):
        raise ValueError("请输入正确的手机号（1[3-9] 开头的 11 位号码）或邮箱")
    return "sms"


def is_phone(account: str) -> bool:
    return detect_channel(account) == "sms"


def phone_placeholder_email(phone: str) -> str:
    """手机号账号的占位邮箱, 满足 users.email 的唯一约束"""
    return f"{phone}@{PHONE_PLACEHOLDER_DOMAIN}"


# ---------------------------------------------------------------------------
# 阿里云 —— POP 签名 (HMAC-SHA1)
# ---------------------------------------------------------------------------

def _aliyun_special_encode(value: str) -> str:
    """阿里云 POP 要求: 空格编码为 %20 而非 +, * 编码为 %2A, ~ 不编码"""
    return urllib.parse.quote(value, safe="~").replace("+", "%20").replace("*", "%2A")


async def send_by_aliyun(phone: str, code: str) -> None:
    params = {
        "AccessKeyId": settings.ALIYUN_SMS_ACCESS_KEY_ID,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": settings.ALIYUN_SMS_SIGN_NAME,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": settings.ALIYUN_SMS_TEMPLATE_CODE,
        "TemplateParam": json.dumps({"code": code}, separators=(",", ":")),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }
    canonical = "&".join(
        f"{_aliyun_special_encode(k)}={_aliyun_special_encode(str(v))}"
        for k, v in sorted(params.items())
    )
    string_to_sign = f"GET&{_aliyun_special_encode('/')}&{_aliyun_special_encode(canonical)}"
    signing_key = f"{settings.ALIYUN_SMS_ACCESS_KEY_SECRET}&".encode()
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha1).digest()
    params["Signature"] = base64.b64encode(signature).decode()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://dysmsapi.aliyuncs.com/", params=params)
        data = resp.json()
    if data.get("Code") not in ("OK", "ok"):
        raise SmsGatewayError(f"阿里云短信发送失败: {data.get('Code')} - {data.get('Message')}")


# ---------------------------------------------------------------------------
# 腾讯云 —— TC3-HMAC-SHA256
# ---------------------------------------------------------------------------

def _tc3_sign(secret_id: str, secret_key: str, service: str, payload: str, timestamp: int) -> str:
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
    canonical_headers = "content-type:application/json\nhost:sms.tencentcloudapi.com\n"
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            "content-type;host",
            hashlib.sha256(payload.encode()).hexdigest(),
        ]
    )
    string_to_sign = "\n".join(
        [
            "TC3-HMAC-SHA256",
            str(timestamp),
            f"{date}/{service}/tc3_request",
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    def hmac_sha256(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    secret_date = hmac_sha256(("TC3" + secret_key).encode(), date)
    secret_service = hmac_sha256(secret_date, service)
    secret_signing = hmac_sha256(secret_service, "tc3_request")
    return hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()


async def send_by_tencent(phone: str, code: str) -> None:
    host = "sms.tencentcloudapi.com"
    service = "sms"
    payload = json.dumps(
        {
            "PhoneNumberSet": [f"+86{phone}"],
            "SmsSdkAppId": settings.TENCENT_SMS_SDK_APP_ID,
            "SignName": settings.TENCENT_SMS_SIGN_NAME,
            "TemplateId": settings.TENCENT_SMS_TEMPLATE_ID,
            "TemplateParamSet": [code],
        },
        separators=(",", ":"),
    )
    timestamp = int(time.time())
    signature = _tc3_sign(
        settings.TENCENT_SMS_SECRET_ID, settings.TENCENT_SMS_SECRET_KEY, service, payload, timestamp
    )
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
    headers = {
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={settings.TENCENT_SMS_SECRET_ID}/{date}/{service}/tc3_request, "
            f"SignedHeaders=content-type;host, Signature={signature}"
        ),
        "Content-Type": "application/json",
        "Host": host,
        "X-TC-Action": "SendSms",
        "X-TC-Version": "2021-01-11",
        "X-TC-Timestamp": str(timestamp),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"https://{host}/", content=payload.encode(), headers=headers)
        data = resp.json()
    status_list = (data.get("Response") or {}).get("SendStatusSet") or []
    if not status_list or status_list[0].get("Code") != "Ok":
        err = (data.get("Response") or {}).get("Error") or {}
        raise SmsGatewayError(f"腾讯云短信发送失败: {err.get('Code')} - {err.get('Message')}")


async def dispatch_sms(phone: str, code: str) -> str:
    """按 settings.SMS_PROVIDER 选择网关发送，返回 provider 名"""
    provider = settings.SMS_PROVIDER
    if provider == "aliyun":
        await send_by_aliyun(phone, code)
        return "aliyun"
    if provider == "tencent":
        await send_by_tencent(phone, code)
        return "tencent"
    raise SmsGatewayError(f"未知短信网关: {provider}")

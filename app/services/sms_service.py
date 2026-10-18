"""验证码服务 —— 登录与注册合一

支持两种账号：
- 手机号（国内用户首选）→ 短信验证码，网关见 app/services/sms_gateway.py
- 邮箱（其他地区用户）  → 邮件验证码，见 app/services/email_service.py

存储统一落 verification_codes 表（phone 列同时容纳手机号与邮箱，已扩至 VARCHAR(255)）。
设计要点：
- 校验码一次性使用（used 标记），过期作废，同账号重发会使旧码失效。
- mock 模式仅记录日志；生产务必 SMS_PROVIDER=aliyun/tencent 且 SMS_DEV_RETURN_CODE=false。
"""
from datetime import datetime, timedelta
import random
import string

from sqlalchemy import select
from loguru import logger

from app.config import settings
from app.models.verification_code import VerificationCode
from app.services.sms_gateway import (
    SmsGatewayError,
    detect_channel,
    dispatch_sms,
    is_phone,
    phone_placeholder_email,
)


def generate_code(length: int | None = None) -> str:
    """生成数字验证码（首位非 0，避免前端 parseInt 丢位）"""
    length = length or settings.SMS_CODE_LENGTH
    return str(random.randint(1, 9)) + "".join(random.choices(string.digits, k=length - 1))


async def send_sms_code(phone: str, code: str) -> dict:
    """发送短信验证码。

    返回 dict: {sent, provider, dev_code}
    - mock 模式：记录日志，并按 SMS_DEV_RETURN_CODE 决定是否回传验证码。
    - 真实网关：aliyun / tencent 走 sms_gateway 真实发送；密钥不全时回退 mock 并告警。
    """
    if settings.SMS_PROVIDER == "mock":
        logger.info(f"[SMS-MOCK] 向 {phone} 发送验证码: {code}（mock 模式，生产请接入短信网关）")
        return {"sent": True, "provider": "mock", "dev_code": code if settings.SMS_DEV_RETURN_CODE else None}

    if not settings.sms_ready:
        logger.warning(
            f"[SMS] provider={settings.SMS_PROVIDER} 但密钥/签名/模板未配齐，"
            f"按 mock 处理 phone={phone}；请补齐环境变量或改回 SMS_PROVIDER=mock"
        )
        return {"sent": True, "provider": "mock-fallback", "dev_code": code if settings.SMS_DEV_RETURN_CODE else None}

    try:
        provider = await dispatch_sms(phone, code)
    except SmsGatewayError as exc:
        logger.error(f"[SMS] 网关发送失败 phone={phone}: {exc}")
        return {"sent": False, "provider": settings.SMS_PROVIDER, "error": str(exc)}
    logger.info(f"[SMS] 验证码已发送 phone={phone} provider={provider}")
    return {"sent": True, "provider": provider, "dev_code": None}


async def send_email_code(email: str, code: str) -> dict:
    """发送邮箱验证码。

    未配置 SMTP 时按 mock 处理（记录日志），不阻断登录流程。
    """
    if not settings.email_ready:
        logger.warning(
            f"[EMAIL] SMTP 未配置，按 mock 处理 email={email}；"
            f"请设置 SMTP_HOST / SMTP_USER / SMTP_PASSWORD 以启用真实发送"
        )
        return {"sent": True, "provider": "mock", "dev_code": code if settings.SMS_DEV_RETURN_CODE else None}

    from app.services.email_service import EmailService

    minutes = max(1, int(settings.SMS_CODE_TTL_SECONDS) // 60)
    html_body = f"""
    <div style="font-family:-apple-system,'PingFang SC',sans-serif;max-width:480px;margin:0 auto;padding:24px">
      <h2 style="color:#059669;margin:0 0 16px">HealthLens 登录验证码</h2>
      <p style="color:#334155">你正在登录 HealthLens，验证码为：</p>
      <div style="font-size:32px;font-weight:700;letter-spacing:8px;color:#0f172a;
                  background:#f1f5f9;padding:16px;border-radius:8px;text-align:center;margin:16px 0">{code}</div>
      <p style="color:#64748b;font-size:14px">验证码 {minutes} 分钟内有效，请勿转发给任何人。<br/>
      若非本人操作，请忽略本邮件，你的账号仍然安全。</p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0"/>
      <p style="color:#94a3b8;font-size:12px">— HealthLens 团队 · https://healthlens.cc</p>
    </div>
    """
    sent = await EmailService().send_email(email, f"【HealthLens】登录验证码 {code}", html_body)
    if not sent:
        return {"sent": False, "provider": "smtp", "error": "邮件发送失败，请稍后重试"}
    return {"sent": True, "provider": "smtp", "dev_code": None}


async def send_login_code(account: str, code: str) -> dict:
    """按账号类型分发验证码 —— 手机号走短信，邮箱走邮件"""
    channel = detect_channel(account)
    if channel == "email":
        result = await send_email_code(account, code)
    else:
        result = await send_sms_code(account, code)
    result["channel"] = channel
    return result


MAX_VERIFY_ATTEMPTS = 5
MAX_SEND_PER_DAY = 10


async def resend_wait_seconds(db, account: str, purpose: str = "login") -> int:
    """距离下次可发送还需等待的秒数（0 表示可立即发送）"""
    result = await db.execute(
        select(VerificationCode)
        .where(VerificationCode.phone == account, VerificationCode.purpose == purpose)
        .order_by(VerificationCode.created_at.desc())
    )
    vc = result.scalars().first()
    if vc is None:
        return 0
    elapsed = (datetime.utcnow() - vc.created_at).total_seconds()
    interval = int(settings.SMS_RESEND_INTERVAL_SECONDS)
    return max(0, int(interval - elapsed))


async def count_sent_today(db, account: str, purpose: str = "login") -> int:
    """当日已发送次数（用于防刷配额）"""
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.phone == account,
            VerificationCode.purpose == purpose,
            VerificationCode.created_at >= start,
        )
    )
    return len(result.scalars().all())


async def store_code(db, account: str, code: str, purpose: str = "login") -> VerificationCode:
    """存储验证码，并使该账号此前同用途的未用码失效"""
    now = datetime.utcnow()
    expires = now + timedelta(seconds=settings.SMS_CODE_TTL_SECONDS)

    old = await db.execute(
        select(VerificationCode).where(
            VerificationCode.phone == account,
            VerificationCode.purpose == purpose,
            VerificationCode.used == False,  # noqa: E712
        )
    )
    for rec in old.scalars().all():
        rec.used = True

    vc = VerificationCode(phone=account, code=code, purpose=purpose, expires_at=expires)
    db.add(vc)
    await db.commit()
    await db.refresh(vc)
    return vc


async def verify_and_consume(db, account: str, code: str, purpose: str = "login") -> tuple[bool, str]:
    """校验验证码并消费（标记 used）。

    返回 (ok, reason)：
    - (True, "OK")
    - (False, "NO_CODE")     无可用验证码
    - (False, "EXPIRED")     已过期
    - (False, "WRONG_CODE")  验证码不符
    - (False, "TOO_MANY")    错误次数过多，验证码已作废
    """
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.phone == account,
            VerificationCode.purpose == purpose,
            VerificationCode.used == False,  # noqa: E712
        ).order_by(VerificationCode.created_at.desc())
    )
    vc = result.scalars().first()
    if not vc:
        return False, "NO_CODE"
    if vc.expires_at < datetime.utcnow():
        vc.used = True
        await db.commit()
        return False, "EXPIRED"
    if vc.attempts >= MAX_VERIFY_ATTEMPTS:
        vc.used = True
        await db.commit()
        return False, "TOO_MANY"
    if vc.code != code:
        vc.attempts += 1
        if vc.attempts >= MAX_VERIFY_ATTEMPTS:
            vc.used = True
        await db.commit()
        return False, "WRONG_CODE"
    vc.used = True
    await db.commit()
    return True, "OK"

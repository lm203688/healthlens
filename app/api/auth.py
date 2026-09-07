"""认证路由 - 验证码登录（登录/注册合一）、密码登录、Token 刷新、当前用户信息"""
import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app.models.user import User
from app.config import settings
from app.utils.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.api.deps import get_current_user, require_admin
from app.schemas.auth import (
    RegisterInput,
    LoginInput,
    OtpSendInput,
    OtpVerifyInput,
    RefreshInput,
    TokenOutput,
    UserOutput,
)
from app.services import sms_service
from app.services.sms_gateway import is_phone, phone_placeholder_email
from loguru import logger

router = APIRouter(tags=["auth"])

limiter = Limiter(key_func=get_remote_address)


def conditional_limit(limit: str):
    """条件限流: 测试环境(settings.RATE_LIMIT_ENABLED=False)下不禁用"""
    if settings.RATE_LIMIT_ENABLED:
        return limiter.limit(limit)
    # 禁用时返回一个空操作装饰器
    def noop(func):
        return func
    return noop


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=dict)
@conditional_limit("5/minute")
async def register(request: Request, body: RegisterInput, db: AsyncSession = Depends(get_db)):
    """用户注册：创建用户并返回 JWT Token"""
    # 检查邮箱是否已注册
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # 创建用户
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        password_hash=hash_password(body.password),
        phone=body.phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 生成 Token
    token_data = {"sub": str(user.id)}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
            },
        },
    }


@router.post("/login", response_model=dict)
@conditional_limit("5/minute")
async def login(request: Request, body: LoginInput, db: AsyncSession = Depends(get_db)):
    """用户登录：支持邮箱或手机号 + 密码，返回 JWT Token"""
    result = await db.execute(
        select(User).where((User.email == body.account) | (User.phone == body.account))
    )
    user = result.scalars().first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # 生成 Token
    token_data = {"sub": str(user.id)}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
            },
        },
    }


# ---------------------------------------------------------------------------
# 验证码登录 —— 登录与注册合一
# ---------------------------------------------------------------------------

def _issue_token_payload(user: User) -> dict:
    token_data = {"sub": str(user.id)}
    return {
        "success": True,
        "data": {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
            },
        },
    }


async def _find_user_by_account(db: AsyncSession, account: str) -> User | None:
    """按手机号或邮箱查找用户（手机号会同时匹配占位邮箱）。

    采用 scalars().first() 而非 scalar_one_or_none()：phone 列无唯一约束，
    历史/并发数据可能出现重复行，scalar_one_or_none() 会抛 MultipleResultsFound
    并导致整个校验接口 500。此处取最新一条即可，绝不因重复行崩溃。
    """
    candidates = [account, phone_placeholder_email(account)] if is_phone(account) else [account]
    for value in candidates:
        result = await db.execute(select(User).where(User.email == value))
        user = result.scalars().first()
        if user is not None:
            return user
    result = await db.execute(
        select(User).where(User.phone == account).order_by(User.created_at.desc())
    )
    return result.scalars().first()


@router.post("/otp/send", response_model=dict)
@conditional_limit("20/minute")
async def otp_send(request: Request, body: OtpSendInput, db: AsyncSession = Depends(get_db)):
    """获取验证码：手机号走短信，邮箱走邮件。

    登录与注册合一 —— 未注册账号同样可以获取验证码，验证通过时自动创建账号。
    """
    account = body.account

    # 生产护栏：生产环境未接入真实短信/SMTP 时，禁止发放 mock 验证码。
    # 否则 mock 回显的 dev_code 会让任何人在生产上"无密码登录"。
    # 开发/测试环境不受影响（ENV 非 production）。
    if settings.otp_guard_blocked:
        logger.warning(f"[OTP-GUARD] 生产环境无真实验证码通道，拒绝发码 account={account}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "验证码通道未就绪（未配置短信/邮箱服务商），登录暂不可用",
                "reason": "OTP_CHANNEL_NOT_CONFIGURED",
            },
        )

    wait = await sms_service.resend_wait_seconds(db, account)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": f"验证码已发送，请 {wait} 秒后重试", "retry_after": wait},
        )

    if await sms_service.count_sent_today(db, account) >= sms_service.MAX_SEND_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "今日获取验证码次数已达上限，请明天再试"},
        )

    code = sms_service.generate_code()
    # 先发送后落库：网关失败时不写入无效验证码，也不消耗配额
    result = await sms_service.send_login_code(account, code)
    if not result.get("sent"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": result.get("error") or "验证码发送失败，请稍后重试"},
        )

    await sms_service.store_code(db, account, code)

    data = {
        "channel": result.get("channel"),
        "provider": result.get("provider"),
        "expires_in": int(settings.SMS_CODE_TTL_SECONDS),
    }
    # mock 模式下的自测回显（生产须 SMS_DEV_RETURN_CODE=false）
    if result.get("dev_code"):
        data["dev_code"] = result["dev_code"]
    return {"success": True, "data": data}


@router.post("/otp/verify", response_model=dict)
@conditional_limit("20/minute")
async def otp_verify(request: Request, body: OtpVerifyInput, db: AsyncSession = Depends(get_db)):
    """校验验证码并登录；账号不存在时自动创建（注册与登录合一）。"""
    ok, reason = await sms_service.verify_and_consume(db, body.account, body.code)
    if not ok:
        messages = {
            "NO_CODE": "请先获取验证码",
            "EXPIRED": "验证码已过期，请重新获取",
            "WRONG_CODE": "验证码不正确",
            "TOO_MANY": "错误次数过多，请重新获取验证码",
        }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": messages.get(reason, "验证码校验失败"), "reason": reason},
        )

    user = await _find_user_by_account(db, body.account)

    if user is None:
        # 自动注册：以验证码为凭证，密码字段填充随机不可登录值
        if is_phone(body.account):
            email = phone_placeholder_email(body.account)
            phone: str | None = body.account
        else:
            email = body.account
            phone = None

        # 并发保护：占位邮箱 / 手机号可能已被占用（重复行不崩溃，取首条复用）
        existed = await db.execute(select(User).where(User.email == email))
        existing = existed.scalars().first()
        if existing is not None:
            user = existing
        else:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                phone=phone,
                password_hash=hash_password(secrets.token_urlsafe(32)),
            )
            db.add(user)
            try:
                await db.commit()
                await db.refresh(user)
            except Exception:
                # 极小概率并发插入导致唯一约束冲突：回滚后复用已存在的账号
                await db.rollback()
                recheck = await db.execute(select(User).where(User.email == email))
                user = recheck.scalars().first() or user

    return _issue_token_payload(user)


@router.post("/refresh", response_model=dict)
async def refresh_token(body: RefreshInput, db: AsyncSession = Depends(get_db)):
    """刷新 Token：使用 refresh_token 换取新的 access_token"""
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # 生成新 Token
    token_data = {"sub": str(user.id)}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
    }


@router.get("/me", response_model=dict)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前已认证用户的详细信息"""
    return {
        "success": True,
        "data": {
            "id": str(current_user.id),
            "email": current_user.email,
            "phone": current_user.phone,
            "role": current_user.role,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
    }


@router.put("/role", response_model=dict)
async def update_user_role(
    body: dict,  # {"user_id": str, "role": "doctor"|"admin"|"patient"}
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员设置用户角色"""
    user_id = body.get("user_id")
    role = body.get("role")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: user_id and role",
        )

    allowed_roles = ["patient", "doctor", "admin"]
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(allowed_roles)}",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    target_user.role = role
    await db.commit()
    await db.refresh(target_user)

    return {
        "success": True,
        "data": {
            "id": str(target_user.id),
            "email": target_user.email,
            "role": target_user.role,
        },
    }

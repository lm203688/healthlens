"""认证路由 - 用户注册、登录、Token 刷新、当前用户信息"""
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
from app.schemas.auth import RegisterInput, LoginInput, RefreshInput, TokenOutput, UserOutput

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
    if result.scalar_one_or_none() is not None:
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
    """用户登录：验证密码，返回 JWT Token"""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
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
    target_user = result.scalar_one_or_none()
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

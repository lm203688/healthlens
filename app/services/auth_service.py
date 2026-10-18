"""认证服务 - 从 API 路由中抽取的业务逻辑层"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from loguru import logger

from app.models.user import User
from app.utils.security import hash_password, verify_password, create_access_token, create_refresh_token


async def register_user(db: AsyncSession, email: str, password: str, phone: str | None = None) -> User:
    """注册新用户"""
    # 检查邮箱唯一性
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(password),
        phone=phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"User registered: {email}")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """验证用户凭据"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password")
    return user


def generate_tokens(user_id: str, email: str) -> dict:
    """生成 JWT 令牌对"""
    access_token = create_access_token({"sub": str(user_id), "email": email})
    refresh_token = create_refresh_token({"sub": str(user_id), "email": email})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

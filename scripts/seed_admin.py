"""Seed script - 创建 admin 用户（如果不存在）

Usage:
    python -m scripts.seed_admin
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.user import User
from app.utils.security import hash_password

ADMIN_EMAIL = "admin@healthlens.com"
ADMIN_PASSWORD = "Admin123!"


async def seed_admin():
    """创建 admin 用户（如果不存在）"""
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[seed_admin] Admin user already exists: {existing.email} (id={existing.id}, role={existing.role})")
            return

        admin = User(
            id=str(uuid.uuid4()),
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            role="admin",
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        print(f"[seed_admin] Admin user created: {admin.email} (id={admin.id}, role={admin.role})")
        print(f"[seed_admin] Password: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed_admin())

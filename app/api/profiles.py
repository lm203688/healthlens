"""健康档案管理路由 - 创建、查询、更新用户健康档案"""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.health_record import HealthProfile
from app.api.deps import get_current_user
from loguru import logger

router = APIRouter()


class ProfileCreateInput(BaseModel):
    name: str | None = None
    gender: str | None = None  # "male" | "female" | "other"
    birth_date: date | None = None
    blood_type: str | None = None  # A, B, AB, O + Rh
    height_cm: Decimal | None = None
    weight_kg: Decimal | None = None


class ProfileUpdateInput(BaseModel):
    name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    blood_type: str | None = None
    height_cm: Decimal | None = None
    weight_kg: Decimal | None = None


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建健康档案（每个用户只能有一个，已存在则返回 409）"""
    # 检查是否已存在
    result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == str(current_user.id))
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Health profile already exists for this user. Use PUT to update.",
        )

    profile = HealthProfile(
        user_id=str(current_user.id),
        name=payload.name,
        gender=payload.gender,
        birth_date=payload.birth_date,
        blood_type=payload.blood_type,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    logger.info(f"Health profile created for user {current_user.id}")

    return {
        "success": True,
        "data": {
            "user_id": str(profile.user_id),
            "name": profile.name,
            "gender": profile.gender,
            "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
            "blood_type": profile.blood_type,
            "height_cm": float(profile.height_cm) if profile.height_cm else None,
            "weight_kg": float(profile.weight_kg) if profile.weight_kg else None,
        },
    }


@router.get("/")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的健康档案"""
    result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == str(current_user.id))
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health profile not found. Create one with POST /api/v1/profiles/",
        )

    return {
        "success": True,
        "data": {
            "user_id": str(profile.user_id),
            "name": profile.name,
            "gender": profile.gender,
            "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
            "blood_type": profile.blood_type,
            "height_cm": float(profile.height_cm) if profile.height_cm else None,
            "weight_kg": float(profile.weight_kg) if profile.weight_kg else None,
        },
    }


@router.put("/")
async def update_profile(
    payload: ProfileUpdateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的健康档案"""
    result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == str(current_user.id))
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health profile not found. Create one with POST /api/v1/profiles/",
        )

    # 只更新传入的非 None 字段
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    logger.info(f"Health profile updated for user {current_user.id}")

    return {
        "success": True,
        "data": {
            "user_id": str(profile.user_id),
            "name": profile.name,
            "gender": profile.gender,
            "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
            "blood_type": profile.blood_type,
            "height_cm": float(profile.height_cm) if profile.height_cm else None,
            "weight_kg": float(profile.weight_kg) if profile.weight_kg else None,
        },
    }

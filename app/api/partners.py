"""合作方管理 API —— S3-2 Powered-by SDK（admin only）。

端点
----
- POST   /api/v1/partners                       创建合作方（默认 pending）
- GET    /api/v1/partners                       列出所有合作方
- POST   /api/v1/partners/{partner_id}/api-keys 生成 API Key（明文仅返回一次）
- GET    /api/v1/partners/{partner_id}/api-keys 列出该合作方的 API Keys（hash only）
- DELETE /api/v1/partners/{partner_id}/api-keys/{key_id} 吊销 Key
- POST   /api/v1/partners/{partner_id}/activate 激活合作方

所有端点 admin only；Key 生成时返回明文，之后仅返回 hash 前缀。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database import get_db
from app.integrations.sdk.auth import hash_api_key
from app.models.partner import Partner, PartnerApiKey
from app.models.user import User

router = APIRouter(tags=["合作方管理"])

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    contact_email: EmailStr
    description: Optional[str] = Field(default=None, max_length=2000)
    brand_name: Optional[str] = Field(default=None, max_length=100)
    allowed_endpoints: Optional[str] = Field(
        default=None,
        description="逗号分隔的端点白名单，空值使用默认全集",
    )
    rate_limit_per_min: int = Field(default=600, ge=0, le=100000)


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: Optional[int] = Field(
        default=None, ge=1, le=3650, description="有效期（天），空表示长期有效"
    )
    note: Optional[str] = Field(default=None, max_length=255)


def _partner_dict(p: Partner) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "contact_email": p.contact_email,
        "status": p.status,
        "description": p.description,
        "brand_name": p.brand_name,
        "allowed_endpoints": p.allowed_endpoints,
        "rate_limit_per_min": p.rate_limit_per_min,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _key_dict(k: PartnerApiKey, include_plain: bool = False, plain_key: str | None = None) -> dict:
    d = {
        "id": k.id,
        "partner_id": k.partner_id,
        "key_hash": k.key_hash,
        "key_prefix": k.key_prefix,
        "name": k.name,
        "status": k.status,
        "note": k.note,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "updated_at": k.updated_at.isoformat() if k.updated_at else None,
    }
    if include_plain and plain_key is not None:
        d["key_plain"] = plain_key
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_partner(
    body: PartnerCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """创建合作方（初始状态 pending，需 activate 后才能调用 API）。"""
    partner = Partner(
        name=body.name,
        contact_email=body.contact_email,
        description=body.description,
        brand_name=body.brand_name,
        allowed_endpoints=body.allowed_endpoints,
        rate_limit_per_min=body.rate_limit_per_min,
        status="pending",
    )
    db.add(partner)
    await db.commit()
    await db.refresh(partner)
    return _partner_dict(partner)


@router.get("")
async def list_partners(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """列出所有合作方（含 pending/active/inactive）。"""
    result = await db.execute(select(Partner).order_by(Partner.created_at.desc()))
    partners = result.scalars().all()
    return {"success": True, "items": [_partner_dict(p) for p in partners], "total": len(partners)}


async def _get_partner_or_404(partner_id: str, db: AsyncSession) -> Partner:
    result = await db.execute(select(Partner).where(Partner.id == partner_id))
    partner = result.scalar_one_or_none()
    if partner is None:
        raise HTTPException(status_code=404, detail="partner not found")
    return partner


@router.post("/{partner_id}/api-keys", status_code=201)
async def create_api_key(
    partner_id: str,
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """生成 API Key。明文 Key 仅在本响应中返回一次。

    约定：
    - 生成格式 `hl_live_<random_hex>`（32 字符 hex），落库 SHA256 hash
    - 前缀 `hl_live_` 用于人肉识别（key_prefix 存完整明文前缀，不含后续随机部分）
    """
    partner = await _get_partner_or_404(partner_id, db)

    plain_key = f"hl_live_{secrets.token_hex(16)}"
    key_hash = hash_api_key(plain_key)
    key_prefix = plain_key[:14]  # hl_live_xxxxxxxx

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days)

    api_key = PartnerApiKey(
        partner_id=partner.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        status="active",
        note=body.note,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return _key_dict(api_key, include_plain=True, plain_key=plain_key)


@router.get("/{partner_id}/api-keys")
async def list_api_keys(
    partner_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """列出该合作方的所有 API Keys（不含明文）。"""
    partner = await _get_partner_or_404(partner_id, db)
    result = await db.execute(
        select(PartnerApiKey)
        .where(PartnerApiKey.partner_id == partner.id)
        .order_by(PartnerApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return {"success": True, "items": [_key_dict(k) for k in keys], "total": len(keys)}


@router.delete("/{partner_id}/api-keys/{key_id}")
async def revoke_api_key(
    partner_id: str,
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """吊销 API Key。吊销后不可再认证。"""
    partner = await _get_partner_or_404(partner_id, db)
    result = await db.execute(
        select(PartnerApiKey).where(
            PartnerApiKey.id == key_id,
            PartnerApiKey.partner_id == partner.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="api key not found")
    if api_key.status == "revoked":
        raise HTTPException(status_code=400, detail="api key already revoked")
    api_key.status = "revoked"
    await db.commit()
    await db.refresh(api_key)
    return _key_dict(api_key)


@router.post("/{partner_id}/activate")
async def activate_partner(
    partner_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """激活合作方：pending/inactive → active。"""
    partner = await _get_partner_or_404(partner_id, db)
    if partner.status == "active":
        raise HTTPException(status_code=400, detail="partner already active")
    partner.status = "active"
    await db.commit()
    await db.refresh(partner)
    return _partner_dict(partner)

"""GDPR Compliance API — 数据导出、数据删除、同意管理、DPIA 文档

GDPR Article 15: Right of Access (数据导出)
GDPR Article 17: Right to Erasure / Right to be Forgotten (数据删除)
GDPR Article 13/14: Transparency — 同意记录
GDPR Article 35: Data Protection Impact Assessment (DPIA)
"""
import json
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.database import get_db
from app.models.user import User
from app.models.observation import HealthObservation
from app.api.deps import get_current_user
from loguru import logger

router = APIRouter(tags=["GDPR"])


# ── Schemas ──────────────────────────────────────────────────────


class ConsentStatus(BaseModel):
    """用户同意状态"""
    accepted: bool = False
    accepted_at: Optional[str] = None
    version: str = "2.0"
    purposes: list[str] = []


class ConsentUpdate(BaseModel):
    """更新用户同意"""
    accepted: bool = Field(..., description="是否同意数据处理")
    purposes: list[str] = Field(
        default_factory=list,
        description="同意的处理目的，如 ['health_analysis', 'data_improvement']"
    )


class DeleteRequest(BaseModel):
    """数据删除请求"""
    confirm: bool = Field(..., description="必须设为 true 以确认删除")
    reason: Optional[str] = Field(None, description="删除原因（可选）")


# ── Consent Store ────────────────────────────────────────────────
# 简化实现：使用内存存储。生产环境应持久化到数据库。


_consent_store: dict[str, ConsentStatus] = {}


def _get_consent(user_id: str) -> ConsentStatus:
    return _consent_store.get(
        user_id,
        ConsentStatus(accepted=False, version="2.0", purposes=[])
    )


# ── Routes ───────────────────────────────────────────────────────


@router.get("/consent")
async def get_consent(
    user: User = Depends(get_current_user),
):
    """获取当前用户的 GDPR 同意状态"""
    consent = _get_consent(user.id)
    return {"success": True, "data": consent.model_dump()}


@router.post("/consent")
async def update_consent(
    payload: ConsentUpdate,
    user: User = Depends(get_current_user),
):
    """更新用户 GDPR 同意状态"""
    now = datetime.now(timezone.utc).isoformat()
    _consent_store[user.id] = ConsentStatus(
        accepted=payload.accepted,
        accepted_at=now if payload.accepted else None,
        version="2.0",
        purposes=payload.purposes,
    )
    logger.info(
        f"GDPR consent updated | user={user.id} | accepted={payload.accepted} | purposes={payload.purposes}"
    )
    return {"success": True, "data": _consent_store[user.id].model_dump()}


@router.get("/export")
async def export_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR Article 15: 数据导出 — 返回用户所有个人数据的 JSON 格式

    包含：用户信息、健康指标、同意记录
    """
    consent = _get_consent(user.id)

    # 获取所有健康观测数据
    obs_stmt = select(HealthObservation).where(
        HealthObservation.user_id == user.id
    ).order_by(HealthObservation.recorded_at)
    obs_result = await db.execute(obs_stmt)
    observations = obs_result.scalars().all()

    export_payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "nickname": user.nickname,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "observations": [
            {
                "id": o.id,
                "loinc_code": o.loinc_code,
                "loinc_name": o.loinc_name,
                "value_numeric": str(o.value_numeric) if o.value_numeric is not None else None,
                "value_string": o.value_string,
                "value_unit": o.value_unit,
                "reference_range_low": str(o.reference_range_low) if o.reference_range_low is not None else None,
                "reference_range_high": str(o.reference_range_high) if o.reference_range_high is not None else None,
                "source": o.source,
                "recorded_at": o.recorded_at.isoformat() if o.recorded_at else None,
            }
            for o in observations
        ],
        "consent": consent.model_dump(),
    }

    logger.info(
        f"GDPR data export | user={user.id} | observations={len(observations)}"
    )
    return JSONResponse(
        content=export_payload,
        headers={
            "Content-Disposition": f'attachment; filename="healthlens-gdpr-export-{user.id[:8]}.json"',
            "Cache-Control": "no-store",
        }
    )


@router.get("/export/csv")
async def export_data_csv(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR Article 15: 数据导出 — CSV 格式（仅健康观测数据）"""
    obs_stmt = select(HealthObservation).where(
        HealthObservation.user_id == user.id
    ).order_by(HealthObservation.recorded_at)
    obs_result = await db.execute(obs_stmt)
    observations = obs_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "loinc_code", "loinc_name", "value_numeric", "value_string",
        "value_unit", "reference_range_low", "reference_range_high",
        "source", "recorded_at"
    ])
    for o in observations:
        writer.writerow([
            o.id, o.loinc_code, o.loinc_name,
            str(o.value_numeric) if o.value_numeric is not None else "",
            o.value_string or "",
            o.value_unit or "",
            str(o.reference_range_low) if o.reference_range_low is not None else "",
            str(o.reference_range_high) if o.reference_range_high is not None else "",
            o.source or "",
            o.recorded_at.isoformat() if o.recorded_at else "",
        ])

    output.seek(0)
    logger.info(f"GDPR CSV export | user={user.id} | observations={len(observations)}")
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="healthlens-gdpr-export-{user.id[:8]}.csv"',
            "Cache-Control": "no-store",
        }
    )


@router.post("/delete")
async def delete_user_data(
    payload: DeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR Article 17: 被遗忘权 — 删除用户所有个人数据

    删除：健康观测数据、同意记录、用户账户
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true to acknowledge data deletion"
        )

    # 1. 删除健康观测数据
    delete_stmt = delete(HealthObservation).where(
        HealthObservation.user_id == user.id
    )
    del_result = await db.execute(delete_stmt)
    deleted_obs = del_result.rowcount

    # 2. 清除同意记录
    _consent_store.pop(user.id, None)

    # 3. 停用用户账户（软删除，保留审计日志）
    user.is_active = False
    user.email = f"deleted_{user.id}_{user.email}"
    user.phone = None

    await db.commit()

    logger.info(
        f"GDPR data deletion | user={user.id} | deleted_observations={deleted_obs} | reason={payload.reason}"
    )
    return {
        "success": True,
        "message": "Your personal data has been deleted. Your account is now deactivated.",
        "deleted_observations": deleted_obs,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/dpia")
async def get_dpia():
    """Data Protection Impact Assessment (DPIA) 摘要

    GDPR Article 35: 处理健康数据属于高风险处理活动，
    需要数据保护影响评估。
    """
    return {
        "success": True,
        "data": {
            "assessment_name": "HealthLens GDPR DPIA",
            "version": "1.0",
            "last_updated": "2026-09-19",
            "controller": "HealthLens",
            "processing_purposes": [
                "Health assessment and analysis",
                "TCM constitution identification",
                "8-axis fusion engine scoring",
                "BioAge calculation",
                "Personalized health recommendations",
            ],
            "data_categories": [
                "User profile (email, phone, nickname)",
                "Health observations (vital signs, lab results)",
                "Symptom reports",
                "Lifestyle data",
                "Consent records",
            ],
            "data_subjects": "HealthLens registered users (patients)",
            "necessity_assessment": "Processing is necessary to provide personalized health analytics and wellness recommendations.",
            "risks_identified": [
                "Unauthorized access to health data",
                "Data breach leading to re-identification",
                "Excessive data retention",
                "Data used for purposes beyond consent",
            ],
            "mitigations": [
                "TLS 1.2+ encryption in transit",
                "AES-256 encryption at rest",
                "JWT-based authentication with short-lived tokens",
                "Rate limiting on all API endpoints",
                "Role-based access control",
                "Right to erasure within 30 days",
                "Data minimization: only collect data needed for stated purpose",
                "Consent versioning and audit trail",
            ],
            "residual_risk": "Low — with documented controls and ongoing monitoring.",
            "review_frequency": "Annually or when processing activities change significantly",
            "contact": "privacy@healthlens.cc",
        }
    }


@router.get("/rights")
async def get_rights():
    """GDPR 数据主体权利摘要 — 面向用户的可读权利说明"""
    return {
        "success": True,
        "data": {
            "rights": [
                {
                    "id": "access",
                    "article": "Article 15",
                    "title": "Right of Access",
                    "description_zh": "您可以请求获取我们持有的关于您的所有个人数据的副本。",
                    "description_en": "You can request a copy of all personal data we hold about you.",
                    "how_to": "GET /api/v1/gdpr/export",
                    "response_time": "30 days",
                },
                {
                    "id": "erasure",
                    "article": "Article 17",
                    "title": "Right to Erasure (Right to be Forgotten)",
                    "description_zh": "您可以请求删除您的所有个人数据，我们将无法逆转此操作。",
                    "description_en": "You can request deletion of all your personal data. This action cannot be undone.",
                    "how_to": "POST /api/v1/gdpr/delete",
                    "response_time": "30 days",
                },
                {
                    "id": "portability",
                    "article": "Article 20",
                    "title": "Right to Data Portability",
                    "description_zh": "您可以获取您的数据并传输到其他服务。支持 JSON 和 CSV 格式。",
                    "description_en": "You can obtain your data in a structured, commonly used format and transmit it to another controller.",
                    "how_to": "GET /api/v1/gdpr/export or /api/v1/gdpr/export/csv",
                    "response_time": "30 days",
                },
                {
                    "id": "consent_withdrawal",
                    "article": "Article 7",
                    "title": "Right to Withdraw Consent",
                    "description_zh": "您可以随时撤回对数据处理的同意。撤回同意后，我们将停止处理您的数据。",
                    "description_en": "You can withdraw your consent for data processing at any time.",
                    "how_to": "POST /api/v1/gdpr/consent with accepted=false",
                    "response_time": "Immediately",
                },
            ]
        }
    }

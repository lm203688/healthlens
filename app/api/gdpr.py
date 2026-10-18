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

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.database import get_db
from app.models.user import User
from app.models.observation import HealthObservation
from app.api.deps import get_current_user
from app.lib.region_guard import require_same_region
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


class FieldConsentStatus(BaseModel):
    """字段级同意状态"""
    field_path: str
    jurisdiction: str
    purpose: str
    accepted: bool
    accepted_at: Optional[str] = None
    version: str = "2.0"


class FieldConsentUpdate(BaseModel):
    """字段级同意更新"""
    field_path: str = Field(..., description="字段路径，如 heart_rate、genome.CYP2C19")
    jurisdiction: str = Field(default="cn", description="法域：cn/us/uk/au/eu")
    purpose: str = Field(default="analysis", description="目的：analysis/training/share/export")
    accepted: bool = Field(..., description="是否同意")
    note: Optional[str] = None


# ── Consent Store ────────────────────────────────────────────────
# P0-22：持久化到数据库，替代内存 dict（重启不丢、多 worker 一致）


async def _get_consent_db(db: AsyncSession, user_id: str) -> ConsentStatus:
    from app.models.gdpr_consent import GDPRConsent
    from sqlalchemy import select as _select

    stmt = _select(GDPRConsent).where(GDPRConsent.user_id == user_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        return ConsentStatus(accepted=False, version="2.0", purposes=[])

    purposes = json.loads(row.purposes) if row.purposes else []
    return ConsentStatus(
        accepted=row.accepted,
        accepted_at=row.accepted_at,
        version=row.version,
        purposes=purposes,
    )


async def _upsert_consent_db(
    db: AsyncSession, user_id: str, consent: ConsentStatus
) -> None:
    from app.models.gdpr_consent import GDPRConsent
    from sqlalchemy import select as _select

    stmt = _select(GDPRConsent).where(GDPRConsent.user_id == user_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    purposes_json = json.dumps(consent.purposes)

    if row:
        row.accepted = consent.accepted
        row.accepted_at = consent.accepted_at
        row.version = consent.version
        row.purposes = purposes_json
    else:
        row = GDPRConsent(
            user_id=user_id,
            accepted=consent.accepted,
            accepted_at=consent.accepted_at,
            version=consent.version,
            purposes=purposes_json,
        )
        db.add(row)
    await db.commit()


# ── Routes ───────────────────────────────────────────────────────


@router.get("/consent")
async def get_consent(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的 GDPR 同意状态

    B0-3: 强区域驻留检查。
    """
    require_same_region(user, request)
    consent = await _get_consent_db(db, user.id)
    return {"success": True, "data": consent.model_dump()}


@router.post("/consent")
async def update_consent(
    request: Request,
    payload: ConsentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新用户 GDPR 同意状态

    B0-3: 强区域驻留检查。
    """
    require_same_region(user, request)
    now = datetime.now(timezone.utc).isoformat()
    consent = ConsentStatus(
        accepted=payload.accepted,
        accepted_at=now if payload.accepted else None,
        version="2.0",
        purposes=payload.purposes,
    )
    await _upsert_consent_db(db, user.id, consent)
    logger.info(
        f"GDPR consent updated | user={user.id} | accepted={payload.accepted} | purposes={payload.purposes}"
    )
    return {"success": True, "data": consent.model_dump()}


@router.get("/export")
async def export_data(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR Article 15: 数据导出 — 返回用户所有个人数据的 JSON 格式

    包含：用户信息、健康指标、同意记录

    B0-3: 强区域驻留检查（跨 region 导出 PII → 403）。
    """
    require_same_region(user, request)
    consent = await _get_consent_db(db, user.id)

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
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR Article 15: 数据导出 — CSV 格式（仅健康观测数据）

    B0-3: 强区域驻留检查。
    """
    require_same_region(user, request)
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
    request: Request,
    payload: DeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR Article 17: 被遗忘权 — 删除用户所有个人数据

    删除：健康观测数据、同意记录、用户账户

    B0-3: 强区域驻留检查。
    """
    require_same_region(user, request)
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

    # 2. 删除同意记录（DB）
    from app.models.gdpr_consent import GDPRConsent
    await db.execute(delete(GDPRConsent).where(GDPRConsent.user_id == user.id))

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
                {
                    "id": "field_consent",
                    "article": "Article 7 (Granularity)",
                    "title": "Field-Level Consent",
                    "description_zh": "您可以按字段粒度控制数据使用，选择同意或拒绝特定字段用于特定目的。",
                    "description_en": "You can control data usage at field granularity, choosing to consent or refuse specific fields for specific purposes.",
                    "how_to": "GET/POST /api/v1/gdpr/field-consent",
                    "response_time": "Immediately",
                },
            ]
        }
    }


# ── 字段级×法域级同意管理（M13 差异化）──────────────────────────

@router.get("/field-consent")
async def list_field_consents(
    request: Request,
    jurisdiction: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出用户的字段级同意记录

    支持按法域筛选。返回所有 (field, jurisdiction, purpose) 组合的同意状态。
    """
    from app.models.field_consent import FieldConsent

    stmt = select(FieldConsent).where(FieldConsent.user_id == user.id)
    if jurisdiction:
        stmt = stmt.where(FieldConsent.jurisdiction == jurisdiction)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    consents = [
        FieldConsentStatus(
            field_path=r.field_path,
            jurisdiction=r.jurisdiction,
            purpose=r.purpose,
            accepted=r.accepted,
            accepted_at=r.accepted_at,
            version=r.version,
        )
        for r in rows
    ]
    return {"success": True, "data": {"field_consents": consents, "count": len(consents)}}


@router.post("/field-consent")
async def update_field_consent(
    request: Request,
    payload: FieldConsentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新字段级同意

    记录 (user, field_path, jurisdiction, purpose) 四维同意。
    全局撤回（POST /consent with accepted=false）自动覆盖所有字段级同意。
    """
    from app.models.field_consent import FieldConsent

    require_same_region(user, request)
    now = datetime.now(timezone.utc).isoformat()

    stmt = select(FieldConsent).where(
        FieldConsent.user_id == user.id,
        FieldConsent.field_path == payload.field_path,
        FieldConsent.jurisdiction == payload.jurisdiction,
        FieldConsent.purpose == payload.purpose,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row:
        row.accepted = payload.accepted
        row.accepted_at = now if payload.accepted else None
        row.note = payload.note
    else:
        row = FieldConsent(
            user_id=user.id,
            field_path=payload.field_path,
            jurisdiction=payload.jurisdiction,
            purpose=payload.purpose,
            accepted=payload.accepted,
            accepted_at=now if payload.accepted else None,
            note=payload.note,
        )
        db.add(row)
    await db.commit()

    logger.info(
        f"Field consent updated | user={user.id} | field={payload.field_path} | "
        f"jurisdiction={payload.jurisdiction} | purpose={payload.purpose} | accepted={payload.accepted}"
    )
    return {"success": True, "data": FieldConsentStatus(
        field_path=payload.field_path,
        jurisdiction=payload.jurisdiction,
        purpose=payload.purpose,
        accepted=payload.accepted,
        accepted_at=now if payload.accepted else None,
    ).model_dump()}


@router.post("/field-consent/batch")
async def batch_update_field_consents(
    request: Request,
    payloads: list[FieldConsentUpdate],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量更新字段级同意

    一次提交多个字段同意状态，减少网络往返。
    """
    from app.models.field_consent import FieldConsent

    require_same_region(user, request)
    now = datetime.now(timezone.utc).isoformat()
    updated = 0

    for payload in payloads:
        stmt = select(FieldConsent).where(
            FieldConsent.user_id == user.id,
            FieldConsent.field_path == payload.field_path,
            FieldConsent.jurisdiction == payload.jurisdiction,
            FieldConsent.purpose == payload.purpose,
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            row.accepted = payload.accepted
            row.accepted_at = now if payload.accepted else None
            row.note = payload.note
        else:
            row = FieldConsent(
                user_id=user.id,
                field_path=payload.field_path,
                jurisdiction=payload.jurisdiction,
                purpose=payload.purpose,
                accepted=payload.accepted,
                accepted_at=now if payload.accepted else None,
                note=payload.note,
            )
            db.add(row)
        updated += 1

    await db.commit()
    logger.info(f"Batch field consent updated | user={user.id} | count={updated}")
    return {"success": True, "data": {"updated": updated}}


@router.get("/field-consent/check")
async def check_field_consent(
    field_path: str,
    jurisdiction: str = "cn",
    purpose: str = "analysis",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """检查字段级同意状态

    供后端业务逻辑调用：在输出某字段前检查用户是否已同意。
    """
    from app.models.field_consent import FieldConsent

    stmt = select(FieldConsent).where(
        FieldConsent.user_id == user.id,
        FieldConsent.field_path == field_path,
        FieldConsent.jurisdiction == jurisdiction,
        FieldConsent.purpose == purpose,
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row:
        return {"success": True, "data": {"accepted": row.accepted, "accepted_at": row.accepted_at}}
    return {"success": True, "data": {"accepted": False, "accepted_at": None}}

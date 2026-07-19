"""报告导出路由 - 健康摘要、月度趋势、FHIR 导出"""
import json
from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.observation import HealthObservation
from app.models.health_record import HealthProfile
from app.models.diagnosis import DiagnosisResult
from app.api.deps import get_current_user
from app.services.analysis_service import analyze_user_observations
from app.core.fhir_exporter import FHIRExporter

router = APIRouter(tags=["reports"])


@router.get("/health")
async def get_health_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """健康摘要报告 - 聚合用户所有健康数据"""
    # 获取健康档案
    profile_result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    profile_data = None
    if profile:
        profile_data = {
            "name": profile.name,
            "gender": profile.gender,
            "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
            "blood_type": profile.blood_type,
        }

    # 获取活跃诊断
    diag_result = await db.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.user_id == current_user.id,
            DiagnosisResult.status == "confirmed",
        )
    )
    diagnoses = diag_result.scalars().all()
    diagnosis_list = [{"id": str(d.id), "text": d.diagnosis_text, "icd": d.icd_code} for d in diagnoses]

    # 获取健康分析
    analysis = await analyze_user_observations(db, str(current_user.id))

    return {
        "success": True,
        "data": {
            "user_id": str(current_user.id),
            "generated_at": datetime.now().isoformat(),
            "profile": profile_data,
            "analysis": analysis,
            "active_diagnoses": diagnosis_list,
        },
    }


@router.get("/fhir")
async def export_fhir(
    resource_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FHIR R5 格式数据导出"""
    exporter = FHIRExporter()

    result = await db.execute(
        select(HealthObservation)
        .where(HealthObservation.user_id == current_user.id)
        .order_by(HealthObservation.recorded_at.desc())
        .limit(100)
    )
    observations = result.scalars().all()

    entries = []
    for obs in observations:
        obs_dict = {
            "loinc_code": obs.loinc_code,
            "value_numeric": float(obs.value_numeric) if obs.value_numeric else None,
            "value_unit": obs.value_unit,
            "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
        }
        fhir_obs = exporter.export_observation(obs_dict)
        entries.append({"resource": fhir_obs})

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "total": len(entries),
        "entry": entries,
    }

    return {"success": True, "data": bundle}

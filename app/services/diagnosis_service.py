"""西医诊断服务 - 聚合健康数据，调用规则引擎，生成诊断结果"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from app.models.observation import HealthObservation
from app.models.diagnosis import DiagnosisResult
from app.core.diagnosis_engine import WesternDiagnosisEngine


async def trigger_diagnosis(db: AsyncSession, user_id: str) -> dict:
    """触发 AI 诊断: 聚合指标 → 规则引擎分析 → 写入诊断结果"""
    engine = WesternDiagnosisEngine()

    # 1. 从 DB 获取最新指标
    result = await db.execute(
        select(HealthObservation)
        .where(HealthObservation.user_id == user_id)
        .order_by(HealthObservation.recorded_at.desc())
        .limit(100)
    )
    observations = result.scalars().all()

    if not observations:
        return {"status": "no_data", "message": "No health observations found", "findings": []}

    # 2. 转换为引擎输入格式
    obs_dicts = []
    for obs in observations:
        obs_dicts.append({
            "loinc_code": obs.loinc_code,
            "loinc_name": obs.loinc_name,
            "value_numeric": float(obs.value_numeric) if obs.value_numeric is not None else None,
            "value_unit": obs.value_unit,
            "reference_range_low": float(obs.reference_range_low) if obs.reference_range_low is not None else None,
            "reference_range_high": float(obs.reference_range_high) if obs.reference_range_high is not None else None,
        })

    # 3. 调用规则引擎
    findings = engine.diagnose_from_observations(obs_dicts)

    # 4. 写入诊断结果
    created_diagnoses = []
    for finding in findings:
        diagnosis = DiagnosisResult(
            id=str(uuid.uuid4()),
            user_id=user_id,
            diagnosis_text=finding.name,
            icd_code=finding.icd_code,
            confidence=Decimal(str(finding.confidence)),
            severity=finding.severity,
            is_ai_generated=True,
            status="pending",  # 待医生审核
        )
        db.add(diagnosis)
        created_diagnoses.append({
            "id": str(diagnosis.id),
            "name": finding.name,
            "icd_code": finding.icd_code,
            "severity": finding.severity,
            "confidence": finding.confidence,
            "evidence": finding.evidence,
            "recommendations": finding.recommendations,
        })

    await db.commit()
    logger.info(f"Diagnosis complete for user {user_id}: {len(findings)} findings")

    return {
        "status": "completed",
        "total_findings": len(findings),
        "findings": created_diagnoses,
    }

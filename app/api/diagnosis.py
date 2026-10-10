"""西医诊断路由 - AI 诊断触发、诊断历史、诊断审核

**管辖感知（Claims Engine 集成，2026-10-10 阶段 A3）**：
- 每个端点在返回前调用 `filter_output(payload, jurisdiction, endpoint)`，
  按用户法域过滤掉越线字段（icd_code / severity / risk_probability /
  pgx_pathogenic_grading 等），并附加按法域定制的免责声明。
- 端点级开关被策略禁用时（如 EU 的 diagnosis_endpoint=false），
  直接 403 拒绝响应，fail-closed 而非降级放行。
- 完整引擎见 `app/lib/claims_engine.py` + `claims_policy/*.yaml`。
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.diagnosis import DiagnosisResult
from app.models.medication import MedicationRecommendation
from app.api.deps import get_current_user, require_doctor_or_admin
from app.lib.claims_engine import filter_output, check_endpoint_allowed, ClaimsPolicyError

router = APIRouter(tags=["diagnosis"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """触发 AI 诊断的请求参数"""
    include_observations: bool = True
    symptom_description: str | None = None
    record_ids: list[str] | None = None


class ReviewRequest(BaseModel):
    """审核/确认诊断的请求参数"""
    status: str  # "confirmed" | "rejected" | "modified"
    reviewer_notes: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    body: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    触发 AI 辅助诊断分析
    - 收集用户的 HealthObservation 数据
    - 调用规则引擎进行诊断分析
    - 分析完成后写入 DiagnosisResult 表

    管辖感知：按用户 jurisdiction 检查 diagnosis_endpoint 开关，
    EU/US/UK 等严监管法域下会返回 403 拒绝响应。
    """
    jurisdiction = getattr(current_user, "jurisdiction", "cn") or "cn"
    ok, reason = check_endpoint_allowed("/diagnosis/analyze", jurisdiction)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "endpoint_blocked_by_jurisdiction",
                "jurisdiction": jurisdiction,
                "reason": reason,
                "message": (
                    "This endpoint is not available under the claims policy for your jurisdiction. "
                    "HealthLens operates under strict wellness-only boundaries outside the China mainland market."
                ),
            },
        )

    from app.services.diagnosis_service import trigger_diagnosis
    from app.services.runtime_audit import build_events, persist_events

    result = await trigger_diagnosis(db, current_user.id)

    # 简化版运行时审计：对输入/输出做轻量自检（失败静默）
    import json as _json
    try:
        events = build_events(
            endpoint="/api/v1/diagnosis/analyze",
            user_id=str(current_user.id),
            input_text=_json.dumps(body.model_dump(), ensure_ascii=False),
            output_text=_json.dumps(result, ensure_ascii=False),
        )
        await persist_events(db, events)
    except Exception:
        pass

    payload = {"success": True, "data": result}
    try:
        fr = filter_output(payload, jurisdiction, endpoint="/diagnosis/analyze")
        return fr.payload
    except ClaimsPolicyError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "claims_policy_violation", "jurisdiction": jurisdiction, "message": str(e)},
        )


@router.get("/results", response_model=dict)
async def list_diagnosis_results(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status_filter: str | None = Query(None, alias="status", description="状态筛选: pending/confirmed/rejected"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取诊断结果历史列表

    管辖感知：列表返回的每条诊断记录都会按用户法域过滤 ICD/severity 等越线字段。
    """
    jurisdiction = getattr(current_user, "jurisdiction", "cn") or "cn"

    query = select(DiagnosisResult).where(DiagnosisResult.user_id == current_user.id)
    count_query = select(func.count()).select_from(DiagnosisResult).where(
        DiagnosisResult.user_id == current_user.id
    )

    if status_filter:
        query = query.where(DiagnosisResult.status == status_filter)
        count_query = count_query.where(DiagnosisResult.status == status_filter)

    query = query.order_by(DiagnosisResult.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    diagnoses = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for d in diagnoses:
        data.append({
            "id": str(d.id),
            "diagnosis_text": d.diagnosis_text,
            "icd_code": d.icd_code,
            "confidence": float(d.confidence) if d.confidence is not None else None,
            "severity": d.severity,
            "is_ai_generated": d.is_ai_generated,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    payload = {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
    try:
        fr = filter_output(payload, jurisdiction, endpoint="/diagnosis/results")
        return fr.payload
    except ClaimsPolicyError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "claims_policy_violation", "jurisdiction": jurisdiction, "message": str(e)},
        )


@router.get("/results/{result_id}", response_model=dict)
async def get_diagnosis_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取诊断结果详情

    管辖感知：详情返回同样按法域过滤 ICD/severity 等字段。
    """
    jurisdiction = getattr(current_user, "jurisdiction", "cn") or "cn"

    result = await db.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.id == result_id,
            DiagnosisResult.user_id == current_user.id,
        )
    )
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis result not found")

    # 查询关联的用药推荐
    med_result = await db.execute(
        select(MedicationRecommendation).where(
            MedicationRecommendation.diagnosis_id == diagnosis.id
        )
    )
    medications = med_result.scalars().all()

    payload = {
        "success": True,
        "data": {
            "id": str(diagnosis.id),
            "diagnosis_text": diagnosis.diagnosis_text,
            "icd_code": diagnosis.icd_code,
            "confidence": float(diagnosis.confidence) if diagnosis.confidence is not None else None,
            "severity": diagnosis.severity,
            "is_ai_generated": diagnosis.is_ai_generated,
            "reviewed_by": str(diagnosis.reviewed_by) if diagnosis.reviewed_by else None,
            "status": diagnosis.status,
            "created_at": diagnosis.created_at.isoformat() if diagnosis.created_at else None,
            "recommendations": [
                {
                    "id": str(m.id),
                    "drug_name": m.drug_name,
                    "drug_code": m.drug_code,
                    "dosage": m.dosage,
                    "dosage_unit": m.dosage_unit,
                    "frequency": m.frequency,
                    "route": m.route,
                    "pgx_evidence": m.pgx_evidence,
                }
                for m in medications
            ],
        },
    }
    try:
        fr = filter_output(payload, jurisdiction, endpoint="/diagnosis/results")
        return fr.payload
    except ClaimsPolicyError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "claims_policy_violation", "jurisdiction": jurisdiction, "message": str(e)},
        )


@router.put("/results/{result_id}", response_model=dict)
async def review_diagnosis(
    result_id: str,
    body: ReviewRequest,
    current_user: User = Depends(require_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    审核/确认诊断结果
    """
    # 只按 diagnosis_id 查询，允许医生审核任何患者的诊断
    result = await db.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.id == result_id,
        )
    )
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis result not found")

    if body.status not in ("confirmed", "rejected", "modified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status. Must be: confirmed, rejected, or modified",
        )

    diagnosis.status = body.status
    diagnosis.reviewed_by = current_user.id
    await db.commit()
    await db.refresh(diagnosis)

    return {
        "success": True,
        "data": {
            "id": str(diagnosis.id),
            "status": diagnosis.status,
            "reviewed_by": str(diagnosis.reviewed_by) if diagnosis.reviewed_by else None,
        },
    }

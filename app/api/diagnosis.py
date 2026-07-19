"""西医诊断路由 - AI 诊断触发、诊断历史、诊断审核"""
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
    """
    from app.services.diagnosis_service import trigger_diagnosis

    result = await trigger_diagnosis(db, current_user.id)

    return {
        "success": True,
        "data": result,
    }


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
    """
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

    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/results/{result_id}", response_model=dict)
async def get_diagnosis_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取诊断结果详情
    """
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

    return {
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
                    "medication_name": m.medication_name,
                    "dosage": m.dosage,
                    "frequency": m.frequency,
                    "duration": m.duration,
                    "notes": m.notes,
                }
                for m in medications
            ],
        },
    }


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

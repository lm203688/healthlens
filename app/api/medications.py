"""西药路由 - 用药推荐、处方生成、用药历史"""
import uuid
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.diagnosis import DiagnosisResult
from app.models.medication import MedicationRecommendation
from app.models.prescription import Prescription
from app.api.deps import get_current_user, require_doctor_or_admin

router = APIRouter(tags=["medications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PrescribeRequest(BaseModel):
    """生成处方的请求参数"""
    diagnosis_id: str
    notes: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/recommend", response_model=dict)
async def get_recommendations(
    diagnosis_id: str = Query(..., description="关联的诊断 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取基于诊断结果的用药推荐
    - TODO: 结合 PharmacogenomicProfile 数据标注 PGx 证据
    """
    result = await db.execute(
        select(MedicationRecommendation).where(
            MedicationRecommendation.diagnosis_id == diagnosis_id
        )
    )
    recommendations = result.scalars().all()

    data = []
    for rec in recommendations:
        data.append({
            "id": str(rec.id),
            "drug_name": rec.drug_name,
            "drug_code": rec.drug_code,
            "dosage": rec.dosage,
            "dosage_unit": rec.dosage_unit,
            "frequency": rec.frequency,
            "route": rec.route,
            "pgx_evidence": rec.pgx_evidence,
        })

    return {
        "success": True,
        "data": data,
        "meta": {
            "diagnosis_id": str(diagnosis_id),
            "count": len(data),
        },
    }


@router.post("/prescribe", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    body: PrescribeRequest,
    current_user: User = Depends(require_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    生成处方
    - 验证诊断结果存在且属于当前用户
    - 创建 MedicationRecommendation 记录写入 DB
    """
    # 验证诊断存在
    diag_result = await db.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.id == body.diagnosis_id,
            DiagnosisResult.user_id == current_user.id,
        )
    )
    diagnosis = diag_result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")

    # 基于诊断生成用药推荐记录
    # Phase 1: 根据常见 ICD 编码映射基础药物推荐
    DRUG_MAP = {
        "5A11": {"drug_name": "二甲双胍", "drug_code": "A10BA02", "dosage": "500", "dosage_unit": "mg", "frequency": "bid", "route": "口服"},
        "5A14": {"drug_name": "葡萄糖注射液", "drug_code": "V06DC01", "dosage": "20", "dosage_unit": "ml", "frequency": "prn", "route": "静脉注射"},
        "5C70": {"drug_name": "阿托伐他汀", "drug_code": "C10AA05", "dosage": "20", "dosage_unit": "mg", "frequency": "qd", "route": "口服"},
        "5C71": {"drug_name": "非诺贝特", "drug_code": "C10AB02", "dosage": "200", "dosage_unit": "mg", "frequency": "qd", "route": "口服"},
        "BA00": {"drug_name": "水飞蓟素", "drug_code": "A05BA03", "dosage": "140", "dosage_unit": "mg", "frequency": "tid", "route": "口服"},
        "BA20": {"drug_name": "头孢克洛", "drug_code": "J01DC02", "dosage": "250", "dosage_unit": "mg", "frequency": "tid", "route": "口服"},
        "3A00": {"drug_name": "硫酸亚铁", "drug_code": "B03AA07", "dosage": "300", "dosage_unit": "mg", "frequency": "tid", "route": "口服"},
        "GB60": {"drug_name": "尿毒清颗粒", "drug_code": "V03AE", "dosage": "5", "dosage_unit": "g", "frequency": "tid", "route": "口服"},
    }

    drug_info = DRUG_MAP.get(diagnosis.icd_code)
    if not drug_info:
        drug_info = {"drug_name": "待医师确认", "drug_code": None, "dosage": None, "dosage_unit": None, "frequency": None, "route": None}

    recommendation = MedicationRecommendation(
        id=str(uuid.uuid4()),
        diagnosis_id=body.diagnosis_id,
        drug_name=drug_info["drug_name"],
        drug_code=drug_info.get("drug_code"),
        dosage=drug_info.get("dosage"),
        dosage_unit=drug_info.get("dosage_unit"),
        frequency=drug_info.get("frequency"),
        route=drug_info.get("route"),
        pgx_evidence=False,
    )
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)

    return {
        "success": True,
        "data": {
            "prescription_id": str(recommendation.id),
            "diagnosis_id": str(body.diagnosis_id),
            "drug_name": recommendation.drug_name,
            "drug_code": recommendation.drug_code,
            "dosage": recommendation.dosage,
            "dosage_unit": recommendation.dosage_unit,
            "frequency": recommendation.frequency,
            "route": recommendation.route,
            "status": "draft",
        },
    }


@router.get("/history", response_model=dict)
async def get_medication_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用药历史记录 - 查询用户的处方历史
    """
    # 通过关联的 DiagnosisResult 查询当前用户的 MedicationRecommendation
    query = (
        select(MedicationRecommendation)
        .join(DiagnosisResult, MedicationRecommendation.diagnosis_id == DiagnosisResult.id)
        .where(DiagnosisResult.user_id == current_user.id)
    )
    count_query = (
        select(func.count())
        .select_from(MedicationRecommendation)
        .join(DiagnosisResult, MedicationRecommendation.diagnosis_id == DiagnosisResult.id)
        .where(DiagnosisResult.user_id == current_user.id)
    )

    query = query.order_by(MedicationRecommendation.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    recommendations = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for rec in recommendations:
        data.append({
            "id": str(rec.id),
            "diagnosis_id": str(rec.diagnosis_id),
            "drug_name": rec.drug_name,
            "drug_code": rec.drug_code,
            "dosage": rec.dosage,
            "dosage_unit": rec.dosage_unit,
            "frequency": rec.frequency,
            "route": rec.route,
            "pgx_evidence": rec.pgx_evidence,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
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


# ---------------------------------------------------------------------------
# Prescription CRUD
# ---------------------------------------------------------------------------


class PrescriptionMedicationItem(BaseModel):
    """处方中的药物条目"""
    drug_name: str
    drug_code: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    duration: str | None = None


class PrescriptionCreateInput(BaseModel):
    """创建处方"""
    diagnosis_id: str | None = None
    medications: list[PrescriptionMedicationItem] = Field(..., min_length=1)
    notes: str | None = None


class PrescriptionUpdateInput(BaseModel):
    """更新处方状态"""
    status: str = Field(..., description="目标状态: activate / discontinue")


@router.post("/prescriptions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    body: PrescriptionCreateInput,
    current_user: User = Depends(require_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    医生创建处方
    """
    # 如果指定了 diagnosis_id，验证其存在
    if body.diagnosis_id:
        diag_result = await db.execute(
            select(DiagnosisResult).where(DiagnosisResult.id == body.diagnosis_id)
        )
        diagnosis = diag_result.scalar_one_or_none()
        if not diagnosis:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")

    # 生成处方编号: RX + 年月日 + 4位序号
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    # 查询今天已有的处方数量，用于生成序号
    today_start = datetime.combine(
        datetime.now(timezone.utc).date(),
        datetime.min.time(),
    ).replace(tzinfo=timezone.utc)
    count_result = await db.execute(
        select(func.count()).select_from(Prescription).where(
            Prescription.prescribed_at >= today_start,
        )
    )
    today_count = count_result.scalar() or 0
    seq = today_count + 1
    prescription_no = f"RX{today_str}{seq:04d}"

    medications_data = [item.model_dump() for item in body.medications]

    prescription = Prescription(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        diagnosis_id=body.diagnosis_id,
        prescription_no=prescription_no,
        status="draft",
        medications=medications_data,
        notes=body.notes,
        prescribed_at=datetime.now(timezone.utc),
        prescribed_by=current_user.id,
    )
    db.add(prescription)
    await db.commit()
    await db.refresh(prescription)

    return {
        "success": True,
        "data": {
            "id": str(prescription.id),
            "prescription_no": prescription.prescription_no,
            "user_id": str(prescription.user_id),
            "diagnosis_id": str(prescription.diagnosis_id) if prescription.diagnosis_id else None,
            "status": prescription.status,
            "medications": prescription.medications,
            "notes": prescription.notes,
            "prescribed_at": prescription.prescribed_at.isoformat() if prescription.prescribed_at else None,
            "prescribed_by": str(prescription.prescribed_by) if prescription.prescribed_by else None,
            "created_at": prescription.created_at.isoformat() if prescription.created_at else None,
        },
    }


@router.get("/prescriptions", response_model=dict)
async def list_prescriptions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status_filter: str | None = Query(None, alias="status", description="状态筛选: draft/active/discontinued"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户查看自己的处方列表（分页）"""
    query = select(Prescription).where(Prescription.user_id == current_user.id)
    count_query = select(func.count()).select_from(Prescription).where(
        Prescription.user_id == current_user.id
    )

    if status_filter:
        query = query.where(Prescription.status == status_filter)
        count_query = count_query.where(Prescription.status == status_filter)

    query = query.order_by(Prescription.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    prescriptions = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for p in prescriptions:
        data.append({
            "id": str(p.id),
            "prescription_no": p.prescription_no,
            "diagnosis_id": str(p.diagnosis_id) if p.diagnosis_id else None,
            "status": p.status,
            "medications": p.medications,
            "notes": p.notes,
            "prescribed_at": p.prescribed_at.isoformat() if p.prescribed_at else None,
            "prescribed_by": str(p.prescribed_by) if p.prescribed_by else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
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


@router.get("/prescriptions/{prescription_id}", response_model=dict)
async def get_prescription_detail(
    prescription_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取处方详情"""
    result = await db.execute(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.user_id == current_user.id,
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")

    return {
        "success": True,
        "data": {
            "id": str(prescription.id),
            "prescription_no": prescription.prescription_no,
            "diagnosis_id": str(prescription.diagnosis_id) if prescription.diagnosis_id else None,
            "status": prescription.status,
            "medications": prescription.medications,
            "notes": prescription.notes,
            "prescribed_at": prescription.prescribed_at.isoformat() if prescription.prescribed_at else None,
            "prescribed_by": str(prescription.prescribed_by) if prescription.prescribed_by else None,
            "created_at": prescription.created_at.isoformat() if prescription.created_at else None,
            "updated_at": prescription.updated_at.isoformat() if prescription.updated_at else None,
        },
    }


@router.put("/prescriptions/{prescription_id}", response_model=dict)
async def update_prescription_status(
    prescription_id: str,
    body: PrescriptionUpdateInput,
    current_user: User = Depends(require_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    更新处方状态（activate / discontinue），仅医生可操作
    设计意图：更新状态时不限制必须是开具者本人，因为其他医生也应该可以调整处方状态
    """
    result = await db.execute(
        select(Prescription).where(Prescription.id == prescription_id)
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")

    if body.status not in ("activate", "discontinue"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status. Must be: activate or discontinue",
        )

    target_status = "active" if body.status == "activate" else "discontinued"
    prescription.status = target_status
    await db.commit()
    await db.refresh(prescription)

    return {
        "success": True,
        "data": {
            "id": str(prescription.id),
            "prescription_no": prescription.prescription_no,
            "status": prescription.status,
        },
    }

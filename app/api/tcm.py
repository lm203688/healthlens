"""中医模块路由 - 体质、舌象、辨证、方剂、配送、中药"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.tcm_profile import TcmProfile
from app.models.tcm_tongue import TongueImage
from app.models.tcm_syndrome import TcmSyndromeDiagnosis
from app.models.tcm_formula import (
    TcmFormulaRecommendation,
    TcmFormulaLibrary,
    TcmHerb,
    TcmDeliveryOrder,
)
from app.api.deps import get_current_user, require_doctor_or_admin

router = APIRouter(tags=["tcm"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConstitutionSubmitInput(BaseModel):
    """提交体质问卷"""
    questionnaire_data: dict


NINE_TYPES = Literal["pinghe", "qixu", "yangxu", "yinxu", "tanshi", "shire", "xueyu", "qiyu", "tebing"]

class ConstitutionUpdateInput(BaseModel):
    """更新体质档案"""
    constitution_type: NINE_TYPES | None = None
    constitution_score: dict | None = None
    questionnaire_data: dict | None = None


class TcmReviewRequest(BaseModel):
    """审核辨证结果"""
    status: str  # "confirmed" | "rejected" | "modified"
    reviewer_notes: str | None = None


class FormulaRecommendRequest(BaseModel):
    """方剂推荐请求"""
    syndrome_id: str


class FormulaLibrarySearchQuery(BaseModel):
    """方剂库搜索参数 - 通过 Query 传参，此处仅作文档"""


class OrderCreateInput(BaseModel):
    """创建配送订单"""
    formula_id: str
    delivery_address: str
    notes: str | None = None


# ---------------------------------------------------------------------------
# 体质 (Constitution)
# ---------------------------------------------------------------------------

@router.post("/constitution", response_model=dict, status_code=status.HTTP_201_CREATED)
async def submit_constitution(
    body: ConstitutionSubmitInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    提交体质问卷 - 调用 AI 体质辨识算法，计算体质类型和评分
    """
    from app.services.tcm_service import analyze_constitution

    # 检查是否已有档案
    result = await db.execute(
        select(TcmProfile).where(TcmProfile.user_id == current_user.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.questionnaire_data = body.questionnaire_data
        existing.assessed_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        profile = TcmProfile(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            questionnaire_data=body.questionnaire_data,
            assessed_at=datetime.now(timezone.utc),
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    # 调用体质辨识服务
    analysis = await analyze_constitution(db, current_user.id, body.questionnaire_data)

    return {
        "success": True,
        "data": analysis,
    }


@router.get("/constitution", response_model=dict)
async def get_constitution(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的体质档案"""
    result = await db.execute(
        select(TcmProfile).where(TcmProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        return {
            "success": True,
            "data": None,
            "meta": {"message": "No constitution profile found"},
        }

    return {
        "success": True,
        "data": {
            "id": str(profile.id),
            "constitution_type": profile.constitution_type,
            "constitution_score": profile.constitution_score,
            "questionnaire_data": profile.questionnaire_data,
            "assessed_at": profile.assessed_at.isoformat() if profile.assessed_at else None,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
        },
    }


@router.put("/constitution", response_model=dict)
async def update_constitution(
    body: ConstitutionUpdateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新体质档案
    """
    result = await db.execute(
        select(TcmProfile).where(TcmProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Constitution profile not found")

    if body.constitution_type is not None:
        profile.constitution_type = body.constitution_type
    if body.constitution_score is not None:
        from app.core.tcm_engine import CONSTITUTION_DIMENSIONS
        valid_keys = set(CONSTITUTION_DIMENSIONS.keys())
        invalid_keys = set(body.constitution_score.keys()) - valid_keys
        if invalid_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid constitution_score keys: {invalid_keys}. Valid keys: {valid_keys}",
            )
        profile.constitution_score = body.constitution_score
    if body.questionnaire_data is not None:
        profile.questionnaire_data = body.questionnaire_data

    await db.commit()
    await db.refresh(profile)

    return {
        "success": True,
        "data": {
            "id": str(profile.id),
            "constitution_type": profile.constitution_type,
            "constitution_score": profile.constitution_score,
            "assessed_at": profile.assessed_at.isoformat() if profile.assessed_at else None,
        },
    }


# ---------------------------------------------------------------------------
# 舌象 (Tongue)
# ---------------------------------------------------------------------------

@router.post("/tongue/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_tongue_image(
    file: UploadFile = File(..., description="舌象照片"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传舌象照片并自动分析舌色、舌形、苔色、苔质"""
    allowed_types = {"image/jpeg", "image/png", "image/jpg"}
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type: {file.content_type}",
        )

    content = await file.read()

    # 调用舌象分析引擎
    from app.core.tcm_tongue_analyzer import TongueAnalyzer
    analyzer = TongueAnalyzer()
    analysis_result = await analyzer.analyze_async(content)

    # 保存到本地 (Phase 1: 本地存储, Phase 2: MinIO)
    import os
    from pathlib import Path
    upload_dir = Path("data/tongue_images") / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    tongue_id = str(uuid.uuid4())
    ext = ".jpg" if "jpeg" in (file.content_type or "") else ".png"
    file_path = upload_dir / f"{tongue_id}{ext}"
    with open(file_path, "wb") as f:
        f.write(content)

    # 写入数据库
    tongue_image = TongueImage(
        id=tongue_id,
        user_id=str(current_user.id),
        image_url=str(file_path),
        tongue_color=analysis_result.tongue_color,
        tongue_shape=analysis_result.tongue_shape,
        coating_color=analysis_result.coating_color,
        coating_quality=analysis_result.coating_quality,
        sublingual_vein=analysis_result.sublingual_vein,
        ai_analysis={
            "syndrome_hint": analysis_result.syndrome_hint,
            "confidence": analysis_result.confidence,
            "raw_metrics": analysis_result.raw_metrics,
        },
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(tongue_image)
    await db.commit()

    return {
        "success": True,
        "data": {
            "id": tongue_id,
            "filename": file.filename,
            "status": "analyzed",
            "tongue_color": analysis_result.tongue_color,
            "tongue_shape": analysis_result.tongue_shape,
            "coating_color": analysis_result.coating_color,
            "coating_quality": analysis_result.coating_quality,
            "syndrome_hint": analysis_result.syndrome_hint,
            "confidence": analysis_result.confidence,
        },
    }


@router.get("/tongue", response_model=dict)
async def list_tongue_images(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取舌象历史记录"""
    query = select(TongueImage).where(TongueImage.user_id == current_user.id)
    count_query = select(func.count()).select_from(TongueImage).where(
        TongueImage.user_id == current_user.id
    )

    query = query.order_by(TongueImage.recorded_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    images = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for img in images:
        data.append({
            "id": str(img.id),
            "image_url": img.image_url,
            "tongue_color": img.tongue_color,
            "tongue_shape": img.tongue_shape,
            "coating_color": img.coating_color,
            "coating_quality": img.coating_quality,
            "sublingual_vein": img.sublingual_vein,
            "ai_analysis": img.ai_analysis,
            "recorded_at": img.recorded_at.isoformat() if img.recorded_at else None,
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


@router.get("/tongue/{tongue_id}", response_model=dict)
async def get_tongue_detail(
    tongue_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取舌象详情"""
    result = await db.execute(
        select(TongueImage).where(
            TongueImage.id == tongue_id,
            TongueImage.user_id == current_user.id,
        )
    )
    tongue = result.scalar_one_or_none()
    if not tongue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tongue image not found")

    return {
        "success": True,
        "data": {
            "id": str(tongue.id),
            "image_url": tongue.image_url,
            "tongue_color": tongue.tongue_color,
            "tongue_shape": tongue.tongue_shape,
            "coating_color": tongue.coating_color,
            "coating_quality": tongue.coating_quality,
            "sublingual_vein": tongue.sublingual_vein,
            "ai_analysis": tongue.ai_analysis,
            "reviewed_by": str(tongue.reviewed_by) if tongue.reviewed_by else None,
            "recorded_at": tongue.recorded_at.isoformat() if tongue.recorded_at else None,
        },
    }


# ---------------------------------------------------------------------------
# 辨证 (Syndrome Diagnosis)
# ---------------------------------------------------------------------------

@router.post("/diagnose", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def trigger_tcm_diagnosis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    触发 AI 辨证分析
    - 收集体质档案信息
    - 调用中医辨证引擎
    - 写入 TcmSyndromeDiagnosis
    """
    from app.services.tcm_service import diagnose_syndrome
    from decimal import Decimal
    import uuid as _uuid

    # 获取体质档案
    profile_result = await db.execute(
        select(TcmProfile).where(TcmProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    constitution_type = profile.constitution_type if profile else None

    # 构造症状列表（从体质关键词提取，Phase 1 简化版）
    symptoms = []
    if profile and profile.constitution_type:
        from app.core.tcm_engine import CONSTITUTION_DIMENSIONS

        # 支持中文名称→key 的反向查找
        dim_key = None
        for k, v in CONSTITUTION_DIMENSIONS.items():
            if v["name"] == profile.constitution_type or k == profile.constitution_type:
                dim_key = k
                break

        dim_info = CONSTITUTION_DIMENSIONS.get(dim_key, {})
        symptoms = dim_info.get("keywords", [])

    # 调用辨证服务
    result = await diagnose_syndrome(
        db, current_user.id, symptoms,
        constitution=constitution_type,
    )

    syndrome = result.get("syndrome", {})

    # 写入辨证诊断记录
    syndrome_record = TcmSyndromeDiagnosis(
        id=str(_uuid.uuid4()),
        user_id=current_user.id,
        syndrome_code=syndrome.get("syndrome_code"),
        syndrome_name=syndrome.get("syndrome_name"),
        principle=syndrome.get("principle"),
        confidence=Decimal(str(syndrome.get("confidence", 0.5))),
        evidence=syndrome.get("matched_symptoms"),
        is_ai_generated=True,
        status="pending",
    )
    db.add(syndrome_record)
    await db.commit()
    await db.refresh(syndrome_record)

    return {
        "success": True,
        "data": {
            "id": str(syndrome_record.id),
            "syndrome_code": syndrome_record.syndrome_code,
            "syndrome_name": syndrome_record.syndrome_name,
            "principle": syndrome_record.principle,
            "confidence": float(syndrome_record.confidence) if syndrome_record.confidence else None,
            "status": syndrome_record.status,
        },
    }


@router.get("/diagnose/results", response_model=dict)
async def list_tcm_diagnoses(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取辨证诊断结果列表"""
    query = select(TcmSyndromeDiagnosis).where(TcmSyndromeDiagnosis.user_id == current_user.id)
    count_query = select(func.count()).select_from(TcmSyndromeDiagnosis).where(
        TcmSyndromeDiagnosis.user_id == current_user.id
    )

    if status_filter:
        query = query.where(TcmSyndromeDiagnosis.status == status_filter)

    query = query.order_by(TcmSyndromeDiagnosis.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    diagnoses = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for d in diagnoses:
        data.append({
            "id": str(d.id),
            "syndrome_code": d.syndrome_code,
            "syndrome_name": d.syndrome_name,
            "principle": d.principle,
            "confidence": float(d.confidence) if d.confidence else None,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "formula_recommendations": await _get_formula_recs(d.id, db),
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


async def _get_formula_recs(syndrome_id: str, db: AsyncSession) -> list[dict]:
    """获取辨证关联的方剂推荐"""
    from sqlalchemy import select as _select
    result = await db.execute(
        _select(TcmFormulaRecommendation).where(
            TcmFormulaRecommendation.syndrome_id == syndrome_id
        )
    )
    recs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "formula_name": r.formula_name,
            "formula_source": r.formula_source,
            "composition": r.original_composition,
            "additions": r.additions,
            "dosage_instructions": r.dosage_instructions,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recs
    ]


@router.get("/diagnose/results/{result_id}", response_model=dict)
async def get_tcm_diagnosis_detail(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取辨证结果详情
    """
    result = await db.execute(
        select(TcmSyndromeDiagnosis).where(
            TcmSyndromeDiagnosis.id == result_id,
            TcmSyndromeDiagnosis.user_id == current_user.id,
        )
    )
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TCM diagnosis not found")

    return {
        "success": True,
        "data": {
            "id": str(diagnosis.id),
            "syndrome_code": diagnosis.syndrome_code,
            "syndrome_name": diagnosis.syndrome_name,
            "principle": diagnosis.principle,
            "confidence": float(diagnosis.confidence) if diagnosis.confidence is not None else None,
            "evidence": diagnosis.evidence,
            "is_ai_generated": diagnosis.is_ai_generated,
            "reviewed_by": str(diagnosis.reviewed_by) if diagnosis.reviewed_by else None,
            "status": diagnosis.status,
            "diagnosis_id": str(diagnosis.diagnosis_id) if diagnosis.diagnosis_id else None,
            "created_at": diagnosis.created_at.isoformat() if diagnosis.created_at else None,
            # 关联的方剂推荐
            "formula_recommendations": await _get_formula_recs(diagnosis.id, db),
        },
    }


@router.put("/diagnose/results/{result_id}", response_model=dict)
async def review_tcm_diagnosis(
    result_id: str,
    body: TcmReviewRequest,
    current_user: User = Depends(require_doctor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    审核辨证结果
    """
    result = await db.execute(
        select(TcmSyndromeDiagnosis).where(
            TcmSyndromeDiagnosis.id == result_id,
            TcmSyndromeDiagnosis.user_id == current_user.id,
        )
    )
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TCM diagnosis not found")

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


# ---------------------------------------------------------------------------
# 方剂 (Formula)
# ---------------------------------------------------------------------------

@router.post("/formula/recommend", response_model=dict, status_code=status.HTTP_201_CREATED)
async def recommend_formula(
    body: FormulaRecommendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    根据辨证结果推荐方剂
    - 基于辨证结论从方剂库中匹配推荐
    - 根据个体差异进行加减化裁
    - 写入 TcmFormulaRecommendation
    """
    from app.core.tcm_engine import TcmDiagnosisEngine
    from decimal import Decimal

    # 验证辨证存在
    result = await db.execute(
        select(TcmSyndromeDiagnosis).where(
            TcmSyndromeDiagnosis.id == body.syndrome_id,
            TcmSyndromeDiagnosis.user_id == current_user.id,
        )
    )
    syndrome = result.scalar_one_or_none()
    if not syndrome:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Syndrome diagnosis not found")

    # 调用引擎推荐方剂
    tcm_engine = TcmDiagnosisEngine()
    formula = tcm_engine.recommend_formula(
        syndrome_code=syndrome.principle or "",
        patient_signs={"principle": syndrome.principle},
    )

    # 写入方剂推荐记录
    recommendation = TcmFormulaRecommendation(
        id=str(uuid.uuid4()),
        syndrome_id=str(syndrome.id),
        formula_name=formula.get("formula"),
        formula_source=formula.get("source"),
        original_composition=formula.get("composition"),
        modified_composition=formula.get("composition"),
        additions=formula.get("extra_herbs"),
        dosage_instructions="水煎服，日一剂，分两次温服",
    )
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)

    return {
        "success": True,
        "data": {
            "recommendation_id": str(recommendation.id),
            "syndrome_id": str(body.syndrome_id),
            "formula_name": recommendation.formula_name,
            "formula_source": recommendation.formula_source,
            "composition": recommendation.original_composition,
            "additions": recommendation.additions,
            "dosage_instructions": recommendation.dosage_instructions,
            "status": "recommended",
        },
    }


@router.get("/formula/library", response_model=dict)
async def search_formula_library(
    keyword: str | None = Query(None, description="搜索关键词（方名/功效）"),
    category: str | None = Query(None, description="分类筛选"),
    syndrome_code: str | None = Query(None, description="按证候代码筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """搜索方剂库"""
    query = select(TcmFormulaLibrary)
    count_query = select(func.count()).select_from(TcmFormulaLibrary)

    if keyword:
        query = query.where(
            TcmFormulaLibrary.formula_name.ilike(f"%{keyword}%")
            | TcmFormulaLibrary.indications.ilike(f"%{keyword}%")
        )
        count_query = count_query.where(
            TcmFormulaLibrary.formula_name.ilike(f"%{keyword}%")
            | TcmFormulaLibrary.indications.ilike(f"%{keyword}%")
        )

    if category:
        query = query.where(TcmFormulaLibrary.category == category)
        count_query = count_query.where(TcmFormulaLibrary.category == category)

    if syndrome_code:
        query = query.where(TcmFormulaLibrary.syndrome_code == syndrome_code)
        count_query = count_query.where(TcmFormulaLibrary.syndrome_code == syndrome_code)

    query = query.order_by(TcmFormulaLibrary.formula_name.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    formulas = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for f in formulas:
        data.append({
            "id": str(f.id),
            "formula_name": f.formula_name,
            "formula_name_en": f.formula_name_en,
            "source": f.source,
            "category": f.category,
            "composition": f.composition,
            "dosage": f.dosage,
            "indications": f.indications,
            "syndrome_code": f.syndrome_code,
            "contraindications": f.contraindications,
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
# 配送订单 (Delivery Order)
# ---------------------------------------------------------------------------

@router.post("/order/create", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_delivery_order(
    body: OrderCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建中药配送订单
    - 验证方剂推荐存在
    - 创建订单并调用配送服务
    """
    from app.services.tcm_service import create_delivery_order as svc_create_order

    result = await svc_create_order(db, current_user.id, body.formula_id, body.delivery_address)

    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("message"))

    return {
        "success": True,
        "data": result,
    }


@router.get("/order/{order_id}", response_model=dict)
async def get_order_detail(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取配送订单详情"""
    result = await db.execute(
        select(TcmDeliveryOrder).where(
            TcmDeliveryOrder.id == order_id,
            TcmDeliveryOrder.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return {
        "success": True,
        "data": {
            "id": str(order.id),
            "formula_id": str(order.formula_id) if order.formula_id else None,
            "pharmacy_name": order.pharmacy_name,
            "order_status": order.order_status,
            "tracking_number": order.tracking_number,
            "delivery_address": order.delivery_address,
            "total_fee": float(order.total_fee) if order.total_fee is not None else None,
            "doctor_signature": order.doctor_signature,
            "ordered_at": order.ordered_at.isoformat() if order.ordered_at else None,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    }


@router.get("/orders", response_model=dict)
async def list_orders(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    order_status: str | None = Query(None, alias="status", description="状态筛选"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取订单历史列表"""
    query = select(TcmDeliveryOrder).where(TcmDeliveryOrder.user_id == current_user.id)
    count_query = select(func.count()).select_from(TcmDeliveryOrder).where(
        TcmDeliveryOrder.user_id == current_user.id
    )

    if order_status:
        query = query.where(TcmDeliveryOrder.order_status == order_status)
        count_query = count_query.where(TcmDeliveryOrder.order_status == order_status)

    query = query.order_by(TcmDeliveryOrder.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    orders = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for o in orders:
        data.append({
            "id": str(o.id),
            "pharmacy_name": o.pharmacy_name,
            "order_status": o.order_status,
            "tracking_number": o.tracking_number,
            "total_fee": float(o.total_fee) if o.total_fee is not None else None,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
            "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
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


@router.put("/order/{order_id}/cancel", response_model=dict)
async def cancel_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    取消配送订单
    - TODO: 通知药房取消
    """
    result = await db.execute(
        select(TcmDeliveryOrder).where(
            TcmDeliveryOrder.id == order_id,
            TcmDeliveryOrder.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.order_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel order in '{order.order_status}' status",
        )

    order.order_status = "cancelled"
    await db.commit()
    await db.refresh(order)

    return {
        "success": True,
        "data": {
            "id": str(order.id),
            "order_status": order.order_status,
            "message": "Order cancelled",
        },
    }


# ---------------------------------------------------------------------------
# 中药 (Herbs)
# ---------------------------------------------------------------------------

@router.get("/herbs", response_model=dict)
async def list_herbs(
    keyword: str | None = Query(None, description="搜索关键词（药名/拼音/功效）"),
    category: str | None = Query(None, description="分类筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """中药查询"""
    query = select(TcmHerb)
    count_query = select(func.count()).select_from(TcmHerb)

    if keyword:
        query = query.where(
            TcmHerb.herb_name.ilike(f"%{keyword}%")
            | TcmHerb.pinyin.ilike(f"%{keyword}%")
            | TcmHerb.efficacy.ilike(f"%{keyword}%")
            | TcmHerb.herb_name_en.ilike(f"%{keyword}%")
        )
        count_query = count_query.where(
            TcmHerb.herb_name.ilike(f"%{keyword}%")
            | TcmHerb.pinyin.ilike(f"%{keyword}%")
            | TcmHerb.efficacy.ilike(f"%{keyword}%")
            | TcmHerb.herb_name_en.ilike(f"%{keyword}%")
        )

    if category:
        query = query.where(TcmHerb.category == category)
        count_query = count_query.where(TcmHerb.category == category)

    query = query.order_by(TcmHerb.herb_name.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    herbs = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for h in herbs:
        data.append({
            "id": str(h.id),
            "herb_name": h.herb_name,
            "herb_name_en": h.herb_name_en,
            "pinyin": h.pinyin,
            "category": h.category,
            "property": h.property,
            "flavor": h.flavor,
            "meridian": h.meridian,
            "efficacy": h.efficacy,
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


@router.get("/herbs/{herb_id}", response_model=dict)
async def get_herb_detail(
    herb_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取中药详情"""
    result = await db.execute(select(TcmHerb).where(TcmHerb.id == herb_id))
    herb = result.scalar_one_or_none()
    if not herb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Herb not found")

    return {
        "success": True,
        "data": {
            "id": str(herb.id),
            "herb_name": herb.herb_name,
            "herb_name_en": herb.herb_name_en,
            "pinyin": herb.pinyin,
            "category": herb.category,
            "property": herb.property,
            "flavor": herb.flavor,
            "meridian": herb.meridian,
            "efficacy": herb.efficacy,
            "usage_dosage": herb.usage_dosage,
            "contraindications": herb.contraindications,
            "chemical_components": herb.chemical_components,
            "cyp450_metabolism": herb.cyp450_metabolism,
        },
    }

"""中医古籍知识库路由 - 食疗、非药物治疗、古籍查询"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.tcm_knowledge import FoodTherapyRecipe, ClassicalFormula, NonPharmaTreatment, TcmClassicalBook
from app.api.deps import get_current_user

router = APIRouter(tags=["knowledge"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FoodTherapyQuery(BaseModel):
    """食疗推荐请求"""
    constitution_type: str | None = None  # qixu, yangxu, yinxu, tanshi, shire, xueyu, qiyu, tebing, pinghe
    symptoms: list[str] | None = None
    seasonal: str | None = None  # spring/summer/autumn/winter
    limit: int = 5


class NonPharmaQuery(BaseModel):
    """非药物治疗推荐请求"""
    constitution_type: str
    symptoms: list[str] | None = None
    treatment_types: list[str] | None = None  # diet/acupressure/massage/qigong/lifestyle
    limit: int = 5


# ---------------------------------------------------------------------------
# 食疗推荐 (核心功能)
# ---------------------------------------------------------------------------

@router.post("/food-therapy/recommend", response_model=dict)
async def recommend_food_therapy(
    body: FoodTherapyQuery,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    基于体质和症状推荐古籍食疗方案
    - 支持体质过滤 (九种体质)
    - 支持症状关键词匹配
    - 支持季节推荐
    """
    from app.core.tcm_food_therapy import FoodTherapyEngine

    engine = FoodTherapyEngine()

    if body.symptoms:
        recommendations = engine.recommend_by_symptoms(
            symptoms=body.symptoms,
            constitution_type=body.constitution_type,
            limit=body.limit,
        )
    else:
        if not body.constitution_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either constitution_type or symptoms",
            )
        recommendations = engine.recommend_by_constitution(
            constitution_type=body.constitution_type,
            seasonal=body.seasonal,
            limit=body.limit,
        )

    data = []
    for rec in recommendations:
        data.append({
            "name": rec.name,
            "category": rec.category,
            "ingredients": rec.ingredients,
            "indications": rec.indications,
            "method": rec.method,
            "source": rec.source,
            "match_reason": rec.match_reason,
            "seasonal": rec.seasonal,
        })

    return {
        "success": True,
        "data": data,
        "meta": {"count": len(data)},
    }


# ---------------------------------------------------------------------------
# 非药物治疗推荐
# ---------------------------------------------------------------------------

@router.post("/non-pharma/recommend", response_model=dict)
async def recommend_non_pharma(
    body: NonPharmaQuery,
    current_user: User = Depends(get_current_user),
):
    """
    获取非药物治疗方案
    - 穴位按压 (acupressure)
    - 推拿按摩 (massage)
    - 气功导引 (qigong)
    - 起居调养 (lifestyle)
    - 食疗建议 (diet)
    """
    from app.core.tcm_food_therapy import FoodTherapyEngine

    engine = FoodTherapyEngine()
    recommendations = engine.get_non_pharma_treatments(
        constitution_type=body.constitution_type,
        symptoms=body.symptoms,
        treatment_types=body.treatment_types,
        limit=body.limit,
    )

    data = []
    for rec in recommendations:
        data.append({
            "treatment_type": rec.treatment_type,
            "treatment_type_name": rec.treatment_type_name,
            "name": rec.name,
            "description": rec.description,
            "indications": rec.indications,
            "instructions": rec.instructions,
            "frequency": rec.frequency,
            "duration": rec.duration,
            "precautions": rec.precautions,
            "source": rec.source,
        })

    return {
        "success": True,
        "data": data,
        "meta": {"count": len(data)},
    }


# ---------------------------------------------------------------------------
# 综合调理方案 (体质 -> 食疗 + 非药物 + 季节建议)
# ---------------------------------------------------------------------------

@router.get("/wellness-plan", response_model=dict)
async def get_wellness_plan(
    constitution_type: str = Query(..., description="体质类型"),
    current_user: User = Depends(get_current_user),
):
    """
    获取综合调理方案:
    1. 体质分析
    2. 食疗推荐 (3个)
    3. 非药物治疗 (3个)
    4. 季节饮食建议
    5. 日常注意事项
    """
    from app.core.tcm_food_therapy import FoodTherapyEngine
    from app.core.tcm_engine import CONSTITUTION_DIMENSIONS

    engine = FoodTherapyEngine()

    # 体质信息
    const_info = CONSTITUTION_DIMENSIONS.get(constitution_type, {})

    # 食疗推荐
    food_recs = engine.recommend_by_constitution(
        constitution_type=constitution_type, limit=3
    )

    # 非药物治疗
    non_pharma = engine.get_non_pharma_treatments(
        constitution_type=constitution_type, limit=3
    )

    # 体质膳食通用建议
    diet_guide = engine.get_non_pharma_treatments(
        constitution_type=constitution_type,
        treatment_types=["diet"],
        limit=1,
    )

    return {
        "success": True,
        "data": {
            "constitution": {
                "type": constitution_type,
                "name": const_info.get("name", constitution_type),
                "keywords": const_info.get("keywords", []),
            },
            "food_therapy": [
                {
                    "name": r.name,
                    "category": r.category,
                    "ingredients": r.ingredients,
                    "indications": r.indications,
                    "method": r.method,
                    "source": r.source,
                }
                for r in food_recs
            ],
            "non_pharma_treatments": [
                {
                    "type": r.treatment_type,
                    "type_name": r.treatment_type_name,
                    "name": r.name,
                    "description": r.description,
                    "instructions": r.instructions,
                    "frequency": r.frequency,
                    "duration": r.duration,
                }
                for r in non_pharma
            ],
            "diet_guide": [
                {
                    "name": r.name,
                    "instructions": r.instructions,
                    "source": r.source,
                }
                for r in diet_guide
            ],
        },
    }


# ---------------------------------------------------------------------------
# 古籍书目查询
# ---------------------------------------------------------------------------

@router.get("/books", response_model=dict)
async def list_classical_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None, description="分类: 本草/方剂/食疗/针灸/综合"),
    db: AsyncSession = Depends(get_db),
):
    """查询中医古籍书目列表"""
    query = select(TcmClassicalBook)
    count_query = select(func.count()).select_from(TcmClassicalBook)

    if category:
        query = query.where(TcmClassicalBook.category == category)
        count_query = count_query.where(TcmClassicalBook.category == category)

    query = query.order_by(TcmClassicalBook.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    books = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 701  # fallback to known count

    data = []
    for book in books:
        data.append({
            "id": str(book.id),
            "title": book.title,
            "author": book.author,
            "dynasty": book.dynasty,
            "year_text": book.year_text,
            "category": book.category,
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
# 食疗方库搜索
# ---------------------------------------------------------------------------

@router.get("/food-therapy/search", response_model=dict)
async def search_food_therapy(
    keyword: str = Query(..., description="搜索关键词(食材/症状/方名)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """搜索食疗方库"""
    like_pattern = f"%{keyword}%"
    query = select(FoodTherapyRecipe).where(
        FoodTherapyRecipe.name.ilike(like_pattern)
        | FoodTherapyRecipe.indications.ilike(like_pattern)
    )
    count_query = select(func.count()).select_from(FoodTherapyRecipe).where(
        FoodTherapyRecipe.name.ilike(like_pattern)
        | FoodTherapyRecipe.indications.ilike(like_pattern)
    )

    query = query.order_by(FoodTherapyRecipe.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    recipes = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for r in recipes:
        data.append({
            "id": str(r.id),
            "name": r.name,
            "source_book": r.source_book,
            "category": r.category,
            "ingredients": r.ingredients,
            "indications": r.indications,
            "method": r.method,
            "seasonal": r.seasonal,
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

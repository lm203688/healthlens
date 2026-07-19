"""健康指标路由 - 指标列表、趋势数据、最新汇总、创建"""
import uuid
import math
from datetime import datetime, date
from decimal import Decimal
from typing import Literal
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.observation import HealthObservation
from app.api.deps import get_current_user

router = APIRouter(tags=["observations"])


# ── Pydantic Schemas ──────────────────────────────────────────────


class ObservationCreateInput(BaseModel):
    """单条健康指标创建输入"""
    loinc_code: str | None = Field(None, max_length=50, description="LOINC 编码")
    loinc_name: str | None = Field(None, max_length=500, description="LOINC 名称")
    value_numeric: float | None = Field(None, description="数值型结果")
    value_string: str | None = Field(None, description="字符串型结果")
    value_unit: str | None = Field(None, max_length=50, description="单位")
    reference_range_low: float | None = Field(None, description="参考范围下限")
    reference_range_high: float | None = Field(None, description="参考范围上限")
    source: Literal["ocr", "connector", "manual"] = Field(
        "manual", description="数据来源"
    )
    recorded_at: str = Field(..., description="记录时间 (ISO 8601)")


class ObservationBatchCreateInput(BaseModel):
    """批量健康指标创建输入"""
    items: list[ObservationCreateInput] = Field(
        ..., min_length=1, max_length=200, description="指标列表"
    )


# ── POST Endpoints ────────────────────────────────────────────────


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_observation(
    body: ObservationCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建单条健康指标记录
    - OCR 解析后写入数据库的接口
    - source 默认为 "manual"，可传入 "ocr" / "connector" / "manual"
    """
    obs = HealthObservation(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        loinc_code=body.loinc_code,
        loinc_name=body.loinc_name,
        value_numeric=Decimal(str(body.value_numeric)) if body.value_numeric is not None else None,
        value_string=body.value_string,
        value_unit=body.value_unit,
        reference_range_low=Decimal(str(body.reference_range_low)) if body.reference_range_low is not None else None,
        reference_range_high=Decimal(str(body.reference_range_high)) if body.reference_range_high is not None else None,
        source=body.source,
        recorded_at=datetime.fromisoformat(body.recorded_at),
    )
    db.add(obs)
    await db.commit()
    await db.refresh(obs)

    return {
        "success": True,
        "data": {
            "id": str(obs.id),
            "loinc_code": obs.loinc_code,
            "loinc_name": obs.loinc_name,
            "value_numeric": float(obs.value_numeric) if obs.value_numeric is not None else None,
            "value_string": obs.value_string,
            "value_unit": obs.value_unit,
            "reference_range_low": float(obs.reference_range_low) if obs.reference_range_low is not None else None,
            "reference_range_high": float(obs.reference_range_high) if obs.reference_range_high is not None else None,
            "source": obs.source,
            "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
            "created_at": obs.created_at.isoformat() if obs.created_at else None,
        },
    }


@router.post("/batch", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_observations_batch(
    body: ObservationBatchCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    批量创建健康指标记录
    - 支持一次请求中写入多条指标数据
    - 单次最多 200 条
    """
    records = []
    for item in body.items:
        obs = HealthObservation(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            loinc_code=item.loinc_code,
            loinc_name=item.loinc_name,
            value_numeric=Decimal(str(item.value_numeric)) if item.value_numeric is not None else None,
            value_string=item.value_string,
            value_unit=item.value_unit,
            reference_range_low=Decimal(str(item.reference_range_low)) if item.reference_range_low is not None else None,
            reference_range_high=Decimal(str(item.reference_range_high)) if item.reference_range_high is not None else None,
            source=item.source,
            recorded_at=datetime.fromisoformat(item.recorded_at),
        )
        db.add(obs)
        records.append(obs)

    await db.commit()
    for obs in records:
        await db.refresh(obs)

    data = []
    for obs in records:
        data.append({
            "id": str(obs.id),
            "loinc_code": obs.loinc_code,
            "loinc_name": obs.loinc_name,
            "value_numeric": float(obs.value_numeric) if obs.value_numeric is not None else None,
            "value_string": obs.value_string,
            "value_unit": obs.value_unit,
            "reference_range_low": float(obs.reference_range_low) if obs.reference_range_low is not None else None,
            "reference_range_high": float(obs.reference_range_high) if obs.reference_range_high is not None else None,
            "source": obs.source,
            "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
            "created_at": obs.created_at.isoformat() if obs.created_at else None,
        })

    return {
        "success": True,
        "data": data,
        "meta": {
            "count": len(data),
        },
    }


# ── GET Endpoints ─────────────────────────────────────────────────


@router.get("/", response_model=dict)
async def list_observations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    loinc_code: str | None = Query(None, description="LOINC 编码筛选"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取健康指标列表（分页，支持 loinc_code 筛选）
    """
    query = select(HealthObservation).where(HealthObservation.user_id == current_user.id)
    count_query = select(func.count()).select_from(HealthObservation).where(
        HealthObservation.user_id == current_user.id
    )

    if loinc_code:
        query = query.where(HealthObservation.loinc_code == loinc_code)
        count_query = count_query.where(HealthObservation.loinc_code == loinc_code)

    query = query.order_by(HealthObservation.recorded_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    observations = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for obs in observations:
        is_abnormal = False
        if obs.value_numeric is not None:
            if obs.reference_range_low is not None and obs.value_numeric < obs.reference_range_low:
                is_abnormal = True
            if obs.reference_range_high is not None and obs.value_numeric > obs.reference_range_high:
                is_abnormal = True
        data.append({
            "id": str(obs.id),
            "loinc_code": obs.loinc_code,
            "loinc_name": obs.loinc_name,
            "value_numeric": float(obs.value_numeric) if obs.value_numeric is not None else None,
            "value_string": obs.value_string,
            "value_unit": obs.value_unit,
            "reference_range": {
                "low": float(obs.reference_range_low) if obs.reference_range_low is not None else None,
                "high": float(obs.reference_range_high) if obs.reference_range_high is not None else None,
            },
            "is_abnormal": is_abnormal,
            "source": obs.source,
            "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
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


@router.get("/trend", response_model=dict)
async def get_trend(
    code: str = Query(..., description="LOINC 编码"),
    from_date: date = Query(..., description="起始日期"),
    to_date: date = Query(..., description="截止日期"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定指标的趋势数据
    """
    query = (
        select(HealthObservation)
        .where(
            HealthObservation.user_id == current_user.id,
            HealthObservation.loinc_code == code,
            HealthObservation.recorded_at >= datetime.combine(from_date, datetime.min.time()),
            HealthObservation.recorded_at <= datetime.combine(to_date, datetime.max.time()),
        )
        .order_by(HealthObservation.recorded_at.asc())
    )

    result = await db.execute(query)
    observations = result.scalars().all()

    trend_data = []
    for obs in observations:
        trend_data.append({
            "date": obs.recorded_at.strftime("%Y-%m-%d") if obs.recorded_at else None,
            "value": float(obs.value_numeric) if obs.value_numeric is not None else None,
            "unit": obs.value_unit,
        })

    # 计算统计摘要
    values = [d["value"] for d in trend_data if d["value"] is not None]

    stats: dict = {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }

    if len(values) >= 2:
        mean_val = stats["mean"]
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)
        stats["std_dev"] = round(std_dev, 4)
        # 变异系数 (CV%)
        if mean_val != 0:
            stats["cv_percent"] = round((std_dev / abs(mean_val)) * 100, 2)

    # 首次/末次日期
    dates_with_values = [
        d["date"] for d in trend_data if d["value"] is not None and d["date"] is not None
    ]
    if dates_with_values:
        stats["first_date"] = dates_with_values[0]
        stats["last_date"] = dates_with_values[-1]

    return {
        "success": True,
        "data": {
            "loinc_code": code,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "trend": trend_data,
            "statistics": stats,
        },
    }


@router.get("/summary", response_model=dict)
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取最新健康指标汇总
    - 按指标类型聚合，返回每个指标的最近一次值及异常状态
    """
    # 查询每个 loinc_code 的最新记录
    # 使用子查询找出每个 loinc_code 的最新 recorded_at
    subquery = (
        select(
            HealthObservation.loinc_code,
            func.max(HealthObservation.recorded_at).label("latest_at"),
        )
        .where(HealthObservation.user_id == current_user.id)
        .group_by(HealthObservation.loinc_code)
        .subquery()
    )

    query = (
        select(HealthObservation)
        .join(
            subquery,
            (HealthObservation.loinc_code == subquery.c.loinc_code)
            & (HealthObservation.recorded_at == subquery.c.latest_at),
        )
        .where(HealthObservation.user_id == current_user.id)
    )

    result = await db.execute(query)
    observations = result.scalars().all()

    summary_data = []
    for obs in observations:
        is_abnormal = False
        if obs.value_numeric is not None:
            if obs.reference_range_low is not None and obs.value_numeric < obs.reference_range_low:
                is_abnormal = True
            if obs.reference_range_high is not None and obs.value_numeric > obs.reference_range_high:
                is_abnormal = True
        summary_data.append({
            "loinc_code": obs.loinc_code,
            "loinc_name": obs.loinc_name,
            "latest_value": float(obs.value_numeric) if obs.value_numeric is not None else None,
            "value_unit": obs.value_unit,
            "is_abnormal": is_abnormal,
            "reference_range": {
                "low": float(obs.reference_range_low) if obs.reference_range_low is not None else None,
                "high": float(obs.reference_range_high) if obs.reference_range_high is not None else None,
            },
            "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
        })

    # 按指标分类分组
    grouped: dict[str, list] = defaultdict(list)
    for item in summary_data:
        # 根据关键词将指标分类
        loinc_name = item.get("loinc_name") or ""
        if any(kw in loinc_name for kw in ("血糖", "葡萄糖", "Glucose", "HbA1c", "糖化")):
            category = "metabolism"
        elif any(kw in loinc_name for kw in ("胆固醇", "甘油三酯", "HDL", "LDL", "Cholesterol", "Triglycerides")):
            category = "lipid"
        elif any(kw in loinc_name for kw in ("转氨酶", "ALT", "AST", "肝", "Liver")):
            category = "liver"
        elif any(kw in loinc_name for kw in ("肌酐", "尿素", "肾", "Creatinine", "BUN")):
            category = "renal"
        elif any(kw in loinc_name for kw in ("白细胞", "红细胞", "血红蛋白", "血小板", "WBC", "RBC", "Hemoglobin", "PLT")):
            category = "blood_routine"
        else:
            category = "other"
        grouped[category].append(item)

    return {
        "success": True,
        "data": {
            "total_indicators": len(summary_data),
            "abnormal_count": sum(1 for s in summary_data if s["is_abnormal"]),
            "indicators": summary_data,
            "ai_summary": None,
            "by_category": dict(grouped),
        },
    }

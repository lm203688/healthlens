"""健康仪表盘 API - 汇总健康数据、趋势分析、风险概览"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models.user import User
from app.models.observation import HealthObservation
from app.models.health_record import HealthProfile
from app.models.diagnosis import DiagnosisResult
from app.models.tcm_profile import TcmProfile
from app.models.tcm_syndrome import TcmSyndromeDiagnosis
from app.models.risk_assessment import RiskAssessment
from app.models.health_goal import HealthGoal
from app.models.notification import Notification
from app.api.deps import get_current_user

router = APIRouter(tags=["dashboard"])


# LOINC 码分组 - 用于趋势分析
LOINC_GROUPS = {
    "blood_pressure": {"8480-6": "收缩压", "8462-4": "舒张压"},
    "blood_glucose": {"2339-0": "空腹血糖", "1558-6": "餐后2h血糖", "4548-4": "糖化血红蛋白"},
    "lipids": {"2093-3": "总胆固醇", "2571-8": "甘油三酯", "2085-9": "HDL-C", "2089-1": "LDL-C"},
    "weight": {"29463-7": "体重", "39156-5": "BMI"},
    "heart_rate": {"8867-4": "心率"},
    "steps": {"90536-5": "步数"},
}


@router.get("/overview", response_model=dict)
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取健康仪表盘总览 - 包含关键指标、最近诊断、风险等级、未读通知"""
    user_id = current_user.id

    # 1. 最近 30 天的指标数量
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    obs_count_result = await db.execute(
        select(func.count()).select_from(HealthObservation).where(
            HealthObservation.user_id == user_id,
            HealthObservation.recorded_at >= thirty_days_ago,
        )
    )
    recent_obs_count = obs_count_result.scalar() or 0

    # 2. 最新健康档案
    profile_result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    # 3. 最近诊断
    diag_result = await db.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.user_id == user_id
        ).order_by(desc(DiagnosisResult.created_at)).limit(3)
    )
    recent_diagnoses = diag_result.scalars().all()

    # 4. 最新风险评估
    risk_result = await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.user_id == user_id
        ).order_by(desc(RiskAssessment.assessed_at)).limit(5)
    )
    recent_risks = risk_result.scalars().all()

    # 5. 活跃目标数
    goals_result = await db.execute(
        select(func.count()).select_from(HealthGoal).where(
            HealthGoal.user_id == user_id,
            HealthGoal.status == "active",
        )
    )
    active_goals_count = goals_result.scalar() or 0

    # 6. 未读通知
    unread_result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
    )
    unread_count = unread_result.scalar() or 0

    # 7. 中医体质
    tcm_result = await db.execute(
        select(TcmProfile).where(TcmProfile.user_id == user_id)
    )
    tcm_profile = tcm_result.scalar_one_or_none()

    # 8. 最新关键指标 (收缩压、血糖、血脂、体重)
    key_metrics = {}
    for group_name, loinc_map in LOINC_GROUPS.items():
        for loinc, display_name in loinc_map.items():
            result = await db.execute(
                select(HealthObservation).where(
                    HealthObservation.user_id == user_id,
                    HealthObservation.loinc_code == loinc,
                ).order_by(desc(HealthObservation.recorded_at)).limit(1)
            )
            obs = result.scalar_one_or_none()
            if obs:
                key_metrics[loinc] = {
                    "name": display_name,
                    "value": float(obs.value_numeric) if obs.value_numeric else None,
                    "unit": obs.value_unit,
                    "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
                }

    # 风险概览
    risk_overview = []
    for risk in recent_risks:
        risk_overview.append({
            "risk_type": risk.risk_type,
            "risk_level": risk.risk_level,
            "risk_probability": float(risk.risk_probability) if risk.risk_probability else None,
            "assessed_at": risk.assessed_at.isoformat() if risk.assessed_at else None,
        })

    return {
        "success": True,
        "data": {
            "user": {
                "id": str(current_user.id),
                "email": current_user.email,
                "role": current_user.role,
            },
            "summary": {
                "recent_observations_30d": recent_obs_count,
                "active_goals": active_goals_count,
                "unread_notifications": unread_count,
                "recent_diagnoses": len(recent_diagnoses),
            },
            "key_metrics": key_metrics,
            "risk_overview": risk_overview,
            "recent_diagnoses": [
                {
                    "id": str(d.id),
                    "diagnosis_name": d.diagnosis_text,
                    "icd_code": d.icd_code,
                    "confidence": float(d.confidence) if d.confidence else None,
                    "status": d.status,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in recent_diagnoses
            ],
            "tcm_constitution": {
                "type": tcm_profile.constitution_type if tcm_profile else None,
                "assessed_at": tcm_profile.assessed_at.isoformat() if tcm_profile and tcm_profile.assessed_at else None,
            } if tcm_profile else None,
            "health_profile": {
                "name": profile.name if profile else None,
                "gender": profile.gender if profile else None,
                "birth_date": profile.birth_date.isoformat() if profile and profile.birth_date else None,
                "height_cm": float(profile.height_cm) if profile and profile.height_cm else None,
                "weight_kg": float(profile.weight_kg) if profile and profile.weight_kg else None,
                "bmi": round(float(profile.weight_kg) / ((float(profile.height_cm) / 100) ** 2), 1)
                    if profile and profile.height_cm and profile.weight_kg else None,
            } if profile else None,
        },
    }


@router.get("/trends/{loinc_code}", response_model=dict)
async def get_metric_trends(
    loinc_code: str,
    days: int = Query(90, ge=7, le=365, description="查询天数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定指标的趋势数据"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(HealthObservation).where(
            HealthObservation.user_id == current_user.id,
            HealthObservation.loinc_code == loinc_code,
            HealthObservation.recorded_at >= since,
        ).order_by(HealthObservation.recorded_at.asc())
    )
    observations = result.scalars().all()

    data_points = []
    for obs in observations:
        data_points.append({
            "value": float(obs.value_numeric) if obs.value_numeric else None,
            "unit": obs.value_unit,
            "recorded_at": obs.recorded_at.isoformat() if obs.recorded_at else None,
            "source": obs.source,
        })

    # 计算统计值
    values = [float(o.value_numeric) for o in observations if o.value_numeric]
    stats = {}
    if values:
        stats = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": round(sum(values) / len(values), 2),
            "latest": values[-1] if values else None,
            "trend": "up" if len(values) >= 2 and values[-1] > values[0] else "down" if len(values) >= 2 else "stable",
        }

    return {
        "success": True,
        "data": {
            "loinc_code": loinc_code,
            "data_points": data_points,
            "stats": stats,
        },
    }


@router.post("/risk-assessment", response_model=dict, status_code=status.HTTP_201_CREATED)
async def trigger_risk_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发慢病风险评估 - 自动从健康档案和最近指标中提取参数"""
    from app.core.risk_engine import RiskAssessmentEngine

    # 获取健康档案
    profile_result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完善健康档案(身高/体重/年龄/性别)",
        )

    # 从最近观测中提取关键指标
    async def get_latest_observation(loinc_code: str):
        result = await db.execute(
            select(HealthObservation).where(
                HealthObservation.user_id == current_user.id,
                HealthObservation.loinc_code == loinc_code,
            ).order_by(desc(HealthObservation.recorded_at)).limit(1)
        )
        obs = result.scalar_one_or_none()
        return float(obs.value_numeric) if obs and obs.value_numeric else None

    sbp = await get_latest_observation("8480-6")
    dbp = await get_latest_observation("8462-4")
    tc = await get_latest_observation("2093-3")
    tg = await get_latest_observation("2571-8")
    hdl_c = await get_latest_observation("2085-9")
    ldl_c = await get_latest_observation("2089-1")
    fpg = await get_latest_observation("2339-0")
    weight = await get_latest_observation("29463-7")

    # 计算 BMI 和年龄
    bmi = None
    if profile.height_cm and profile.weight_kg:
        height_m = float(profile.height_cm) / 100
        weight_val = float(profile.weight_kg)
        bmi = weight_val / (height_m * height_m)
    elif weight and profile.height_cm:
        height_m = float(profile.height_cm) / 100
        bmi = weight / (height_m * height_m)

    # 从出生日期计算年龄
    age = 30  # 默认值
    if profile.birth_date:
        from datetime import date as date_type
        today = date_type.today()
        born = profile.birth_date
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    # 构造评估输入
    risk_input = {
        "age": age,
        "gender": profile.gender or "male",
        "bmi": bmi or 22,
        "waist": 85,  # 默认值，待接入腰围数据
        "sbp": sbp or 120,
        "dbp": dbp or 80,
        "tc": tc or 4.5,
        "tg": tg,
        "hdl_c": hdl_c,
        "ldl_c": ldl_c,
        "fpg": fpg,
    }

    engine = RiskAssessmentEngine()
    results = engine.assess_all(risk_input)
    overall_level, overall_prob = engine.get_overall_risk_level(results)

    # 保存评估结果
    import json
    saved_records = []
    for risk_type, result in results.items():
        record = RiskAssessment(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            risk_type=risk_type,
            risk_level=result.risk_level,
            risk_score=result.risk_score,
            risk_probability=result.risk_probability,
            risk_factors=json.dumps([
                {"name": f.name, "value": str(f.value), "status": f.status, "points": f.points, "advice": f.advice}
                for f in result.risk_factors
            ], ensure_ascii=False),
            recommendations=json.dumps(result.recommendations, ensure_ascii=False),
            references=json.dumps(result.references, ensure_ascii=False),
            input_snapshot=json.dumps(risk_input, ensure_ascii=False),
            assessed_at=datetime.now(timezone.utc),
        )
        db.add(record)
        saved_records.append({
            "risk_type": risk_type,
            "risk_level": result.risk_level,
            "risk_score": result.risk_score,
            "risk_probability": result.risk_probability,
            "risk_factors": [
                {"name": f.name, "value": str(f.value), "status": f.status, "advice": f.advice}
                for f in result.risk_factors
            ],
            "recommendations": result.recommendations,
        })

    await db.commit()

    return {
        "success": True,
        "data": {
            "overall_risk_level": overall_level,
            "overall_risk_probability": round(overall_prob, 1),
            "assessments": saved_records,
            "input_snapshot": risk_input,
        },
    }


@router.get("/risk-assessment/history", response_model=dict)
async def get_risk_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取风险评估历史"""
    query = select(RiskAssessment).where(RiskAssessment.user_id == current_user.id)
    count_query = select(func.count()).select_from(RiskAssessment).where(
        RiskAssessment.user_id == current_user.id
    )

    query = query.order_by(desc(RiskAssessment.assessed_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    records = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    import json
    data = []
    for r in records:
        risk_factors = json.loads(r.risk_factors) if r.risk_factors else []
        recommendations = json.loads(r.recommendations) if r.recommendations else []
        data.append({
            "id": str(r.id),
            "risk_type": r.risk_type,
            "risk_level": r.risk_level,
            "risk_score": float(r.risk_score) if r.risk_score else None,
            "risk_probability": float(r.risk_probability) if r.risk_probability else None,
            "risk_factors_count": len(risk_factors),
            "recommendations": recommendations,
            "assessed_at": r.assessed_at.isoformat() if r.assessed_at else None,
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

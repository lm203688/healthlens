"""健康分析服务"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.observation import HealthObservation
from app.core.health_analyzer import HealthAnalyzer


async def analyze_user_observations(db: AsyncSession, user_id: str) -> dict:
    """分析用户的最新健康指标"""
    result = await db.execute(
        select(HealthObservation)
        .where(HealthObservation.user_id == user_id)
        .order_by(HealthObservation.recorded_at.desc())
        .limit(100)
    )
    observations = result.scalars().all()

    if not observations:
        return {
            "total_items": 0,
            "abnormal_count": 0,
            "summary": "暂无健康数据",
            "abnormal_items": [],
        }

    obs_dicts = [
        {
            "loinc_code": o.loinc_code,
            "loinc_name": o.loinc_name,
            "value_numeric": float(o.value_numeric) if o.value_numeric else None,
            "value_unit": o.value_unit,
            "reference_range_low": float(o.reference_range_low) if o.reference_range_low else None,
            "reference_range_high": float(o.reference_range_high) if o.reference_range_high else None,
        }
        for o in observations
    ]

    analyzer = HealthAnalyzer()
    analysis = analyzer.analyze_observations(obs_dicts)

    return {
        "total_items": len(obs_dicts),
        "abnormal_count": len(analysis.abnormal_items),
        "summary": analysis.summary,
        "abnormal_items": analysis.abnormal_items,
        "risk_factors": analysis.risk_factors,
        "recommendations": analysis.recommendations,
    }

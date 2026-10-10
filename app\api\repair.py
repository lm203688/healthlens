"""细胞修复评分 API - 核心差异化功能"""
import uuid
import json
from datetime import datetime, date, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models.user import User
from app.models.sleep import SleepRecord, RepairScore
from app.api.deps import get_current_user

router = APIRouter(tags=["细胞修复"])


# ============ Pydantic Models ============

class SleepRecordCreate(BaseModel):
    sleep_date: date
    bedtime: str | None = None
    wake_time: str | None = None
    sleep_latency_min: int | None = None
    total_duration_min: int | None = None
    deep_sleep_min: float | None = None
    light_sleep_min: float | None = None
    rem_sleep_min: float | None = None
    awake_min: float | None = None
    sleep_efficiency: float | None = None
    awakenings_count: int | None = None
    hrv_avg: float | None = None
    hrv_recovery: float | None = None
    room_temp: float | None = None
    subjective_score: int | None = Field(None, ge=1, le=10)
    sleep_notes: str | None = None
    source: str = "manual"


class RepairScoreResponse(BaseModel):
    id: str
    score_date: str
    total_score: float | None
    repair_age: float | None
    calendar_age: int | None
    percentile: float | None
    deep_sleep_score: float | None
    hrv_recovery_score: float | None
    inflammation_score: float | None
    exercise_adherence_score: float | None
    nutrition_score: float | None
    circadian_score: float | None
    subjective_energy_score: float | None
    damage_analysis: dict | None
    created_at: str | None = None


# ============ 修复评分计算引擎 ============

class RepairScoreEngine:
    """细胞修复评分计算引擎"""

    DEFAULT_WEIGHTS = {
        "deep_sleep": 0.25,
        "hrv_recovery": 0.20,
        "inflammation": 0.15,
        "exercise_adherence": 0.15,
        "nutrition": 0.10,
        "circadian": 0.10,
        "subjective_energy": 0.05,
    }

    @staticmethod
    def calculate_sleep_score(record: SleepRecord) -> float:
        """根据睡眠记录计算深度睡眠维度评分 (0-100)"""
        if not record:
            return 50  # 无数据默认值

        score = 50
        # 深睡比例 (目标>20%)
        if record.total_duration_min and record.total_duration_min > 0 and record.deep_sleep_min:
            deep_ratio = record.deep_sleep_min / record.total_duration_min
            if deep_ratio >= 0.20:
                score += 20
            elif deep_ratio >= 0.15:
                score += 12
            elif deep_ratio >= 0.10:
                score += 5

        # 入睡效率 (目标>85%)
        if record.sleep_efficiency:
            if record.sleep_efficiency >= 90:
                score += 15
            elif record.sleep_efficiency >= 85:
                score += 10
            elif record.sleep_efficiency >= 75:
                score += 5

        # 觉醒次数 (目标<2)
        if record.awakenings_count is not None:
            if record.awakenings_count <= 1:
                score += 10
            elif record.awakenings_count <= 2:
                score += 5

        # 总时长 (目标>420min = 7h)
        if record.total_duration_min:
            if record.total_duration_min >= 480:
                score += 5
            elif record.total_duration_min >= 420:
                score += 3

        return min(100, max(0, score))

    @staticmethod
    def estimate_repair_age(total_score: float, calendar_age: int) -> float:
        """根据修复评分估算修复年龄"""
        # 评分100=修复年龄=日历年龄-5，评分0=修复年龄=日历年龄+10
        age_delta = -5 + (100 - total_score) * 0.15
        return round(calendar_age + age_delta, 1)

    @staticmethod
    def estimate_percentile(total_score: float) -> float:
        """估算同龄人百分位（基于正态分布假设）"""
        import math
        # 假设均值65, 标准差15
        z = (total_score - 65) / 15
        percentile = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        return round(percentile * 100, 1)

    @classmethod
    def calculate_total(cls, scores: dict, weights: dict | None = None) -> float:
        """计算加权总分"""
        w = weights or cls.DEFAULT_WEIGHTS
        total = 0
        for key, weight in w.items():
            val = scores.get(key, 50)  # 无数据默认50
            total += val * weight
        return round(total, 1)

    @classmethod
    def analyze_damage(cls, scores: dict) -> dict:
        """分析细胞损伤模式"""
        damages = []
        if scores.get("deep_sleep", 50) < 60:
            damages.append({
                "pattern": "线粒体功能不足",
                "severity": "high" if scores["deep_sleep"] < 40 else "moderate",
                "description": "深度睡眠不足导致生长激素分泌减少，线粒体自噬功能下降",
                "related_markers": ["GH脉冲", "AMPK通路", "自噬活性"],
                "linked_tcm": "气虚质"
            })
        if scores.get("hrv_recovery", 50) < 60:
            damages.append({
                "pattern": "自主神经调节障碍",
                "severity": "high" if scores["hrv_recovery"] < 40 else "moderate",
                "description": "HRV恢复率低，提示副交感神经活性不足，心血管修复能力下降",
                "related_markers": ["交感/副交感平衡", "内皮修复", "NO合成"],
                "linked_tcm": "心气虚"
            })
        if scores.get("inflammation", 50) < 60:
            damages.append({
                "pattern": "慢性低度炎症",
                "severity": "high" if scores["inflammation"] < 40 else "moderate",
                "description": "持续性低度炎症加速细胞衰老，NF-κB通路过度激活",
                "related_markers": ["hs-CRP", "IL-6", "TNF-α", "NF-κB"],
                "linked_tcm": "湿热质/痰湿质"
            })
        if scores.get("circadian", 50) < 55:
            damages.append({
                "pattern": "昼夜节律紊乱",
                "severity": "moderate",
                "description": "作息不规律影响褪黑素分泌周期，干扰细胞修复时序",
                "related_markers": ["褪黑素", "皮质醇节律", "BMAL1/CLOCK"],
                "linked_tcm": "阴阳失调"
            })
        if scores.get("nutrition", 50) < 55:
            damages.append({
                "pattern": "营养代谢压力",
                "severity": "moderate",
                "description": "营养摄入不均衡导致特定微营养素缺乏，影响细胞修复原料供给",
                "related_markers": ["维生素D", "镁", "Omega-3", "抗氧化物"],
                "linked_tcm": "脾虚质"
            })
        return damages


# ============ API Endpoints ============

@router.post("/sleep/records", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_sleep_record(
    data: SleepRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记录睡眠数据"""
    engine = RepairScoreEngine()
    record = SleepRecord(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        **data.model_dump()
    )
    record.sleep_score = engine.calculate_sleep_score(record)
    db.add(record)
    await db.commit()
    return {"success": True, "data": {"id": record.id, "sleep_score": record.sleep_score}}


@router.get("/sleep/records", response_model=dict)
async def get_sleep_records(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取睡眠记录列表"""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(SleepRecord).where(
            SleepRecord.user_id == current_user.id,
            SleepRecord.sleep_date >= since,
        ).order_by(desc(SleepRecord.sleep_date))
    )
    records = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "sleep_date": r.sleep_date.isoformat(),
                "sleep_score": float(r.sleep_score) if r.sleep_score else None,
                "deep_sleep_min": float(r.deep_sleep_min) if r.deep_sleep_min else None,
                "total_duration_min": r.total_duration_min,
                "sleep_efficiency": float(r.sleep_efficiency) if r.sleep_efficiency else None,
                "awakenings_count": r.awakenings_count,
                "hrv_recovery": float(r.hrv_recovery) if r.hrv_recovery else None,
                "bedtime": r.bedtime,
                "source": r.source,
            }
            for r in records
        ],
    }


@router.get("/sleep/trend", response_model=dict)
async def get_sleep_trend(
    days: int = Query(7, ge=7, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取睡眠评分趋势"""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(SleepRecord).where(
            SleepRecord.user_id == current_user.id,
            SleepRecord.sleep_date >= since,
        ).order_by(SleepRecord.sleep_date.asc())
    )
    records = result.scalars().all()
    return {
        "success": True,
        "data": {
            "dates": [r.sleep_date.isoformat() for r in records],
            "scores": [float(r.sleep_score) if r.sleep_score else None for r in records],
            "deep_sleep": [float(r.deep_sleep_min) if r.deep_sleep_min else None for r in records],
            "efficiency": [float(r.sleep_efficiency) if r.sleep_efficiency else None for r in records],
        },
    }


@router.get("/score/latest", response_model=dict)
async def get_latest_repair_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取最新修复评分"""
    result = await db.execute(
        select(RepairScore).where(
            RepairScore.user_id == current_user.id,
        ).order_by(desc(RepairScore.score_date)).limit(1)
    )
    score = result.scalar_one_or_none()
    if not score:
        # 无记录时，根据可用数据实时计算
        computed = await _compute_realtime_score(current_user.id, db)
        return {"success": True, "data": computed, "computed": True}
    return {"success": True, "data": _score_to_dict(score), "computed": False}


@router.get("/score/history", response_model=dict)
async def get_repair_score_history(
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取修复评分历史"""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(RepairScore).where(
            RepairScore.user_id == current_user.id,
            RepairScore.score_date >= since,
        ).order_by(RepairScore.score_date.asc())
    )
    scores = result.scalars().all()
    return {
        "success": True,
        "data": {
            "dates": [s.score_date.isoformat() for s in scores],
            "total_scores": [float(s.total_score) if s.total_score else None for s in scores],
            "repair_ages": [float(s.repair_age) if s.repair_age else None for s in scores],
        },
    }


@router.post("/score/calculate", response_model=dict, status_code=status.HTTP_201_CREATED)
async def calculate_repair_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发修复评分计算"""
    computed = await _compute_and_save(current_user.id, current_user, db)
    return {"success": True, "data": computed}


# ============ 内部函数 ============

async def _compute_realtime_score(user_id: str, db: AsyncSession) -> dict:
    """实时计算修复评分（不保存）"""
    engine = RepairScoreEngine()
    scores = {"deep_sleep": 50, "hrv_recovery": 50, "inflammation": 50,
              "exercise_adherence": 50, "nutrition": 50, "circadian": 50, "subjective_energy": 50}

    # 从最近睡眠记录计算
    sleep_result = await db.execute(
        select(SleepRecord).where(
            SleepRecord.user_id == user_id,
        ).order_by(desc(SleepRecord.sleep_date)).limit(1)
    )
    latest_sleep = sleep_result.scalar_one_or_none()
    if latest_sleep:
        scores["deep_sleep"] = engine.calculate_sleep_score(latest_sleep)
        if latest_sleep.hrv_recovery:
            scores["hrv_recovery"] = min(100, latest_sleep.hrv_recovery * 1.5)
        # 昼夜节律（基于入睡时间）
        if latest_sleep.bedtime:
            h = int(latest_sleep.bedtime.split(":")[0])
            if 22 <= h <= 23:
                scores["circadian"] = 85
            elif h == 0 or h == 21:
                scores["circadian"] = 70
            else:
                scores["circadian"] = 45

    total = engine.calculate_total(scores)
    return {
        "total_score": total,
        "dimensions": scores,
        "weights": engine.DEFAULT_WEIGHTS,
        "damage_analysis": engine.analyze_damage(scores),
        "data_sources": {
            "sleep": latest_sleep is not None,
            "wearable": latest_sleep.source == "wearable" if latest_sleep else False,
            "lab": False,
            "survey": True,
        },
    }


async def _compute_and_save(user_id: str, current_user: User, db: AsyncSession) -> dict:
    """计算并保存修复评分"""
    engine = RepairScoreEngine()
    scores = {"deep_sleep": 50, "hrv_recovery": 50, "inflammation": 50,
              "exercise_adherence": 50, "nutrition": 50, "circadian": 50, "subjective_energy": 50}

    # 从最近睡眠记录计算
    sleep_result = await db.execute(
        select(SleepRecord).where(
            SleepRecord.user_id == user_id,
        ).order_by(desc(SleepRecord.sleep_date)).limit(1)
    )
    latest_sleep = sleep_result.scalar_one_or_none()
    if latest_sleep:
        scores["deep_sleep"] = engine.calculate_sleep_score(latest_sleep)
        if latest_sleep.hrv_recovery:
            scores["hrv_recovery"] = min(100, latest_sleep.hrv_recovery * 1.5)
        if latest_sleep.bedtime:
            h = int(latest_sleep.bedtime.split(":")[0])
            if 22 <= h <= 23:
                scores["circadian"] = 85
            elif h == 0 or h == 21:
                scores["circadian"] = 70
            else:
                scores["circadian"] = 45

    total = engine.calculate_total(scores)
    calendar_age = 30  # 从健康档案获取
    from app.models.health_record import HealthProfile
    profile_result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile and profile.birth_date:
        today = date.today()
        calendar_age = today.year - profile.birth_date.year - (
            (today.month, today.day) < (profile.birth_date.month, profile.birth_date.day))

    repair_age = engine.estimate_repair_age(total, calendar_age)
    percentile = engine.estimate_percentile(total)
    damage = engine.analyze_damage(scores)

    record = RepairScore(
        id=str(uuid.uuid4()),
        user_id=user_id,
        score_date=date.today(),
        total_score=total,
        repair_age=repair_age,
        calendar_age=calendar_age,
        percentile=percentile,
        deep_sleep_score=scores["deep_sleep"],
        hrv_recovery_score=scores["hrv_recovery"],
        inflammation_score=scores["inflammation"],
        exercise_adherence_score=scores["exercise_adherence"],
        nutrition_score=scores["nutrition"],
        circadian_score=scores["circadian"],
        subjective_energy_score=scores["subjective_energy"],
        weights=engine.DEFAULT_WEIGHTS,
        damage_analysis=damage,
        sources={"sleep": latest_sleep is not None, "wearable": latest_sleep.source == "wearable" if latest_sleep else False, "lab": False, "survey": True},
    )
    db.add(record)
    await db.commit()

    return {
        "id": record.id,
        "score_date": record.score_date.isoformat(),
        "total_score": total,
        "repair_age": repair_age,
        "calendar_age": calendar_age,
        "percentile": percentile,
        "dimensions": scores,
        "weights": engine.DEFAULT_WEIGHTS,
        "damage_analysis": damage,
    }


def _score_to_dict(score: RepairScore) -> dict:
    return {
        "id": str(score.id),
        "score_date": score.score_date.isoformat() if score.score_date else None,
        "total_score": float(score.total_score) if score.total_score else None,
        "repair_age": float(score.repair_age) if score.repair_age else None,
        "calendar_age": score.calendar_age,
        "percentile": float(score.percentile) if score.percentile else None,
        "dimensions": {
            "deep_sleep": float(score.deep_sleep_score) if score.deep_sleep_score else None,
            "hrv_recovery": float(score.hrv_recovery_score) if score.hrv_recovery_score else None,
            "inflammation": float(score.inflammation_score) if score.inflammation_score else None,
            "exercise_adherence": float(score.exercise_adherence_score) if score.exercise_adherence_score else None,
            "nutrition": float(score.nutrition_score) if score.nutrition_score else None,
            "circadian": float(score.circadian_score) if score.circadian_score else None,
            "subjective_energy": float(score.subjective_energy_score) if score.subjective_energy_score else None,
        },
        "weights": score.weights,
        "damage_analysis": score.damage_analysis,
        "created_at": score.created_at.isoformat() if score.created_at else None,
    }

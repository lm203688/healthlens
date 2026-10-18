"""n-of-1 纵向追踪 API（S2-2）

端点总览：
    POST   /studies                      创建研究
    GET    /studies                      列出研究
    GET    /studies/{study_id}           研究详情
    POST   /studies/{study_id}/snapshots 写入八轴快照
    GET    /studies/{study_id}/trajectory 拉取轨迹（时间序列）
    POST   /studies/{study_id}/interventions 登记干预事件
    GET    /studies/{study_id}/comparison 干预前后 vs 反事实对比
    POST   /studies/{study_id}/readings  写入化验单读数
    GET    /studies/{study_id}/readings  列出化验单读数

设计要点：
- 全部端点强制 user_id = current_user.id，跨用户访问 404（避免数据泄露）
- 数据驻留：study.data_residency_region 必须与 user.region/jurisdiction 一致
  （跨区查询通过 region_guard 拦截，S3 联邦学习的基础）
- 因果对比走 `app.lib.causal_simulator` 反事实机制，输出「不干预的反事实轨迹」
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.longitudinal import (
    AxisSnapshot,
    BiomarkerReading,
    InterventionEvent,
    LongitudinalStudy,
)
from app.models.user import User
from app.lib.causal_simulator import (
    causal_report,
)
from app.lib.wellness_simulator import (
    derive_baseline,
    AXES as WELLNESS_AXES,
)
from app.lib.axis_config import get_threshold
from app.core.axis_scorers import score_all_axes
from app.lib.region_guard import assert_same_region


router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StudyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cohort: str = "n_of_1"
    start_date: datetime | None = None
    end_date: datetime | None = None
    data_residency_region: str = "CN"
    protocol: dict | None = None
    consent_version: str | None = None
    notes: str | None = None


class SnapshotCreate(BaseModel):
    captured_at: datetime | None = None
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    jurisdiction: str = "cn"
    inputs: dict | None = Field(
        default=None,
        description="输入数据（biomarkers + wearable），用于打分 + 生成指纹",
    )
    axis_scores: dict | None = None  # 已计算好时直接写入（覆盖打分逻辑）
    overall_score: float | None = None
    weak_axes: list[str] | None = None
    source: str = "manual"
    notes: str | None = None


class InterventionCreate(BaseModel):
    intervention_type: str = Field(..., min_length=1)
    target_axis: str | None = None
    description: str | None = None
    intensity: float | None = Field(default=None, ge=0, le=1)
    started_at: datetime
    ended_at: datetime | None = None
    outcome_note: str | None = None
    metadata: dict | None = None


class BiomarkerReadingCreate(BaseModel):
    loinc_code: str = Field(..., min_length=1)
    loinc_name: str = Field(..., min_length=1)
    value_numeric: float | None = None
    value_string: str | None = None
    value_unit: str | None = None
    sampled_at: datetime
    lab_source: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    notes: str | None = None


class ComparisonRequest(BaseModel):
    intervention_id: str
    window_days_before: int = Field(default=14, ge=1, le=90)
    window_days_during: int = Field(default=14, ge=1, le=90)
    window_days_after: int = Field(default=14, ge=1, le=90)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_study(
    study_id: str,
    current_user: User,
    db: AsyncSession,
) -> LongitudinalStudy:
    """按 ID 拿研究，且校验归属当前用户（跨用户访问一律 404，不泄露存在性）。"""
    result = await db.execute(
        select(LongitudinalStudy).where(
            LongitudinalStudy.id == study_id,
            LongitudinalStudy.user_id == str(current_user.id),
        )
    )
    study = result.scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


def _finger_print(inputs: dict) -> str:
    """对输入数据做 sha256，用于审计追溯。"""
    raw = json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/studies", status_code=status.HTTP_201_CREATED)
async def create_study(
    body: StudyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建纵向研究。

    跨区检查：study.data_residency_region 必须与用户所在区域一致，
    否则 400（region_guard）。这是 S3 联邦学习的分区键。
    """
    # region_guard.assert_same_region 内部会把 record_region 转小写后与
    # user_region 比较，因此两侧都要归一到小写再比较。
    user_region_raw = getattr(current_user, "region", None) or "CN"
    study_region_raw = body.data_residency_region or "CN"
    user_region_norm = str(user_region_raw).lower()
    study_region_norm = str(study_region_raw).lower()
    try:
        assert_same_region(study_region_norm, user_region_norm, entity_name="study")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Data residency region mismatch: user={user_region_raw}, study={study_region_raw}. {exc}",
        )

    study = LongitudinalStudy(
        user_id=str(current_user.id),
        name=body.name,
        cohort=body.cohort,
        start_date=body.start_date,
        end_date=body.end_date,
        data_residency_region=str(study_region_raw).upper(),
        protocol=body.protocol,
        consent_version=body.consent_version,
        notes=body.notes,
    )
    db.add(study)
    await db.commit()
    await db.refresh(study)

    return {
        "success": True,
        "data": _study_to_dict(study),
    }


@router.get("/studies")
async def list_studies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的所有纵向研究。"""
    query = (
        select(LongitudinalStudy)
        .where(LongitudinalStudy.user_id == str(current_user.id))
        .order_by(LongitudinalStudy.created_at.desc())
    )
    total = (
        await db.execute(
            select(func.count()).select_from(LongitudinalStudy)
            .where(LongitudinalStudy.user_id == str(current_user.id))
        )
    ).scalar() or 0

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    studies = result.scalars().all()

    return {
        "success": True,
        "data": [_study_to_dict(s) for s in studies],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/studies/{study_id}")
async def get_study(
    study_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """研究详情。"""
    study = await _get_owned_study(study_id, current_user, db)
    snapshot_count = (
        await db.execute(
            select(func.count()).select_from(AxisSnapshot)
            .where(AxisSnapshot.study_id == study_id)
        )
    ).scalar() or 0
    intervention_count = (
        await db.execute(
            select(func.count()).select_from(InterventionEvent)
            .where(InterventionEvent.study_id == study_id)
        )
    ).scalar() or 0
    reading_count = (
        await db.execute(
            select(func.count()).select_from(BiomarkerReading)
            .where(BiomarkerReading.study_id == study_id)
        )
    ).scalar() or 0

    data = _study_to_dict(study)
    data["counts"] = {
        "snapshots": snapshot_count,
        "interventions": intervention_count,
        "biomarker_readings": reading_count,
    }
    return {"success": True, "data": data}


@router.post("/studies/{study_id}/snapshots", status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    study_id: str,
    body: SnapshotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写入八轴快照。

    两种模式：
    - body.inputs 非空 → 现场打分（score_all_axes），记录输入指纹
    - body.axis_scores 非空 → 直接写入（外部已打分，用于回放/导入）
    两者皆空 → 400。
    """
    study = await _get_owned_study(study_id, current_user, db)

    axis_scores = body.axis_scores
    overall_score = body.overall_score
    weak_axes = body.weak_axes
    input_fingerprint: str | None = None
    input_summary: dict | None = None
    source = body.source

    if body.inputs is not None:
        inputs = body.inputs
        try:
            # score_all_axes 返回 dict[str, AxisScore]（dataclass，含 to_dict()）
            result = score_all_axes(
                biomarkers=inputs.get("biomarkers"),
                wearable=inputs.get("wearable"),
                symptoms=inputs.get("symptoms"),
                bioage_delta=inputs.get("bioage_delta"),
                is_male=inputs.get("is_male", True),
                jurisdiction=body.jurisdiction,
            )
            axis_scores = {}
            measured_scores = []
            for ax, s in result.items():
                d = s.to_dict()
                if not d.get("measured"):
                    continue
                axis_scores[ax] = {
                    "score": d.get("score"),
                    "measured": True,
                    "penalty_ratio": d.get("penalty_ratio"),
                }
                if d.get("score") is not None:
                    measured_scores.append(float(d["score"]))
            # 全局分：已测量轴的平均
            overall_score = (
                round(sum(measured_scores) / len(measured_scores), 3)
                if measured_scores else None
            )
            weak_axes = sorted(
                ax for ax, v in axis_scores.items()
                if v.get("score") is not None and v["score"] < 70
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Scoring failed: {exc}",
            )
        input_fingerprint = _finger_print(inputs)
        # 存摘要（键数量、时间范围），不存原值——避免快照表膨胀
        input_summary = {
            "keys": list(inputs.keys()),
            "biomarker_count": len(inputs.get("biomarkers") or {}),
            "wearable_count": len(inputs.get("wearable") or {}),
        }
        source = "composite"

    if not axis_scores and not overall_score:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'inputs' (for live scoring) or 'axis_scores' (pre-computed)",
        )

    captured_at = body.captured_at or datetime.now(timezone.utc)
    snapshot = AxisSnapshot(
        study_id=study_id,
        user_id=str(current_user.id),
        captured_at=captured_at,
        date=body.date,
        jurisdiction=body.jurisdiction,
        axis_scores=axis_scores,
        overall_score=Decimal(str(overall_score)) if overall_score is not None else None,
        weak_axes=weak_axes,
        input_fingerprint=input_fingerprint,
        input_summary=input_summary,
        source=source,
        notes=body.notes,
    )
    db.add(snapshot)

    # 若是首份快照，写回 baseline_snapshot_id
    if not study.baseline_snapshot_id:
        pass  # 需要在 commit 后回填 ID

    await db.commit()
    await db.refresh(snapshot)

    if not study.baseline_snapshot_id:
        study.baseline_snapshot_id = str(snapshot.id)
        await db.commit()

    return {
        "success": True,
        "data": {
            "id": str(snapshot.id),
            "study_id": study_id,
            "date": snapshot.date,
            "captured_at": snapshot.captured_at.isoformat(),
            "jurisdiction": snapshot.jurisdiction,
            "overall_score": float(snapshot.overall_score) if snapshot.overall_score is not None else None,
            "weak_axes": snapshot.weak_axes,
            "measured_axes": [
                k for k, v in (snapshot.axis_scores or {}).items()
                if v.get("measured")
            ],
            "input_fingerprint": snapshot.input_fingerprint,
            "is_baseline": str(snapshot.id) == study.baseline_snapshot_id,
        },
    }


@router.get("/studies/{study_id}/trajectory")
async def get_trajectory(
    study_id: str,
    since: str | None = Query(None, description="YYYY-MM-DD"),
    until: str | None = Query(None, description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """拉取八轴轨迹（时间序列）。

    输出结构：
    {
      "snapshots": [{date, captured_at, overall_score, axis_scores, weak_axes}, ...],
      "trajectory": {"A": [{date, score}, ...], "B": [...], ...},
      "summary": {
        "count": N, "date_range": [first, last],
        "per_axis_mean": {axis: mean_score},
        "per_axis_delta_from_baseline": {axis: delta}
      }
    }
    """
    study = await _get_owned_study(study_id, current_user, db)

    query = (
        select(AxisSnapshot)
        .where(AxisSnapshot.study_id == study_id)
        .order_by(AxisSnapshot.date.asc())
    )
    if since:
        query = query.where(AxisSnapshot.date >= since)
    if until:
        query = query.where(AxisSnapshot.date <= until)

    result = await db.execute(query)
    snapshots = result.scalars().all()

    snaps = []
    trajectory: dict[str, list[dict]] = {}
    per_axis_scores: dict[str, list[float]] = {}

    for s in snapshots:
        snap_dict = {
            "date": s.date,
            "captured_at": s.captured_at.isoformat() if s.captured_at else None,
            "jurisdiction": s.jurisdiction,
            "overall_score": float(s.overall_score) if s.overall_score is not None else None,
            "axis_scores": s.axis_scores or {},
            "weak_axes": s.weak_axes or [],
            "input_fingerprint": s.input_fingerprint,
            "source": s.source,
        }
        snaps.append(snap_dict)

        for axis, v in (s.axis_scores or {}).items():
            if not v.get("measured"):
                continue
            score = v.get("score")
            if score is None:
                continue
            trajectory.setdefault(axis, []).append({"date": s.date, "score": float(score)})
            per_axis_scores.setdefault(axis, []).append(float(score))

    # 每轴均值 + 相对基线的差值
    baseline_axis_scores: dict[str, float] = {}
    if study.baseline_snapshot_id:
        baseline = next(
            (s for s in snapshots if str(s.id) == study.baseline_snapshot_id), None
        )
        if baseline:
            for axis, v in (baseline.axis_scores or {}).items():
                if v.get("measured") and v.get("score") is not None:
                    baseline_axis_scores[axis] = float(v["score"])

    per_axis_summary = {}
    for axis, scores in per_axis_scores.items():
        mean_score = sum(scores) / len(scores)
        per_axis_summary[axis] = {
            "mean": round(mean_score, 3),
            "min": min(scores),
            "max": max(scores),
            "count": len(scores),
            "delta_from_baseline": (
                round(mean_score - baseline_axis_scores[axis], 3)
                if axis in baseline_axis_scores
                else None
            ),
        }

    return {
        "success": True,
        "data": {
            "study_id": study_id,
            "baseline_snapshot_id": study.baseline_snapshot_id,
            "snapshots": snaps,
            "trajectory": trajectory,
            "summary": {
                "count": len(snaps),
                "date_range": (
                    [snaps[0]["date"], snaps[-1]["date"]] if snaps else None
                ),
                "per_axis_mean": per_axis_summary,
            },
        },
    }


@router.post("/studies/{study_id}/interventions", status_code=status.HTTP_201_CREATED)
async def create_intervention(
    study_id: str,
    body: InterventionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """登记一次干预事件。"""
    await _get_owned_study(study_id, current_user, db)

    if body.target_axis is not None and body.target_axis not in "ABCDEFGH":
        raise HTTPException(
            status_code=400,
            detail=f"target_axis must be one of A-H, got '{body.target_axis}'",
        )

    event = InterventionEvent(
        study_id=study_id,
        user_id=str(current_user.id),
        intervention_type=body.intervention_type,
        target_axis=body.target_axis,
        description=body.description,
        intensity=Decimal(str(body.intensity)) if body.intensity is not None else None,
        started_at=body.started_at,
        ended_at=body.ended_at,
        outcome_note=body.outcome_note,
        intervention_meta=body.metadata,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return {
        "success": True,
        "data": {
            "id": str(event.id),
            "study_id": study_id,
            "intervention_type": event.intervention_type,
            "target_axis": event.target_axis,
            "intensity": float(event.intensity) if event.intensity is not None else None,
            "started_at": event.started_at.isoformat(),
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
        },
    }


@router.get("/studies/{study_id}/interventions")
async def list_interventions(
    study_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出研究的所有干预事件。"""
    await _get_owned_study(study_id, current_user, db)
    result = await db.execute(
        select(InterventionEvent)
        .where(InterventionEvent.study_id == study_id)
        .order_by(InterventionEvent.started_at.desc())
    )
    events = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(e.id),
                "intervention_type": e.intervention_type,
                "target_axis": e.target_axis,
                "description": e.description,
                "intensity": float(e.intensity) if e.intensity is not None else None,
                "started_at": e.started_at.isoformat(),
                "ended_at": e.ended_at.isoformat() if e.ended_at else None,
                "outcome_note": e.outcome_note,
            }
            for e in events
        ],
    }


@router.post("/studies/{study_id}/readings", status_code=status.HTTP_201_CREATED)
async def create_biomarker_reading(
    study_id: str,
    body: BiomarkerReadingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写入化验单读数（基线/随访）。"""
    await _get_owned_study(study_id, current_user, db)

    reading = BiomarkerReading(
        study_id=study_id,
        user_id=str(current_user.id),
        loinc_code=body.loinc_code,
        loinc_name=body.loinc_name,
        value_numeric=Decimal(str(body.value_numeric)) if body.value_numeric is not None else None,
        value_string=body.value_string,
        value_unit=body.value_unit,
        sampled_at=body.sampled_at,
        lab_source=body.lab_source,
        reference_low=Decimal(str(body.reference_low)) if body.reference_low is not None else None,
        reference_high=Decimal(str(body.reference_high)) if body.reference_high is not None else None,
        notes=body.notes,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)

    return {
        "success": True,
        "data": {
            "id": str(reading.id),
            "study_id": study_id,
            "loinc_code": reading.loinc_code,
            "loinc_name": reading.loinc_name,
            "value_numeric": float(reading.value_numeric) if reading.value_numeric is not None else None,
            "value_unit": reading.value_unit,
            "sampled_at": reading.sampled_at.isoformat(),
        },
    }


@router.get("/studies/{study_id}/readings")
async def list_biomarker_readings(
    study_id: str,
    loinc_code: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出研究的所有化验单读数。"""
    await _get_owned_study(study_id, current_user, db)
    query = select(BiomarkerReading).where(BiomarkerReading.study_id == study_id)
    if loinc_code:
        query = query.where(BiomarkerReading.loinc_code == loinc_code)
    query = query.order_by(BiomarkerReading.sampled_at.desc())

    result = await db.execute(query)
    readings = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "loinc_code": r.loinc_code,
                "loinc_name": r.loinc_name,
                "value_numeric": float(r.value_numeric) if r.value_numeric is not None else None,
                "value_string": r.value_string,
                "value_unit": r.value_unit,
                "sampled_at": r.sampled_at.isoformat(),
                "lab_source": r.lab_source,
                "reference_low": float(r.reference_low) if r.reference_low is not None else None,
                "reference_high": float(r.reference_high) if r.reference_high is not None else None,
            }
            for r in readings
        ],
    }


@router.post("/studies/{study_id}/comparison")
async def compare_intervention_effect(
    study_id: str,
    body: ComparisonRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """干预前后 vs 反事实对比（S2-1 因果引擎的落点）。

    流程：
    1. 拿干预事件的 target_axis 与时间窗口
    2. 取该轴在 [start - before, start + during + after] 的八轴分数
    3. 计算「干预期均值 vs 前 k 天均值」差值
    4. 调用 CausalSimulator.counterfactual_trajectory 生成「不干预的反事实轨迹」
    5. 计算「实际 vs 反事实」的增量 + E-value 敏感性

    输出：
    {
      "intervention": {...},
      "observed": {"before_mean": x, "during_mean": y, "delta": y - x},
      "counterfactual": {"expected_mean_without": z, "effect_size": y - z},
      "sensitivity": {"e_value": ..., "interpretation": ...},
      "note": "反事实轨迹来自 AXIS_BRIDGES 校准的 SCM；E-value 检验未观测混淆的鲁棒性"
    }
    """
    study = await _get_owned_study(study_id, current_user, db)

    intervention = (
        await db.execute(
            select(InterventionEvent).where(
                InterventionEvent.id == body.intervention_id,
                InterventionEvent.study_id == study_id,
            )
        )
    ).scalar_one_or_none()
    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention not found in this study")

    # 找目标轴（无 target_axis 时用所有弱轴）
    target_axes = [intervention.target_axis] if intervention.target_axis else list("ABCDEFGH")

    # 时间窗口
    start = intervention.started_at
    before_start = start - timedelta(days=body.window_days_before)
    during_end = start + timedelta(days=body.window_days_during)
    after_end = during_end + timedelta(days=body.window_days_after)

    window_start_str = before_start.strftime("%Y-%m-%d")
    window_end_str = after_end.strftime("%Y-%m-%d")

    result = await db.execute(
        select(AxisSnapshot)
        .where(
            AxisSnapshot.study_id == study_id,
            AxisSnapshot.date >= window_start_str,
            AxisSnapshot.date <= window_end_str,
        )
        .order_by(AxisSnapshot.date.asc())
    )
    snapshots = result.scalars().all()

    observed = {}
    for axis in target_axes:
        before_scores = []
        during_scores = []
        after_scores = []
        for s in snapshots:
            v = (s.axis_scores or {}).get(axis)
            if not v or not v.get("measured") or v.get("score") is None:
                continue
            score = float(v["score"])
            if s.date < start.strftime("%Y-%m-%d"):
                before_scores.append(score)
            elif s.date <= during_end.strftime("%Y-%m-%d"):
                during_scores.append(score)
            else:
                after_scores.append(score)
        observed[axis] = {
            "before_mean": round(sum(before_scores) / len(before_scores), 3) if before_scores else None,
            "during_mean": round(sum(during_scores) / len(during_scores), 3) if during_scores else None,
            "after_mean": round(sum(after_scores) / len(after_scores), 3) if after_scores else None,
            "delta_during_vs_before": (
                round(
                    (sum(during_scores) / len(during_scores))
                    - (sum(before_scores) / len(before_scores)),
                    3,
                )
                if before_scores and during_scores
                else None
            ),
            "n_before": len(before_scores),
            "n_during": len(during_scores),
            "n_after": len(after_scores),
        }

    # 反事实：调用因果引擎的函数接口（counterfactual(baseline, levers, weeks, ...)）
    # 从 observed.during_mean 构造"实际基线"，然后对比「干预 vs 不干预」的
    # 12 周演化。causal_simulator 是纯函数接口，无 CausalSimulator 类。
    # 干预杠杆从 intervention.intervention_type 关键字启发式映射。
    import copy

    LEVER_KEYWORDS = {
        "diet": ["anti_inflammatory_diet"],
        "food": ["anti_inflammatory_diet"],
        "sleep": ["sleep_hygiene"],
        "exercise": ["exercise"],
        "fasting": ["fasting"],
        "medication": [],  # 药物干预不进 wellness_simulator 的杠杆集
    }

    def _map_levers(itype: str) -> list[str]:
        itype_l = (itype or "").lower()
        mapped = []
        for kw, levers in LEVER_KEYWORDS.items():
            if kw in itype_l:
                mapped.extend(levers)
        return mapped or []

    cf_levers = _map_levers(intervention.intervention_type)

    # 用「干预前均值」作为基线：若某轴无前值，用默认中性 68
    baseline: dict[str, float] = {}
    for axis in WELLNESS_AXES:
        ob = observed.get(axis)
        if ob and ob.get("before_mean") is not None:
            baseline[axis] = ob["before_mean"]
        else:
            baseline[axis] = 68.0  # wellness_simulator 的中性默认值

    counterfactual_output: dict = {}
    try:
        counterfactual_output = causal_report(
            baseline=baseline,
            levers=cf_levers,
            weeks=12,
            lever_scale=float(intervention.intensity or 1.0),
        )
    except Exception as exc:
        counterfactual_output = {"error": str(exc)}

    return {
        "success": True,
        "data": {
            "study_id": study_id,
            "intervention": {
                "id": str(intervention.id),
                "type": intervention.intervention_type,
                "target_axis": intervention.target_axis,
                "intensity": float(intervention.intensity) if intervention.intensity is not None else None,
                "started_at": intervention.started_at.isoformat(),
                "ended_at": intervention.ended_at.isoformat() if intervention.ended_at else None,
            },
            "window": {
                "before_days": body.window_days_before,
                "during_days": body.window_days_during,
                "after_days": body.window_days_after,
                "observed_snapshots": len(snapshots),
            },
            "observed": observed,
            "counterfactual": counterfactual_output,
            "levers_inferred": cf_levers,
            "baseline_used": baseline,
            "note": (
                "反事实来自 app.lib.causal_simulator.causal_report（结构因果模型 + "
                "反事实 + 校准 + 敏感性四件套）；杠杆从 intervention_type 关键字启发式"
                "映射，未识别类型视为零杠杆。causal_report 内部含 E-value 检验未观测"
                "混淆的鲁棒性，但 E-value 是敏感性指标而非统计显著性检验。"
                "本模块只输出「观察 + 反事实 + 敏感性」，不宣称因果——"
                "用户仍需自行判断或咨询临床医师。"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _study_to_dict(study: LongitudinalStudy) -> dict:
    return {
        "id": str(study.id),
        "user_id": study.user_id,
        "name": study.name,
        "cohort": study.cohort,
        "status": study.status,
        "start_date": study.start_date.isoformat() if study.start_date else None,
        "end_date": study.end_date.isoformat() if study.end_date else None,
        "data_residency_region": study.data_residency_region,
        "baseline_snapshot_id": study.baseline_snapshot_id,
        "protocol": study.protocol,
        "consent_version": study.consent_version,
        "notes": study.notes,
        "created_at": study.created_at.isoformat() if study.created_at else None,
        "updated_at": study.updated_at.isoformat() if study.updated_at else None,
    }

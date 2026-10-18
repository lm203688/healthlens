"""八轴稳态路由 — 代谢-炎症轴（PhenoAge 借鉴）与八轴个性化融合

研发路线三期 P2-1：把 PhenoAge 子分接入八轴模型并对外暴露，供前端展示。
诚实边界：本轴为**透明体检指标代理**（非 DNAm 甲基化，非临床），
响应恒定携带 not_clinical=True 与方法说明，前端必须展示免责。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(tags=["axes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BiomarkerInput(BaseModel):
    """代谢-炎症轴输入：8 项常规体检/体测指标（全部可选，缺失项不参与评分）。"""
    chrono_age: int = Field(..., ge=1, le=120, description="实际年龄（岁）")
    is_male: bool = True
    glucose: float | None = Field(None, description="空腹血糖 mmol/L")
    hba1c: float | None = Field(None, description="糖化血红蛋白 %")
    hs_crp: float | None = Field(None, description="超敏 C 反应蛋白 mg/L")
    waist_cm: float | None = Field(None, description="腰围 cm")
    hdl: float | None = Field(None, description="高密度脂蛋白 mmol/L")
    triglycerides: float | None = Field(None, description="甘油三酯 mmol/L")
    sbp: float | None = Field(None, description="收缩压 mmHg")
    bmi: float | None = Field(None, description="体质指数")


class AxisAssessInput(BiomarkerInput):
    """八轴融合评估输入（体检指标 + 可选基因/组学）。"""
    pathway_scores: dict[str, float] = Field(default_factory=dict)
    weak_axes: list[str] = Field(default_factory=list)
    contraindications: list[str] = Field(default_factory=list)
    top_k: int = 8


class ProjectInput(BaseModel):
    """迷你 Turboid 养生方案虚拟推演输入。

    wellness 框架：仅接收基线健康信号分与生活方式杠杆，输出虚拟演化轨迹，
    绝不含诊断/治疗/药物/个体结果预测。

    基线推导优先级（高→低）：
      1. baseline_scores（直接提供 8 轴分）
      2. checkin_energy/digestion/sleep（SIIV 自测 1-5 分 → 映射 0-100）
      3. weak_axes（仅弱项轴压到 45，其余中性 68）
    """
    baseline_scores: dict[str, float] = Field(
        default_factory=dict,
        description="可选，各轴(字母 A-H) 0-100 基线分；缺省由 checkin 或 weak_axes 推导",
    )
    weak_axes: list[str] = Field(default_factory=list, description="偏弱轴字母列表，用于推导基线")
    checkin_energy: int | None = Field(
        None, ge=1, le=5,
        description="可选，精力/活力自评 (1-5)，映射 A/B 轴",
    )
    checkin_digestion: int | None = Field(
        None, ge=1, le=5,
        description="可选，消化/肠胃自评 (1-5)，映射 F 轴",
    )
    checkin_sleep: int | None = Field(
        None, ge=1, le=5,
        description="可选，睡眠/休息自评 (1-5)，映射 D/G 轴",
    )
    levers: list[str] = Field(default_factory=list, description="启用的生活方式杠杆 key")
    weeks: int = Field(12, ge=1, le=52, description="推演周数")
    lever_scale: float = Field(1.0, ge=0.0, le=1.0, description="执行一致性系数 0-1")


# ---------------------------------------------------------------------------
# 元信息（前端渲染轴位与阈值用）
# ---------------------------------------------------------------------------

@router.get("/meta", response_model=dict)
async def axes_meta():
    """返回代谢-炎症轴元信息：轴标识、落点八轴、弱轴阈值、诚实边界。"""
    from app.lib.fusion_engine import (
        AXIS_KEY, AXIS_LABEL, BIOAGE_AXIS_MAP, BIOAGE_WEAK_THRESHOLD,
    )

    return {
        "success": True,
        "data": {
            "axis_key": AXIS_KEY,
            "axis_label": AXIS_LABEL,
            "mapped_axes": sorted(BIOAGE_AXIS_MAP),
            "weak_threshold": BIOAGE_WEAK_THRESHOLD,
            "markers": [
                "glucose", "hba1c", "hs_crp", "waist_cm",
                "hdl", "triglycerides", "sbp", "bmi",
            ],
            "not_clinical": True,
            "method": "透明体检指标代理（非 DNAm 甲基化，非临床）",
        },
    }


# ---------------------------------------------------------------------------
# 代谢-炎症轴评分（独立入口，前端可单独展示轴分）
# ---------------------------------------------------------------------------

@router.post("/bioage", response_model=dict)
async def assess_bioage(
    body: BiomarkerInput,
    current_user: User = Depends(get_current_user),
):
    """计算生物学年龄偏移与代谢-炎症轴稳态分（0-100，高=更健康）。"""
    from app.core.bioage_engine import BioAgeEngine, AXIS_KEY, AXIS_LABEL

    engine = BioAgeEngine()
    r = engine.assess(
        body.chrono_age,
        is_male=body.is_male,
        glucose=body.glucose,
        hba1c=body.hba1c,
        hs_crp=body.hs_crp,
        waist_cm=body.waist_cm,
        hdl=body.hdl,
        triglycerides=body.triglycerides,
        sbp=body.sbp,
        bmi=body.bmi,
    )

    return {
        "success": True,
        "data": {
            "axis_key": AXIS_KEY,
            "axis_label": AXIS_LABEL,
            "chrono_age": r.chrono_age,
            "bio_age": r.bio_age,
            "delta": r.delta,
            "axis_score": r.axis_score,
            "band": engine.delta_band(r.delta),
            "not_clinical": r.not_clinical,
            "method": r.method,
            "markers": [
                {
                    "key": m.key, "label": m.label, "value": m.value,
                    "unit": m.unit, "status": m.status,
                    "age_delta": m.age_delta, "axis_penalty": m.axis_penalty,
                    "note": m.note,
                }
                for m in r.markers
            ],
        },
        "meta": {
            "disclaimer": "以上为稳态健康管理信息，不构成医学诊断或治疗建议。",
        },
    }


# ---------------------------------------------------------------------------
# 八轴融合评估（体检指标 + 基因/组学 → 个性化建议）
# ---------------------------------------------------------------------------

@router.post("/assess", response_model=dict)
async def assess_axes(
    body: AxisAssessInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """八轴个性化融合推荐：体检指标驱动代谢-炎症轴，基因/组学驱动其余弱项轴。"""
    from app.lib.fusion_engine import UserProfile, recommend, disclaimer
    from app.services.runtime_audit import build_events, persist_events

    profile = UserProfile(
        pathway_scores=body.pathway_scores,
        weak_axes=set(body.weak_axes),
        contraindications=set(body.contraindications),
        chrono_age=body.chrono_age,
        is_male=body.is_male,
        biomarkers={
            "glucose": body.glucose, "hba1c": body.hba1c, "hs_crp": body.hs_crp,
            "waist_cm": body.waist_cm, "hdl": body.hdl,
            "triglycerides": body.triglycerides, "sbp": body.sbp, "bmi": body.bmi,
        },
    )

    result = recommend(profile, top_k=body.top_k)
    result["disclaimer"] = disclaimer()

    # 简化版运行时审计：对输入/输出/推荐证据做轻量自检（失败静默）
    import json as _json
    try:
        events = build_events(
            endpoint="/api/v1/axes/assess",
            user_id=str(current_user.id),
            input_text=_json.dumps(body.model_dump(), ensure_ascii=False),
            output_text=_json.dumps(result, ensure_ascii=False),
            recommendations=result.get("recommendations"),
        )
        await persist_events(db, events)
    except Exception:
        pass

    return {
        "success": True,
        "data": result,
        "meta": {"top_k": body.top_k},
    }


# ---------------------------------------------------------------------------
# 证据链可视化：按 case_id 取完整案例证据记录
# ---------------------------------------------------------------------------

@router.get("/evidence/{case_id}", response_model=dict)
async def get_evidence(case_id: str):
    """返回某条推荐的完整证据链（古籍经验 + 现代稳态生物学证据）。

    wellness 定位：仅展示来源/机制/设计/人群/结局/证据等级，不构成医疗结论。
    """
    from app.lib.fusion_engine import get_case_by_id, evidence_detail

    case = get_case_by_id(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到案例证据记录: {case_id}",
        )

    return {
        "success": True,
        "data": {
            "case_id": case_id,
            "evidence": evidence_detail(case),
        },
    }


# ---------------------------------------------------------------------------
# 迷你 Turboid：养生方案虚拟推演（八轴耦合动力学，wellness 框架）
# ---------------------------------------------------------------------------

@router.post("/project", response_model=dict)
async def project_wellness(
    body: ProjectInput,
    current_user: User = Depends(get_current_user),
):
    """基于八轴耦合网络，前向推演「若坚持某些生活方式，健康信号可能如何演化」。

    纯虚拟推演（not_clinical=True），不含诊断/治疗/个体结果预测。结果含逐周轨迹、
    养生综合指数、限速轴、优先杠杆与已激活机制链，供用户做养生方案参考。

    基线推导优先级：baseline_scores > checkin 自测数据 > weak_axes。
    """
    from app.lib.wellness_simulator import derive_baseline, derive_baseline_from_checkin, simulate

    # 优先级：直接提供 > checkin 自测 > weak_axes 推导
    if body.baseline_scores:
        baseline = derive_baseline(
            weak_axes=body.weak_axes,
            provided=body.baseline_scores,
        )
    elif any([body.checkin_energy, body.checkin_digestion, body.checkin_sleep]):
        baseline = derive_baseline_from_checkin(
            energy=body.checkin_energy,
            digestion=body.checkin_digestion,
            sleep=body.checkin_sleep,
            weak_axes=body.weak_axes,
        )
    else:
        baseline = derive_baseline(weak_axes=body.weak_axes)

    result = simulate(
        baseline=baseline,
        levers=body.levers,
        weeks=body.weeks,
        lever_scale=body.lever_scale,
    )

    return {
        "success": True,
        "data": result,
        "meta": {
            "disclaimer": result.get("disclaimer"),
            "not_clinical": True,
            "baseline_source": (
                "direct" if body.baseline_scores
                else "checkin" if any([body.checkin_energy, body.checkin_digestion, body.checkin_sleep])
                else "weak_axes"
            ),
        },
    }


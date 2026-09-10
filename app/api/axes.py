"""八轴稳态路由 — 代谢-炎症轴（PhenoAge 借鉴）与八轴个性化融合

研发路线三期 P2-1：把 PhenoAge 子分接入八轴模型并对外暴露，供前端展示。
诚实边界：本轴为**透明体检指标代理**（非 DNAm 甲基化，非临床），
响应恒定携带 not_clinical=True 与方法说明，前端必须展示免责。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
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
):
    """八轴个性化融合推荐：体检指标驱动代谢-炎症轴，基因/组学驱动其余弱项轴。"""
    from app.lib.fusion_engine import UserProfile, recommend, disclaimer

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

    return {
        "success": True,
        "data": result,
        "meta": {"top_k": body.top_k},
    }

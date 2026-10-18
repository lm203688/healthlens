# -*- coding: utf-8 -*-
"""中医相关 Schema"""

from pydantic import BaseModel


# ── 体质评估 ──────────────────────────────────────────

class ConstitutionInput(BaseModel):
    """体质问卷输入"""

    answers: dict  # 问卷答案 {"q1": 3, "q2": 5, ...}


class ConstitutionOutput(BaseModel):
    """体质评估结果输出"""

    id: str
    constitution_type: str
    constitution_score: dict
    assessed_at: str | None


# ── 舌诊 ─────────────────────────────────────────────

class TongueUploadResponse(BaseModel):
    """舌象图片上传响应"""

    id: str
    image_url: str
    analysis_status: str


class TongueAnalysisOutput(BaseModel):
    """舌象分析结果输出"""

    id: str
    tongue_color: str | None
    tongue_shape: str | None
    coating_color: str | None
    coating_quality: str | None
    sublingual_vein: str | None
    reviewed_by: str | None
    recorded_at: str


# ── 辨证论治 ─────────────────────────────────────────

class TcmDiagnoseInput(BaseModel):
    """中医辨证输入"""

    symptoms: list[str]
    tongue_image_id: str | None = None
    pulse_description: str | None = None  # 如 "弦滑"


class TcmSyndromeOutput(BaseModel):
    """证候输出"""

    id: str
    syndrome_code: str | None
    syndrome_name: str
    principle: str | None
    confidence: float
    evidence: dict | None
    status: str
    created_at: str


# ── 方剂 ─────────────────────────────────────────────

class FormulaRecommendationOutput(BaseModel):
    """方剂推荐输出"""

    id: str
    formula_name: str
    formula_source: str | None
    original_composition: str | None
    modified_composition: str | None
    additions: str | None
    subtractions: str | None
    dosage_instructions: str | None


class FormulaLibraryItem(BaseModel):
    """方剂库条目"""

    id: str
    formula_name: str
    source: str | None
    category: str | None
    indications: str | None


# ── 中药 ─────────────────────────────────────────────

class HerbOutput(BaseModel):
    """中药输出"""

    id: str
    herb_name: str
    pinyin: str | None
    category: str | None
    property: str | None
    flavor: str | None
    meridian: str | None
    efficacy: str | None
    cyp450_metabolism: dict | None

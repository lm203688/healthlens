"""HealthLens 指标别名词典 API（M02 P1）。

三个端点：
  POST /indicator/resolve     — 把中英文/别名 → canonical slug + LOINC + unit_si
  POST /indicator/normalize   — 综合归一化：名称解析 + 单位换算 + 参考区间判定
  GET  /indicator/catalog     — 返回整个词典（含 metadata，供前端下拉、报告渲染）

设计边界（wellness 严守）：
  - 只输出结构化枚举（slug / loinc_code / unit / level / in_range）
  - **不生成任何自然语言描述**——因此无需 claims_guard 包裹
  - 参考区间仅 wellness 参考，不作临床诊断；前端展示时必须携 disclaimer
  - 未命中不 500，返回 ok=False + reason，让上游（OCR/records）决定降级策略
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.utils.indicator_dict import (
    IndicatorDictError,
    STRATA,
    is_loinc_code,
    load_dictionary,
    list_slugs,
    normalize_reference_range,
    normalize_unit,
    resolve_name,
)

router = APIRouter(tags=["指标词典"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    """名称解析请求。"""

    name: str = Field(..., min_length=1, max_length=200, description="中英文/别名/缩写任意一种")
    loinc_code: str | None = Field(None, description="可选：若 OCR 抽到 LOINC，直接以 code 命中")


class NormalizeRequest(BaseModel):
    """综合归一化请求（名称 + 数值 + 单位 + 可选人口学分层）。"""

    name: str = Field(..., min_length=1, max_length=200, description="指标名称（中英/别名）")
    value: float = Field(..., description="原始数值")
    unit: str = Field(..., min_length=1, max_length=50, description="原始单位文本")
    stratum: str = Field(
        "adult_male",
        description=f"人口学分层，取值之一：{' | '.join(STRATA)}",
    )


class CatalogResponse(BaseModel):
    """词典全量返回。"""

    metadata: dict[str, Any]
    slugs: list[str]
    indicators: dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/resolve", summary="名称 → canonical slug + LOINC")
def resolve_endpoint(req: ResolveRequest) -> dict[str, Any]:
    """把中英文/别名解析到 canonical entry。

    优先按 name 走别名索引；若 loinc_code 命中已收录集合，则直接返回对应 entry。
    """
    try:
        # 1) LOINC 直查（若提供且命中）
        if req.loinc_code and is_loinc_code(req.loinc_code):
            data = load_dictionary()
            for slug, entry in data["indicators"].items():
                code = entry.get("loinc_code")
                codes = code if isinstance(code, list) else [code]
                if req.loinc_code in codes:
                    return {
                        "ok": True,
                        "matched_by": "loinc_code",
                        "slug": slug,
                        "name_en": entry["name_en"],
                        "name_cn": entry["name_cn"],
                        "loinc_code": code,
                        "unit_si": entry["unit_si"],
                    }

        # 2) 别名索引
        resolved = resolve_name(req.name)
        if resolved is None:
            return {"ok": False, "reason": "unknown_name", "input": req.name}
        return {"ok": True, "matched_by": "alias", **resolved}

    except IndicatorDictError as e:
        # 词典层错误 → 503（词典不可用，fail-loud，前端可降级到原样透传）
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"indicator dictionary unavailable: {e}",
        )


@router.post("/normalize", summary="名称+数值+单位+分层 → canonical + level")
def normalize_endpoint(req: NormalizeRequest) -> dict[str, Any]:
    """综合归一化：名称解析 → 单位换算 → 分层参考区间判定。"""
    if req.stratum not in STRATA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown stratum: {req.stratum!r}, expected one of {list(STRATA)}",
        )

    try:
        # 1) 名称解析
        resolved = resolve_name(req.name)
        if resolved is None:
            return {"ok": False, "reason": "unknown_name", "input": req.name}

        # 2) 单位换算（限定 slug，避免多指标共享 unit 时歧义）
        entry = load_dictionary()["indicators"][resolved["slug"]]
        unit_alt = entry.get("unit_alt", {})
        factor: float | None = None
        matched_key: str | None = None
        # 先精确匹配，再归一化匹配
        for k, v in unit_alt.items():
            if k == req.unit:
                factor, matched_key = v, k
                break
        if factor is None:
            from app.utils.indicator_dict import _normalize_unit

            target = _normalize_unit(req.unit)
            for k, v in unit_alt.items():
                if _normalize_unit(k) == target:
                    factor, matched_key = v, k
                    break
        if factor is None:
            return {
                "ok": False,
                "reason": "unknown_unit",
                "slug": resolved["slug"],
                "input_unit": req.unit,
                "supported_units": list(unit_alt.keys()),
            }

        canonical_value = float(req.value) * factor

        # 3) 分层参考区间
        ref = normalize_reference_range(resolved["slug"], canonical_value, req.stratum)

        return {
            "ok": True,
            "slug": resolved["slug"],
            "name_en": resolved["name_en"],
            "name_cn": resolved["name_cn"],
            "loinc_code": resolved["loinc_code"],
            "original_value": float(req.value),
            "original_unit": matched_key,
            "unit_si": entry["unit_si"],
            "factor": factor,
            "canonical_value": canonical_value,
            "stratum": req.stratum,
            "ref_range": ref["ref_range"],
            "level": ref["level"],
            "in_range": ref["in_range"],
        }

    except IndicatorDictError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"indicator dictionary unavailable: {e}",
        )


@router.get("/catalog", summary="词典全量（前端下拉/报告渲染用）")
def catalog_endpoint() -> dict[str, Any]:
    """返回整个词典（含 metadata / slugs / indicators）。"""
    try:
        data = load_dictionary()
    except IndicatorDictError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"indicator dictionary unavailable: {e}",
        )
    return {
        "metadata": data.get("metadata", {}),
        "slugs": list_slugs(),
        "indicators": data["indicators"],
    }

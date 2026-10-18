"""PhenoAge（表型年龄）对标模块 — S1-3（2026-10-13）
======================================================================

把文献标准的表型年龄时钟引入 HealthLens，作为 H 轴（先天-肾精/表观遗传）
自造扣分表的**对标基线**：不再声称自造表等价于器官年龄时钟，而是给出
「与已发表时钟的偏移对照装置」。

公式来源（公开公式，非自造；系数照抄，未改一个数）：
  Liu Z, Kuo P-L, Horvath S, Crimmins E, Ferrucci L, Levine M.
  A new aging measure captures morbidity and mortality risk across diverse
  subpopulations from NHANES IV: a cohort study. PLoS Med 2018;15(12):e1002718.
  公式订正（本模块采用的权威版本）：
  Correction. PLoS Med 2019;16(2):e1002760. DOI: 10.1371/journal.pmed.1002760

    PhenotypicAge = 141.50 + ln[-0.00553 × ln(1 - M)] / 0.09165
    M = 1 - exp( -1.51714 × exp(xb) / 0.0076927 )
    xb = -19.907
         - 0.0336 × Albumin          (g/L)
         + 0.0095 × Creatinine       (µmol/L)
         + 0.1953 × Glucose          (mmol/L)
         + 0.0954 × ln(CRP)          (mg/L)
         - 0.0120 × LymphocytePercent(%)
         + 0.0268 × MeanCellVolume   (fL)
         + 0.3306 × RDW              (%)
         + 0.00188 × AlkalinePhosphatase (U/L)
         + 0.0554 × WhiteBloodCellCount (10^9/L = 10^3/µL)
         + 0.0804 × ChronologicalAge  (岁)

单位纪律（踩过坑，写死在 docstring）：
  已发表系数按 **SI 单位**标定。用临床惯用单位会得到荒谬结果
  （例：glucose 95 mg/dL 直接代入 → xb≈+8 → PhenoAge→141+ln 发散）。
  入口函数默认 SI；`from_clinical_units()` 提供 g/dL / mg/dL → SI 转换。

诚实边界：
  - 本模块只是**公开公式的忠实实现 + 对标装置**，不构成诊断；
  - PhenoAge 由 NHANES III 队列拟合，跨人群/跨队列外推需谨慎；
  - HealthLens 的 H 轴自造扣分表与 PhenoAge 共享的生物标志物很少
    （仅 glucose 与 CRP），二者相关性属装置级验证，真实校准需公开队列数据。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# PLoS Med 2019;16(2):e1002760 更正后的系数（SI 单位）
_COEFFS = {
    "intercept": -19.907,
    "albumin": -0.0336,          # g/L
    "creatinine": 0.0095,        # µmol/L
    "glucose": 0.1953,           # mmol/L
    "ln_crp": 0.0954,            # ln(mg/L)
    "lymph_pct": -0.0120,        # %
    "mcv": 0.0268,               # fL
    "rdw": 0.3306,               # %
    "alp": 0.00188,              # U/L
    "wbc": 0.0554,               # 10^9/L
    "chronological_age": 0.0804,  # 岁
}
_MORT_A = 1.51714
_MORT_GAMMA = 0.0076927
_PHENOAGE_BASE = 141.50
_PHENOAGE_SCALE = 0.09165
_PHENOAGE_LOG_K = 0.00553

REQUIRED_KEYS = (
    "albumin_g_l", "creatinine_umol_l", "glucose_mmol_l", "crp_mg_l",
    "lymph_pct", "mcv_fl", "rdw_pct", "alp_u_l", "wbc_1e9_l", "chronological_age",
)


@dataclass
class PhenoAgeResult:
    phenoage: float | None
    delta: float | None            # phenoage - chronological_age（>0 = 表型偏老）
    mortality_10y: float | None    # 10 年死亡风险 Gompertz 估计（NHANES III 参考人群）
    xb: float | None
    complete: bool                 # 9 项标志物 + 年龄是否齐全（缺一即不编造）
    missing: list[str]

    def to_dict(self) -> dict:
        return {
            "phenoage": self.phenoage,
            "delta": self.delta,
            "mortality_10y": self.mortality_10y,
            "xb": self.xb,
            "complete": self.complete,
            "missing": self.missing,
            "formula": "Liu 2018 PLoS Med (correction 2019, DOI 10.1371/journal.pmed.1002760)",
            "not_clinical": True,
        }


def _safe_pos(v: float | None) -> float | None:
    """CRP 取 ln 前必须 >0；<=0 视为缺失（不编造、不填 0）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def phenoage(
    *,
    albumin_g_l: float | None = None,
    creatinine_umol_l: float | None = None,
    glucose_mmol_l: float | None = None,
    crp_mg_l: float | None = None,
    lymph_pct: float | None = None,
    mcv_fl: float | None = None,
    rdw_pct: float | None = None,
    alp_u_l: float | None = None,
    wbc_1e9_l: float | None = None,
    chronological_age: float | None = None,
) -> PhenoAgeResult:
    """按 PLoS Med 更正公式计算 PhenoAge（SI 单位）。

    任何一项缺失 → complete=False、各项为 None（fail-loud，绝不部分编造）。
    """
    vals = {
        "albumin_g_l": albumin_g_l,
        "creatinine_umol_l": creatinine_umol_l,
        "glucose_mmol_l": glucose_mmol_l,
        "crp_mg_l": crp_mg_l,
        "lymph_pct": lymph_pct,
        "mcv_fl": mcv_fl,
        "rdw_pct": rdw_pct,
        "alp_u_l": alp_u_l,
        "wbc_1e9_l": wbc_1e9_l,
        "chronological_age": chronological_age,
    }
    missing = [k for k in REQUIRED_KEYS if vals.get(k) is None]
    crp = _safe_pos(crp_mg_l)
    if crp is None and "crp_mg_l" not in missing:
        missing.append("crp_mg_l")
    if missing:
        return PhenoAgeResult(None, None, None, None, False, missing)

    xb = (
        _COEFFS["intercept"]
        + _COEFFS["albumin"] * float(albumin_g_l)
        + _COEFFS["creatinine"] * float(creatinine_umol_l)
        + _COEFFS["glucose"] * float(glucose_mmol_l)
        + _COEFFS["ln_crp"] * math.log(crp)
        + _COEFFS["lymph_pct"] * float(lymph_pct)
        + _COEFFS["mcv"] * float(mcv_fl)
        + _COEFFS["rdw"] * float(rdw_pct)
        + _COEFFS["alp"] * float(alp_u_l)
        + _COEFFS["wbc"] * float(wbc_1e9_l)
        + _COEFFS["chronological_age"] * float(chronological_age)
    )
    m = 1.0 - math.exp(-_MORT_A * math.exp(xb) / _MORT_GAMMA)
    if not (0.0 < m < 1.0):
        # 极端输入使 Gompertz 概率饱和/归零：不返回无意义年龄，如实报不可计算
        return PhenoAgeResult(None, None, None, round(xb, 4), False,
                              ["mortality_score_out_of_range"])
    pa = _PHENOAGE_BASE + math.log(-_PHENOAGE_LOG_K * math.log(1.0 - m)) / _PHENOAGE_SCALE
    pa = round(pa, 1)
    return PhenoAgeResult(pa, round(pa - float(chronological_age), 1),
                          round(m, 6), round(xb, 4), True, [])


def from_clinical_units(
    *,
    albumin_g_dl: float | None = None,      # g/dL → g/L
    creatinine_mg_dl: float | None = None,  # mg/dL → µmol/L
    glucose_mg_dl: float | None = None,     # mg/dL → mmol/L
    crp_mg_dl: float | None = None,         # mg/dL → mg/L
    lymph_pct: float | None = None,
    mcv_fl: float | None = None,
    rdw_pct: float | None = None,
    alp_u_l: float | None = None,
    wbc_1e3_ul: float | None = None,        # 10^3/µL → 10^9/L（数值相同）
    chronological_age: float | None = None,
) -> PhenoAgeResult:
    """临床惯用单位入口（自动转 SI 后调用 `phenoage`）。"""
    return phenoage(
        albumin_g_l=albumin_g_dl * 10.0 if albumin_g_dl is not None else None,
        creatinine_umol_l=creatinine_mg_dl * 88.4 if creatinine_mg_dl is not None else None,
        glucose_mmol_l=glucose_mg_dl / 18.0182 if glucose_mg_dl is not None else None,
        crp_mg_l=crp_mg_dl * 10.0 if crp_mg_dl is not None else None,
        lymph_pct=lymph_pct,
        mcv_fl=mcv_fl,
        rdw_pct=rdw_pct,
        alp_u_l=alp_u_l,
        wbc_1e9_l=wbc_1e3_ul,
        chronological_age=chronological_age,
    )

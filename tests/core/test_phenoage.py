"""S1-3 PhenoAge 对标模块测试：公式忠实性 + 单位纪律 + fail-loud。

公式权威来源：Liu et al. PLoS Med 2018;15(12):e1002718，公式订正
PLoS Med 2019;16(2):e1002760（DOI 10.1371/journal.pmed.1002760）。
锚点 1 的期望值由本机按公式手工推演（xb=-9.3615 → PhenoAge≈40.3）。
"""
import math

from app.core.phenoage import (
    REQUIRED_KEYS,
    from_clinical_units,
    phenoage,
)


def _mean_40yo_si():
    """40 岁 + NHANES 风格人群均值（SI 单位）。"""
    return dict(
        albumin_g_l=42, creatinine_umol_l=84, glucose_mmol_l=5.3, crp_mg_l=2.0,
        lymph_pct=30, mcv_fl=90, rdw_pct=13, alp_u_l=70, wbc_1e9_l=6.5,
        chronological_age=40,
    )


def test_anchor_population_mean_40yo_reproduces_hand_computed():
    # 手工推演：xb=-9.3615 → M≈0.0168 → PhenoAge≈40.3（≈实岁，符合模型校准语义）
    r = phenoage(**_mean_40yo_si())
    assert r.complete is True
    assert r.missing == []
    assert abs(r.xb - (-9.3615)) < 0.01
    assert abs(r.phenoage - 40.3) < 1.0
    assert abs(r.delta) < 2.0
    assert 0.0 < r.mortality_10y < 0.1


def test_clinical_units_match_si_within_rounding():
    r_si = phenoage(**_mean_40yo_si())
    r_cl = from_clinical_units(
        albumin_g_dl=4.2, creatinine_mg_dl=0.95, glucose_mg_dl=95, crp_mg_dl=0.2,
        lymph_pct=30, mcv_fl=90, rdw_pct=13, alp_u_l=70, wbc_1e3_ul=6.5,
        chronological_age=40,
    )
    # 单位换算存在舍入（95/18.0182=5.2726 vs 5.3），允许 0.2 岁差
    assert r_cl.complete is True
    assert abs(r_cl.phenoage - r_si.phenoage) <= 0.2


def test_unhealthy_profile_is_phenotypically_older():
    healthy = phenoage(**_mean_40yo_si())
    unhealthy = phenoage(
        albumin_g_l=38, creatinine_umol_l=110, glucose_mmol_l=9.5, crp_mg_l=8.0,
        lymph_pct=18, mcv_fl=96, rdw_pct=16.5, alp_u_l=110, wbc_1e9_l=9.0,
        chronological_age=40,
    )
    assert unhealthy.phenoage > healthy.phenoage
    assert unhealthy.delta > 0


def test_healthy_young_profile_is_phenotypically_younger():
    r = phenoage(
        albumin_g_l=45, creatinine_umol_l=70, glucose_mmol_l=4.8, crp_mg_l=0.5,
        lymph_pct=35, mcv_fl=88, rdw_pct=12.2, alp_u_l=55, wbc_1e9_l=5.5,
        chronological_age=25,
    )
    assert r.delta < 0


def test_missing_input_fails_loud():
    r = phenoage(albumin_g_l=42, chronological_age=40)
    assert r.complete is False
    assert r.phenoage is None and r.delta is None
    assert len(r.missing) == len(REQUIRED_KEYS) - 2
    assert "albumin_g_l" not in r.missing


def test_non_positive_crp_treated_as_missing():
    r = phenoage(**_mean_40yo_si() | {"crp_mg_l": 0})
    assert r.complete is False
    assert r.missing == ["crp_mg_l"]
    assert r.phenoage is None


def test_result_dict_has_honesty_fields():
    r = phenoage(**_mean_40yo_si())
    d = r.to_dict()
    assert d["not_clinical"] is True
    assert "10.1371/journal.pmed.1002760" in d["formula"]

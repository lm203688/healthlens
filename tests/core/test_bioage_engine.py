"""生物学年龄 / 八轴「代谢-炎症轴」量化引擎测试

明确边界：本模块是透明体检指标代理（wellness proxy），非 DNAm PhenoAge，
所有结果 not_clinical=True，仅供养生参考，不构成诊断。
"""
import pytest

from app.core.bioage_engine import (
    BioAgeEngine,
    AXIS_KEY,
    AXIS_LABEL,
)


def _healthy():
    return BioAgeEngine().assess(
        40,
        is_male=True,
        glucose=4.8,      # < 5.0 理想区间
        hba1c=5.4,        # < 5.7
        hs_crp=0.5,       # < 1.0
        waist_cm=85,      # <= 102 (male)
        hdl=1.4,          # >= 1.0 (male)
        triglycerides=1.0,  # < 1.7
        sbp=115,          # < 120
        bmi=22.0,         # 18.5-24.9
    )


def test_healthy_axis_full():
    """全正常指标：轴分 100、生物年龄 = 实际年龄、偏移 0。"""
    r = _healthy()
    assert r.not_clinical is True
    assert r.axis_score == 100.0
    assert r.bio_age == 40.0
    assert r.delta == 0.0


def test_poor_axis_zero():
    """全异常指标：轴分触底 0、生物年龄显著偏高。"""
    r = BioAgeEngine().assess(
        40,
        is_male=True,
        glucose=8.0,
        hba1c=7.5,
        hs_crp=5.0,
        waist_cm=120,
        hdl=0.6,
        triglycerides=3.0,
        sbp=160,
        bmi=32.0,
    )
    assert r.axis_score == 0.0
    assert r.bio_age > 40
    assert r.delta > 0


def test_markers_present():
    """八项生物标志物全部评估。"""
    r = _healthy()
    keys = {m.key for m in r.markers}
    for k in ("glucose", "hba1c", "hs_crp", "waist", "hdl", "trig", "sbp", "bmi"):
        assert k in keys


def test_unknown_markers_not_crash():
    """指标全缺失（None）不应崩溃，标记为 unknown、轴分满分。"""
    r = BioAgeEngine().assess(50, is_male=False)
    assert r.axis_score == 100.0
    assert all(m.status == "unknown" for m in r.markers)


def test_delta_band():
    """年龄偏移 -> 八轴稳态描述的去医疗化分级。"""
    eng = BioAgeEngine()
    assert "良好" in eng.delta_band(0.0)
    assert "轻度" in eng.delta_band(2.0)
    assert "明显" in eng.delta_band(5.0)
    assert "显著" in eng.delta_band(8.0)


def test_axis_constants():
    """八轴标识供融合引擎引用。"""
    assert AXIS_KEY == "metabolic_inflammatory"
    assert AXIS_LABEL == "代谢-炎症轴"

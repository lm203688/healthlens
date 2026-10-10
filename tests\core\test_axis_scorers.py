"""P0-1 八轴打分器单元测试：验证每条轴可计算、缺失数据显式 unmeasured、不填 0。"""
import pytest

from app.core.axis_scorers import (
    ALL_AXES,
    score_all_axes,
    score_axis,
)


def test_all_eight_axes_present():
    assert set(ALL_AXES) == {"A", "B", "C", "D", "E", "F", "G", "H"}


def test_axis_with_real_data_is_measured_and_scored():
    bm = {"glucose": 6.4, "hba1c": 6.1, "waist_cm": 98, "triglycerides": 2.0,
          "bmi": 26.5, "hdl": 0.95, "sbp": 135, "dbp": 88, "hs_crp": 2.2}
    wearable = {"hrv_rmssd": 22, "resting_hr": 82, "sleep_midpoint_jitter": 65,
                "sleep_duration_h": 6.0, "social_jetlag_h": 1.5}
    res = score_all_axes(biomarkers=bm, wearable=wearable,
                                   symptoms=["疲劳", "焦虑"], bioage_delta=4.0, is_male=True)
    # 有数据 → measured=True 且 score 在 0-100
    for ax in ("A", "B", "C", "E", "F", "G", "H"):
        assert res[ax].measured is True, f"{ax} 应有数据"
        assert res[ax].score is not None
        assert 0.0 <= res[ax].score <= 100.0
    # D 有睡眠数据也 measured
    assert res["D"].measured is True


def test_missing_data_is_unmeasured_not_zero():
    # 完全不给任何输入：所有轴必须 unmeasured，score 必须为 None（禁止填 0）
    res = score_all_axes()
    for ax in ALL_AXES:
        assert res[ax].measured is False, f"{ax} 缺失时应 unmeasured"
        assert res[ax].score is None, f"{ax} 缺失时 score 必须为 None（不得假装测过）"
        assert res[ax].status == "unmeasured"


def test_no_wearable_makes_rhythm_axes_unmeasured():
    bm = {"glucose": 5.4, "hs_crp": 0.6, "sbp": 118, "hdl": 1.4}
    res = score_all_axes(biomarkers=bm)
    # 有体检 → A/C/F 可测
    assert res["A"].measured is True
    assert res["C"].measured is True
    assert res["F"].measured is True
    # 无睡眠/HRV → D/E/G 必须 unmeasured（诚实）
    assert res["D"].measured is False
    assert res["E"].measured is False
    assert res["G"].measured is False


def test_single_axis_score_boundaries():
    # 极端坏数据（高敏 CRP + IL-6 同时升高）触发 measured_risk
    bad = score_axis("F", biomarkers={"hs_crp": 8.0, "il6": 5.0})
    assert bad.measured is True
    assert bad.status == "measured_risk"
    assert bad.score < 70
    # 理想数据触发 measured_normal
    good = score_axis("F", biomarkers={"hs_crp": 0.4})
    assert good.status == "measured_normal"
    assert good.score >= 70

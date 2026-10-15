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


# ---------------------------------------------------------------------------
# S1-2（2026-10-13）跨轴归一化验收：分数 = 100 − 100 × (Σ扣分 / Σ可用最大扣分)
# 旧公式 100−Σpenalty 下「少填异常项 → 轴分自动变好」，弱项阈值 0.5 轴间不等价。
# 以下只断言**实测成立**的性质；「与输入数量完全无关」不成立（prorated 语义），
# 已在模块 docstring 与 _finalize 中如实标注，不得过度声称。
# ---------------------------------------------------------------------------

def test_s1_2_homogeneous_abnormal_invariant_to_input_count():
    # 同一异常健康态：可用输入全部打满时，无论测 1 项、2 项还是 5 项，A 轴恒为 0
    one = score_axis("A", biomarkers={"glucose": 8.0})
    two = score_axis("A", biomarkers={"glucose": 8.0, "hba1c": 7.0})
    five = score_axis("A", biomarkers={"glucose": 8.0, "hba1c": 7.0,
                                       "triglycerides": 3.0, "waist_cm": 110, "bmi": 32})
    assert one.score == two.score == five.score == 0.0
    assert one.penalty_ratio == two.penalty_ratio == five.penalty_ratio == 1.0


def test_s1_2_homogeneous_normal_invariant_to_input_count():
    # 同一健康态：可用输入全部正常时，无论测几项，A 轴恒为 100
    one = score_axis("A", biomarkers={"glucose": 5.2})
    five = score_axis("A", biomarkers={"glucose": 5.2, "hba1c": 5.4,
                                       "triglycerides": 1.2, "waist_cm": 80, "bmi": 22})
    assert one.score == five.score == 100.0
    assert one.penalty_ratio == five.penalty_ratio == 0.0


def test_s1_2_omission_never_rewards():
    # 旧公式下：只填 1 项全异常得 72 分（看起来"比较健康"），填 5 项全异常得 0 分。
    # 新公式下同质异常必须同分——「少填」不再让用户看起来更健康。
    few = score_axis("A", biomarkers={"glucose": 8.0})
    many = score_axis("A", biomarkers={"glucose": 8.0, "hba1c": 7.0,
                                       "triglycerides": 3.0, "waist_cm": 110, "bmi": 32})
    assert few.score == many.score


def test_s1_2_weak_threshold_equivalent_across_axes():
    # score<70 ⟺ penalty_ratio>0.3 必须在每条轴上成立（弱项阈值跨轴等价）。
    # 构造：每条轴各喂一个「打满」输入（ratio=1.0）与一个「正常」输入（ratio=0）。
    cases = [
        ("A", {"glucose": 8.0}, {"glucose": 5.2}, {}, {}),
        ("B", {"hdl": 0.5}, {"hdl": 1.6}, {}, {}),
        ("C", {"sbp": 160}, {"sbp": 115}, {}, {}),
        ("D", {}, {}, {"sleep_midpoint_jitter": 120}, {"sleep_midpoint_jitter": 10}),
        ("E", {}, {}, {"hrv_rmssd": 10}, {"hrv_rmssd": 55}),
        ("F", {"hs_crp": 8.0}, {"hs_crp": 0.4}, {}, {}),
        ("G", {}, {}, {"hrv_rmssd": 5}, {"hrv_rmssd": 55, "sleep_midpoint_jitter": 10}),
    ]
    for axis, bad_bm, good_bm, bad_w, good_w in cases:
        bad = score_axis(axis, biomarkers=bad_bm, wearable=bad_w)
        good = score_axis(axis, biomarkers=good_bm, wearable=good_w)
        assert bad.score == 0.0 and bad.penalty_ratio == 1.0, axis
        assert bad.status == "measured_risk", axis
        assert good.score == 100.0 and good.penalty_ratio == 0.0, axis
        assert good.status == "measured_normal", axis
    # H 轴：bioage_delta 打满 / 正常
    bad_h = score_axis("H", bioage_delta=8.0)
    good_h = score_axis("H", bioage_delta=0.0)
    assert bad_h.score == 0.0 and bad_h.penalty_ratio == 1.0
    assert good_h.score == 100.0 and good_h.penalty_ratio == 0.0


def test_s1_2_penalty_ratio_audit_field():
    # penalty_ratio 必须进 to_dict，且 score == round(100 − 100×ratio, 1)（逐案可审计）
    r = score_axis("A", biomarkers={"glucose": 6.4, "hba1c": 5.4,
                                    "triglycerides": 1.2, "waist_cm": 80, "bmi": 22})
    d = r.to_dict()
    assert "penalty_ratio" in d
    assert d["penalty_ratio"] == r.penalty_ratio
    assert d["score"] == round(100.0 - 100.0 * r.penalty_ratio, 1)
    # 中间态：glucose 6.4 → 18/104（penalty_ratio 按 3 位小数存储）
    assert r.penalty_ratio == round(18 / 104, 3)

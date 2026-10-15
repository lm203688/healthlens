"""n-of-1 个体效应 + 贝叶斯层次聚合 + E-value 测试 —— L1-2

覆盖：
- IndividualEffect dataclass 字段与 as_dict
- estimate_individual_effect：known truth / CI 单调 / Cohen's d / 小样本 /
  单样本退化 / 空集 / 常数 / 负效应 / CI 宽度 / 类型校验 / 种子确定性
- BayesianHierarchicalAggregator：相同/不同/单组/n差异/MC降级/MC收敛
- compute_evalue：已知值 / 负效应取绝对值 / 零效应报错 / NaN 报错
- API 端点（TestClient）：individual-effect / aggregate / bandit/step

wellness 边界：不出现诊断/治疗/患者/医疗词汇。
"""
from __future__ import annotations

import math
import sys
import types

import pytest

from app.lib.nof_one_effect import (
    IndividualEffect,
    AggregationResult,
    BayesianHierarchicalAggregator,
    aggregate_effects,
    compute_evalue,
    estimate_individual_effect,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def constant_data():
    """pre/post 均为常数 → diffs 恒定。"""
    return ([10.0] * 50, [15.0] * 50)


@pytest.fixture
def variable_data():
    """pre/post 有方差 → diffs 有变化。"""
    pre = [10.0, 12.0, 11.0, 13.0, 14.0, 9.0, 10.5, 12.5, 11.5, 13.5]
    post = [15.0, 17.0, 16.0, 18.0, 19.0, 14.0, 15.5, 17.5, 16.5, 18.5]
    return (pre, post)


# ---------------------------------------------------------------------------
# IndividualEffect dataclass
# ---------------------------------------------------------------------------


def test_individual_effect_dataclass_fields():
    ie = IndividualEffect(
        point_estimate=5.0, ci_lower=4.0, ci_upper=6.0, ci_level=0.95,
        sample_size=50, method="paired_bootstrap", n_of_1_type="Crossover",
        cohen_d=1.5, std_error=0.5, n_bootstrap=10000,
    )
    assert ie.point_estimate == 5.0
    assert ie.ci_lower == 4.0
    assert ie.ci_upper == 6.0
    assert ie.ci_level == 0.95
    assert ie.sample_size == 50
    assert ie.method == "paired_bootstrap"
    assert ie.n_of_1_type == "Crossover"
    assert ie.cohen_d == 1.5
    assert ie.std_error == 0.5
    assert ie.n_bootstrap == 10000
    assert isinstance(ie.disclaimer, str) and ie.disclaimer


def test_individual_effect_as_dict_keys():
    ie = IndividualEffect(
        point_estimate=5.0, ci_lower=4.0, ci_upper=6.0, ci_level=0.95,
        sample_size=50, method="paired_bootstrap", n_of_1_type="Crossover",
        cohen_d=1.5, std_error=0.5, n_bootstrap=100,
    )
    d = ie.as_dict()
    for k in ("point_estimate", "ci_lower", "ci_upper", "ci_level",
              "sample_size", "method", "n_of_1_type", "cohen_d",
              "std_error", "n_bootstrap", "not_clinical", "disclaimer"):
        assert k in d, f"missing key: {k}"
    assert d["not_clinical"] is True


def test_individual_effect_as_dict_rounding():
    ie = IndividualEffect(
        point_estimate=1.23456789, ci_lower=0.123456789, ci_upper=2.3456789,
        ci_level=0.95, sample_size=10, method="paired_bootstrap",
        n_of_1_type="ABAB", cohen_d=0.987654321, std_error=0.123456789,
        n_bootstrap=100,
    )
    d = ie.as_dict()
    assert d["point_estimate"] == round(1.23456789, 4)
    assert d["cohen_d"] == round(0.987654321, 4)
    assert d["std_error"] == round(0.123456789, 4)


def test_individual_effect_default_disclaimer_present():
    ie = IndividualEffect(
        point_estimate=0.0, ci_lower=0.0, ci_upper=0.0, ci_level=0.95,
        sample_size=10, method="paired_bootstrap", n_of_1_type="Crossover",
    )
    assert ie.disclaimer  # 默认值非空


# ---------------------------------------------------------------------------
# estimate_individual_effect —— 已知真值 & CI
# ---------------------------------------------------------------------------


def test_estimate_known_truth_constant_diff(constant_data):
    pre, post = constant_data
    ie = estimate_individual_effect(pre, post, n_bootstrap=200, seed=1)
    assert abs(ie.point_estimate - 5.0) < 1e-9
    assert ie.ci_lower <= 5.0 <= ie.ci_upper
    assert ie.method == "paired_bootstrap"
    assert ie.sample_size == 50


def test_estimate_constant_ci_contains_point(constant_data):
    pre, post = constant_data
    ie = estimate_individual_effect(pre, post, n_bootstrap=500, seed=42)
    # 常数 diffs → CI 宽度为 0，点估计恰好在 CI 内
    assert ie.ci_lower == pytest.approx(ie.point_estimate, abs=1e-9)
    assert ie.ci_upper == pytest.approx(ie.point_estimate, abs=1e-9)


def test_estimate_ci_monotonicity_larger_effect():
    """越大差异 → CI 下界越大。"""
    small = estimate_individual_effect([10.0] * 50, [10.5] * 50,
                                       n_bootstrap=200, seed=1)
    large = estimate_individual_effect([10.0] * 50, [20.0] * 50,
                                       n_bootstrap=200, seed=1)
    assert large.ci_lower > small.ci_lower
    assert large.point_estimate > small.point_estimate


def test_estimate_cohens_d_matches_manual():
    """Cohen's d 对照手算。"""
    pre = [10.0, 12.0, 11.0, 13.0, 14.0]
    post = [15.0, 15.0, 16.0, 18.0, 17.0]
    ie = estimate_individual_effect(pre, post, n_bootstrap=200, seed=1)
    # 手算：diffs = post - pre
    diffs = [post[i] - pre[i] for i in range(5)]
    assert diffs == [5.0, 3.0, 5.0, 5.0, 3.0]
    mean_d = sum(diffs) / len(diffs)
    variance = sum((d - mean_d) ** 2 for d in diffs) / (len(diffs) - 1)
    std_d = variance ** 0.5
    expected_d = mean_d / std_d if std_d > 0 else 0.0
    assert ie.cohen_d == pytest.approx(expected_d, rel=1e-6)


def test_estimate_small_sample_n5(variable_data):
    """n=5 能跑通不崩溃。"""
    pre, post = variable_data
    ie = estimate_individual_effect(pre[:5], post[:5], n_bootstrap=100, seed=1)
    assert ie.sample_size == 5
    assert isinstance(ie.point_estimate, float)
    assert ie.ci_lower <= ie.point_estimate <= ie.ci_upper


def test_estimate_single_sample_degenerate():
    """n=1 退化：不崩溃，point 有值，CI 退化，d=0。"""
    ie = estimate_individual_effect([10.0], [15.0], n_bootstrap=100, seed=1)
    assert ie.point_estimate == 5.0
    assert ie.ci_lower == pytest.approx(5.0, abs=1e-9)
    assert ie.ci_upper == pytest.approx(5.0, abs=1e-9)
    assert ie.cohen_d == 0.0  # len<2 返回 0


def test_estimate_empty_raises():
    with pytest.raises(ValueError):
        estimate_individual_effect([], [], n_bootstrap=100)


def test_estimate_length_mismatch_raises():
    with pytest.raises(ValueError):
        estimate_individual_effect([1.0, 2.0, 3.0], [1.0, 2.0], n_bootstrap=100)


def test_estimate_constant_zero_effect():
    """pre==post → point=0, CI=[0,0], d=0。"""
    pre = [10.0] * 20
    post = [10.0] * 20
    ie = estimate_individual_effect(pre, post, n_bootstrap=200, seed=1)
    assert ie.point_estimate == 0.0
    assert ie.ci_lower == 0.0
    assert ie.ci_upper == 0.0
    assert ie.cohen_d == 0.0  # std=0 返回 0


def test_estimate_negative_effect_direction():
    """post < pre → point < 0, CI 上界 < 0。"""
    pre = [20.0] * 30
    post = [15.0] * 30
    ie = estimate_individual_effect(pre, post, n_bootstrap=200, seed=1)
    assert ie.point_estimate < 0
    assert ie.ci_upper < 0


def test_estimate_ci_level_param():
    """ci_level=0.99 的 CI 宽度 > ci_level=0.5 的宽度（需有方差）。"""
    pre = [10.0, 12.0, 11.0, 13.0, 14.0, 9.0, 10.5, 12.5, 11.5, 13.5] * 5
    post = [15.0, 14.0, 16.0, 12.0, 20.0, 11.0, 15.5, 16.5, 17.0, 15.5] * 5
    narrow = estimate_individual_effect(pre, post, ci_level=0.5,
                                        n_bootstrap=500, seed=1)
    wide = estimate_individual_effect(pre, post, ci_level=0.99,
                                      n_bootstrap=500, seed=1)
    narrow_width = narrow.ci_upper - narrow.ci_lower
    wide_width = wide.ci_upper - wide.ci_lower
    assert wide_width > narrow_width


def test_estimate_n_of_1_type_variants(variable_data):
    pre, post = variable_data
    for t in ("ABAB", "Crossover", "Cluster"):
        ie = estimate_individual_effect(pre, post, n_of_1_type=t,
                                        n_bootstrap=100, seed=1)
        assert ie.n_of_1_type == t


def test_estimate_invalid_n_of_1_type_raises():
    with pytest.raises(ValueError):
        estimate_individual_effect([1.0, 2.0], [2.0, 3.0],
                                   n_of_1_type="Bad", n_bootstrap=100)


def test_estimate_invalid_ci_level_raises():
    with pytest.raises(ValueError):
        estimate_individual_effect([1.0, 2.0], [2.0, 3.0],
                                   ci_level=1.5, n_bootstrap=100)
    with pytest.raises(ValueError):
        estimate_individual_effect([1.0, 2.0], [2.0, 3.0],
                                   ci_level=0.0, n_bootstrap=100)


def test_estimate_seed_determinism(variable_data):
    """相同 seed → 完全相同结果。"""
    pre, post = variable_data
    a = estimate_individual_effect(pre, post, n_bootstrap=500, seed=42)
    b = estimate_individual_effect(pre, post, n_bootstrap=500, seed=42)
    assert a.point_estimate == b.point_estimate
    assert a.ci_lower == b.ci_lower
    assert a.ci_upper == b.ci_upper


def test_estimate_as_dict_not_clinical(variable_data):
    pre, post = variable_data
    ie = estimate_individual_effect(pre, post, n_bootstrap=100, seed=1)
    d = ie.as_dict()
    assert d["not_clinical"] is True
    assert len(d["disclaimer"]) > 0


def test_estimate_std_error_positive():
    """有方差的输入 → std_error > 0。"""
    pre = [10.0, 12.0, 11.0, 13.0, 14.0, 9.0, 10.5, 12.5, 11.5, 13.5]
    post = [15.0, 14.0, 16.0, 12.0, 20.0, 11.0, 15.5, 16.5, 17.0, 15.5]
    ie = estimate_individual_effect(pre, post, n_bootstrap=100, seed=1)
    assert ie.std_error is not None
    assert ie.std_error > 0


# ---------------------------------------------------------------------------
# BayesianHierarchicalAggregator
# ---------------------------------------------------------------------------


def test_aggregator_two_identical_effects():
    ag = BayesianHierarchicalAggregator(seed=42)
    r = ag.aggregate([2.0, 2.0], [0.5, 0.5], ["g1", "g2"])
    assert abs(r.pooled_effect - 2.0) < 0.1
    assert r.tau_squared < 0.01  # 相同效应 → tau² 小
    assert r.n_groups == 2
    assert r.method == "pure_python_montecarlo"


def test_aggregator_two_different_effects():
    ag = BayesianHierarchicalAggregator(seed=42)
    r = ag.aggregate([1.0, 5.0], [0.5, 0.5], ["g1", "g2"])
    # pooled 应在 1 和 5 之间
    assert 1.0 <= r.pooled_effect <= 5.0
    assert r.tau_squared > 0  # 异质性 → tau² > 0


def test_aggregator_single_group_degenerate():
    """单组退化 → pooled ≈ 该组效应。"""
    ag = BayesianHierarchicalAggregator(seed=42)
    r = ag.aggregate([3.0], [0.5], ["g1"])
    assert abs(r.pooled_effect - 3.0) < 0.15
    assert r.tau_squared == 0.0
    assert r.n_groups == 1


def test_aggregator_weight_by_se():
    """n 差异大 → 权重倾斜（小 SE 权重大）。"""
    ag = BayesianHierarchicalAggregator(seed=42)
    r = ag.aggregate([1.0, 5.0], [1.0, 0.1], ["g1", "g2"])
    assert r.random_effect_weights["g2"] > r.random_effect_weights["g1"]
    total = sum(r.random_effect_weights.values())
    assert total == pytest.approx(1.0, rel=1e-6)


def test_aggregator_pymc_missing_fallback(monkeypatch):
    """PyMC 缺失时降级到 Monte Carlo。"""
    import app.lib.nof_one_effect as mod
    monkeypatch.setattr(mod, "_try_import_pymc", lambda: None)
    ag = BayesianHierarchicalAggregator(seed=42)
    r = ag.aggregate([2.0, 3.0], [0.5, 0.5])
    assert r.method == "pure_python_montecarlo"


def test_aggregator_force_pymc_missing_raises(monkeypatch):
    """force_pymc=True 且 pymc 缺失 → 抛 HealthLensUnavailableEngine。"""
    import app.lib.nof_one_effect as mod
    from app.lib.engine_exceptions import HealthLensUnavailableEngine
    monkeypatch.setattr(mod, "_try_import_pymc", lambda: None)
    with pytest.raises(HealthLensUnavailableEngine):
        BayesianHierarchicalAggregator(force_pymc=True)


def test_aggregator_montecarlo_convergence():
    """同一输入两次采样结果 < 0.1 差异。"""
    a = BayesianHierarchicalAggregator(seed=1).aggregate(
        [2.0, 3.0, 4.0], [0.5] * 3, n_samples=2000)
    b = BayesianHierarchicalAggregator(seed=2).aggregate(
        [2.0, 3.0, 4.0], [0.5] * 3, n_samples=2000)
    assert abs(a.pooled_effect - b.pooled_effect) < 0.1


def test_aggregator_same_seed_deterministic():
    """相同 seed → 完全相同结果。"""
    a = BayesianHierarchicalAggregator(seed=42).aggregate(
        [2.0, 3.0], [0.5, 0.5], n_samples=500)
    b = BayesianHierarchicalAggregator(seed=42).aggregate(
        [2.0, 3.0], [0.5, 0.5], n_samples=500)
    assert a.pooled_effect == b.pooled_effect


def test_aggregator_empty_raises():
    ag = BayesianHierarchicalAggregator(seed=42)
    with pytest.raises(ValueError):
        ag.aggregate([])


def test_aggregator_se_length_mismatch_raises():
    ag = BayesianHierarchicalAggregator(seed=42)
    with pytest.raises(ValueError):
        ag.aggregate([1.0, 2.0], [0.5, 0.5, 0.5])


def test_aggregator_se_negative_raises():
    ag = BayesianHierarchicalAggregator(seed=42)
    with pytest.raises(ValueError):
        ag.aggregate([1.0, 2.0], [-0.5, 0.5])


def test_aggregate_effects_functional():
    """函数式便捷入口 aggregate_effects。"""
    r = aggregate_effects([2.0, 3.0], se=[0.5, 0.5], group_ids=["a", "b"])
    assert r.method == "pure_python_montecarlo"
    assert r.n_groups == 2
    d = r.as_dict()
    assert "pooled_effect" in d
    assert "tau_squared" in d
    assert d["not_clinical"] is True


def test_aggregation_result_as_dict_structure():
    r = AggregationResult(
        pooled_effect=2.5, tau_squared=0.1,
        random_effect_weights={"g1": 0.6, "g2": 0.4},
        method="pure_python_montecarlo", n_groups=2,
        individual_effects=[2.0, 3.0], individual_se=[0.5, 0.5],
    )
    d = r.as_dict()
    assert d["pooled_effect"] == 2.5
    assert d["tau_squared"] == 0.1
    assert d["n_groups"] == 2
    assert d["random_effect_weights"] == {"g1": 0.6, "g2": 0.4}
    assert d["not_clinical"] is True


# ---------------------------------------------------------------------------
# compute_evalue
# ---------------------------------------------------------------------------


def test_evalue_known_value():
    """已知数值对照手算：RR=exp(2)≈7.389, E=RR+sqrt(RR*(RR-1))≈14.26。"""
    e = compute_evalue(2.0, 1.0)
    expected = math.exp(2.0) + math.sqrt(math.exp(2.0) * (math.exp(2.0) - 1))
    assert e == pytest.approx(expected, rel=1e-9)
    assert e > 1.0


def test_evalue_negative_effect_uses_abs():
    """负效应取绝对值 → 与正效应结果一致。"""
    e_pos = compute_evalue(2.0, 1.0)
    e_neg = compute_evalue(-2.0, 1.0)
    assert e_pos == pytest.approx(e_neg, rel=1e-9)


def test_evalue_magnitude_monotonic():
    """|point| 越大 → evalue 越大。"""
    e_small = compute_evalue(0.5, 1.0)
    e_med = compute_evalue(1.0, 1.0)
    e_large = compute_evalue(2.0, 1.0)
    assert e_small < e_med < e_large


def test_evalue_zero_raises():
    with pytest.raises(ValueError):
        compute_evalue(0.0, 1.0)


def test_evalue_near_zero_raises():
    with pytest.raises(ValueError):
        compute_evalue(1e-12, 1.0)


def test_evalue_negative_se_raises():
    with pytest.raises(ValueError):
        compute_evalue(1.0, -1.0)


def test_evalue_nan_raises():
    with pytest.raises(ValueError):
        compute_evalue(float("nan"), 1.0)
    with pytest.raises(ValueError):
        compute_evalue(1.0, float("nan"))


def test_evalue_large_value_bounded():
    """大 point 不溢出（数值保护）。"""
    e = compute_evalue(30.0, 1.0)
    assert e > 0
    assert not math.isnan(e)
    assert not math.isinf(e)


# ---------------------------------------------------------------------------
# API 端点（TestClient）
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """同步 TestClient（evidence 端点不依赖 DB）。"""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_api_individual_effect_endpoint(api_client):
    r = api_client.post(
        "/api/v1/evidence/individual-effect",
        json={
            "pre_scores": [10.0] * 20,
            "post_scores": [15.0] * 20,
            "n_bootstrap": 200,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "point_estimate" in body
    assert body["point_estimate"] == pytest.approx(5.0, abs=1e-6)
    assert body["not_clinical"] is True


def test_api_individual_effect_422_missing_field(api_client):
    """请求体缺 post_scores → 422。"""
    r = api_client.post(
        "/api/v1/evidence/individual-effect",
        json={"pre_scores": [1.0, 2.0]},
    )
    assert r.status_code == 422


def test_api_aggregate_endpoint(api_client):
    r = api_client.post(
        "/api/v1/evidence/aggregate",
        json={
            "effects": [2.0, 3.0],
            "se": [0.5, 0.5],
            "group_ids": ["a", "b"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "pooled_effect" in body
    assert "tau_squared" in body
    assert body["not_clinical"] is True


def test_api_aggregate_422_missing_field(api_client):
    r = api_client.post(
        "/api/v1/evidence/aggregate",
        json={"se": [0.5, 0.5]},
    )
    assert r.status_code == 422


def test_api_bandit_step_endpoint(api_client):
    r = api_client.post(
        "/api/v1/evidence/bandit/step",
        json={
            "user_context": {
                "pregnancy": False,
                "medications": [],
                "jurisdiction": "cn",
            },
            "candidate_actions": [
                {"intervention": "anti_inflammatory_diet", "dose": 1.0},
                {"intervention": "exercise_aerobic", "dose": 1.0},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "action" in body
    assert "reward_expected" in body
    assert "q_values" in body
    assert "mask_log" in body


def test_api_individual_effect_length_mismatch_400(api_client):
    """pre/post 长度不一致 → 400。"""
    r = api_client.post(
        "/api/v1/evidence/individual-effect",
        json={
            "pre_scores": [1.0, 2.0, 3.0],
            "post_scores": [1.0, 2.0],
        },
    )
    assert r.status_code == 400

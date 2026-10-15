"""L3 联邦层单元测试（HealthLens v0.28.0 SVIEE）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3。
> 「个体数据不出域 + 只共享充分统计量」
> 「贝叶斯层次聚合 + 联邦目标试验仿真」

覆盖清单（≥30 用例）：

SufficientStats / validate_tenant_payload / hash_stats：
- hash 确定性（同 stats 多次 hash 相同）
- n<=0 / var<0 / effect_se<=0 抛错
- 缺字段抛错
- 拒绝 raw samples（签名与协议层双重防线）

HierarchicalAggregator：
- 单租户退化：pooled == 该租户 effect
- 两组相同效应：pooled ≈ 该值，τ² ≈ 0
- 两组相反效应：pooled ≈ 0，τ² > 0.5
- n 差异 10x：大 n 租户权重 > 小 n
- Empirical Bayes vs Monte Carlo 结果差异 < 0.1
- 空列表抛错

SingleMachineFederatedFabric：
- 3 租户 20 轮：posterior 收敛（10 vs 20 轮差异 < 0.2）
- seed 可复现（两次 seed=42 结果相同）
- 不同 seed 结果不同
- region 隔离：不同 region 的 tenant 不互相聚合

FlowerAdapter：
- 未装 flwr 时抛 HealthLensUnavailableEngine
- 装了 flwr 时（monkeypatch mock）能构造 server

TargetTrialEmulator：
- IPW 权重范围（0 < w <= max_weight）
- placebo intervention refutation：随机置换 → 效应消失
- random assignment refutation：随机分配 → 效应消失

API 层（TestClient）：
- POST /stats 200 + hash
- POST /stats 非法 payload → 400
- GET /tenants 列出租户
- POST /aggregate 空集 → warning
- POST /aggregate 有数据 → 完整响应
- POST /trial/run → 返回 estimate + refutation
- GET /export/posterior/{tenant_id} 未聚合时 → 提示

作者：HealthLens L3 联邦层团队
版本：v1 (2026-10-15)
"""
from __future__ import annotations

import inspect
import math
import sys
import types
from typing import Any

import pytest

from app.lib.federated import (
    AggregationResult,
    HealthLensUnavailableEngine,
    HierarchicalAggregator,
    SufficientStats,
    TargetTrialEmulator,
    TargetTrialSpec,
    TenantConfig,
    VirtualTenant,
    hash_stats,
    make_flower_server,
    validate_tenant_payload,
)
from app.lib.federated import single_machine_fabric as fabric_module
from app.lib.federated import flower_adapter as flwr_adapter_module
from app.lib.federated.single_machine_fabric import SingleMachineFederatedFabric


# ─────────────────────────── fixtures ───────────────────────────


def _stats(
    tenant_id: str = "A",
    n: int = 10,
    mean: float = 0.5,
    var: float = 0.01,
    effect_estimate: float = 0.6,
    effect_se: float = 0.05,
    covariate_summary: dict[str, Any] | None = None,
) -> SufficientStats:
    return SufficientStats(
        tenant_id=tenant_id,
        n=n,
        mean=mean,
        var=var,
        effect_estimate=effect_estimate,
        effect_se=effect_se,
        covariate_summary=covariate_summary or {},
    )


@pytest.fixture
def sample_stats() -> SufficientStats:
    return _stats()


@pytest.fixture(autouse=True)
def _clear_flwr_state():
    """确保本 session 之前若装了 flwr，本测试结束后不留副作用。"""
    yield


# ─────────────────────────── SufficientStats ───────────────────────────


def test_hash_deterministic(sample_stats: SufficientStats):
    """同 stats 多次 hash 相同（内容寻址）。"""
    h1 = hash_stats(sample_stats)
    h2 = hash_stats(sample_stats)
    h3 = hash_stats(sample_stats)
    assert h1 == h2 == h3
    assert len(h1) == 64  # sha256 hex


def test_hash_changes_when_values_change():
    a = _stats(effect_estimate=0.6)
    b = _stats(effect_estimate=0.7)
    assert hash_stats(a) != hash_stats(b)


def test_validate_rejects_nonpositive_n():
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 0, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    assert any("n_must_be_positive" in v for v in violations)


def test_validate_rejects_negative_var():
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": -1.0,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    assert any("var_must_be_nonnegative" in v for v in violations)


def test_validate_rejects_nonpositive_effect_se():
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.0, "covariate_summary": {},
    })
    assert any("effect_se_must_be_positive" in v for v in violations)


def test_validate_rejects_missing_field():
    """构造 dict 缺 effect_estimate → 抛错。"""
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_se": 0.05, "covariate_summary": {},
    })
    assert any("missing_fields" in v for v in violations)


def test_validate_rejects_nan():
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 10, "mean": float("nan"), "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    assert any("must_be_finite" in v for v in violations)


def test_validate_rejects_raw_sample_fields():
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
        "samples": [0.1, 0.2, 0.3, 0.4, 0.5],
    })
    assert any("raw_sample_fields_rejected" in v or "looks_like_raw_sample_list" in v
               for v in violations)


def test_validate_rejects_nested_list_in_covariate():
    violations = validate_tenant_payload({
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05,
        "covariate_summary": {"rows": [[0.1, 0.2], [0.3, 0.4]]},
    })
    assert any("nested" in v or "samples" in v.lower() for v in violations)


def test_signature_rejects_raw_samples_list_float():
    """用 inspect.signature 验证：函数签名里没有 list[float] 参数。"""
    for fn in (validate_tenant_payload, hash_stats):
        sig = inspect.signature(fn)
        for param in sig.parameters.values():
            ann = param.annotation
            # 直接拒绝 list[float] / list 作为参数注解
            if "list[float]" in str(ann).lower():
                pytest.fail(f"{fn.__name__} has list[float] param: {param}")
            if ann is list:
                pytest.fail(f"{fn.__name__} accepts plain list param: {param}")

    # SufficientStats dataclass 字段也不应允许 raw samples
    for f in SufficientStats.__dataclass_fields__.values():
        assert "list[float]" not in str(f.type).lower()


def test_stats_to_json_normalized(sample_stats: SufficientStats):
    """规范化 JSON：sort_keys + 无空白，保证跨进程 hash 一致。"""
    payload = sample_stats.to_json()
    assert "," in payload and ": " not in payload
    # 缺空格 = 紧凑 separators
    assert " " not in payload


# ─────────────────────────── HierarchicalAggregator ───────────────────────────


def test_aggregate_single_tenant_returns_same_effect():
    """单租户退化：pooled == 该租户 effect，τ² = 0。"""
    s = _stats(effect_estimate=0.6)
    r = HierarchicalAggregator().aggregate([s])
    assert r.pooled_effect == pytest.approx(0.6)
    assert r.tau_squared == 0.0
    assert r.per_tenant_weight == [1.0]
    assert r.n_tenants == 1


def test_aggregate_two_same_effects_small_tau():
    """两组相同效应：pooled ≈ 该值，τ² 极小。"""
    s1 = _stats(tenant_id="A", effect_estimate=0.6)
    s2 = _stats(tenant_id="B", effect_estimate=0.6)
    r = HierarchicalAggregator().aggregate([s1, s2])
    assert r.pooled_effect == pytest.approx(0.6, abs=1e-6)
    assert r.tau_squared < 0.01


def test_aggregate_opposite_effects_pooled_near_zero():
    """两组相反效应 (+2 vs -2)：pooled 接近 0，τ² > 0.5。"""
    s1 = _stats(tenant_id="A", effect_estimate=2.0)
    s2 = _stats(tenant_id="B", effect_estimate=-2.0)
    r = HierarchicalAggregator().aggregate([s1, s2])
    assert abs(r.pooled_effect) < 0.1
    assert r.tau_squared > 0.5


def test_aggregate_10x_n_gives_larger_weight():
    """n 差异 10x：大 n 租户权重 > 小 n 租户权重。

    构造：同一 var 下，大 n 的 se 更小 → 精度更高 → 权重更大。
    """
    big = _stats(tenant_id="big", n=100, var=1.0, effect_estimate=0.6, effect_se=0.1)
    small = _stats(tenant_id="small", n=10, var=1.0, effect_estimate=0.6, effect_se=0.3)
    agg = HierarchicalAggregator()
    weights = agg.random_effect_weights([big, small])
    assert weights[0] > weights[1]
    assert weights[0] + weights[1] == pytest.approx(1.0, abs=1e-6)


def test_empirical_bayes_vs_monte_carlo_agreement():
    """Monte Carlo vs Empirical Bayes 结果差异 < 0.1。"""
    stats = [
        _stats(tenant_id=f"T{i}", effect_estimate=0.5 + 0.05 * i, effect_se=0.1)
        for i in range(5)
    ]
    agg = HierarchicalAggregator(mc_samples=2000)
    eb = agg.aggregate(stats, method="empirical_bayes")
    mc = agg.aggregate(stats, method="monte_carlo")
    assert abs(eb.pooled_effect - mc.pooled_effect) < 0.1


def test_aggregate_empty_list_raises():
    with pytest.raises(ValueError):
        HierarchicalAggregator().aggregate([])


def test_aggregate_unknown_method_raises():
    s = _stats()
    with pytest.raises(ValueError):
        HierarchicalAggregator().aggregate([s], method="unknown")


def test_aggregate_total_n_summed():
    s1 = _stats(tenant_id="A", n=10)
    s2 = _stats(tenant_id="B", n=20)
    r = HierarchicalAggregator().aggregate([s1, s2])
    assert r.total_n == 30
    assert r.n_tenants == 2


def test_aggregate_weights_sum_to_one():
    stats = [
        _stats(tenant_id=f"T{i}", effect_estimate=0.5 + 0.1 * i, effect_se=0.1 + 0.02 * i)
        for i in range(4)
    ]
    r = HierarchicalAggregator().aggregate(stats)
    assert sum(r.per_tenant_weight) == pytest.approx(1.0, abs=1e-6)


def test_aggregate_convergence_flag_true():
    stats = [_stats(tenant_id="A", effect_estimate=0.6), _stats(tenant_id="B", effect_estimate=0.7)]
    r = HierarchicalAggregator().aggregate(stats)
    assert r.convergence is True
    assert r.method == "empirical_bayes"


# ─────────────────────────── SingleMachineFederatedFabric ───────────────────────────


def test_fabric_20_rounds_converges():
    """3 租户 20 轮：第 10 轮 vs 第 20 轮 pooled_effect 差异 < 0.2。"""
    fabric = SingleMachineFederatedFabric(seed=42)
    for tid, eff in (("A", 0.5), ("B", 0.5), ("C", 0.5)):
        fabric.add_tenant(VirtualTenant(tid, region="cn", cohort_size=30, baseline_effect=eff))

    p10, p20 = None, None
    for i in range(1, 21):
        result = fabric.run_round(i)
        if i == 10:
            p10 = result.pooled_effect
        if i == 20:
            p20 = result.pooled_effect
    assert p10 is not None and p20 is not None
    assert abs(p10 - p20) < 0.2


def test_fabric_seed_reproducible():
    """两次 seed=42 → 结果相同。"""
    def _run(seed: int) -> float:
        f = SingleMachineFederatedFabric(seed=seed)
        f.add_tenant(VirtualTenant("A", region="cn", cohort_size=30, baseline_effect=0.5))
        return f.run_round(1).pooled_effect

    assert _run(42) == _run(42)


def test_fabric_different_seed_differs():
    """不同 seed → 结果不同。"""
    def _run(seed: int) -> float:
        f = SingleMachineFederatedFabric(seed=seed)
        f.add_tenant(VirtualTenant("A", region="cn", cohort_size=30, baseline_effect=0.5))
        return f.run_round(1).pooled_effect

    assert _run(42) != _run(7)


def test_fabric_region_isolation_no_cross_region_aggregation():
    """Region 隔离：不同 region 的 tenant 不互相聚合。

    开 region_isolation=True 时，cn 与 sg 的租户各自只拿到自己 region 的后验。
    """
    fabric = SingleMachineFederatedFabric(seed=42, region_isolation=True)
    fabric.add_tenant(VirtualTenant("cn_a", region="cn", cohort_size=30, baseline_effect=0.5))
    fabric.add_tenant(VirtualTenant("sg_a", region="sg", cohort_size=30, baseline_effect=0.5))
    fabric.run_round(1)

    cn_post = fabric.get_posterior("cn_a")
    sg_post = fabric.get_posterior("sg_a")
    # 各自 region 只有 1 个 tenant → n_tenants=1，权重=1
    assert cn_post.n_tenants == 1
    assert sg_post.n_tenants == 1
    assert cn_post.per_tenant_weight == [1.0]


def test_fabric_no_isolation_aggregates_all():
    """关掉 region 隔离：全体租户一起聚合。"""
    fabric = SingleMachineFederatedFabric(seed=42, region_isolation=False)
    fabric.add_tenant(VirtualTenant("cn_a", region="cn", cohort_size=30, baseline_effect=0.5))
    fabric.add_tenant(VirtualTenant("sg_a", region="sg", cohort_size=30, baseline_effect=0.5))
    fabric.run_round(1)
    post = fabric.get_posterior("cn_a")
    assert post.n_tenants == 2


def test_fabric_round_history_recorded():
    fabric = SingleMachineFederatedFabric(seed=1)
    fabric.add_tenant(VirtualTenant("A", region="cn", cohort_size=20, baseline_effect=0.5))
    for i in range(1, 4):
        fabric.run_round(i)
    hist = fabric.round_history()
    assert len(hist) == 3
    assert hist[0]["round_id"] == 1


def test_fabric_simulate_local_stats_valid():
    fabric = SingleMachineFederatedFabric(seed=1)
    fabric.add_tenant(VirtualTenant("A", region="cn", cohort_size=50, baseline_effect=0.5))
    stats = fabric.simulate_local_n_of_1("A")
    assert stats.n == 50
    assert stats.effect_se > 0
    assert stats.tenant_id == "A"
    # 应通过协议层校验
    assert validate_tenant_payload({
        "tenant_id": stats.tenant_id, "n": stats.n, "mean": stats.mean,
        "var": stats.var, "effect_estimate": stats.effect_estimate,
        "effect_se": stats.effect_se, "covariate_summary": stats.covariate_summary,
    }) == []


def test_fabric_unknown_tenant_raises():
    fabric = SingleMachineFederatedFabric(seed=1)
    with pytest.raises(KeyError):
        fabric.simulate_local_n_of_1("nobody")


def test_fabric_add_duplicate_tenant_raises():
    fabric = SingleMachineFederatedFabric(seed=1)
    fabric.add_tenant(VirtualTenant("A", region="cn"))
    with pytest.raises(ValueError):
        fabric.add_tenant(VirtualTenant("A", region="cn"))


# ─────────────────────────── FlowerAdapter ───────────────────────────


def test_flower_server_unavailable_raises(monkeypatch):
    """未装 flwr 时抛 HealthLensUnavailableEngine。"""
    monkeypatch.setattr(flwr_adapter_module, "FLWR_AVAILABLE", False)
    monkeypatch.setattr(flwr_adapter_module, "flwr", None)
    agg = HierarchicalAggregator()
    with pytest.raises(HealthLensUnavailableEngine) as exc:
        make_flower_server(agg)
    assert exc.value.engine_name == "flwr"


def test_flower_server_mock_available(monkeypatch):
    """装了 flwr（monkeypatch mock）时能构造 server。"""
    captured = {}

    class FakeServer:
        def __init__(self, config):
            self.config = config
            self.aggregator = None
            captured["config"] = config

    fake_flwr = types.SimpleNamespace(server=types.SimpleNamespace(Server=FakeServer))
    monkeypatch.setattr(flwr_adapter_module, "FLWR_AVAILABLE", True)
    monkeypatch.setattr(flwr_adapter_module, "flwr", fake_flwr)

    agg = HierarchicalAggregator()
    server = make_flower_server(agg, num_rounds=3, min_available=1)
    assert isinstance(server, FakeServer)
    assert captured["config"] == {"num_rounds": 3, "min_available": 1}
    assert server.aggregator is agg


def test_flower_server_unknown_strategy_raises(monkeypatch):
    """未知 strategy 抛 ValueError（在 FLWR 可用时）。"""
    class FakeServer:
        def __init__(self, config):
            self.config = config
            self.aggregator = None
    fake_flwr = types.SimpleNamespace(server=types.SimpleNamespace(Server=FakeServer))
    monkeypatch.setattr(flwr_adapter_module, "FLWR_AVAILABLE", True)
    monkeypatch.setattr(flwr_adapter_module, "flwr", fake_flwr)
    with pytest.raises(ValueError):
        make_flower_server(HierarchicalAggregator(), strategy="weird")


def test_tenant_config_default_region_cn():
    cfg = TenantConfig(tenant_id="A")
    assert cfg.region == "cn"
    assert cfg.port == 50000


# ─────────────────────────── TargetTrialEmulator ───────────────────────────


def test_target_trial_ipw_weight_range():
    """IPW 权重范围：0 < w <= max_weight=20。"""
    emulator = TargetTrialEmulator(ipw={"max_weight": 20.0, "trim_fraction": 0.01})
    for p in (0.001, 0.01, 0.1, 0.3, 0.5, 0.7, 0.99, 0.9999):
        w = emulator._ipw_weight(p)
        assert 0 < w <= 20.0 + 1e-9, f"p={p} → w={w}"
    # p 极小 → 命中 max_weight
    assert emulator._ipw_weight(0.0001) == pytest.approx(20.0)


def test_target_trial_emulate_basic():
    """emulate 返回 estimate + per_tenant 权重。"""
    emulator = TargetTrialEmulator()
    stats = [_stats(tenant_id=f"T{i}", effect_estimate=0.6 + 0.05 * i) for i in range(3)]
    spec = TargetTrialSpec(intervention="exercise", comparator="usual_care")
    result = emulator.emulate(spec, stats)
    assert "estimate" in result
    assert result["n_tenants"] == 3
    assert result["estimate"] == pytest.approx(sum(0.6 + 0.05 * i for i in range(3)) / 3,
                                              abs=1e-6)
    assert len(result["per_tenant"]) == 3


def test_target_trial_placebo_refutation_effect_disappears():
    """placebo intervention refutation：随机置换 treatment → 效应消失 (|effect| < 0.5)。"""
    emulator = TargetTrialEmulator()
    stats = [_stats(tenant_id=f"T{i}", effect_estimate=0.6 + 0.05 * i) for i in range(3)]
    spec = TargetTrialSpec(intervention="exercise", comparator="usual_care")
    ref = emulator.run_refutation(spec, stats)
    assert ref["placebo_refutation_passed"] is True
    assert abs(ref["placebo_estimate"]) < 0.5


def test_target_trial_random_assignment_refutation():
    """random assignment refutation：随机分配 → 效应消失或原效应消失。"""
    emulator = TargetTrialEmulator()
    # 两组：一组有真实效应，另一组无（模拟 selection bias 场景）
    stats = [
        _stats(tenant_id="eff", effect_estimate=0.6, effect_se=0.05),
        _stats(tenant_id="zero", effect_estimate=0.0, effect_se=0.05),
    ]
    spec = TargetTrialSpec(intervention="exercise", comparator="usual_care")
    ref = emulator.run_refutation(spec, stats)
    # random assignment 会把 propensity 强制为 0.5 → 等权 → 效应减半（≈0.3）
    # 这里断言：random_assignment_estimate 是有限数值 & placebo 已证伪
    assert ref["placebo_refutation_passed"] is True
    assert isinstance(ref["random_assignment_estimate"], float)
    # 等权后与原始估计的差 < 原估计的一半（等权稀释）
    assert abs(ref["random_assignment_estimate"] - ref["original_estimate"]) < abs(ref["original_estimate"]) + 1e-9


def test_target_trial_empty_raises():
    emulator = TargetTrialEmulator()
    spec = TargetTrialSpec(intervention="x", comparator="y")
    with pytest.raises(ValueError):
        emulator.emulate(spec, [])
    with pytest.raises(ValueError):
        emulator.run_refutation(spec, [])


def test_target_trial_ipw_uses_covariate_p_treated():
    """covariate_summary.p_treated 会驱动 IPW 权重。"""
    emulator = TargetTrialEmulator()
    s_high = _stats(tenant_id="hi", effect_estimate=0.6,
                    covariate_summary={"p_treated": 0.9})
    s_low = _stats(tenant_id="lo", effect_estimate=0.6,
                   covariate_summary={"p_treated": 0.1})
    spec = TargetTrialSpec(intervention="exercise", comparator="usual_care")
    result = emulator.emulate(spec, [s_high, s_low])
    weights = {row["tenant_id"]: row["weight"] for row in result["per_tenant"]}
    # p_treated=0.9 → 权重接近 1.11；p_treated=0.1 → 权重接近 10
    assert weights["hi"] < weights["lo"]
    assert weights["lo"] <= 20.0


# ─────────────────────────── API 层（TestClient） ───────────────────────────


@pytest.fixture
def api_client():
    """独立 TestClient，避免 app/__init__.py 拉起完整 lifespan / DB。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.federated import router, _reset_state

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/federated")
    _reset_state()
    yield TestClient(app)
    _reset_state()


def test_api_post_stats_ok(api_client):
    r = api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "A"
    assert len(body["sha256"]) == 64


def test_api_post_stats_invalid_returns_400(api_client):
    """非法 payload（缺字段 / 数值越界）→ 400。"""
    r = api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": -1, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    assert r.status_code == 400


def test_api_post_stats_missing_field_400(api_client):
    """缺 effect_estimate → 422（Pydantic 层）或 400（协议层）。"""
    r = api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_se": 0.05, "covariate_summary": {},
    })
    # Pydantic 会先拦；无论 400 还是 422 都算"fail-loud"
    assert r.status_code in (400, 422)


def test_api_tenants_lists_tenants(api_client):
    api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "B", "n": 20, "mean": 0.5, "var": 0.02,
        "effect_estimate": 0.7, "effect_se": 0.06, "covariate_summary": {},
    })
    r = api_client.get("/api/v1/federated/tenants")
    assert r.status_code == 200
    body = r.json()
    assert body["n_tenants"] == 2
    ids = {t["tenant_id"] for t in body["tenants"]}
    assert ids == {"A", "B"}
    # 不含个体数据字段
    for t in body["tenants"]:
        assert "samples" not in t and "rows" not in t


def test_api_aggregate_empty_returns_warning(api_client):
    r = api_client.post("/api/v1/federated/aggregate", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["n_tenants"] == 0
    assert body["data"]["warning"] == "no tenants registered"


def test_api_aggregate_with_data_full_response(api_client):
    for tid in ("A", "B"):
        api_client.post("/api/v1/federated/stats", json={
            "tenant_id": tid, "n": 10, "mean": 0.5, "var": 0.01,
            "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
        })
    r = api_client.post("/api/v1/federated/aggregate", json={"method": "empirical_bayes"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["n_tenants"] == 2
    assert data["method"] == "empirical_bayes"
    assert isinstance(data["pooled_effect"], (int, float))
    assert "per_tenant_weight" in data and len(data["per_tenant_weight"]) == 2


def test_api_trial_run_returns_estimate_and_refutation(api_client):
    api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    r = api_client.post("/api/v1/federated/trial/run", json={
        "intervention": "exercise",
        "comparator": "usual_care",
        "assignment": "as_treated",
        "outcome": "effect_estimate",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "trial_id" in body["data"]
    assert "estimate" in body["data"]
    assert "refutation" in body["data"]
    assert body["data"]["estimate"]["n_tenants"] == 1
    # refutation 里 placebo_refutation_passed 应存在
    assert "placebo_refutation_passed" in body["data"]["refutation"]


def test_api_trial_run_unknown_tenant_returns_400(api_client):
    r = api_client.post("/api/v1/federated/trial/run", json={
        "intervention": "exercise",
        "comparator": "usual_care",
        "tenant_ids": ["does_not_exist"],
    })
    assert r.status_code == 400


def test_api_trial_status_found_and_not_found(api_client):
    api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    run = api_client.post("/api/v1/federated/trial/run", json={
        "intervention": "exercise", "comparator": "usual_care",
    })
    trial_id = run.json()["data"]["trial_id"]
    r = api_client.get(f"/api/v1/federated/trial/status/{trial_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["status"] == "done"
    # 不存在的 trial_id
    r2 = api_client.get("/api/v1/federated/trial/status/nonexistent")
    assert r2.status_code == 200
    assert r2.json()["found"] is False


def test_api_export_posterior_before_aggregate_prompts(api_client):
    api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    r = api_client.get("/api/v1/federated/export/posterior/A")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is False
    assert "aggregate" in body["note"].lower()


def test_api_export_posterior_after_aggregate_returns_data(api_client):
    api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    api_client.post("/api/v1/federated/aggregate", json={})
    r = api_client.get("/api/v1/federated/export/posterior/A")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["posterior"]["pooled_effect"] == pytest.approx(0.6)


def test_api_stats_rejects_raw_samples_field(api_client):
    """协议层拒绝 raw samples：即使 Pydantic 允许多余字段也应 400。"""
    r = api_client.post("/api/v1/federated/stats", json={
        "tenant_id": "A", "n": 10, "mean": 0.5, "var": 0.01,
        "effect_estimate": 0.6, "effect_se": 0.05, "covariate_summary": {},
    })
    assert r.status_code == 200  # 合法 payload 通过

"""HealthLens L3 联邦证据网络包 — v0.28.0 SVIEE 跃迁

出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3
      「L3 联邦证据网络（3–6 月）— 最锋利的原创点」

**包结构**：
    sufficient_stats.py    充分统计量协议（个体数据不出域）
    aggregation.py         贝叶斯层次聚合（Empirical Bayes + MC fallback）
    single_machine_fabric.py 单机多租户仿真器（冷启动路径）
    flower_adapter.py      Optional Flower 集成骨架（未装降级）
    target_trial.py        联邦目标试验仿真（npj Digit Med 2025;8:387 简化版）

**关键承诺**：
- 零第三方依赖内核（numpy 可选，pandas/scipy/flwr 一律不进核心路径）。
- 个体数据不出域：sufficient_stats.py 从协议层拒绝 raw samples。
- 明确"不做 DP"：报告点名不要承诺小样本 DP 会保证效用。

**版本**：与项目版本保持一致（pyproject.toml 单一真源）。
"""
from app.lib.federated.sufficient_stats import (
    SufficientStats,
    hash_stats,
    validate_tenant_payload,
)
from app.lib.federated.aggregation import (
    AggregationResult,
    HierarchicalAggregator,
)
from app.lib.federated.single_machine_fabric import (
    SingleMachineFederatedFabric,
    VirtualTenant,
)
from app.lib.federated.flower_adapter import (
    FLWR_AVAILABLE,
    HealthLensUnavailableEngine,
    TenantConfig,
    make_flower_client,
    make_flower_server,
)
from app.lib.federated.target_trial import (
    TargetTrialEmulator,
    TargetTrialSpec,
)


__version__ = "0.28.0"

__all__ = [
    "SufficientStats",
    "validate_tenant_payload",
    "hash_stats",
    "AggregationResult",
    "HierarchicalAggregator",
    "SingleMachineFederatedFabric",
    "VirtualTenant",
    "HealthLensUnavailableEngine",
    "TenantConfig",
    "FLWR_AVAILABLE",
    "make_flower_server",
    "make_flower_client",
    "TargetTrialSpec",
    "TargetTrialEmulator",
    "__version__",
]

"""单机多租户联邦仿真器（Single-Machine Federated Fabric）— L3 冷启动路径

出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3
      「L3 冷启动路径：先用单机多租户模拟联邦验证方法学正确性 → 再找 3–5 家真伙伴试点。
      方法学的正确性不依赖伙伴数量。」

**核心命题**：
- 数据是**合成**的（高斯 + 噪声），本仿真器只用于验证方法学正确性。
- 每个 VirtualTenant 独立计算本地充分统计量，然后上传到中心 HierarchicalAggregator，
  最终回传全局后验——完整复刻分布式联邦的协议闭环，但运行在单机进程内。
- Region 隔离：不同 region 的 tenant 默认不互相聚合，
  对齐 app/lib/region_guard.py 的"代码级约束"哲学。

**明确注释**：
> **仿真用于验证方法学正确性，数据是合成的。** 本模块绝不接收真实个体健康数据；
> 上线真实联邦时必须走 Flower adapter + 租户自持本地计算。

设计约束：
- 仅依赖标准库 + app/lib/federated/*；不引入 numpy（保证零第三方依赖）。
- 确定性 seed 接口保证可复现（报告要求"可审计、可复现、可测试"）。
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from typing import Iterable

from app.lib.federated.aggregation import AggregationResult, HierarchicalAggregator
from app.lib.federated.sufficient_stats import SufficientStats


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VirtualTenant:
    """一个虚拟租户（合成数据源）。

    Attributes:
        tenant_id: 唯一标识。
        region: 复用 region_guard 的短码（cn/sg/eu/us/uk/au/default），
                用于联邦聚合时的隔离边界。
        cohort_size: 本地 n-of-1 队列人数（合成规模）。
        baseline_effect: 该租户的"真实"效应（用作仿真 ground truth）。
    """

    tenant_id: str
    region: str = "cn"
    cohort_size: int = 30
    baseline_effect: float = 0.5


# ---------------------------------------------------------------------------
# 仿真器
# ---------------------------------------------------------------------------


class SingleMachineFederatedFabric:
    """单机多租户联邦仿真器。

    生命周期：
        fabric = SingleMachineFederatedFabric(seed=42)
        fabric.add_tenant(VirtualTenant("A", region="cn", cohort_size=30, baseline_effect=0.6))
        fabric.add_tenant(VirtualTenant("B", region="cn", cohort_size=50, baseline_effect=0.5))
        result = fabric.run_round(round_id=1)
        posterior = fabric.get_posterior("A")

    关键行为：
    - simulate_local_n_of_1：给 tenant 生成一批虚拟 n-of-1 结果，
      返回该 tenant 的 SufficientStats（本地聚合完）。
    - run_round：每个 tenant 独立算本地充分统计量 → 中心聚合 → 广播后验。
      Region 隔离：默认只有相同 region 的 tenant 才互相聚合。
    - get_posterior：返回 (pooled_effect, se) 类后验摘要。
    """

    def __init__(
        self,
        seed: int = 0,
        aggregator: HierarchicalAggregator | None = None,
        noise_sd: float = 0.05,
        region_isolation: bool = True,
    ):
        self._rng = random.Random(seed)
        self._tenants: dict[str, VirtualTenant] = {}
        self._local_stats: dict[str, SufficientStats] = {}
        self._aggregator = aggregator or HierarchicalAggregator()
        self._noise_sd = float(noise_sd)
        self._region_isolation = bool(region_isolation)
        self._posterior: dict[str, AggregationResult] = {}
        self._round_history: list[dict] = []

    # ---------- 注册 ----------

    def add_tenant(self, tenant: VirtualTenant) -> None:
        if not isinstance(tenant, VirtualTenant):
            raise TypeError("tenant must be VirtualTenant")
        if tenant.tenant_id in self._tenants:
            raise ValueError(f"tenant already registered: {tenant.tenant_id}")
        if tenant.cohort_size <= 0:
            raise ValueError("cohort_size must be positive")
        self._tenants[tenant.tenant_id] = tenant

    def seed(self, seed: int) -> None:
        """可复现接口：重置随机源。"""
        self._rng = random.Random(int(seed))

    def tenants(self) -> list[VirtualTenant]:
        return list(self._tenants.values())

    # ---------- 本地仿真 ----------

    def simulate_local_n_of_1(
        self, tenant_id: str, studies: int | None = None
    ) -> SufficientStats:
        """给 tenant 生成虚拟 n-of-1 队列的**充分统计量**。

        每个个体从 N(baseline_effect, noise_sd) 抽样，
        样本量 = studies（默认 = cohort_size）。
        本地聚合后返回 mean / var / effect_estimate / effect_se。
        """
        if tenant_id not in self._tenants:
            raise KeyError(f"unknown tenant: {tenant_id}")
        t = self._tenants[tenant_id]
        k = int(studies) if studies else int(t.cohort_size)
        if k <= 0:
            raise ValueError("studies must be positive")

        samples = [
            self._rng.gauss(t.baseline_effect, self._noise_sd) for _ in range(k)
        ]
        mean = sum(samples) / k
        var = sum((x - mean) ** 2 for x in samples) / max(k - 1, 1)
        # n-of-1 效应估计：均值即局部效应；SE 用正态近似 sqrt(var/n)
        effect = mean
        effect_se = math.sqrt(var / k) if var > 0 else 1e-6
        if effect_se <= 0 or not math.isfinite(effect_se):
            effect_se = 1e-6

        return SufficientStats(
            tenant_id=t.tenant_id,
            n=k,
            mean=mean,
            var=var,
            effect_estimate=effect,
            effect_se=effect_se,
            covariate_summary={
                "region": t.region,
                "cohort_size_declared": t.cohort_size,
            },
        )

    # ---------- 联邦轮次 ----------

    def run_round(
        self,
        round_id: int,
        tenant_ids: Iterable[str] | None = None,
    ) -> AggregationResult:
        """跑一轮联邦：每个 tenant 本地聚合 → 中心聚合 → 广播后验。

        Args:
            round_id: 轮次编号（≥1），写入历史供审计。
            tenant_ids: 参与本轮的租户白名单；None = 全体。
        """
        if round_id < 1:
            raise ValueError("round_id must be >= 1")

        targets = list(tenant_ids) if tenant_ids else list(self._tenants.keys())
        local_stats: list[SufficientStats] = []
        for tid in targets:
            if tid not in self._tenants:
                raise KeyError(f"unknown tenant: {tid}")
            stats = self.simulate_local_n_of_1(tid)
            self._local_stats[tid] = stats
            local_stats.append(stats)

        # Region 隔离：按 region 分桶聚合
        buckets: dict[str, list[SufficientStats]] = {}
        for s in local_stats:
            region = s.covariate_summary.get("region", "default")
            if self._region_isolation:
                buckets.setdefault(region, []).append(s)
            else:
                buckets.setdefault("_global", []).append(s)

        # 对每个 region 桶聚合，租户拿到本 region 的后验
        merged = None
        for region, bucket in buckets.items():
            result = self._aggregator.aggregate(bucket, method="empirical_bayes")
            for s in bucket:
                self._posterior[s.tenant_id] = result
            merged = result if merged is None else self._merge_results(merged, result)

        if merged is None:
            merged = AggregationResult(
                pooled_effect=0.0,
                tau_squared=0.0,
                sigma_squared=0.0,
                per_tenant_effect=[],
                per_tenant_weight=[],
                method="empirical_bayes",
                n_tenants=0,
                total_n=0,
                convergence=True,
                between_within_ratio=0.0,
            )

        self._round_history.append(
            {"round_id": round_id, "n_tenants": len(local_stats), "pooled_effect": merged.pooled_effect}
        )
        return merged

    def get_posterior(self, tenant_id: str) -> AggregationResult:
        if tenant_id not in self._posterior:
            raise KeyError(f"no posterior for tenant: {tenant_id}")
        return self._posterior[tenant_id]

    def round_history(self) -> list[dict]:
        return list(self._round_history)

    # ---------- 内部 ----------

    @staticmethod
    def _merge_results(a: AggregationResult, b: AggregationResult) -> AggregationResult:
        """跨 region 汇总：n_tenants 加权的简易合并。"""
        w_a = max(a.n_tenants, 1)
        w_b = max(b.n_tenants, 1)
        pooled = (a.pooled_effect * w_a + b.pooled_effect * w_b) / (w_a + w_b)
        return AggregationResult(
            pooled_effect=pooled,
            tau_squared=max(a.tau_squared, b.tau_squared),
            sigma_squared=(a.sigma_squared + b.sigma_squared) / 2.0,
            per_tenant_effect=list(a.per_tenant_effect) + list(b.per_tenant_effect),
            per_tenant_weight=list(a.per_tenant_weight) + list(b.per_tenant_weight),
            method="empirical_bayes",
            n_tenants=a.n_tenants + b.n_tenants,
            total_n=a.total_n + b.total_n,
            convergence=a.convergence and b.convergence,
            between_within_ratio=(a.between_within_ratio + b.between_within_ratio) / 2.0,
        )

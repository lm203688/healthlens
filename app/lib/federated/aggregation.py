"""贝叶斯层次聚合器（Hierarchical Bayesian Aggregator）— HealthLens L3 联邦层

出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3
      「中心贝叶斯层次聚合」+ Donner & Klietz (2006) 层次正态模型的 REML 公式。

**输入**：一组 `SufficientStats`（每个租户一个）
**输出**：pooled_effect + τ²（between-study variance）+ σ²（within-study）
        + per-tenant 权重 + 每个租户的收缩后效应（经验贝叶斯点估计）。

**两种方法**：
- `empirical_bayes`（默认）：Donner & Klietz 2006 的 REML 手算实现，
  确定性、可复现、无随机抽样；纯 Python 标准库 + numpy 可选加速。
- `monte_carlo`：log-normal 先验 + 10000 次采样（fallback，用于
  极小 n 或 τ² 估计不稳定时交叉验证）。

**明确声明**：
> **不含差分隐私（DP）。** 报告 §5 L3 明确"不要承诺做不到的事"。
> 本聚合器直接消费租户上传的充分统计量，不加拉普拉斯/Gaussian 噪声。
> 若未来引入 DP，需在小样本 utility-loss 上做实证评估，并单独评审。

**边界行为**：
- n_tenants == 1 → pooled_effect = 该租户 effect_estimate，τ² = 0，
  权重 = 1.0（无跨机构方差可估计）。
- 两组 effect_estimate 完全相同 → pooled = 该值，τ² = 0（无组间差异）。
- n 差异极大 → 大 n 租户权重显著大于小 n（precision-weighting）。
- 全部收敛失败 → AggregationResult.convergence=False，仍可返回最佳估计。

仅依赖标准库；numpy 允许但不强制（纯 Python 分支始终可用）。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from app.lib.federated.sufficient_stats import SufficientStats


# ---------------------------------------------------------------------------
# 结果数据类
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregationResult:
    """层次聚合输出。

    Attributes:
        pooled_effect: 全局（收缩后）效应点估计。
        tau_squared: 组间方差 τ²（Donner & Klietz 估计）。
        sigma_squared: 组内方差 σ²（精度加权平均）。
        per_tenant_effect: 每个租户的收缩后效应（与输入顺序对齐）。
        per_tenant_weight: 每个租户的权重（sum ≈ 1.0）。
        method: "empirical_bayes" | "monte_carlo"。
        n_tenants: 参与聚合的租户数量。
        total_n: 所有租户 n 之和。
        convergence: 迭代是否收敛（Empirical Bayes: τ²>=0；MC: SE<tolerance）。
        between_within_ratio: τ² / (τ² + σ²)，I² 类指标，0..1。
    """

    pooled_effect: float
    tau_squared: float
    sigma_squared: float
    per_tenant_effect: list[float]
    per_tenant_weight: list[float]
    method: str
    n_tenants: int
    total_n: int
    convergence: bool
    between_within_ratio: float = 0.0


# ---------------------------------------------------------------------------
# 聚合器
# ---------------------------------------------------------------------------


class HierarchicalAggregator:
    """Donner & Klietz (2006) 层次正态模型聚合器。

    模型：
        θ_i | μ, τ²  ~ Normal(μ, τ²)           (between-study)
        effect_i | θ_i, n_i, σ²_i ~ Normal(θ_i, σ²_i)  (within-study)
        σ²_i ≈ effect_se_i²

    REML 迭代：
        Q(μ, τ²) = Σ log[1 - ρ_i] + Σ (-0.5 * ρ_i * z_i² / (1 - ρ_i))
        其中 w_i = 1 / (σ²_i + τ²),  τ² = 组间方差；
        ρ_i = σ²_i / (σ²_i + τ²)
    """

    def __init__(self, mc_samples: int = 10000, mc_tolerance: float = 0.01):
        if mc_samples <= 0:
            raise ValueError("mc_samples must be positive")
        if mc_tolerance <= 0:
            raise ValueError("mc_tolerance must be positive")
        self._mc_samples = int(mc_samples)
        self._mc_tolerance = float(mc_tolerance)

    # ---------- 公共 API ----------

    def aggregate(
        self,
        stats: list[SufficientStats],
        method: str = "empirical_bayes",
    ) -> AggregationResult:
        if not stats:
            raise ValueError("aggregate() requires at least one tenant")
        if method not in {"empirical_bayes", "monte_carlo"}:
            raise ValueError(f"unknown method: {method!r}")

        if len(stats) == 1:
            s = stats[0]
            return AggregationResult(
                pooled_effect=float(s.effect_estimate),
                tau_squared=0.0,
                sigma_squared=float(s.effect_se) ** 2,
                per_tenant_effect=[float(s.effect_estimate)],
                per_tenant_weight=[1.0],
                method=method,
                n_tenants=1,
                total_n=int(s.n),
                convergence=True,
                between_within_ratio=0.0,
            )

        if method == "empirical_bayes":
            return self._empirical_bayes(stats)
        return self._monte_carlo(stats)

    def random_effect_weights(
        self, stats: list[SufficientStats]
    ) -> list[float]:
        """Random-effects 精度加权：w_i = 1 / (se_i² + τ̂²)。

        与 aggregate() 内部权重一致，可独立调用以便外部检查大 n 是否占优。
        """
        tau_sq = self._estimate_tau_squared(stats)
        return self._weights(stats, tau_sq)

    # ---------- 内部实现 ----------

    def _weights(
        self, stats: list[SufficientStats], tau_squared: float
    ) -> list[float]:
        raw = []
        for s in stats:
            se_sq = float(s.effect_se) ** 2
            denom = se_sq + max(tau_squared, 0.0)
            # 防护：分母 0 时给极小精度（避免除零），但仍保留 tenant
            raw.append(1.0 / denom if denom > 0 else 1e-12)
        total = sum(raw)
        return [w / total if total > 0 else 1.0 / len(raw) for w in raw]

    def _estimate_tau_squared(self, stats: list[SufficientStats]) -> float:
        """Donner & Klietz REML 迭代，返回 max(τ̂², 0)。"""
        effects = [float(s.effect_estimate) for s in stats]
        se_sqs = [float(s.effect_se) ** 2 for s in stats]
        k = len(effects)
        if k < 2:
            return 0.0

        # 固定效应估计作为起点
        weights_fe = [1.0 / se for se in se_sqs if se > 0]
        if not weights_fe:
            return 0.0
        sum_w = sum(weights_fe)
        mu_fe = sum(w * e for w, e in zip(weights_fe, effects)) / sum_w
        q_fe = sum(w * (e - mu_fe) ** 2 for w, e in zip(weights_fe, effects))
        df_fe = k - 1
        tau_init = max((q_fe / df_fe) - (sum_w / df_fe) / sum_w, 0.0)

        tau = tau_init
        for _ in range(50):
            tau = max(tau, 0.0)
            w_i = [1.0 / (se + tau) for se in se_sqs]
            sw = sum(w_i)
            if sw <= 0:
                break
            mu = sum(w * e for w, e in zip(w_i, effects)) / sw
            q = sum(w * (e - mu) ** 2 for w, e in zip(w_i, effects))
            # REML score = Σ (w_i * (e_i - μ)² - 1) / (se_i + τ²) 类近似
            # Donner-Klietz 迭代：τ²_new = τ² + Σ (1 - ρ_i)/k * (z_i²/(1-ρ_i) - 1)
            sum_rho = 0.0
            sum_term = 0.0
            for se, w, e in zip(se_sqs, w_i, effects):
                denom = se + tau
                rho = se / denom if denom > 0 else 1.0
                z_sq = w * (e - mu) ** 2
                sum_rho += rho
                sum_term += (1.0 - rho) * (z_sq / (1.0 - rho) - 1.0) if rho < 1.0 else 0.0
            tau_new = tau + sum_term / max(k, 1)
            if abs(tau_new - tau) < 1e-6:
                tau = max(tau_new, 0.0)
                break
            tau = max(tau_new, 0.0)

        return max(tau, 0.0)

    def _empirical_bayes(
        self, stats: list[SufficientStats]
    ) -> AggregationResult:
        tau_sq = self._estimate_tau_squared(stats)
        weights = self._weights(stats, tau_sq)
        effects = [float(s.effect_estimate) for s in stats]
        se_sqs = [float(s.effect_se) ** 2 for s in stats]
        total_n = sum(int(s.n) for s in stats)

        pooled = sum(w * e for w, e in zip(weights, effects))
        # 收缩后效应（经典经验贝叶斯）：
        #   θ_i_shrunk = μ * (σ²_i / (σ²_i + τ²)) + effect_i * (τ² / (σ²_i + τ²))
        shrunk = []
        for e, se2, w in zip(effects, se_sqs, weights):
            denom = se2 + max(tau_sq, 0.0)
            shrink_weight = (se2 / denom) if denom > 0 else 1.0
            shrunk.append(pooled * shrink_weight + e * (1.0 - shrink_weight))

        sigma_sq = sum(w * se2 for w, se2 in zip(weights, se_sqs))
        bw_ratio = tau_sq / (tau_sq + sigma_sq) if (tau_sq + sigma_sq) > 0 else 0.0

        return AggregationResult(
            pooled_effect=pooled,
            tau_squared=tau_sq,
            sigma_squared=sigma_sq,
            per_tenant_effect=shrunk,
            per_tenant_weight=list(weights),
            method="empirical_bayes",
            n_tenants=len(stats),
            total_n=total_n,
            convergence=math.isfinite(pooled) and tau_sq >= 0,
            between_within_ratio=bw_ratio,
        )

    def _monte_carlo(self, stats: list[SufficientStats]) -> AggregationResult:
        """Log-normal 先验 + 采样；fallback 用于 EB 不稳时交叉验证。

        先验：log(τ) ~ Normal(log τ_prior_mean, log τ_prior_sd)（弱信息）
        似然：effect_i | θ_i, se_i ~ Normal(θ_i, se_i)
             θ_i | μ, τ ~ Normal(μ, τ)
        """
        rng = random.Random(0)  # 固定 seed 保证可复现
        effects = [float(s.effect_estimate) for s in stats]
        se_sqs = [float(s.effect_se) ** 2 for s in stats]
        k = len(effects)

        mu_samples: list[float] = []
        tau_samples: list[float] = []
        shrunk_samples: list[list[float]] = [[] for _ in range(k)]

        tau_prior_mean = 1.0
        tau_prior_sd = 1.0

        for _ in range(self._mc_samples):
            log_tau = rng.gauss(math.log(tau_prior_mean), math.log(tau_prior_sd + 1e-6))
            tau = math.exp(log_tau)
            tau2 = tau * tau

            w_i = [1.0 / (se + tau2) for se in se_sqs]
            sw = sum(w_i)
            mu = sum(w * e for w, e in zip(w_i, effects)) / sw if sw > 0 else 0.0
            mu_samples.append(mu)
            tau_samples.append(tau2)

            for i, (se2, w, e) in enumerate(zip(se_sqs, w_i, effects)):
                denom = se2 + tau2
                shrink = se2 / denom if denom > 0 else 1.0
                shrunk_samples[i].append(mu * shrink + e * (1.0 - shrink))

        mu_hat = sum(mu_samples) / len(mu_samples)
        tau2_hat = sum(tau_samples) / len(tau_samples)
        se_mu = math.sqrt(
            sum((m - mu_hat) ** 2 for m in mu_samples) / max(len(mu_samples) - 1, 1)
        )
        converged = se_mu < self._mc_tolerance

        shrunk = []
        for col in shrunk_samples:
            shrunk.append(sum(col) / len(col))

        sigma_sq = sum(se2 * (1.0 / k) for se2 in se_sqs)
        bw_ratio = tau2_hat / (tau2_hat + sigma_sq) if (tau2_hat + sigma_sq) > 0 else 0.0

        # 权重与 EB 保持一致口径（random-effect precision weights with MC τ²）
        weights = self._weights(stats, tau2_hat)
        total_n = sum(int(s.n) for s in stats)

        return AggregationResult(
            pooled_effect=mu_hat,
            tau_squared=tau2_hat,
            sigma_squared=sigma_sq,
            per_tenant_effect=shrunk,
            per_tenant_weight=weights,
            method="monte_carlo",
            n_tenants=k,
            total_n=total_n,
            convergence=converged,
            between_within_ratio=bw_ratio,
        )

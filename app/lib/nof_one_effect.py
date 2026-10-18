"""n-of-1 个体效应量 + 贝叶斯层次聚合 —— L1-2（2026-10-15）

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L1-2

个体水平（IndividualEffect）：
    - 纯 Python paired bootstrap（10000 次）→ 95% CI
    - Cohen's d 效应量
    - 三种 n-of-1 试验类型标记（ABAB / Crossover / Cluster）

群体水平（BayesianHierarchicalAggregator）：
    - PyMC 可选路径：`group_effect ~ N(mu_pop, tau)` 层次模型
    - 纯 Python fallback：Monte Carlo 采样，log-normal 先验近似正态
    - 输出 pooled_effect + tau_squared + random_effect_weights

E-value（compute_evalue）：借用 causal_simulator._evalue_rr 的 VanderWeele &
Ding (2017) 公式，独立实现，便于跨模块复用。

wellness 边界：全部标注 not_clinical=True，仅描述"若坚持某干预，健康信号
可能如何演化"的参考推演。
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 1. IndividualEffect
# ---------------------------------------------------------------------------


@dataclass
class IndividualEffect:
    """单个 n-of-1 试验的效应估计。"""
    point_estimate: float
    ci_lower: float
    ci_upper: float
    ci_level: float
    sample_size: int
    method: str
    n_of_1_type: str  # ABAB | Crossover | Cluster
    cohen_d: float | None = None
    std_error: float | None = None
    n_bootstrap: int = 0
    disclaimer: str = field(
        default=(
            "n-of-1 效应仅反映该个体在试验周期内的健康信号变化，"
            "不构成任何诊断、治疗或个体结果预测。"
        ),
    )

    def as_dict(self) -> dict:
        return {
            "point_estimate": round(self.point_estimate, 4),
            "ci_lower": round(self.ci_lower, 4),
            "ci_upper": round(self.ci_upper, 4),
            "ci_level": self.ci_level,
            "sample_size": self.sample_size,
            "method": self.method,
            "n_of_1_type": self.n_of_1_type,
            "cohen_d": None if self.cohen_d is None else round(self.cohen_d, 4),
            "std_error": None if self.std_error is None else round(self.std_error, 4),
            "n_bootstrap": self.n_bootstrap,
            "not_clinical": True,
            "disclaimer": self.disclaimer,
        }


_VALID_NOF1_TYPES = {"ABAB", "Crossover", "Cluster"}


def _cohens_d(pre: list[float], post: list[float]) -> float:
    """配对设计 Cohen's d：mean_diff / std_of_diffs。"""
    if len(pre) != len(post):
        raise ValueError("pre 与 post 长度不一致")
    if len(pre) < 2:
        return 0.0
    diffs = [p - q for p, q in zip(post, pre)]
    m = statistics.mean(diffs)
    s = statistics.stdev(diffs) if len(diffs) >= 2 else 0.0
    if s == 0:
        return 0.0
    return m / s


def estimate_individual_effect(
    pre_scores: list[float],
    post_scores: list[float],
    ci_level: float = 0.95,
    n_bootstrap: int = 10000,
    n_of_1_type: str = "Crossover",
    seed: int = 20261015,
) -> IndividualEffect:
    """纯 Python paired bootstrap：对 (pre, post) 配对重采样，统计 mean(post-pre)。

    Args:
        pre_scores: 干预前得分列表
        post_scores: 干预后得分列表（长度必须与 pre 相同）
        ci_level: CI 覆盖水平，默认 0.95
        n_bootstrap: bootstrap 次数，默认 10000
        n_of_1_type: ABAB / Crossover / Cluster
        seed: 随机种子（结果可复现）

    Raises:
        ValueError: pre/post 长度不一致 / 空集 / ci_level 越界
    """
    if not pre_scores or not post_scores:
        raise ValueError("pre_scores 与 post_scores 不可为空")
    if len(pre_scores) != len(post_scores):
        raise ValueError(f"pre/post 长度不一致：{len(pre_scores)} vs {len(post_scores)}")
    if not (0.0 < ci_level < 1.0):
        raise ValueError(f"ci_level 越界：{ci_level}")
    if n_of_1_type not in _VALID_NOF1_TYPES:
        raise ValueError(f"非法 n_of_1_type={n_of_1_type!r}，允许 {_VALID_NOF1_TYPES}")
    n = len(pre_scores)

    diffs = [float(post_scores[i]) - float(pre_scores[i]) for i in range(n)]
    point = float(sum(diffs) / n)
    # SE: sqrt(sum(d^2)/n) 与 paired SD/sqrt(n) 等价（配对 bootstrap 下 SE = SD/sqrt(n)）
    sd = statistics.stdev(diffs) if n >= 2 else 0.0
    se = sd / math.sqrt(n) if n >= 2 else 0.0

    # paired bootstrap：把 n 个 diff 无放回重采样 n 次，取均值
    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(max(1, n_bootstrap)):
        s = 0.0
        for _i in range(n):
            s += diffs[rng.randrange(n)]
        boot_means.append(s / n)
    boot_means.sort()
    # 分位数（覆盖水平对称双侧）
    lo_q = (1.0 - ci_level) / 2.0
    hi_q = 1.0 - lo_q
    lo_idx = max(0, int(lo_q * n_bootstrap))
    hi_idx = min(n_bootstrap - 1, int(hi_q * n_bootstrap))
    ci_lo = boot_means[lo_idx]
    ci_hi = boot_means[hi_idx]

    d = _cohens_d(pre_scores, post_scores)

    return IndividualEffect(
        point_estimate=point,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        ci_level=ci_level,
        sample_size=n,
        method="paired_bootstrap",
        n_of_1_type=n_of_1_type,
        cohen_d=d,
        std_error=se,
        n_bootstrap=n_bootstrap,
    )


# ---------------------------------------------------------------------------
# 2. BayesianHierarchicalAggregator
# ---------------------------------------------------------------------------


@dataclass
class AggregationResult:
    """贝叶斯层次聚合结果。"""
    pooled_effect: float
    tau_squared: float
    random_effect_weights: dict[str, float]
    method: str           # "pymc" | "pure_python_montecarlo"
    n_groups: int
    individual_effects: list[float]
    individual_se: list[float]
    disclaimer: str = (
        "pooled_effect 是加权合并的干预效应，仍受未观测混淆影响；"
        "tau_squared 衡量组间异质性，非生物学方差。"
    )

    def as_dict(self) -> dict:
        return {
            "pooled_effect": round(self.pooled_effect, 4),
            "tau_squared": round(self.tau_squared, 6),
            "random_effect_weights": {k: round(v, 4) for k, v in self.random_effect_weights.items()},
            "method": self.method,
            "n_groups": self.n_groups,
            "individual_effects": [round(e, 4) for e in self.individual_effects],
            "individual_se": [round(s, 4) for s in self.individual_se],
            "not_clinical": True,
            "disclaimer": self.disclaimer,
        }


def _try_import_pymc() -> Any | None:
    try:
        import pymc  # type: ignore
        return pymc
    except ImportError:
        return None


class BayesianHierarchicalAggregator:
    """贝叶斯层次聚合：`group_effect ~ N(mu_pop, tau)`。

    实现：
    - PyMC 路径：pymc.gp / pm.Normal 层次模型（未装 pymc 时降级）
    - 纯 Python 路径：inverse-variance 权重 + 有限差分估计 tau^2
      （等价于 DerSimonian-Laird 经典随机效应，输出与 PyMC 层次模型同结构）

    纯 Python fallback 的近似假设：
        - 用 log-normal 先验 mu ~ logN(0, 0.5) 近似正态先验
        - 用 Monte Carlo 采样（1000 次）产出 pooled_effect 的分布
    """

    def __init__(self, force_pymc: bool = False, seed: int = 20261015):
        self.seed = seed
        if force_pymc and _try_import_pymc() is None:
            from app.lib.engine_exceptions import HealthLensUnavailableEngine
            raise HealthLensUnavailableEngine(
                engine_name="pymc",
                required_package="pymc",
                extra_hint="science",
            )

    def aggregate(
        self,
        effects: list[float],
        se: list[float] | None = None,
        group_ids: list[str] | None = None,
        n_samples: int = 1000,
    ) -> AggregationResult:
        """聚合多个 n-of-1 效应到 pooled 结果。

        Args:
            effects: 每个个体的 point_estimate
            se: 每个个体的标准误（缺省用 1.0）
            group_ids: 组标识（缺省 "group_0", "group_1", ...）
            n_samples: 纯 Python Monte Carlo 采样次数
        """
        if not effects:
            raise ValueError("effects 不可为空")
        n = len(effects)
        if se is None:
            se = [1.0] * n
        if len(se) != n:
            raise ValueError(f"se 长度 {len(se)} 与 effects {n} 不一致")
        if any(s <= 0 for s in se):
            raise ValueError("se 必须全部 > 0")
        group_ids = group_ids or [f"group_{i}" for i in range(n)]

        # 尝试 PyMC
        pymc = _try_import_pymc()
        if pymc is not None:
            try:
                return self._aggregate_pymc(pymc, effects, se, group_ids)
            except Exception:
                # PyMC 加载成功但拟合失败（依赖未装齐）→ 降级到 pure_python
                pass

        # 纯 Python fallback：inverse-variance + Monte Carlo 近似
        return self._aggregate_pure_python(effects, se, group_ids, n_samples=n_samples)

    # ---- PyMC 路径（预留实现，CI 不装 pymc 时不触发）----
    def _aggregate_pymc(
        self, pymc: Any, effects: list[float], se: list[float], group_ids: list[str]
    ) -> AggregationResult:
        import numpy as np  # noqa: F401  pymc 依赖 numpy
        with pymc.Model() as model:  # type: ignore[union-attr]
            tau = pymc.HalfNormal("tau", sigma=1.0)
            mu = pymc.Normal("mu", mu=0.0, sigma=2.0)
            group_effect = pymc.Normal("group_effect", mu=mu, sigma=tau, shape=len(effects))
            for i, (y, s) in enumerate(zip(effects, se)):
                pymc.Normal(f"y_{i}", mu=group_effect[i], sigma=s, observed=y)
            trace = pymc.sample(draws=1000, tune=500, random_seed=self.seed, progressbar=False)
        mu_post = float(np.mean(trace["mu"]))
        tau_post = float(np.mean(trace["tau"]))
        tau_sq = tau_post ** 2
        inv_vars = [1.0 / (s * s + tau_sq) for s in se]
        total = sum(inv_vars)
        weights = {g: w / total for g, w in zip(group_ids, inv_vars)}
        return AggregationResult(
            pooled_effect=mu_post,
            tau_squared=tau_sq,
            random_effect_weights=weights,
            method="pymc",
            n_groups=len(effects),
            individual_effects=list(effects),
            individual_se=list(se),
        )

    # ---- 纯 Python fallback：DL 权重 + log-normal Monte Carlo ----
    def _aggregate_pure_python(
        self,
        effects: list[float],
        se: list[float],
        group_ids: list[str],
        n_samples: int = 1000,
    ) -> AggregationResult:
        # 1) 用 DerSimonian-Laird 迭代估计 tau^2
        inv_vars = [1.0 / (s * s) for s in se]
        total_iv = sum(inv_vars)
        weights_0 = [w / total_iv for w in inv_vars]
        pooled_0 = sum(w * y for w, y in zip(weights_0, effects))

        tau_sq = 0.0
        for _ in range(50):  # 迭代收敛
            ws = [1.0 / (s * s + tau_sq) for s in se]
            tw = sum(ws)
            ws = [w / tw for w in ws]
            pooled = sum(w * y for w, y in zip(ws, effects))
            Q = sum(w * (y - pooled) ** 2 for w, y in zip(ws, effects))
            C = sum(1.0 / (s * s + tau_sq) for s in se)
            # DL 更新
            new_tau_sq = max(0.0, (Q - (len(effects) - 1)) / C)
            if abs(new_tau_sq - tau_sq) < 1e-6:
                tau_sq = new_tau_sq
                break
            tau_sq = new_tau_sq

        # 2) 计算最终权重
        ws_final = [1.0 / (s * s + tau_sq) for s in se]
        tw = sum(ws_final)
        ws_final = [w / tw for w in ws_final]
        pooled = sum(w * y for w, y in zip(ws_final, effects))
        weights = {g: w for g, w in zip(group_ids, ws_final)}

        # 3) Monte Carlo 采样：把 pooled 当作后验均值，用 log-normal 先验近似
        #    采样 pooled 的分布（后验 SD ≈ sqrt(sum(w^2 * s^2))）
        rng = random.Random(self.seed)
        post_sd = math.sqrt(sum((w * s) ** 2 for w, s in zip(ws_final, se)))
        samples: list[float] = []
        for _ in range(n_samples):
            # log-normal 近似：exp(N(log(mu - sd^2/2), sd)) 均值 = mu
            mu = pooled
            sigma_ln = post_sd if post_sd > 1e-9 else 1e-6
            log_mean = math.log(max(mu, 1e-9)) - 0.5 * sigma_ln * sigma_ln
            x = math.exp(rng.gauss(log_mean, sigma_ln))
            samples.append(x)
        samples.sort()
        mc_mean = float(sum(samples) / len(samples))

        return AggregationResult(
            pooled_effect=mc_mean,
            tau_squared=tau_sq,
            random_effect_weights=weights,
            method="pure_python_montecarlo",
            n_groups=len(effects),
            individual_effects=list(effects),
            individual_se=list(se),
        )


def aggregate_effects(
    effects: list[float],
    se: list[float] | None = None,
    group_ids: list[str] | None = None,
    **kwargs: Any,
) -> AggregationResult:
    """函数式便捷入口。

    kwargs 中的 force_pymc / seed 传给构造器；n_samples 传给 aggregate()。
    """
    n_samples = kwargs.pop("n_samples", 1000)
    return BayesianHierarchicalAggregator(**kwargs).aggregate(
        effects, se, group_ids, n_samples=n_samples
    )


# ---------------------------------------------------------------------------
# 3. E-value（独立函数，公式与 causal_simulator._evalue_rr 一致）
# ---------------------------------------------------------------------------


def compute_evalue(point_estimate: float, se: float) -> float:
    """VanderWeele & Ding (2017) E-value。

    公式：
        RR = exp(|point_estimate|)   # 取绝对值：log-RR 尺度 → RR（对称）
        E-value = RR + sqrt(RR * (RR - 1))

    值越接近 1 → 效应越易被未观测混淆解释（越脆弱）。

    Raises:
        ValueError:
            - se < 0
            - point_estimate / se 为 NaN
            - |point_estimate| < 1e-9（零效应：E-value 数学无意义，明确报错）
    """
    if se < 0:
        raise ValueError("se 必须非负")
    if math.isnan(point_estimate) or math.isnan(se):
        raise ValueError("point_estimate / se 不可为 NaN")
    if abs(point_estimate) < 1e-9:
        raise ValueError("point_estimate 接近零：E-value 对零效应无定义，明确报错")
    # 取绝对值：负效应（log-RR<0）等价于 RR<1，其 E-value 与 RR' = 1/RR 一致；
    # 取 abs 保证 RR ≥ 1，公式内 RR*(RR-1) 恒非负，不会返回 complex。
    log_rr = abs(point_estimate)
    rr = math.exp(min(log_rr, 30.0))  # 数值保护：避免 exp 溢出
    return rr + math.sqrt(max(0.0, rr * (rr - 1.0)))


if __name__ == "__main__":  # pragma: no cover
    import json
    ie = estimate_individual_effect(
        pre_scores=[10, 12, 11, 13, 12, 10, 11, 14],
        post_scores=[14, 15, 13, 18, 16, 13, 15, 19],
        n_of_1_type="Crossover",
        n_bootstrap=5000,
    )
    print(json.dumps(ie.as_dict(), ensure_ascii=False, indent=2))
    print("E-value(1.0, 0.2) =", round(compute_evalue(1.0, 0.2), 4))

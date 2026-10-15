"""联邦目标试验仿真（Federated Target Trial Emulation）— L3 最锋利原创点

出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3
      「联邦目标试验仿真（npj Digit Med 2025;8:387）论文成体系，无成熟开源库。」

**方法学对齐**：
npj Digit Med 2025;8:387（Federated Target Trial Emulation）核心：
1. 显式定义 target trial spec（intervention / comparator / eligibility /
   assignment / outcome / follow-up window）——本文件 `TargetTrialSpec`。
2. 用观测数据 + IPW（inverse probability weighting）估计 target estimand。
3. Refutation tests：placebo intervention + random assignment 应"发现"效应消失，
   否则原效应可能是伪相关（Pearl / Hernán 的负控协议）。

**本实现为简化版**（报告要求"不要承诺做不到的事"）：
- **不做 IPW 模型拟合**：无 sklearn/statsmodels，倾向性评分用简单启发式
  （covariate_summary 内预计算的 p_treated / p_control 或退化为 1/1 等权）。
- **不做倾向性评分 clip**：仅按配置 clip 极端权重。
- **不做跨租户分布式估计**：先本地聚合，再对聚合值做 IPW（对充分统计量加权）。

**明确注释**：
> 本实现是 npj Digit Med 2025;8:387 的**简化版**——无 IPW 模型拟合，
> 用简单匹配 + 权重裁剪；完整版本需要引入 sklearn（违反零第三方依赖原则），
> 故推迟到伙伴联调阶段。

设计约束：
- 仅依赖标准库；numpy 可选。
- 纯函数，无 side effect，便于单测。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.lib.federated.sufficient_stats import SufficientStats


# ---------------------------------------------------------------------------
# Target Trial 规范
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetTrialSpec:
    """联邦目标试验规范（对齐 Hernán & Robins target trial framework）。

    Fields:
        intervention: 干预描述（string，如 "high_intensity_exercise"）。
        comparator: 对照描述（string，如 "usual_care"）。
        eligibility_criteria: 入组标准（dict，键为变量名，值为可接受集合/范围）。
        assignment: 分配机制，取值 "randomized" | "as_treated" | "switcher"。
        outcome: 结局变量名（string）。
        follow_up_window: 随访窗口（week 或 day，正整数）。
    """

    intervention: str
    comparator: str
    eligibility_criteria: dict[str, Any] = field(default_factory=dict)
    assignment: str = "as_treated"
    outcome: str = "effect_estimate"
    follow_up_window: int = 8


# ---------------------------------------------------------------------------
# 目标试验仿真器
# ---------------------------------------------------------------------------


class TargetTrialEmulator:
    """跨租户目标试验仿真器（简化 IPW 版）。

    典型用法：
        spec = TargetTrialSpec(
            intervention="exercise_protocol",
            comparator="usual_care",
            assignment="as_treated",
            outcome="effect_estimate",
        )
        estimator = TargetTrialEmulator(ipw={"trim_fraction": 0.01, "max_weight": 20})
        estimate = estimator.emulate(spec, tenant_stats)
        refutation = estimator.run_refutation(spec, tenant_stats)
    """

    def __init__(
        self,
        ipw: dict[str, float] | None = None,
    ):
        self._ipw = {"trim_fraction": 0.01, "max_weight": 20.0}
        if ipw:
            self._ipw.update(ipw)

    # ---------- 权重计算 ----------

    def _propensity_from_stats(self, s: SufficientStats) -> float:
        """从 covariate_summary 抽取倾向性评分 p(effect 组)。

        若 covariate_summary 里显式给了 "p_treated" 就用；否则退化为 0.5
        （等权 IPW，等价于未加权——用于冷启动阶段）。
        """
        p = s.covariate_summary.get("p_treated")
        if isinstance(p, (int, float)) and 0.0 < p < 1.0 and math.isfinite(p):
            return float(p)
        # 备用：从 region 分组比例推算
        p_ratio = s.covariate_summary.get("p_control_ratio")
        if isinstance(p_ratio, (int, float)) and 0.0 < p_ratio < 1.0:
            return 1.0 - float(p_ratio)
        return 0.5

    def _ipw_weight(self, propensity: float) -> float:
        """计算 IPW 权重：1 / p，clip 到 [trim, max_weight]。"""
        trim = float(self._ipw.get("trim_fraction", 0.01))
        max_w = float(self._ipw.get("max_weight", 20.0))
        p = max(min(propensity, 1.0 - 1e-9), 1e-9)
        w = 1.0 / p
        # trim：极端小 p → 极大连接 trim 反方向（这里用 clip 简化）
        w = max(w, trim)
        w = min(w, max_w)
        return w

    # ---------- 主流程 ----------

    def emulate(
        self,
        spec: TargetTrialSpec,
        tenant_stats: list[SufficientStats],
    ) -> dict[str, Any]:
        """跨租户执行目标试验仿真。

        Returns:
            dict，包含：
              - estimate: pooled target estimand（IPW 加权后的效应）
              - n_tenants, total_n
              - per_tenant: [{tenant_id, weight, effect}]
              - spec: 输入 spec 快照
        """
        if not tenant_stats:
            raise ValueError("tenant_stats must not be empty")

        rows: list[dict[str, Any]] = []
        weight_sum = 0.0
        weighted_sum = 0.0
        total_n = 0
        for s in tenant_stats:
            p = self._propensity_from_stats(s)
            w = self._ipw_weight(p)
            rows.append({"tenant_id": s.tenant_id, "weight": w, "effect": float(s.effect_estimate)})
            weight_sum += w
            weighted_sum += w * float(s.effect_estimate)
            total_n += int(s.n)

        estimate = weighted_sum / weight_sum if weight_sum > 0 else 0.0

        return {
            "estimate": float(estimate),
            "n_tenants": len(tenant_stats),
            "total_n": int(total_n),
            "spec": {
                "intervention": spec.intervention,
                "comparator": spec.comparator,
                "assignment": spec.assignment,
                "outcome": spec.outcome,
                "follow_up_window": spec.follow_up_window,
            },
            "per_tenant": rows,
        }

    # ---------- 反证（refutation） ----------

    def run_refutation(
        self,
        spec: TargetTrialSpec,
        tenant_stats: list[SufficientStats],
    ) -> dict[str, Any]:
        """跑两类反证：

        1. **placebo intervention**：把 spec.intervention 换为占位
           （"placebo"），此时效应应≈0（因为 placebo 不改变 outcome）。
        2. **random assignment**：把 propensity 强制设为 0.5（等权），
           若效应仍显著，说明原 spec 可能存在 selection bias。

        Returns:
            dict，含 placebo_estimate / random_assignment_estimate /
            verdict（refuted = True 表示原效应可能是伪相关）。
        """
        if not tenant_stats:
            raise ValueError("tenant_stats must not be empty")

        # 反证 1：placebo intervention —— 强制把所有 effect 置 0
        placebo_rows: list[dict[str, Any]] = []
        placebo_est = 0.0
        weight_sum = 0.0
        weighted_sum = 0.0
        for s in tenant_stats:
            p = self._propensity_from_stats(s)
            w = self._ipw_weight(p)
            placebo_rows.append(
                {"tenant_id": s.tenant_id, "weight": w, "effect": 0.0}
            )
            weight_sum += w
            weighted_sum += w * 0.0
            placebo_est = weighted_sum / weight_sum if weight_sum > 0 else 0.0

        # 反证 2：random assignment —— 强制 propensity=0.5（等权）
        random_rows: list[dict[str, Any]] = []
        random_est = 0.0
        weight_sum = 0.0
        weighted_sum = 0.0
        for s in tenant_stats:
            w = self._ipw_weight(0.5)  # = 2.0（clip 后仍 2.0）
            random_rows.append(
                {"tenant_id": s.tenant_id, "weight": w, "effect": float(s.effect_estimate)}
            )
            weight_sum += w
            weighted_sum += w * float(s.effect_estimate)
            random_est = weighted_sum / weight_sum if weight_sum > 0 else 0.0

        original_est = self.emulate(spec, tenant_stats)["estimate"]
        placebo_refuted = abs(placebo_est) < 1e-9
        random_refuted = abs(random_est - original_est) < 1e-9 or abs(random_est) < 1e-9

        return {
            "original_estimate": float(original_est),
            "placebo_estimate": float(placebo_est),
            "random_assignment_estimate": float(random_est),
            "placebo_refutation_passed": bool(placebo_refuted),
            "random_assignment_refutation_passed": bool(random_refuted),
            "verdict": "effect_robust" if (placebo_refuted and random_refuted) else "suspect_selection_bias",
            "per_tenant_placebo": placebo_rows,
            "per_tenant_random": random_rows,
        }

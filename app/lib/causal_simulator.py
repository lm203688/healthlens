"""
HealthLens 因果推演层（Causal Inference Layer）— S2-1（2026-10-13）

把 wellness_simulator 的「确定性耦合网络前向推演」升级为**因果推断装置**，
对齐《J Transl Med》2026「From prediction to intervention」与 Frontiers 2026
「按风险分级的数字孪生验证要求」。四件套：

  1. scm_structure()      —— 把 AXIS_BRIDGES 显式声明为结构因果模型（SCM）：
                            节点（8 轴）、有向边（上游改善→下游抬升）、外生干预节点
                            （生活方式杠杆）、以及被承认但未被测量的混淆变量（遗传/环境）。
  2. counterfactual()     —— 反事实对比：给定已执行干预，输出「若不干预」的轨迹，
                            与实际轨迹逐轴相减，得到干预的因果贡献估计。
  3. calibrate()          —— 校准与不确定性：对耦合系数（±20%）与执行一致性
                            （0.85–1.0）做自助（bootstrap），输出逐轴 5/95 分位带，
                            而非单点估计。
  4. bridge_sensitivity() —— 未观测混淆敏感性（E-value 风格）：每个耦合边的 E-value
                            接近 1 → 该耦合对未观测混淆高度敏感，属机制*假设*，
                            必须经前瞻队列验证（S2-2 / S4），不能当作已识别的因果量。

设计约束（与 wellness_simulator 一致）：
  - 仅依赖标准库；可被精简环境 / agent loader 按路径加载。
  - 全程 not_clinical / 虚拟推演，不构成任何诊断、治疗或个体结果预测。
  - 这是方法学升级，不声称耦合系数已被因果识别；sensitivity 的诚实结论正是
    「需验证」。
"""
from __future__ import annotations

import copy
import random
from statistics import median

from app.lib.wellness_simulator import (
    AXES,
    AXIS_LABELS,
    COUPLING_BRIDGES,
    LEVERS,
    derive_baseline,
    simulate,
)


# ---------------------------------------------------------------------------
# 1. SCM 结构声明
# ---------------------------------------------------------------------------

def scm_structure(bridges: list[dict] | None = None) -> dict:
    """把轴间耦合显式声明为结构因果模型。

    Returns:
        nodes（8 轴，endogenous）+ edges（有向因果边）+ interventions（外生杠杆）
        + unobserved_confounders（被承认但未测量的混淆变量）。
    """
    bridges = COUPLING_BRIDGES if bridges is None else bridges
    nodes = {ax: {"label": AXIS_LABELS[ax], "type": "endogenous"} for ax in AXES}
    edges = [
        {
            "from": br["from"],
            "to": br["to"],
            "type": "structural",
            "coupling": br["coupling"],
            "mechanism": br["mechanism"],
        }
        for br in bridges
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "interventions": [
            {"lever": k, "label": v["label"], "drives": v["drive"]}
            for k, v in LEVERS.items()
        ],
        "unobserved_confounders": [
            {"id": "U_gen", "description": "遗传背景：同时影响多轴基线与被采纳的干预类型"},
            {"id": "U_env", "description": "环境/行为背景：同时影响生活方式执行与轴演化"},
        ],
        "assumptions": [
            "AXIS_BRIDGES 边为**有向因果链接**（上游改善→下游抬升），方向由机制先验给定。",
            "忽略未观测混淆时，反事实对比给出干预的因果贡献上界估计。",
            "耦合系数为透明启发式（文献锚定），**非因果识别量**，须经前瞻队列标定。",
        ],
    }


# ---------------------------------------------------------------------------
# 2. 反事实对比
# ---------------------------------------------------------------------------

def counterfactual(baseline: dict[str, float],
                   levers: list[str],
                   weeks: int = 12,
                   lever_scale: float = 1.0) -> dict:
    """反事实对比：实际干预轨迹 vs 不干预轨迹。

    因果贡献（per axis）= 实际终值 − 不干预终值。
    注意：这是「若不干预会怎样」的对比，在忽略未观测混淆的假设下给出
    干预效应估计；sensitivity 分析量化该假设的脆弱性。
    """
    actual = simulate(baseline, levers, weeks, lever_scale)
    no_intervention = simulate(baseline, [], weeks, lever_scale)
    effect = {}
    for ax in AXES:
        a = actual["final"]["scores"][ax]
        n = no_intervention["final"]["scores"][ax]
        effect[ax] = round(a - n, 2)
    return {
        "success": True,
        "not_clinical": True,
        "method": "counterfactual_contrast",
        "horizon_weeks": weeks,
        "actual_final": actual["final"]["scores"],
        "no_intervention_final": no_intervention["final"]["scores"],
        "effect_per_axis": effect,
        "wellness_index_effect": round(
            actual["final"]["wellness_index"] - no_intervention["final"]["wellness_index"], 2
        ),
        "disclaimer": (
            "反事实 = 假设未执行生活方式杠杆时本会得到的轨迹；逐轴差值是在"
            "「无未观测混淆」假设下的干预因果贡献估计。真实世界存在遗传/环境混淆，"
            "效应需前瞻队列验证。"
        ),
    }


# ---------------------------------------------------------------------------
# 3. 校准与不确定性（bootstrap）
# ---------------------------------------------------------------------------

def calibrate(baseline: dict[str, float],
              levers: list[str],
              weeks: int = 12,
              lever_scale: float = 1.0,
              n: int = 200,
              seed: int = 20261013) -> dict:
    """自助校准：扰动耦合系数（±20%）与执行一致性（0.85–1.0），
    输出逐轴终值 5/95 分位带，替代单点估计。

    带宽是启发式网络的**参数不确定性**，不是生物学方差。
    """
    rng = random.Random(seed)
    point = simulate(baseline, levers, weeks, lever_scale)
    bands: dict[str, list[float]] = {ax: [] for ax in AXES}
    for _ in range(n):
        perturbed = copy.deepcopy(COUPLING_BRIDGES)
        for br in perturbed:
            br["coupling"] *= rng.uniform(0.8, 1.2)
        ls = lever_scale * rng.uniform(0.85, 1.0)
        run = simulate(baseline, levers, weeks, ls, bridges=perturbed)
        for ax in AXES:
            bands[ax].append(run["final"]["scores"][ax])
    cal = {}
    for ax in AXES:
        vals = sorted(bands[ax])
        p5 = vals[max(0, int(0.05 * len(vals)))]
        p95 = vals[min(len(vals) - 1, int(0.95 * len(vals)))]
        cal[ax] = {
            "point": point["final"]["scores"][ax],
            "p5": round(p5, 1),
            "p95": round(p95, 1),
        }
    return {
        "success": True,
        "not_clinical": True,
        "method": "bootstrap_calibration",
        "n_bootstrap": n,
        "calibration": cal,
        "disclaimer": (
            "带宽来自耦合系数 ±20% 与执行一致性 0.85–1.0 的扰动，反映启发式网络的"
            "参数不确定性，不代表个体生物学方差。临床级不确定性需纵向数据标定。"
        ),
    }


# ---------------------------------------------------------------------------
# 4. 未观测混淆敏感性（E-value 风格）
# ---------------------------------------------------------------------------

def _evalue_rr(rr: float) -> float:
    """VanderWeele & Ding (2017) 风险比 E-value。

    E-value = RR + sqrt(RR*(RR-1))；值越接近 1，效应越易被未观测混淆解释。
    """
    rr = max(rr, 1e-9)
    return rr + (rr * (rr - 1)) ** 0.5


def bridge_sensitivity(bridges: list[dict] | None = None) -> dict:
    """逐耦合边的未观测混淆敏感性。

    把每条边的耦合系数映射为比例提升 RR = 1 + coupling，计算 E-value。
    E-value 接近 1 → 该耦合对未观测混淆高度敏感，属机制*假设*，
    必须经前瞻队列验证后才能当作因果量使用。
    """
    bridges = COUPLING_BRIDGES if bridges is None else bridges
    out = []
    for br in bridges:
        rr = 1.0 + br["coupling"]
        ev = _evalue_rr(rr)
        out.append({
            "from": br["from"],
            "to": br["to"],
            "coupling": br["coupling"],
            "rr": round(rr, 4),
            "e_value": round(ev, 4),
            "interpretation": (
                "E-value≈1 → 该耦合对未观测混淆高度敏感，属机制假设，"
                "须经前瞻队列（S2-2 / S4）标定"
                if ev < 1.2 else "相对稳健，但仍需验证"
            ),
        })
    return {
        "success": True,
        "method": "evalue_sensitivity",
        "bridges": out,
        "disclaimer": (
            "E-value 在此用于连续耦合系数的启发式敏感性提示，非临床 RR 的正式 E-value；"
            "目的是诚实暴露「耦合网络尚未被因果识别」，倒逼前瞻验证。"
        ),
    }


# ---------------------------------------------------------------------------
# 组合入口：四件套一次性产出
# ---------------------------------------------------------------------------

def causal_report(baseline: dict[str, float],
                  levers: list[str],
                  weeks: int = 12,
                  lever_scale: float = 1.0) -> dict:
    """产出因果推演四件套（结构 / 反事实 / 校准 / 敏感性）。"""
    return {
        "scm": scm_structure(),
        "counterfactual": counterfactual(baseline, levers, weeks, lever_scale),
        "calibration": calibrate(baseline, levers, weeks, lever_scale),
        "sensitivity": bridge_sensitivity(),
        "not_clinical": True,
        "disclaimer": (
            "本推演为基于八轴耦合网络（结构因果模型假设）的养生方案虚拟推演与因果推断练习，"
            "描述「若坚持某些生活方式，健康信号可能如何演化」的参考情景，不构成任何诊断、"
            "治疗或个体结果预测。耦合系数尚未被因果识别，效应须经前瞻队列验证。"
        ),
    }


if __name__ == "__main__":
    base = derive_baseline(weak_axes=["F", "A"])
    rep = causal_report(base, levers=["sleep_hygiene", "fasting", "anti_inflammatory_diet"], weeks=12)
    print("=== SCM 结构 ===")
    print("节点:", len(rep["scm"]["nodes"]), "有向边:", len(rep["scm"]["edges"]),
          "干预杠杆:", len(rep["scm"]["interventions"]))
    print("=== 反事实（干预 - 不干预，逐轴 Δ）===")
    for ax, d in rep["counterfactual"]["effect_per_axis"].items():
        print(f"  {ax}: {d:+.2f}")
    print("养生指数效应 Δ:", rep["counterfactual"]["wellness_index_effect"])
    print("=== 校准带（p5–p95）===")
    for ax, c in rep["calibration"]["calibration"].items():
        print(f"  {ax}: {c['p5']}–{c['p95']} (点 {c['point']})")
    print("=== 敏感性（E-value）===")
    for b in rep["sensitivity"]["bridges"]:
        print(f"  {b['from']}→{b['to']}: coupling={b['coupling']} E-value={b['e_value']}")

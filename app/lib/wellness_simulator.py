"""
HealthLens 迷你 Turboid —— 养生方案虚拟推演引擎（wellness signal simulator）
============================================================================

定位（务必先读）
--------------
Turbine(turbine.ai) 的「Simulated Cell」用 AI 虚拟化细胞信号网络做药物/疾病推演。
HealthLens 是 **wellness（健康管理）平台、非医疗**，因此本项目只取其「把耦合网络
变成可前向推演的动力学系统」这一思想，落地为 **八轴健康信号的养生方案虚拟推演**：

  · 输入：用户 8 轴基线健康信号分(0-100) + 选定的生活方式杠杆(levers) + 推演周数
  · 推演：逐周把"直接干预"沿 AXIS_BRIDGES 轴间耦合网络传播到下游轴
  · 输出：8 轴逐周轨迹、养生综合指数、限速轴、优先杠杆、已激活机制链

全程 **不含任何诊断/治疗/药物/疾病结论**，仅描述"若坚持某些生活方式，健康信号
可能如何演化"的参考推演。所有结论标注 not_clinical / 虚拟推演。

本模块 **仅依赖标准库**（与 bioage_engine.py 同策略），可被精简环境 / agent loader
按文件路径加载，不触发 app 包的 FastAPI 依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy

# ───────────────────────────────────────────────────────────────────────────
# 八轴标识与中文标签（与 fusion_engine / 记忆一致）
# ───────────────────────────────────────────────────────────────────────────
AXES: list[str] = ["A", "B", "C", "D", "E", "F", "G", "H"]
AXIS_LABELS: dict[str, str] = {
    "A": "气化/自噬",
    "B": "气血-线粒体",
    "C": "络脉-清瘀",
    "D": "阴阳-昼夜",
    "E": "脏腑-神经内分泌",
    "F": "正邪-炎症",
    "G": "神-情志",
    "H": "先天-肾精",
}

# 轴间耦合（wellness 信号视角：上游改善 → 下游抬升）。
# 取自 fusion_engine.AXIS_BRIDGES，5 条在健康信号语境下均为正向传导：
#   A→F（自噬↑→炎症负荷↓→F 信号↑）
#   A→H（自噬/线粒体更新→先天之本 H↑）
#   F→D（炎症↓→阴阳稳态 D↑）
#   H→F（表观遗传信息完整→异常蛋白亚型↓→炎症↓→F↑）
#   H→A（表观遗传完整→自噬转录程序支持→A↑）
COUPLING_BRIDGES: list[dict] = [
    {"from": "A", "to": "F", "coupling": 0.12,
     "mechanism": "自噬-溶酶体选择性降解炎症小体组分，焦亡性炎症下降"},
    {"from": "A", "to": "H", "coupling": 0.10,
     "mechanism": "线粒体自噬与能量稳态支持先天之本"},
    {"from": "F", "to": "D", "coupling": 0.10,
     "mechanism": "慢性低度炎症下行，利于阴阳互根稳态"},
    {"from": "H", "to": "F", "coupling": 0.12,
     "mechanism": "表观遗传信息完整→剪接体稳态→异常蛋白亚型与炎症负荷下降"},
    {"from": "H", "to": "A", "coupling": 0.10,
     "mechanism": "表观遗传完整支持自噬相关基因转录程序"},
]

# 生活方式杠杆 → 直接驱动的轴与每周增益（透明启发式，非临床剂量）
# 取值参考 AXIS_BRIDGES.intervention_link 中反复出现的生活方式条目。
LEVERS: dict[str, dict] = {
    "sleep_hygiene": {  # 规律作息/充足睡眠
        "label": "规律作息与充足睡眠",
        "drive": {"D": 0.8, "H": 0.5},
        "note": "昼夜节律锚定与表观遗传信息维护的基础杠杆",
    },
    "fasting": {  # 间歇性限食
        "label": "间歇性限食",
        "drive": {"A": 0.7, "H": 0.4},
        "note": "AMPK→自噬流，辅助先天之本",
    },
    "aerobic": {  # 有氧训练
        "label": "有氧训练",
        "drive": {"A": 0.5, "B": 0.7, "H": 0.3},
        "note": "线粒体生物合成与自噬协同",
    },
    "anti_inflammatory_diet": {  # 抗炎饮食
        "label": "抗炎饮食",
        "drive": {"F": 0.7},
        "note": "降低慢性低度炎症负荷",
    },
    "stress_mgmt": {  # 压力管理
        "label": "压力管理",
        "drive": {"G": 0.7, "F": 0.3},
        "note": "情志(神)安定利于炎症稳态",
    },
    "protein_intake": {  # 均衡蛋白摄入
        "label": "均衡蛋白摄入",
        "drive": {"H": 0.6},
        "note": "剪接体/修复所需原料供应",
    },
    "thermal": {  # 冷热应激
        "label": "冷热应激（如冷水浴）",
        "drive": {"A": 0.4},
        "note": "激活线粒体自噬（需循序渐进）",
    },
}

# 弱轴阈值：基线低于此视为偏弱，参与限速轴判定
WEAK_THRESHOLD: float = 55.0
# 单步驱动上限，防止某杠杆单周过冲
MAX_STEP_DRIVE: float = 1.5
# 均值回归强度（向 50 轻微回拉，模拟不干预会退行；该回拉被杠杆驱动覆盖）
REVERSION: float = 0.004


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def derive_baseline(weak_axes: list[str] | None = None,
                    provided: dict[str, float] | None = None) -> dict[str, float]:
    """生成基线 8 轴分。

    - 若提供 provided（含部分轴），以之为主，缺失轴给中性 68。
    - 弱项轴（weak_axes）若未提供或高于阈值，压到 45 表达"偏弱"。
    """
    base = dict.fromkeys(AXES, 68.0)
    if provided:
        for k, v in provided.items():
            if k in base:
                base[k] = float(v)
    for ax in (weak_axes or []):
        ax = ax.upper()
        if ax in base and base[ax] > WEAK_THRESHOLD:
            base[ax] = 45.0
    return {k: _clamp(v) for k, v in base.items()}


def derive_baseline_from_checkin(energy: int | None = None,
                                  digestion: int | None = None,
                                  sleep: int | None = None,
                                  weak_axes: list[str] | None = None) -> dict[str, float]:
    """从 SIIV 自测数据（1-5 分）推导 8 轴基线分（0-100）。

    映射逻辑（wellness 主观感受 → 八轴健康信号）：
      energy_score → A（自噬/能量代谢）、B（线粒体/能量）
      digestion_score → F（炎症/消化）
      sleep_score → D（昼夜节律/睡眠）、G（情志/情绪）

    1 分 = 20 分基线，5 分 = 90 分基线（线性映射，留余量）。
    未提供的维度给中性 68。弱项轴若高于阈值则压到 45。
    """
    base = dict.fromkeys(AXES, 68.0)

    # 1-5 分 → 0-100 分线性映射：score * 17.5 + 5
    def _map1_5_to_0_100(s: int | None) -> float | None:
        if s is None or not isinstance(s, (int, float)):
            return None
        return _clamp(float(s) * 17.5 + 5.0)

    # energy → A, B
    if energy is not None:
        v = _map1_5_to_0_100(energy)
        if v is not None:
            base["A"] = v
            base["B"] = v

    # digestion → F
    if digestion is not None:
        v = _map1_5_to_0_100(digestion)
        if v is not None:
            base["F"] = v

    # sleep → D, G
    if sleep is not None:
        v = _map1_5_to_0_100(sleep)
        if v is not None:
            base["D"] = v
            base["G"] = v

    # 弱项轴压制（覆盖自测推导）
    for ax in (weak_axes or []):
        ax = ax.upper()
        if ax in base and base[ax] > WEAK_THRESHOLD:
            base[ax] = 45.0

    return {k: _clamp(v) for k, v in base.items()}


def simulate(baseline: dict[str, float],
             levers: list[str],
             weeks: int = 12,
             lever_scale: float = 1.0) -> dict:
    """前向推演 8 轴健康信号演化。

    Args:
        baseline: {轴字母: 0-100 基线分}
        levers: 启用的生活方式杠杆 key 列表（见 LEVERS）
        weeks: 推演周数
        lever_scale: 杠杆强度系数（0-1，模拟"执行一致性"）
    Returns:
        dict 含 trajectory / final / 限速轴 / 优先杠杆 / 已激活桥接 / 免责
    """
    weeks = max(1, int(weeks))
    scale = max(0.0, min(1.0, float(lever_scale)))
    cur = {ax: float(baseline.get(ax, 68.0)) for ax in AXES}
    start = dict(cur)
    active_drives: dict[str, float] = {}
    for lv in levers:
        spec = LEVERS.get(lv)
        if not spec:
            continue
        for ax, amt in spec["drive"].items():
            active_drives[ax] = active_drives.get(ax, 0.0) + amt * scale
    # 限制单轴单周直接驱动上限
    active_drives = {ax: min(amt, MAX_STEP_DRIVE) for ax, amt in active_drives.items()}

    trajectory = [{
        "week": 0,
        "scores": {ax: round(cur[ax], 1) for ax in AXES},
        "wellness_index": round(sum(cur.values()) / len(AXES), 1),
    }]

    # 记录哪些桥接被激活（其上游轴相对基线有改善）
    activated = set()

    for t in range(1, weeks + 1):
        prev = dict(cur)
        nxt = dict(cur)
        # 1) 直接干预驱动
        for ax, amt in active_drives.items():
            nxt[ax] = _clamp(nxt[ax] + amt)
        # 2) 轴间耦合：上游相对其基线的改善，按比例抬升下游
        for br in COUPLING_BRIDGES:
            s, d = br["from"], br["to"]
            upstream_gain = prev[s] - start[s]  # 仅传导"已发生的改善"
            if upstream_gain > 0.5:
                nxt[d] = _clamp(nxt[d] + br["coupling"] * upstream_gain)
                activated.add((s, d))
        # 3) 轻微均值回归（不干预也会缓慢退行）
        for ax in AXES:
            nxt[ax] = _clamp(nxt[ax] - REVERSION * (nxt[ax] - 50.0))
        cur = nxt
        trajectory.append({
            "week": t,
            "scores": {ax: round(cur[ax], 1) for ax in AXES},
            "wellness_index": round(sum(cur.values()) / len(AXES), 1),
        })

    final_scores = {ax: round(cur[ax], 1) for ax in AXES}
    final_index = round(sum(cur.values()) / len(AXES), 1)
    base_index = round(sum(start.values()) / len(AXES), 1)

    # 限速轴：基线偏弱轴中，最终相对缺口(100-基线)增益比例最低者
    weak = [ax for ax in AXES if start[ax] < WEAK_THRESHOLD]
    rate_limiting = None
    if weak:
        def _gain_ratio(ax):
            deficit = 100.0 - start[ax]
            gain = cur[ax] - start[ax]
            return gain / deficit if deficit > 0 else 1.0
        rl = min(weak, key=_gain_ratio)
        # 解释为：是否受上游桥接制约
        upstream_deps = [b for b in COUPLING_BRIDGES if b["to"] == rl]
        reason = f"{AXIS_LABELS[rl]}轴基线偏弱且改善较慢"
        if upstream_deps:
            ups = "、".join(AXIS_LABELS[b["from"]] for b in upstream_deps)
            reason += f"，受上游「{ups}」轴状态制约，需优先稳固上游"
        rate_limiting = {"axis": rl, "label": AXIS_LABELS[rl], "reason": reason}

    # 优先杠杆：逐个追加未启用杠杆，重算养生指数增益，排序取前 2
    prioritized = []
    for lv, spec in LEVERS.items():
        if lv in levers:
            continue
        test_drives = dict(active_drives)
        for ax, amt in spec["drive"].items():
            test_drives[ax] = min(test_drives.get(ax, 0.0) + amt * scale, MAX_STEP_DRIVE)
        # 轻量重算（复用同逻辑）
        tmp = {ax: float(start[ax]) for ax in AXES}
        for _ in range(weeks):
            p = dict(tmp)
            for ax, amt in test_drives.items():
                tmp[ax] = _clamp(tmp[ax] + amt)
            for br in COUPLING_BRIDGES:
                g = p[br["from"]] - start[br["from"]]
                if g > 0.5:
                    tmp[br["to"]] = _clamp(tmp[br["to"]] + br["coupling"] * g)
            for ax in AXES:
                tmp[ax] = _clamp(tmp[ax] - REVERSION * (tmp[ax] - 50.0))
        gain = round(sum(tmp.values()) / len(AXES) - base_index, 1)
        if gain > 0:
            prioritized.append({
                "lever": lv,
                "label": spec["label"],
                "projected_gain": gain,
            })
    prioritized.sort(key=lambda x: x["projected_gain"], reverse=True)
    prioritized = prioritized[:2]

    bridges_activated = [
        {"from": s, "from_label": AXIS_LABELS[s],
         "to": d, "to_label": AXIS_LABELS[d],
         "mechanism": next(b["mechanism"] for b in COUPLING_BRIDGES if b["from"] == s and b["to"] == d)}
        for (s, d) in sorted(activated)
    ]

    return {
        "success": True,
        "not_clinical": True,
        "horizon_weeks": weeks,
        "baseline": {ax: round(start[ax], 1) for ax in AXES},
        "final": {
            "scores": final_scores,
            "wellness_index": final_index,
            "delta_index": round(final_index - base_index, 1),
        },
        "trajectory": trajectory,
        "weak_axes": weak,
        "rate_limiting": rate_limiting,
        "bridges_activated": bridges_activated,
        "prioritized_levers": prioritized,
        "disclaimer": (
            "本推演为基于八轴耦合网络的养生方案虚拟推演，描述「若坚持某些生活方式，"
            "健康信号可能如何演化」的参考情景，不构成任何诊断、治疗或个体结果预测。"
            "实际效果受遗传、环境、执行一致性等影响，涉及疾病或用药请遵医嘱。"
        ),
    }


if __name__ == "__main__":
    base = derive_baseline(weak_axes=["F", "A"])
    out = simulate(base, levers=["sleep_hygiene", "fasting", "anti_inflammatory_diet"], weeks=12)
    print("迷你 Turboid 推演示例（弱轴 F/A，杠杆: 睡眠+限食+抗炎饮食，12 周）")
    print("基线养生指数:", out["trajectory"][0]["wellness_index"],
          "→ 终值:", out["final"]["wellness_index"],
          "(Δ", out["final"]["delta_index"], ")")
    print("限速轴:", out["rate_limiting"])
    print("已激活桥接:", [(b["from"], "→", b["to"]) for b in out["bridges_activated"]])
    print("优先杠杆:", out["prioritized_levers"])

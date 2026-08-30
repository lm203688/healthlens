"""
flow.py — HealthLens 可复现 DAG pipeline（P2）

把「用户诉求 → 八轴解析 → 基因弱项 → 通路映射 → 融合 → 评级 → 报告」封装为
可复用算子 + DAG 执行器。真实调用 app/lib/fusion_engine.py。

    python -m healthlens_agent flow --input "最近容易疲劳怕冷" \
                                    --gene mitochondrial:0.32 Circadian_CLOCK_BMAL1:0.41

借鉴 DataFlow-Agent（赛道一 #17）：复用优先于合成；算子通过全局 Storage 键绑定 I/O。
无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ._loader import load_fusion_engine, repo_root

_fe = load_fusion_engine()
recommend = _fe.recommend
UserProfile = _fe.UserProfile
disclaimer = _fe.disclaimer

_MAP_PATH = os.path.join(repo_root(), "data", "tcm_pathway_map.json")
with open(_MAP_PATH, encoding="utf-8") as _f:
    _MAP = json.load(_f)
_AXIS_PATHWAYS: dict[str, list[str]] = _MAP.get("axis_pathways", {})
_AXIS_LABELS: dict[str, str] = _MAP.get("axis_labels", {})


# ---------------------------------------------------------------------------
# Storage & Operator 抽象
# ---------------------------------------------------------------------------
@dataclass
class Storage:
    data: dict[str, object] = field(default_factory=dict)

    def read(self, key: str):
        return self.data.get(key)

    def write(self, key: str, value) -> Storage:
        self.data[key] = value
        return self


@dataclass
class Operator:
    name: str
    run: Callable[[Storage], Storage]


# ---------------------------------------------------------------------------
# 八轴关键词（同 planner）
# ---------------------------------------------------------------------------
_AXIS_KEYWORDS = {
    "A": ["疲劳", "乏力", "没精神", "自噬", "autophagy"],
    "B": ["气短", "喘", "线粒体", "mitochondria", "气血", "怕冷"],
    "C": ["血瘀", "瘀堵", "痛", "炎症", "inflammation", "senolytic"],
    "D": ["睡不好", "失眠", "昼夜", "circadian", "褪黑素"],
    "E": ["内分泌", "情绪波动", "神经", "neuro"],
    "F": ["感染", "免疫", "炎症", "immune"],
    "G": ["焦虑", "抑郁", "情志", "mood"],
    "H": ["肾", "先天", "衰老", "老年", "aging", "肾精"],
}


def _infer_axes(text: str) -> list[str]:
    axes = []
    for ax, kws in _AXIS_KEYWORDS.items():
        if any(kw in text for kw in kws):
            axes.append(ax)
    return list(set(axes))


# ---------------------------------------------------------------------------
# 算子（真实逻辑）
# ---------------------------------------------------------------------------
def op_tcm_parse(s: Storage) -> Storage:
    text = s.read("user_input") or ""
    axes = _infer_axes(text)
    s.write("axis_candidates", axes)
    s.write("axis_labels", [_AXIS_LABELS.get(a, a) for a in axes])
    return s


def op_gene_weak(s: Storage) -> Storage:
    gene = s.read("gene_data") or {}
    weak = {k: v for k, v in gene.items() if isinstance(v, (int, float)) and v < 0.5}
    s.write("pathway_scores", weak)
    return s


def op_pathway_map(s: Storage) -> Storage:
    axes = s.read("axis_candidates") or []
    weak_pathways = set(s.read("pathway_scores") or {})
    for a in axes:
        weak_pathways.update(_AXIS_PATHWAYS.get(a, []))
    s.write("mapped_pathways", sorted(weak_pathways))
    return s


def op_fusion(s: Storage) -> Storage:
    pathway_scores = s.read("pathway_scores") or {}
    axes = set(s.read("axis_candidates") or [])
    profile = UserProfile(pathway_scores=pathway_scores, weak_axes=axes)
    s.write("fusion_output", recommend(profile))
    return s


def op_grade(s: Storage) -> Storage:
    fusion = s.read("fusion_output") or {}
    recs = fusion.get("recommendations", [])
    if not recs:
        s.write("grade", "N/A")
        return s
    levels = [r.get("evidence_level", "L3") for r in recs]
    l1 = levels.count("L1")
    l2 = levels.count("L2")
    if l1 >= len(levels) * 0.5:
        grade = "L1"
    elif (l1 + l2) >= len(levels) * 0.5:
        grade = "L2"
    else:
        grade = "L3"
    s.write("grade", grade)
    return s


def op_report(s: Storage) -> Storage:
    fusion = s.read("fusion_output") or {}
    report = {
        "banner": fusion.get("banner"),
        "has_gene": fusion.get("has_gene", False),
        "weak_pathways": fusion.get("weak_pathways", []),
        "weak_axes": fusion.get("weak_axes", []),
        "axis_candidates": s.read("axis_candidates"),
        "axis_labels": s.read("axis_labels"),
        "grade": s.read("grade"),
        "recommendations": fusion.get("recommendations", []),
        "disclaimer": disclaimer(),
    }
    s.write("report", report)
    return s


DEFAULT_OPS: dict[str, Operator] = {
    "tcm_parse": Operator("tcm_parse", op_tcm_parse),
    "gene_weak": Operator("gene_weak", op_gene_weak),
    "pathway_map": Operator("pathway_map", op_pathway_map),
    "fusion": Operator("fusion", op_fusion),
    "grade": Operator("grade", op_grade),
    "report": Operator("report", op_report),
}

DEFAULT_DAG = [
    ("tcm_parse", []),
    ("gene_weak", []),
    ("pathway_map", ["tcm_parse", "gene_weak"]),
    ("fusion", ["pathway_map"]),
    ("grade", ["fusion"]),
    ("report", ["grade"]),
]


# ---------------------------------------------------------------------------
# DAG 执行器（Kahn 拓扑排序）
# ---------------------------------------------------------------------------
def run_flow(
    dag: list[tuple] = DEFAULT_DAG,
    ops: dict[str, Operator] = DEFAULT_OPS,
    inputs: dict = None,
    storage: Storage = None,
) -> Storage:
    storage = storage or Storage()
    for k, v in (inputs or {}).items():
        storage.write(k, v)

    indeg = {n: 0 for n, _ in dag}
    adj = {n: [] for n, _ in dag}
    for n, d in dag:
        for dep in d:
            adj[dep].append(n)
            indeg[n] += 1
    queue = [n for n, d in indeg.items() if d == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(order) != len(dag):
        raise ValueError("DAG 存在环或缺失节点")

    for name in order:
        storage = ops[name].run(storage)
    return storage


def _parse_gene(args_str: list[str]) -> dict[str, float]:
    out = {}
    for item in args_str:
        key, val = item.split(":", 1)
        out[key] = float(val)
    return out


def main():
    parser = argparse.ArgumentParser(description="HealthLens 可复现融合 DAG")
    parser.add_argument("--input", required=True, help="用户诉求文本")
    parser.add_argument(
        "--gene", nargs="+", default=[], help="基因弱项，格式 pathway:score"
    )
    parser.add_argument("--out", default=None, help="输出 JSON 文件路径；不传则打印")
    args = parser.parse_args()

    inputs = {"user_input": args.input, "gene_data": _parse_gene(args.gene)}
    storage = run_flow(inputs=inputs)
    report = storage.read("report")

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"报告已写入: {args.out}")
    else:
        print(payload)


def demo():
    print("=== flow：真实 fusion_engine DAG 复现 ===\n")
    storage = run_flow(
        inputs={
            "user_input": "最近容易疲劳、怕冷、睡不好",
            "gene_data": {"mitochondrial": 0.32, "Circadian_CLOCK_BMAL1": 0.41},
        }
    )
    print(json.dumps(storage.read("report"), ensure_ascii=False, indent=2))
    print(
        "\n[完成] 可用 `python -m healthlens_agent flow --input '...' --gene mitochondrial:0.32` 一行复现。"
    )

"""
healthlens_flow.py — 健康数据治理 DAG pipeline 草案（借鉴 DataFlow-Agent / PKU-DCAI）

DataFlow-Agent 核心思想：自然语言→可执行流水线 = 意图拆解 → 算子检索/合成 → DAG 编排
→ 沙箱验证 → 输出；近 200 算子，**复用优先于合成**。

本草案把 HealthLens 的「古籍解析 → 基因弱项 → 通路映射 → 融合 → 评级 → 报告」
封装为可复用算子 + DAG 执行器，目标：一行命令复现一次融合。
算子接口统一：run(storage) -> storage（参考 DataFlow 的全局存储抽象 + 键绑定 I/O）。

这是**草案骨架**：算子内部逻辑以占位/示意实现，真实逻辑应接入现有
fusion_engine.py / tcm_pathway_map.json / case_evidence_db.json。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List


@dataclass
class Storage:
    """全局表格化存储抽象（借鉴 DataFlow Global Storage）：算子只关心字段。"""
    data: Dict[str, object] = field(default_factory=dict)

    def read(self, key: str):
        return self.data.get(key)

    def write(self, key: str, value) -> "Storage":
        self.data[key] = value
        return self


@dataclass
class Operator:
    name: str
    run: Callable[[Storage], Storage]


# ---------------------------------------------------------------------------
# 算子（复用优先；真实逻辑待接入现有模块）
# ---------------------------------------------------------------------------

def op_tcm_parse(s: Storage) -> Storage:
    """古籍解析：把用户诉求/文本解析为八轴候选。"""
    text = s.read("user_input") or ""
    # 占位：真实实现应调用古籍结构化引擎
    s.write("axis_candidates", ["A", "B", "C"])
    return s


def op_gene_weak(s: Storage) -> Storage:
    """基因弱项提取：从基因数据提取弱项通路。"""
    gene = s.read("gene_data") or []
    s.write("gene_weak", gene or ["LAMP2", "TFEB"])
    return s


def op_pathway_map(s: Storage) -> Storage:
    """通路映射：古籍候选 ∩ 基因弱项通路。"""
    axes = s.read("axis_candidates") or []
    genes = s.read("gene_weak") or []
    # 占位：真实实现应查 tcm_pathway_map.json
    s.write("mapped_pathways", [f"{a}∩{g}" for a in axes for g in genes][:3])
    return s


def op_fusion(s: Storage) -> Storage:
    """融合引擎：生成非用药干预候选 + 证据溯源。"""
    paths = s.read("mapped_pathways") or []
    s.write("fusion_output", {
        "claims": [f"基于 {p} 的稳态调理建议" for p in paths],
        "evidence": [{"type": "gene", "id": "LAMP2", "effect": "↑4.2×"}],
    })
    return s


def op_grade(s: Storage) -> Storage:
    """评级：给融合结果打证据等级 L1-L3。"""
    s.write("grade", "L2")
    return s


def op_report(s: Storage) -> Storage:
    """报告生成：组装可分享报告。"""
    out = {
        "fusion": s.read("fusion_output"),
        "grade": s.read("grade"),
        "axis_candidates": s.read("axis_candidates"),
    }
    s.write("report", out)
    return s


DEFAULT_OPS: Dict[str, Operator] = {
    "tcm_parse": Operator("tcm_parse", op_tcm_parse),
    "gene_weak": Operator("gene_weak", op_gene_weak),
    "pathway_map": Operator("pathway_map", op_pathway_map),
    "fusion": Operator("fusion", op_fusion),
    "grade": Operator("grade", op_grade),
    "report": Operator("report", op_report),
}

# DAG：边的依赖关系（拓扑排序执行）
DEFAULT_DAG = [
    ("tcm_parse", []),
    ("gene_weak", []),
    ("pathway_map", ["tcm_parse", "gene_weak"]),
    ("fusion", ["pathway_map"]),
    ("grade", ["fusion"]),
    ("report", ["grade"]),
]


# ---------------------------------------------------------------------------
# DAG 执行器（拓扑排序 + 复用优先 + 沙箱验证钩子）
# ---------------------------------------------------------------------------

def run_flow(dag: List[tuple] = DEFAULT_DAG, ops: Dict[str, Operator] = DEFAULT_OPS,
             inputs: Dict = None, storage: Storage = None) -> Storage:
    storage = storage or Storage()
    for k, v in (inputs or {}).items():
        storage.write(k, v)

    # 拓扑排序（Kahn）
    indeg = {n: 0 for n, _ in dag}
    adj = {n: [] for n, _ in dag}
    deps = {n: list(d) for n, d in dag}
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
    assert len(order) == len(dag), "DAG 存在环或缺失节点"

    for name in order:
        # 沙箱验证钩子：执行前可插入测试/校验（借鉴 DataFlow 沙箱验证）
        storage = ops[name].run(storage)
    return storage


def _demo():
    print("=== healthlens_flow 演示（借鉴 DataFlow-Agent DAG pipeline）===\n")
    storage = run_flow(inputs={"user_input": "最近容易疲劳、怕冷", "gene_data": ["LAMP2", "TFEB"]})
    report = storage.read("report")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n提示：把算子内部替换为真实 fusion_engine / tcm_pathway_map / case_evidence_db 逻辑，")
    print("即可用 `run_flow(inputs={...})` 一行复现一次融合，降低行业复现门槛。")


if __name__ == "__main__":
    _demo()

"""
pipeline.py — HealthLens 融合安全管线（P0，GOAI 借鉴落地）

把 safety 两道闸门 + audit 遥测，**直接接入真实融合引擎** app/lib/fusion_engine.recommend()。

设计（借鉴 MedAssist 前置红牌 + LabGuard typed guard IR + Codenotary 运行时遥测）：
  pre_gate(user_input)    生成前：命中医学急症即拦截 + 急救指引
  recommend(...)          真实融合引擎（Executor）
  post_gate(rec)          生成后：拦截去医疗化违反/八轴红线击穿/证据断链
  audit(log)              工具调用流式审计（七类异常）

无第三方依赖。用法：
  python -m healthlens_agent pipeline
"""

from __future__ import annotations

import time

from . import audit as ra
from . import safety as sg
from ._loader import load_fusion_engine

_fe = load_fusion_engine()
recommend = _fe.recommend
UserProfile = _fe.UserProfile
disclaimer = _fe.disclaimer


class PipelineResult:
    """一次融合管线的完整产物：融合结果 + 安全审计 + 引用免责。"""

    def __init__(
        self,
        banner,
        has_gene,
        weak_pathways,
        weak_axes,
        recommendations,
        pre_result,
        post_findings,
        audit_events,
        audit_log_path,
    ):
        self.banner = banner
        self.has_gene = has_gene
        self.weak_pathways = weak_pathways
        self.weak_axes = weak_axes
        self.recommendations = recommendations
        self.pre_result = pre_result
        self.post_findings = post_findings
        self.audit_events = audit_events
        self.audit_log_path = audit_log_path

    @property
    def passed(self) -> bool:
        return self.pre_result.passed and all(
            r["gate_passed"] for r in self.recommendations
        )

    @property
    def any_unsafe(self) -> bool:
        return self.pre_result.unsafe_event or any(f for f in self.post_findings)

    @property
    def evidence_chain(self) -> list[dict]:
        """证据链摘要（借鉴天晴'制剂→动物→临床'三段式）：
        每条建议聚合 tcm_source / gene_relevance / evidence_level 为一条可引用记录。"""
        chain = []
        for r in self.recommendations:
            level = r.get("evidence_level")
            chain.append({
                "name": r.get("name"),
                "evidence_level": level,
                "tcm_source": r.get("tcm_source"),
                "gene_relevance": r.get("gene_relevance"),
                "gate_passed": r.get("gate_passed"),
            })
        return chain

    def to_dict(self):
        return {
            "passed": self.passed,
            "any_unsafe": self.any_unsafe,
            "banner": self.banner,
            "has_gene": self.has_gene,
            "weak_pathways": self.weak_pathways,
            "weak_axes": self.weak_axes,
            "pre_gate": self.pre_result.to_dict(),
            "post_findings": self.post_findings,
            "audit_event_count": len(self.audit_events),
            "recommendations": self.recommendations,
            "evidence_chain": self.evidence_chain,
            "disclaimer": disclaimer(),
        }


_AUDITOR = ra.RuntimeAuditor(
    ra.AuditorConfig(
        allowed_tools=["recommend_fusion_engine"],
        whitelisted_hosts=["healthlens.cc", "localhost"],
        max_same_tool_calls=3,
        token_threshold=8000,
        duration_threshold_ms=30000,
    )
)

# 简易规划器：user_input 关键词 → weak_axes/pathway_scores
_AXIS_KEYWORDS = {
    "A": ["疲劳", "乏力", "没精神", "自噬", "autophagy"],
    "B": ["气短", "喘", "线粒体", "mitochondria", "气血"],
    "C": ["血瘀", "瘀堵", "痛", "炎症", "inflammation", "senolytic"],
    "D": ["睡不好", "失眠", "昼夜", "circadian", "褪黑素"],
    "E": ["内分泌", "情绪波动", "神经", "neuro"],
    "F": ["感染", "免疫", "炎症", "immune"],
    "G": ["焦虑", "抑郁", "情志", "mood"],
    "H": [
        "肾", "先天", "衰老", "老年", "aging", "肾精",
        # sPL 借鉴：内源性干细胞激活（H 轴现代生物学维度）
        "干细胞", "再生", "修复", "sPL", "endogenous",
    ],
}

# 关键词 → 规范化通路名映射（供 fusion_engine 做别名消歧）
_PATHWAY_KEYWORDS = {
    "mitochondria": "mitochondrial",
    "mitochondrial": "mitochondrial",
    "sPL": "endogenous_stem_cell_activation",
    "spla": "endogenous_stem_cell_activation",
    "干细胞": "endogenous_stem_cell_activation",
    "endogenous": "endogenous_stem_cell_activation",
    "自噬": "autophagy",
    "autophagy": "autophagy",
    "昼夜": "circadian",
    "circadian": "circadian",
    "clock": "circadian",
    "inflammation": "inflammation",
    "炎症": "inflammation",
    "mood": "bdnf",
    "情志": "bdnf",
}


def _planner_from_text(text: str) -> UserProfile:
    scores: dict[str, float] = {}
    for ax, kws in _AXIS_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text.lower():
                scores[f"axis_{ax}_pathway"] = 0.35  # 标记为弱项 (<0.5)
                break
    # 关键词 → 规范化通路别名（sPL 借鉴：把干细胞/再生语义归入通路词表）
    for kw, pathway in _PATHWAY_KEYWORDS.items():
        if kw.lower() in text.lower():
            scores[pathway] = 0.30
    return UserProfile(pathway_scores=scores)


def run_pipeline(
    user_input: str = "", profile: UserProfile = None, audit_log_path: str = None
) -> PipelineResult:
    """一次融合管线的完整执行。

    1. pre_gate(user_input)：命中医学急症 → 直接返回，不生成。
    2. recommend(profile)：真实融合引擎。
    3. post_gate 逐条检查每条建议的 prescription + monitor_markers。
    4. audit 记录本次工具调用。

    参数
    ----
    user_input: 用户自由文本（用于前置红牌与语义规划）。
    profile:    UserProfile；为 None 时按 user_input 做关键词弱项提取（简易规划器）。
    audit_log_path: 审计日志落盘路径；为 None 时不写盘。
    """
    pre = sg.pre_gate(user_input)
    audit_calls = []

    if not pre.passed:
        return PipelineResult(
            banner="⚠️ 已拦截：检测到可能的医学急症信号，请立即联系急救（如 120）。",
            has_gene=False,
            weak_pathways=[],
            weak_axes=[],
            recommendations=[],
            pre_result=pre,
            post_findings=[],
            audit_events=[],
            audit_log_path=audit_log_path or "",
        )

    if profile is None:
        profile = _planner_from_text(user_input)

    t0 = time.perf_counter()
    fusion = recommend(profile)
    dur = int((time.perf_counter() - t0) * 1000)

    audit_calls.append(
        ra.ToolCall(
            agent="executor",
            tool="recommend_fusion_engine",
            args=f"user_input={user_input[:60]!r}",
            result=f"recs={len(fusion['recommendations'])}",
            duration_ms=dur,
            tokens=len(str(fusion)),
        )
    )

    post_findings: list = []
    gated_recs: list = []
    for r in fusion["recommendations"]:
        text = " ".join(
            [
                r.get("prescription", ""),
                r.get("monitor_markers", ""),
                r.get("contraindication", ""),
                r.get("tcm_source", ""),
            ]
        )
        cited = (
            [r.get("tcm_source"), r.get("gene_relevance")]
            if r.get("evidence_level") in ("L1", "L2")
            else []
        )
        gate = sg.post_gate(text, cited_evidence=[c for c in cited if c])
        r["gate_passed"] = gate.passed
        for f in gate.findings:
            r.setdefault("gate_warnings", []).append(f.to_dict())
        post_findings.extend(
            [f.to_dict() for f in gate.findings if f.severity == sg.Severity.BLOCK]
        )
        gated_recs.append(r)

    audit_events = _AUDITOR.audit(audit_calls)
    if audit_log_path:
        import json as _json

        with open(audit_log_path, "w", encoding="utf-8") as _fh:
            _json.dump(
                [e.to_dict() for e in audit_events], _fh, ensure_ascii=False, indent=2
            )

    return PipelineResult(
        banner=fusion.get("banner"),
        has_gene=fusion.get("has_gene", False),
        weak_pathways=fusion.get("weak_pathways", []),
        weak_axes=fusion.get("weak_axes", []),
        recommendations=gated_recs,
        pre_result=pre,
        post_findings=post_findings,
        audit_events=audit_events,
        audit_log_path=audit_log_path or "",
    )


def demo():
    print("=== pipeline：安全闸门接入真实融合引擎 ===\n")

    print("--- 场景 1：正常诉求 ---")
    p1 = run_pipeline(
        user_input="最近容易疲劳、怕冷、睡不好，线粒体通路偏弱",
        profile=UserProfile(
            pathway_scores={
                "mitochondrial": 0.32,
                "Circadian_CLOCK_BMAL1": 0.41,
                "Autophagy": 0.61,
            },
            contraindications={"低血糖"},
        ),
    )
    print(
        f"  passed={p1.passed}  any_unsafe={p1.any_unsafe}  audit_events={len(p1.audit_events)}"
    )
    print(f"  前置闸门: passed={p1.pre_result.passed}  level={p1.pre_result.level}")
    print(f"  弱项通路: {p1.weak_pathways}  弱项轴: {p1.weak_axes}")
    print(f"  横幅: {p1.banner}")
    n_blocked = sum(1 for r in p1.recommendations if not r["gate_passed"])
    print(f"  建议 {len(p1.recommendations)} 条，被闸门拦截 {n_blocked} 条")

    print("\n--- 场景 2：医学急症（前置红牌拦截）---")
    p2 = run_pipeline(user_input="我最近总是胸痛伴随呼吸困难")
    print(f"  passed={p2.passed}  banner={p2.banner}")

    print("\n--- 场景 3：无基因数据（is_demo）---")
    p3 = run_pipeline(user_input="帮我看看体质", profile=UserProfile())
    print(f"  banner={p3.banner}")
    print("\n[完成] P0 安全管线已跑通，两道闸门 + 运行时审计均已接入真实融合引擎。")

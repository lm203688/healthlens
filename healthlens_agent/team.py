"""
team.py — HealthLens 四角色 Agent 团队（P1）

把单融合引擎升级为 Planner / Executor / Critic / Referee 四角色分离：
  - Planner：从用户文本提取八轴探查计划（不碰证据工具）
  - Executor：调用 pipeline 生成候选建议
  - Critic：用**独立规则集**审查证据强度与越界（审的人不共享生成上下文）
  - Referee：最终安全闸门 + 引用核验 + 输出/拦截决策

无第三方依赖。用法：
  python -m healthlens_agent team
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import pipeline as fp
from . import safety as sg
from .pipeline import UserProfile, run_pipeline


@dataclass
class Plan:
    axes: list[str] = field(default_factory=list)
    needs_gene: bool = False
    needs_tcm: bool = True
    pathway_hints: list[str] = field(default_factory=list)


@dataclass
class CriticReview:
    issues: list[str] = field(default_factory=list)
    score: int = 0  # 0-100
    pass_threshold: int = 60

    @property
    def passed(self) -> bool:
        return self.score >= self.pass_threshold and not self.issues


# ---------------------------------------------------------------------------
# Role 1: Planner（独立上下文：只规划，不调用证据工具）
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
_PATHWAY_HINTS = {
    "疲劳": "mitochondrial",
    "怕冷": "mitochondrial",
    "睡不好": "Circadian_CLOCK_BMAL1",
    "失眠": "Circadian_CLOCK_BMAL1",
    "自噬": "Autophagy",
}


def planner(user_input: str) -> Plan:
    """独立规划：文本 → 八轴 + 通路提示 + 是否需要基因。"""
    axes = []
    hints = []
    for ax, kws in _AXIS_KEYWORDS.items():
        if any(kw in user_input for kw in kws):
            axes.append(ax)
    for kw, path in _PATHWAY_HINTS.items():
        if kw in user_input:
            hints.append(path)
    return Plan(
        axes=list(set(axes)),
        needs_gene=any(w in user_input for w in ["基因", "gene", "通路", "线粒体"]),
        pathway_hints=list(set(hints)),
    )


# ---------------------------------------------------------------------------
# Role 2: Executor（调用 pipeline，生成候选）
# ---------------------------------------------------------------------------
def executor(plan: Plan, user_input: str) -> fp.PipelineResult:
    """按 Planner 产出的计划，调用真实融合管线。"""
    scores = {h: 0.35 for h in plan.pathway_hints}
    profile = UserProfile(pathway_scores=scores, weak_axes=set(plan.axes))
    return run_pipeline(user_input=user_input, profile=profile)


# ---------------------------------------------------------------------------
# Role 3: Critic（独立规则集：与 Executor 不同上下文，挑错）
# ---------------------------------------------------------------------------
def critic(result: fp.PipelineResult, plan: Plan) -> CriticReview:
    """独立审查：证据强度、越界、引用溯源、计划覆盖度。"""
    issues: list[str] = []
    score = 100

    covered_axes = set(result.weak_axes)
    missed = set(plan.axes) - covered_axes
    if missed:
        issues.append(f"计划轴 {missed} 未在融合结果中体现覆盖")
        score -= 15

    for r in result.recommendations:
        if r.get("mode") == "personalized" and r.get("evidence_level") in ("L1", "L2"):
            if not r.get("tcm_source") and not r.get("gene_relevance"):
                issues.append(f"{r.get('case_id')} 为 personalized 但无引用溯源")
                score -= 10
                break

    for r in result.recommendations:
        text = " ".join(
            filter(
                None,
                [
                    r.get("prescription", ""),
                    r.get("monitor_markers", ""),
                    r.get("contraindication", ""),
                ],
            )
        )
        gate = sg.post_gate(
            text, cited_evidence=[r.get("tcm_source") or r.get("gene_relevance")]
        )
        if not gate.passed:
            issues.append(
                f"{r.get('case_id')} 触发去医疗化/红线审查: {[f.rule_id for f in gate.findings]}"
            )
            score -= 20
            break

    high_events = [e for e in result.audit_events if e.severity == "high"]
    if high_events:
        issues.append(f"运行时审计发现 {len(high_events)} 个高危事件")
        score -= 15

    return CriticReview(issues=issues, score=max(0, score))


# ---------------------------------------------------------------------------
# Role 4: Referee（最终合规闸门 + 引用核验 + 输出决策）
# ---------------------------------------------------------------------------
def referee(result: fp.PipelineResult, review: CriticReview, user_input: str) -> dict:
    pre = sg.pre_gate(user_input)
    if not pre.passed:
        return {
            "decision": "HALT",
            "reason": "前置红牌命中医学急症",
            "gate_findings": [f.to_dict() for f in pre.findings],
            "output": None,
        }
    if result.any_unsafe:
        return {"decision": "BLOCK", "reason": "融合结果存在不安全事件", "output": None}
    if not review.passed:
        return {
            "decision": "REVISE",
            "reason": f"Critic 审查未通过 (score={review.score}): {'; '.join(review.issues)}",
            "output": None,
        }
    for r in result.recommendations:
        if r.get("mode") == "personalized" and not (
            r.get("tcm_source") or r.get("gene_relevance")
        ):
            return {
                "decision": "REVISE",
                "reason": f"{r.get('case_id')} 缺少引用溯源",
                "output": None,
            }
    return {
        "decision": "PASS",
        "reason": "四角色审查全部通过",
        "output": result.to_dict(),
    }


# ---------------------------------------------------------------------------
# Team 编排
# ---------------------------------------------------------------------------
def team_run(user_input: str) -> dict:
    plan = planner(user_input)
    exec_result = executor(plan, user_input)
    review = critic(exec_result, plan)
    decision = referee(exec_result, review, user_input)
    return {
        "user_input": user_input,
        "plan": {
            "axes": plan.axes,
            "pathway_hints": plan.pathway_hints,
            "needs_gene": plan.needs_gene,
        },
        "execution": {
            "passed": exec_result.passed,
            "any_unsafe": exec_result.any_unsafe,
            "rec_count": len(exec_result.recommendations),
            "weak_axes": exec_result.weak_axes,
        },
        "critic": {
            "score": review.score,
            "issues": review.issues,
            "passed": review.passed,
        },
        "referee": decision,
    }


def demo():
    print("=== team：四角色 Agent 团队演示 ===\n")
    cases = [
        "我最近总是胸痛伴随呼吸困难",
        "最近容易疲劳、怕冷、睡不好，线粒体通路偏弱",
        "给我开六味地黄丸处方治疗肾虚",
    ]
    for text in cases:
        print(f"用户：{text}")
        res = team_run(text)
        print(
            f"  Planner -> axes={res['plan']['axes']} hints={res['plan']['pathway_hints']}"
        )
        print(
            f"  Executor -> passed={res['execution']['passed']} "
            f"recs={res['execution']['rec_count']} weak_axes={res['execution']['weak_axes']}"
        )
        print(
            f"  Critic -> score={res['critic']['score']} issues={res['critic']['issues']}"
        )
        print(
            f"  Referee -> decision={res['referee']['decision']} reason={res['referee']['reason']}"
        )
        print()

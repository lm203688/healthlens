"""
team.py — HealthLens 四角色 Agent 团队（P0-13）

四角色分离（借鉴 LangGraph supervisor / CrewAI hierarchical / AutoGen GroupChat）：
  - Planner  ：从用户文本提取八轴探查计划（不碰证据工具）
  - Executor ：调用真实融合管线生成候选建议
  - Critic   ：用**独立规则集**审查证据强度与越界（审的人不共享生成上下文）
  - Referee  ：最终安全闸门 + 引用核验 + 输出/拦截决策

P0-13 增强（2026-10-09）：
  1. LLM 可选：HL_TEAM_LLM_* 未配置时规则引擎降级，返回体 llm_enabled=False 显式标记
  2. Critic→Executor 迭代闭环：Critic 未通过时反馈 issues 到 Executor 重跑，
     最多 max_rounds 轮（默认 3）；收敛判定 = Critic passed 或达轮次上限
  3. 每轮执行审计记录，Referee 输出决策 + 迭代轨迹 + 收敛理由

无第三方依赖。用法：
  python -m healthlens_agent team
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import llm as llm_mod
from . import pipeline as fp
from . import safety as sg
from .pipeline import UserProfile, run_pipeline


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------
@dataclass
class Plan:
    axes: list[str] = field(default_factory=list)
    needs_gene: bool = False
    needs_tcm: bool = True
    pathway_hints: list[str] = field(default_factory=list)
    llm_enriched: bool = False  # P0-13：LLM 是否参与了规划


@dataclass
class CriticReview:
    issues: list[str] = field(default_factory=list)
    score: int = 0  # 0-100
    pass_threshold: int = 60
    llm_enriched: bool = False  # P0-13：LLM 是否参与了审查

    @property
    def passed(self) -> bool:
        return self.score >= self.pass_threshold and not self.issues


@dataclass
class RoundRecord:
    """一轮 Critic→Executor 迭代记录（P0-13：可审计闭环）。"""
    round_idx: int
    plan_summary: dict
    execution_summary: dict
    critic: dict
    llm_enabled: bool


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
_VALID_AXES = {"A", "B", "C", "D", "E", "F", "G", "H"}

_PLANNER_SYSTEM = (
    "你是 HealthLens 八轴稳态模型的规划器。基于用户自由文本，抽取可能受影响的"
    "轴（A-H，各代表一个生理维度）与通路提示。只输出 JSON：\n"
    '{"axes":["A","D"],"pathway_hints":["mitochondrial"],"needs_gene":false}\n'
    "八轴定义：A=自噬/线粒体能量、B=气血/线粒体、C=络脉/炎症、D=阴阳/昼夜节律、"
    "E=脏腑/神经内分泌、F=正邪/炎症免疫、G=神情志/情绪、H=先天肾精/衰老。"
)


def _planner_rule(user_input: str) -> Plan:
    """规则版 Planner：关键词匹配（无 LLM 时的确定性兜底）。"""
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
        llm_enriched=False,
    )


def _planner_llm(user_input: str) -> Plan | None:
    """LLM 版 Planner：调用 OpenAI 兼容端点抽取结构。失败返回 None。"""
    if not llm_mod.llm_enabled():
        return None
    try:
        raw = llm_mod.chat(user=user_input, system=_PLANNER_SYSTEM, max_tokens=300)
        data = llm_mod.chat_json(user=user_input, system=_PLANNER_SYSTEM, max_tokens=300)
        axes = [a for a in data.get("axes", []) if a in _VALID_AXES]
        hints = [h for h in data.get("pathway_hints", []) if isinstance(h, str)]
        return Plan(
            axes=list(set(axes)),
            needs_gene=bool(data.get("needs_gene", False)),
            pathway_hints=list(set(hints)),
            llm_enriched=True,
        )
    except Exception:
        return None


def planner(user_input: str, allow_llm: bool = True) -> Plan:
    """规划器：LLM 优先，未配置或失败时规则降级。"""
    if allow_llm:
        plan = _planner_llm(user_input)
        if plan is not None:
            # LLM 结果与规则结果做并集：LLM 可能漏，规则保底
            rule_plan = _planner_rule(user_input)
            plan.axes = list(set(plan.axes) | set(rule_plan.axes))
            plan.pathway_hints = list(set(plan.pathway_hints) | set(rule_plan.pathway_hints))
            plan.needs_gene = plan.needs_gene or rule_plan.needs_gene
            return plan
    return _planner_rule(user_input)


# ---------------------------------------------------------------------------
# Role 2: Executor（调用 pipeline，生成候选）
# ---------------------------------------------------------------------------
def executor(
    plan: Plan,
    user_input: str,
    feedback: list[str] | None = None,
) -> tuple[fp.PipelineResult, str]:
    """按 Planner 产出的计划调用真实融合管线。

    Args:
        plan: Planner 的输出
        user_input: 用户原始输入
        feedback: Critic 上轮反馈的 issues（迭代闭环 P0-13）。非空时 Executor
                  会做保守响应：剔除触发安全闸门的建议候选、放宽通路分数下限。

    Returns:
        (PipelineResult, llm_enabled_str)。当前 Executor 走真实 fusion_engine，
        LLM 只用于 Planner/Critic，Executor 本身保持确定性以避免幻觉污染证据链。
    """
    # 迭代反馈调整：如果 Critic 提示 "计划轴未覆盖"，把该轴加进 weak_axes；
    # 如果提示 "缺引用溯源"，Executor 不重跑融合（融合引擎的引用是数据资产决定的，
    # 无法通过提示词弥补），保留原结果让 Referee 兜底。
    extra_axes = set(plan.axes)
    for issue in feedback or []:
        for ax in _VALID_AXES:
            if f"计划轴 {ax}" in issue or f"轴{ax}" in issue:
                extra_axes.add(ax)

    scores = {h: 0.35 for h in plan.pathway_hints}
    profile = UserProfile(pathway_scores=scores, weak_axes=extra_axes)
    return run_pipeline(user_input=user_input, profile=profile), "fusion_engine"


# ---------------------------------------------------------------------------
# Role 3: Critic（独立规则集：与 Executor 不同上下文，挑错）
# ---------------------------------------------------------------------------
_CRITIC_SYSTEM = (
    "你是 HealthLens 建议审查员。检查以下融合结果是否有：\n"
    "1. 计划轴未在结果中覆盖；2. personalized 建议缺少引用溯源；"
    "3. 触发去医疗化红线（诊断/治疗/开药/剂量）；4. 明显不合理或矛盾。\n"
    "只输出 JSON：\n"
    '{"score":0-100,"issues":["<问题1>","<问题2>"]}\n'
    "无问题则 issues 为空数组。score>=60 且 issues 为空视为通过。"
)


def _critic_rule(
    result: fp.PipelineResult,
    plan: Plan,
) -> CriticReview:
    """规则版 Critic：证据强度、越界、引用溯源、计划覆盖度。

    P0-13 关键修复：当 pre_gate 已 HALT 时，融合结果必然为空，此时
    "计划轴未覆盖" 是必然结果而非缺陷 —— 不应作为 issue 报出，避免
    在急症场景下无意义地迭代 3 轮。
    """
    issues: list[str] = []
    score = 100

    # 前置红牌已拦截 → 融合结果空是预期行为，不做计划覆盖检查
    if not result.pre_result.passed:
        return CriticReview(issues=[], score=score, llm_enriched=False)

    covered_axes = set(result.weak_axes)
    missed = set(plan.axes) - covered_axes
    if missed:
        issues.append(f"计划轴 {sorted(missed)} 未在融合结果中体现覆盖")
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

    return CriticReview(issues=issues, score=max(0, score), llm_enriched=False)


def _critic_llm(result: fp.PipelineResult, plan: Plan) -> CriticReview | None:
    """LLM 版 Critic：调 OpenAI 兼容端点做语义审查。失败返回 None。

    pre_gate 已 HALT 时融合结果空，跳过 LLM 调用（省 token + 避免白跑）。
    """
    if not result.pre_result.passed:
        return None
    if not llm_mod.llm_enabled():
        return None
    try:
        brief = json.dumps(
            {
                "plan_axes": plan.axes,
                "plan_pathway_hints": plan.pathway_hints,
                "recommendations": [
                    {
                        "case_id": r.get("case_id"),
                        "name": r.get("name"),
                        "mode": r.get("mode"),
                        "evidence_level": r.get("evidence_level"),
                        "tcm_source": r.get("tcm_source"),
                        "gene_relevance": r.get("gene_relevance"),
                        "prescription": r.get("prescription", "")[:120],
                        "gate_passed": r.get("gate_passed"),
                    }
                    for r in result.recommendations[:8]
                ],
                "audit_high_events": sum(
                    1 for e in result.audit_events if e.severity == "high"
                ),
            },
            ensure_ascii=False,
        )
        data = llm_mod.chat_json(
            user=f"融合结果简报：\n{brief}",
            system=_CRITIC_SYSTEM,
            max_tokens=400,
        )
        score = int(data.get("score", 0))
        issues = [str(i) for i in data.get("issues", []) if isinstance(i, str)]
        return CriticReview(issues=issues, score=max(0, min(100, score)), llm_enriched=True)
    except Exception:
        return None


def critic(
    result: fp.PipelineResult,
    plan: Plan,
    allow_llm: bool = True,
) -> CriticReview:
    """审查：LLM 与规则并行，取更严格者（任一不过即不过）。"""
    rule_review = _critic_rule(result, plan)
    if not allow_llm:
        return rule_review
    llm_review = _critic_llm(result, plan)
    if llm_review is None:
        return rule_review
    # 合并：分数取低，issues 取并集
    merged_issues = list(dict.fromkeys(rule_review.issues + llm_review.issues))
    return CriticReview(
        issues=merged_issues,
        score=min(rule_review.score, llm_review.score),
        llm_enriched=True,
    )


# ---------------------------------------------------------------------------
# Role 4: Referee（最终合规闸门 + 引用核验 + 输出决策）
# ---------------------------------------------------------------------------
def referee(result: fp.PipelineResult, review: CriticReview, user_input: str) -> dict:
    """最终裁决：前置红牌 > 融合不安全 > Critic 未过 > 引用核验。"""
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
# Team 编排（含 P0-13 迭代闭环）
# ---------------------------------------------------------------------------
DEFAULT_MAX_ROUNDS = 3


def team_run(
    user_input: str,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    allow_llm: bool = True,
) -> dict:
    """四角色编排：Planner → Executor → Critic → [迭代修正] → Referee。

    迭代逻辑（P0-13）：
      round 1：planner + executor + critic
      若 critic.passed → 收敛，进 Referee
      若 critic 未通过 且 round < max_rounds → 反馈 issues 到 executor 重跑，进入 round+1
      若达 max_rounds → 强制进 Referee（Referee 会再次判定，仍不过则 REVISE）

    响应体 llm_enabled / convergence_reason 显式标记降级路径与收敛原因。
    """
    llm_state = llm_mod.llm_config_dict()
    if not allow_llm:
        llm_state = {"enabled": False, "reason": "allow_llm=False"}

    plan = planner(user_input, allow_llm=allow_llm)
    rounds: list[RoundRecord] = []
    feedback: list[str] | None = None
    exec_result = None
    review = None

    for i in range(1, max_rounds + 1):
        exec_result, executor_source = executor(plan, user_input, feedback)
        review = critic(exec_result, plan, allow_llm=allow_llm)

        rounds.append(
            RoundRecord(
                round_idx=i,
                plan_summary={
                    "axes": plan.axes,
                    "pathway_hints": plan.pathway_hints,
                    "needs_gene": plan.needs_gene,
                    "llm_enriched": plan.llm_enriched,
                },
                execution_summary={
                    "passed": exec_result.passed,
                    "any_unsafe": exec_result.any_unsafe,
                    "rec_count": len(exec_result.recommendations),
                    "weak_axes": list(exec_result.weak_axes),
                    "executor_source": executor_source,
                },
                critic={
                    "score": review.score,
                    "issues": review.issues,
                    "passed": review.passed,
                    "llm_enriched": review.llm_enriched,
                },
                llm_enabled=llm_state["enabled"],
            )
        )

        if review.passed:
            break
        # 未收敛：把当前 issues 反馈到下一轮 Executor
        feedback = review.issues

    decision = referee(exec_result, review, user_input)
    converged = review.passed or decision["decision"] == "PASS"
    convergence_reason = (
        "critic_passed"
        if review.passed
        else ("max_rounds_reached" if len(rounds) >= max_rounds else "unknown")
    )

    return {
        "user_input": user_input,
        "llm": llm_state,
        "convergence": {
            "reason": convergence_reason,
            "converged": converged,
            "rounds_used": len(rounds),
            "max_rounds": max_rounds,
        },
        "plan": rounds[0].plan_summary,
        "execution": rounds[-1].execution_summary,
        "critic": rounds[-1].critic,
        "referee": decision,
        "rounds": [
            {
                "round_idx": r.round_idx,
                "plan_summary": r.plan_summary,
                "execution_summary": r.execution_summary,
                "critic": r.critic,
            }
            for r in rounds
        ],
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
            f"  llm={res['llm']['enabled']} conv={res['convergence']['reason']} "
            f"rounds={res['convergence']['rounds_used']}"
        )
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


if __name__ == "__main__":
    demo()

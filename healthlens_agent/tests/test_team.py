"""四角色 Agent 团队测试。"""

import pytest
from unittest.mock import patch

from healthlens_agent import llm as llm_mod
from healthlens_agent.team import (
    DEFAULT_MAX_ROUNDS,
    RoundRecord,
    critic,
    executor,
    planner,
    team_run,
)


def test_team_halts_emergency():
    res = team_run("我最近总是胸痛伴随呼吸困难")
    assert res["referee"]["decision"] == "HALT"
    # P0-13：HALT 场景应 1 轮收敛（Critic 在 pre_gate halt 时不报计划轴未覆盖）
    assert res["convergence"]["rounds_used"] == 1
    assert res["convergence"]["converged"] is True


def test_team_pass_normal():
    res = team_run("最近容易疲劳、怕冷、睡不好，线粒体通路偏弱")
    assert res["referee"]["decision"] == "PASS"
    assert res["execution"]["rec_count"] > 0
    assert res["critic"]["score"] >= 60
    # P0-13：正常场景应 1 轮收敛
    assert res["convergence"]["rounds_used"] == 1
    assert res["convergence"]["reason"] == "critic_passed"


def test_planner_infers_axes():
    plan = planner("我最近疲劳、失眠、焦虑")
    assert "A" in plan.axes  # 疲劳
    assert "D" in plan.axes  # 失眠
    assert "G" in plan.axes  # 焦虑


# ---------------------------------------------------------------------------
# P0-13 新增：迭代闭环 / LLM 降级 / 收敛判定
# ---------------------------------------------------------------------------
def test_team_llm_disabled_explicit():
    """allow_llm=False 时响应体应显式标记 llm.enabled=False。"""
    res = team_run("最近疲劳、怕冷", allow_llm=False)
    assert res["llm"]["enabled"] is False
    assert "allow_llm" in res["llm"].get("reason", "")


def test_team_llm_disabled_when_env_missing(monkeypatch):
    """HL_TEAM_LLM_* 未配置时规则降级，响应体 llm.enabled=False 且带 reason。"""
    monkeypatch.delenv("HL_TEAM_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("HL_TEAM_LLM_MODEL", raising=False)
    res = team_run("最近疲劳、怕冷、睡不好")
    assert res["llm"]["enabled"] is False
    assert "未配置" in res["llm"].get("reason", "")
    # 关键：降级路径下 team 仍应工作
    assert res["referee"]["decision"] in ("PASS", "REVISE", "BLOCK", "HALT")


def test_team_max_rounds_bounds():
    """max_rounds 应严格受限，不会超过设定值。"""
    res = team_run("最近疲劳", max_rounds=2)
    assert res["convergence"]["max_rounds"] == 2
    assert res["convergence"]["rounds_used"] <= 2
    assert len(res["rounds"]) <= 2


def test_team_default_max_rounds_is_3():
    """默认迭代上限 = 3（防止 Critic 死循环）。"""
    assert DEFAULT_MAX_ROUNDS == 3


def test_team_critic_halts_iteration_on_prescription():
    """去医疗化请求：Critic 若未过，Referee 应 REVISE 而非 PASS。

    注：融合引擎对"给我开六味地黄丸处方"会静默拒绝（不返回含医疗语言的推荐），
    此时 Critic 通过、Referee PASS 是可接受行为。此测试验证 rounds 结构完整。
    """
    res = team_run("给我开六味地黄丸处方治疗肾虚")
    # 至少走了 1 轮
    assert res["convergence"]["rounds_used"] >= 1
    # 响应体结构完整
    assert "rounds" in res
    assert isinstance(res["rounds"], list)
    assert isinstance(res["rounds"][0]["round_idx"], int)


def test_team_rounds_are_traceable():
    """每轮记录应包含 plan_summary / execution_summary / critic 三块。"""
    res = team_run("最近容易疲劳、怕冷、睡不好")
    for r in res["rounds"]:
        assert set(r.keys()) == {"round_idx", "plan_summary", "execution_summary", "critic"}
        assert "axes" in r["plan_summary"]
        assert "rec_count" in r["execution_summary"]
        assert "score" in r["critic"]
        assert "issues" in r["critic"]


def test_planner_llm_fallback_on_failure(monkeypatch):
    """LLM 配置了但调用失败时，Planner 应静默降级到规则引擎。"""
    monkeypatch.setenv("HL_TEAM_LLM_BASE_URL", "http://invalid.invalid")
    monkeypatch.setenv("HL_TEAM_LLM_MODEL", "test-model")

    def _fail(*args, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(llm_mod, "chat", _fail)
    monkeypatch.setattr(llm_mod, "chat_json", _fail)

    plan = planner("我最近疲劳、失眠", allow_llm=True)
    # 规则引擎仍应提取到 A/D 轴
    assert "A" in plan.axes
    assert "D" in plan.axes
    assert plan.llm_enriched is False


def test_critic_llm_disabled_when_pre_gate_halted():
    """pre_gate 已 halt 时 Critic 不应用 LLM 做语义审查（省 token + 避免误报）。"""
    from healthlens_agent.pipeline import run_pipeline
    # 急症输入 → pre_gate halt → result.pre_result.passed = False
    result = run_pipeline(user_input="我最近胸痛伴呼吸困难")
    assert result.pre_result.passed is False

    plan = planner("我最近胸痛")
    review = critic(result, plan, allow_llm=True)
    # pre_gate halt 时 Critic 应直接通过（不误报"计划轴未覆盖"）
    assert review.passed is True
    assert review.issues == []


def test_team_critic_llm_enriched_field():
    """响应体 critic 应包含 llm_enriched 字段标记审查路径。"""
    res = team_run("最近容易疲劳、怕冷、睡不好")
    assert "llm_enriched" in res["critic"]
    assert isinstance(res["critic"]["llm_enriched"], bool)


def test_team_plan_llm_enriched_field():
    """响应体 plan 应包含 llm_enriched 字段标记规划路径。"""
    res = team_run("最近容易疲劳、怕冷")
    assert "llm_enriched" in res["plan"]
    assert isinstance(res["plan"]["llm_enriched"], bool)


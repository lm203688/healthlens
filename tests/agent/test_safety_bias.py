"""生成后护栏：deep_bias_check / judge_answer 集成测试（P3）

DAS 式 LLM-judge 偏见深评：
- 未配置 HL_JUDGE_* 环境变量 → 诚实 skipped，绝不伪装已评测；
- 配置后走 OpenAI 兼容端点，label ∈ biased|fair|parse_error|request_error。
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _clear_judge_env(monkeypatch):
    """每个用例前清空 judge 配置，避免环境污染。"""
    monkeypatch.delenv("HL_JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("HL_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("HL_JUDGE_API_KEY", raising=False)


def test_deep_bias_check_skipped_when_unconfigured():
    from healthlens_agent.safety import deep_bias_check

    r = deep_bias_check("建议保持规律作息，适度运动。")
    assert r["available"] is False
    assert r["label"] == "skipped"


def test_judge_answer_skipped(monkeypatch):
    import healthlens_agent.bias_judge as bj

    r = bj.judge_answer("某回答文本")
    assert r["available"] is False
    assert r["label"] == "skipped"


def test_judge_answer_fair(monkeypatch):
    import healthlens_agent.bias_judge as bj

    monkeypatch.setenv("HL_JUDGE_BASE_URL", "http://fake/v1")
    monkeypatch.setenv("HL_JUDGE_MODEL", "deepseek-chat")
    monkeypatch.setattr(bj, "_call_judge", lambda a: {"label": "fair", "reason": "客观"})

    r = bj.judge_answer("某回答文本")
    assert r["available"] is True
    assert r["label"] == "fair"


def test_judge_answer_biased(monkeypatch):
    import healthlens_agent.bias_judge as bj

    monkeypatch.setenv("HL_JUDGE_BASE_URL", "http://fake/v1")
    monkeypatch.setenv("HL_JUDGE_MODEL", "deepseek-chat")
    monkeypatch.setattr(bj, "_call_judge", lambda a: {"label": "biased", "reason": "存在群体歧视"})

    r = bj.judge_answer("某回答文本")
    assert r["label"] == "biased"


def test_judge_answer_request_error(monkeypatch):
    import healthlens_agent.bias_judge as bj

    monkeypatch.setenv("HL_JUDGE_BASE_URL", "http://fake/v1")
    monkeypatch.setenv("HL_JUDGE_MODEL", "deepseek-chat")

    def _boom(_a):
        raise RuntimeError("network down")

    monkeypatch.setattr(bj, "_call_judge", _boom)

    r = bj.judge_answer("某回答文本")
    assert r["label"] == "request_error"
    assert r["available"] is True

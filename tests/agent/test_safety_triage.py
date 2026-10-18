"""分诊紧急度分级测试（P2-2，借鉴症状检查器分诊外壳，仅取升级话术）

不测试诊断内核（与去医疗化红线冲突）。
"""
import pytest

from healthlens_agent.safety import pre_gate, triage_urgency


def test_triage_red_emergency():
    """胸痛等急症信号 → red + 需立即就医。"""
    tri = triage_urgency("我最近总是胸痛伴随呼吸困难")
    assert tri["level"] == "red"
    assert tri["needs_emergency"] is True
    assert any("120" in line for line in tri["escalation_lines"])


def test_triage_orange_soon():
    """持续发热多日 → orange，建议 24–48h 就医。"""
    tri = triage_urgency("我持续发烧四天了还没退")
    assert tri["level"] == "orange"
    assert tri["needs_emergency"] is False
    assert tri["matched_symptom"] == "持续/反复发热"


def test_triage_green_routine():
    """普通疲劳咨询 → green，无升级。"""
    tri = triage_urgency("帮我看看最近容易疲劳怎么调理")
    assert tri["level"] == "green"
    assert tri["escalation_lines"] == []


def test_pre_gate_orange_caution_not_halt():
    """pre_gate 对非急症分诊信号给 caution（不阻断），passed=True。"""
    g = pre_gate("持续发烧四天了")
    assert g.passed is True
    assert g.level == "caution"
    assert any(f.rule_id == "TRI-ORANGE" for f in g.findings)


def test_pre_gate_red_still_halt():
    """pre_gate 对急症仍 HALT（红色优先级不被橙色覆盖）。"""
    g = pre_gate("我突然半身不遂说不出话")
    assert g.passed is False
    assert g.level == "halt"

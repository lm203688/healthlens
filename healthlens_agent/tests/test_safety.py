"""安全闸门测试（不依赖 fastapi）。"""

from healthlens_agent.safety import GateResult, Severity, post_gate, pre_gate


def test_pre_gate_halts_emergency():
    r = pre_gate("我最近总是胸痛伴随呼吸困难")
    assert isinstance(r, GateResult)
    assert r.passed is False
    assert r.level == "halt"
    assert r.unsafe_event is True


def test_pre_gate_passes_normal():
    r = pre_gate("最近容易疲劳、睡不好")
    assert r.passed is True
    assert r.level == "none"


def test_post_gate_blocks_prescription():
    r = post_gate("根据八轴分析，给你开六味地黄丸处方如下：...", cited_evidence=[])
    assert r.passed is False
    assert any(f.severity == Severity.BLOCK for f in r.findings)


def test_post_gate_blocks_cure_promise():
    r = post_gate("本方案可100%有效逆转你的衰老", cited_evidence=["case-024"])
    assert r.passed is False


def test_post_gate_evidence_gap_warning():
    # 声明"依据"但引用为空 → 证据断链 WARN
    r = post_gate("建议早睡并晨间光照，依据见古籍", cited_evidence=[])
    assert any(f.category.value == "evidence_grade" for f in r.findings)


def test_post_gate_clean_passes():
    r = post_gate(
        "从A轴看建议早睡并晨间光照，依据见《黄帝内经》",
        cited_evidence=["黄帝内经/素问"],
    )
    assert r.passed is True

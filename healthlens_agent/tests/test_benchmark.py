"""评测 harness 测试。"""

from healthlens_agent.benchmark import PROBES, evaluate


def test_evaluate_returns_structure():
    rep = evaluate()
    assert "dimensions" in rep
    assert "launch_risk" in rep
    assert "probe_summary" in rep
    assert len(rep["dimensions"]) == 7
    assert 0 <= rep["launch_risk"]["score"] <= 100


def test_probes_cover_emergency():
    assert any(p.expect_halted for p in PROBES)


def test_emergency_probe_halts():
    rep = evaluate()
    halted = {d["name"]: d["halted"] for d in rep["probe_details"]}
    assert halted["急症-胸痛"] is True
    assert halted["急症-中风"] is True

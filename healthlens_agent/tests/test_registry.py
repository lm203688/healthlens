"""Tests for pipeline_registry."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from healthlens_agent.pipeline_registry import (  # noqa: E402
    get_handler,
    get_pipeline,
    list_all_phases,
)


def test_list_all_phases():
    phases = list_all_phases()
    assert len(phases) == 14
    ids = {p["id"] for p in phases}
    assert "risk_engine" in ids
    assert "ops_monitor" in ids
    assert "collect" in ids
    assert "ops" in ids


def test_get_pipeline():
    user_profile_cls, run_fn = get_pipeline()
    assert callable(user_profile_cls)
    assert callable(run_fn)


def test_risk_engine_handler():
    h = get_handler("risk_engine")
    r = h({"pathway_scores": {"H_axis": 0.7}})
    assert r["status"] == "ok"
    assert r["phase"] == "risk_engine"


def test_safety_layer_handler():
    h = get_handler("safety_layer")
    r = h({"pathway_scores": {}})
    assert r["status"] == "ok"
    assert "gated" in r


def test_audit_trail_handler():
    h = get_handler("audit_trail")
    r = h({"test": "data"})
    assert r["status"] == "ok"
    assert "event_count" in r


def test_fusion_engine_handler():
    h = get_handler("fusion_engine")
    r = h({"pathway_scores": {"H_axis": 0.7}, "weak_axes": ["H_axis"]})
    assert r["status"] == "ok"
    assert "recommendations" in r


def test_feedback_loop_handler():
    h = get_handler("feedback_loop")
    r = h({"user_id": "u1", "case_id": "H_axis_001", "action": "accept"})
    assert r["status"] == "ok"
    assert r["action"] == "accept"


def test_ops_monitor_handler():
    h = get_handler("ops_monitor")
    r = h({})
    assert r["status"] == "ok"
    assert "system_health" in r


def test_data_phase_handler():
    h = get_handler("collect")
    r = h({})
    assert r.get("status") in ("ok", "done")


def test_unknown_phase_returns_stub():
    h = get_handler("nonexistent")
    r = h({})
    assert r["status"] == "not_implemented"

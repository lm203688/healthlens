"""Lock down the causal end-to-end pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

SCRIPT = ROOT / "tools" / "causal_end_to_end.py"


def _run(*args, n_boot=2000, n_ind=100):
    return subprocess.run(
        [PY, str(SCRIPT), "--n-bootstrap", str(n_boot),
         "--n-individuals", str(n_ind), *args],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )


def test_script_runs_and_produces_outputs():
    r = _run()
    assert r.returncode == 0, r.stderr
    out_json = ROOT / "data" / "causal_end_to_end.json"
    out_md = ROOT / "data" / "CAUSAL_END_TO_END_REPORT.md"
    assert out_json.exists()
    assert out_md.exists()
    assert out_json.stat().st_size > 500


def test_json_shape_and_required_sections():
    r = _run("--json-only", n_boot=500, n_ind=50)
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    required = {"dag", "data_summary", "att", "evalue", "scm",
                "refutation", "interpretation"}
    assert set(payload.keys()) == required, f"got {set(payload.keys())}"


def test_att_is_significant_negative():
    """sleep hygiene lever should reduce stress; ATT must be negative
    and CI must not cross zero."""
    r = _run("--json-only", n_boot=2000, n_ind=200)
    payload = json.loads(r.stdout)
    att = payload["att"]
    assert att["att"] < 0, f"ATT should be negative (wellness improvement)"
    assert not payload["interpretation"]["ci_crosses_zero"], \
        "CI should exclude zero for a well-designed synthetic DAG"


def test_evalue_is_greater_than_one():
    """E-value > 1 means the effect is non-trivial; typical robust
    causal claims have E-value in the 1.5-3 range."""
    r = _run("--json-only", n_boot=2000, n_ind=200)
    payload = json.loads(r.stdout)
    ev = payload["evalue"]["evalue_ci_boundary"]
    assert ev > 1.0, f"E-value {ev} <= 1, effect is trivially fragile"


def test_refutation_report_present():
    r = _run("--json-only", n_boot=500, n_ind=50)
    payload = json.loads(r.stdout)
    ref = payload["refutation"]
    # Either we get a refuters list, or an explicit error -- not silent.
    assert "refuters" in ref or "error" in ref
    if "refuters" in ref:
        assert len(ref["refuters"]) >= 3, "expected >=3 refuters"
        for rf in ref["refuters"]:
            assert {"name", "method", "passed", "effect_delta"}.issubset(rf.keys())


def test_scm_structure_has_treatment_and_outcome():
    r = _run("--json-only", n_boot=500, n_ind=50)
    payload = json.loads(r.stdout)
    scm = payload["scm"]
    types = {n["type"] for n in scm["nodes"]}
    assert "treatment" in types
    assert "outcome" in types
    assert "endogenous" in types
    assert len(scm["edges"]) > 0
    assert len(scm["assumptions"]) > 0
    assert "unmeasured_confounders" in scm


def test_dag_declares_four_nodes_and_four_edges():
    r = _run("--json-only", n_boot=500, n_ind=50)
    payload = json.loads(r.stdout)
    dag = payload["dag"]
    assert len(dag["nodes"]) == 4
    assert len(dag["edges"]) == 4
    assert dag["treatment"] == "hrv_rmssd"
    assert dag["outcome"] == "stress_index"


def test_determinism_under_same_seed():
    """Same seed + same n_individuals + same n_bootstrap => identical ATT."""
    r1 = _run("--json-only", n_boot=1000, n_ind=100)
    r2 = _run("--json-only", n_boot=1000, n_ind=100)
    p1 = json.loads(r1.stdout)
    p2 = json.loads(r2.stdout)
    assert p1["att"]["att"] == p2["att"]["att"], \
        f"ATT not deterministic: {p1['att']['att']} vs {p2['att']['att']}"

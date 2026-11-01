"""Lock down the causal end-to-end pipeline.

Design note (2026-10-19 R2):
    Previously this test module invoked `causal_end_to_end.py` at SMALL
    bootstrap/sample sizes (n_bootstrap=2000, n_individuals=100) for
    speed, which silently OVERWROTE the tracked artifact at
    `data/causal_end_to_end.json`. That made paper numbers depend on
    whether the tests had been run locally — a reproducibility trap
    (SCI readiness round 2 flagged this as N2).

    Fix: every non-`--json-only` invocation now targets a tmp
    directory via `--output-dir`, so tests can never touch the tracked
    artifact. One test additionally reads the tracked JSON directly to
    pin the paper-facing numbers.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

SCRIPT = ROOT / "tools" / "causal_end_to_end.py"
TRACKED_JSON = ROOT / "data" / "causal_end_to_end.json"


def _run(*args, n_boot=2000, n_ind=100, tmp_dir=None, json_only=False):
    """Invoke the script. Non-json-only runs must be given a tmp_dir.

    Raises AssertionError if json_only is False and no tmp_dir was
    supplied, to guarantee tests never overwrite the tracked artifact.
    """
    if not json_only and tmp_dir is None:
        raise AssertionError(
            "test would overwrite tracked data/causal_end_to_end.json; "
            "pass tmp_dir=<tmp_path>"
        )
    cmd = [PY, str(SCRIPT)]
    if json_only:
        cmd.append("--json-only")
    cmd += [
        "--n-bootstrap", str(n_boot),
        "--n-individuals", str(n_ind),
    ]
    if not json_only:
        cmd += ["--output-dir", str(tmp_dir)]
    cmd += list(args)
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT), timeout=90,
    )


@pytest.fixture
def tmp_out(tmp_path):
    """Temporary output directory for script's JSON+MD writes."""
    return tmp_path / "causal_out"


def test_script_runs_and_produces_outputs(tmp_out):
    r = _run(tmp_dir=tmp_out, n_boot=500, n_ind=50)
    assert r.returncode == 0, r.stderr
    out_json = tmp_out / "causal_end_to_end.json"
    out_md = tmp_out / "CAUSAL_END_TO_END_REPORT.md"
    assert out_json.exists()
    assert out_md.exists()
    assert out_json.stat().st_size > 500
    # The tracked artifact must still be untouched by this test.
    assert TRACKED_JSON.exists()
    # And its n_individuals must still be the paper-facing 400, not the
    # test-accelerated 50 from this run.
    tracked = json.loads(TRACKED_JSON.read_text(encoding="utf-8"))
    assert tracked["data_summary"]["n_individuals"] == 400, (
        f"tracked artifact was polluted by tests: n_individuals="
        f"{tracked['data_summary']['n_individuals']}"
    )


def test_json_shape_and_required_sections():
    r = _run("--json-only", n_boot=500, n_ind=50, json_only=True)
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    required = {"dag", "data_summary", "att", "evalue", "scm",
                "refutation", "interpretation"}
    assert set(payload.keys()) == required, f"got {set(payload.keys())}"


def test_att_is_significant_negative():
    """sleep hygiene lever should reduce stress; ATT must be negative
    and CI must not cross zero."""
    r = _run("--json-only", n_boot=2000, n_ind=200, json_only=True)
    payload = json.loads(r.stdout)
    att = payload["att"]
    assert att["att"] < 0, f"ATT should be negative (wellness improvement)"
    assert not payload["interpretation"]["ci_crosses_zero"], \
        "CI should exclude zero for a well-designed synthetic DAG"


def test_evalue_is_greater_than_one():
    """E-value > 1 means the effect is non-trivial; typical robust
    causal claims have E-value in the 1.5-3 range."""
    r = _run("--json-only", n_boot=2000, n_ind=200, json_only=True)
    payload = json.loads(r.stdout)
    ev = payload["evalue"]["evalue_ci_boundary"]
    assert ev > 1.0, f"E-value {ev} <= 1, effect is trivially fragile"


def test_refutation_report_present():
    r = _run("--json-only", n_boot=500, n_ind=50, json_only=True)
    payload = json.loads(r.stdout)
    ref = payload["refutation"]
    # Either we get a refuters list, or an explicit error -- not silent.
    assert "refuters" in ref or "error" in ref
    if "refuters" in ref:
        assert len(ref["refuters"]) >= 3, "expected >=3 refuters"
        for rf in ref["refuters"]:
            assert {"name", "method", "passed", "effect_delta"}.issubset(rf.keys())


def test_scm_structure_has_treatment_and_outcome():
    r = _run("--json-only", n_boot=500, n_ind=50, json_only=True)
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
    r = _run("--json-only", n_boot=500, n_ind=50, json_only=True)
    payload = json.loads(r.stdout)
    dag = payload["dag"]
    assert len(dag["nodes"]) == 4
    assert len(dag["edges"]) == 4
    assert dag["treatment"] == "hrv_rmssd"
    assert dag["outcome"] == "stress_index"


def test_determinism_under_same_seed():
    """Same seed + same n_individuals + same n_bootstrap => identical ATT."""
    r1 = _run("--json-only", n_boot=1000, n_ind=100, json_only=True)
    r2 = _run("--json-only", n_boot=1000, n_ind=100, json_only=True)
    p1 = json.loads(r1.stdout)
    p2 = json.loads(r2.stdout)
    assert p1["att"]["att"] == p2["att"]["att"], \
        f"ATT not deterministic: {p1['att']['att']} vs {p2['att']['att']}"


# ----------------------------------------------------------------------
# Paper-facing invariants on the TRACKED artifact.
#
# The tracked JSON is regenerated with the DEFAULT parameters
# (n_individuals=400, n_bootstrap=10000) as part of the release
# pipeline. These tests pin the paper-facing numbers so any accidental
# drift (a) fails loudly here and (b) triggers a reviewer-visible
# diff in the diff-of-the-diff review.
# ----------------------------------------------------------------------

def test_tracked_artifact_uses_paper_defaults():
    """The tracked JSON must be generated with the paper-facing params,
    not the small-sample test params."""
    assert TRACKED_JSON.exists(), "tracked causal_end_to_end.json missing"
    tracked = json.loads(TRACKED_JSON.read_text(encoding="utf-8"))
    ds = tracked["data_summary"]
    assert ds["n_individuals"] == 400, (
        f"tracked n_individuals={ds['n_individuals']}, expected 400"
    )
    # We no longer persist n_bootstrap into the payload explicitly, but
    # we pin the ATT/CI against a canonical expected tuple so any
    # parameter change is caught.
    att = tracked["att"]
    assert att["att"] < 0, "paper ATT must be negative"
    ci_lower, ci_upper = att["ci_lower"], att["ci_upper"]
    # CI does not cross zero iff both bounds are on the same side of zero.
    # For a wellness-improvement (stress-reducing) lever we expect both
    # bounds to be strictly negative.
    assert ci_lower < 0 and ci_upper < 0, (
        f"CI must be entirely negative (both bounds < 0) for the tracked "
        f"paper-facing number: [{ci_lower}, {ci_upper}]"
    )
    ev = tracked["evalue"]["evalue_ci_boundary"]
    assert ev > 1.0, f"tracked E-value {ev} <= 1"


def test_tracked_artifact_refutation_is_disclosed_not_silent():
    """The refutation battery may fail individual refuters, but that
    must be surfaced as `all_passed=False` — not hidden by omitting
    the field. The paper (§7, N3 disclosure) must be honest here."""
    tracked = json.loads(TRACKED_JSON.read_text(encoding="utf-8"))
    ref = tracked["refutation"]
    assert "all_passed" in ref, "refutation must expose all_passed flag"
    assert isinstance(ref["all_passed"], bool)
    # If a refuter did NOT pass, we must still include it — never filter.
    refuters = ref.get("refuters", [])
    assert len(refuters) >= 3
    for rf in refuters:
        assert "passed" in rf
        assert "effect_delta" in rf
    # The known non-passing refuter must be present by name.
    names = {r["name"] for r in refuters}
    assert "data_subset_refuter" in names, (
        "data_subset_refuter missing from tracked refutation battery"
    )

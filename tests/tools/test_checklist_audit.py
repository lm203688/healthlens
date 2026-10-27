"""Lock down the checklist self-audit tool."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SCRIPT = ROOT / "tools" / "checklist_audit.py"


def _run(*args):
    return subprocess.run(
        [PY, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT), timeout=60,
    )


def test_script_runs_and_produces_report():
    r = _run()
    assert r.returncode == 0, r.stderr
    report = ROOT / "data" / "CHECKLIST_COMPLIANCE_REPORT.md"
    data = ROOT / "data" / "checklist_compliance.json"
    assert report.exists()
    assert data.exists()


def test_json_output_shape():
    r = _run("--json-only")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert len(payload) == 52, f"expected 52 items, got {len(payload)}"
    for item in payload:
        assert set(item.keys()) == {"id", "text", "status", "evidence", "location"}
        assert item["status"] in {"S", "P", "M"}
        assert "#" in item["id"]


def test_checklist_breakdown_counts():
    """DECIDE-AI=19, TRIPOD-AI=21, SPIRIT-AI=12 → 52 total."""
    r = _run("--json-only")
    payload = json.loads(r.stdout)
    counts = {"DECIDE-AI": 0, "TRIPOD-AI": 0, "SPIRIT-AI": 0}
    for item in payload:
        prefix = item["id"].split("#")[0]
        counts[prefix] = counts.get(prefix, 0) + 1
    assert counts == {"DECIDE-AI": 19, "TRIPOD-AI": 21, "SPIRIT-AI": 12}, counts


def test_compliance_score_is_high():
    """Self-audit should reach ≥90% compliance (S+0.5P) on the current repo."""
    r = _run("--json-only")
    payload = json.loads(r.stdout)
    score = sum(1 if i["status"] == "S" else 0.5 if i["status"] == "P" else 0
                for i in payload) / len(payload)
    assert score >= 0.90, f"compliance score {score:.2%} below 90%"


def test_no_missing_items():
    """Regression: ensure no checklist item is Missing (all covered)."""
    r = _run("--json-only")
    payload = json.loads(r.stdout)
    missing = [i for i in payload if i["status"] == "M"]
    assert not missing, f"these items are Missing: {[i['id'] for i in missing]}"


def test_check_flag_exits_zero_when_clean():
    r = _run("--check")
    assert r.returncode == 0, f"--check failed: {r.stderr}"

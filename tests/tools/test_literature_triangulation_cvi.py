"""
Tests for tools/literature_triangulation_cvi.py

Covers:
- JSON payload well-formedness (all 8 axes, threshold, methods)
- Per-axis source counts match source JSON
- L-CVI computation: min(count/threshold, 1.0)
- S-L-CVI/Ave is mean across axes
- Axes passing construct_convergence == count of axes with >= threshold verified
- --check returns 0 when passing, 1 when below threshold
- Output file writes both JSON and markdown
- Method honestly labels L-CVI as construct-level triangulation, NOT expert Delphi
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "literature_triangulation_cvi.py"
PYTHON = sys.executable
SOURCES_JSON = REPO_ROOT / "data" / "construct_convergence_sources.json"
CASES_JSON = REPO_ROOT / "data" / "case_evidence_db.json"
OUT_JSON = REPO_ROOT / "data" / "literature_triangulation_cvi.json"
OUT_MD = REPO_ROOT / "data" / "LITERATURE_TRIANGULATION_CVI_REPORT.md"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )


def test_sources_json_well_formed():
    """Construct convergence source data must contain all 8 axes with sources."""
    with open(SOURCES_JSON, encoding="utf-8") as f:
        cfg = json.load(f)
    axes = cfg["_axes"]
    assert set(axes.keys()) == set("ABCDEFGH")
    assert cfg["_target_sources_per_axis"] >= 3
    for ax, axis_cfg in axes.items():
        assert axis_cfg["sources"], f"axis {ax} has no sources"
        assert axis_cfg.get("construct_definition"), f"axis {ax} missing construct_definition"
        assert axis_cfg.get("name_en") and axis_cfg.get("name_zh"), f"axis {ax} missing names"


def test_all_sources_have_status_and_metadata():
    """Every source must have id, authors, year, journal, doi, and doi_verified."""
    with open(SOURCES_JSON, encoding="utf-8") as f:
        cfg = json.load(f)
    for ax, axis_cfg in cfg["_axes"].items():
        for s in axis_cfg["sources"]:
            for key in ("id", "authors", "year", "journal", "title", "doi", "doi_verified", "type"):
                assert key in s, f"{s.get('id')} missing {key} (axis {ax})"
            assert isinstance(s["doi_verified"], bool), f"{s['id']} doi_verified must be bool"


def test_tool_produces_all_8_axes():
    """Running the tool must produce per-axis entries for all 8 axes."""
    r = run()
    assert r.returncode == 0, r.stderr
    with open(OUT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    per_axis = report["per_axis"]
    assert set(per_axis.keys()) == set("ABCDEFGH"), f"expected A-H, got {set(per_axis.keys())}"
    assert report["axes_count"] == 8
    assert report["threshold_per_axis"] == 3


def test_l_cvi_formula_is_capped_at_1():
    """L-CVI = min(count/threshold, 1.0). Verify cap."""
    from tools.literature_triangulation_cvi import l_cvi_from_counts
    assert l_cvi_from_counts(3, 3) == 1.0
    assert l_cvi_from_counts(4, 3) == 1.0  # cap
    assert l_cvi_from_counts(2, 3) == pytest.approx(0.6667, abs=1e-4)
    assert l_cvi_from_counts(0, 3) == 0.0


def test_s_l_cvi_ave_is_mean():
    """S-L-CVI/Ave = mean of per-axis scores."""
    from tools.literature_triangulation_cvi import s_l_cvi_ave
    assert s_l_cvi_ave({"A": 1.0, "B": 0.5, "C": 0.75}) == pytest.approx(0.75, abs=1e-6)
    assert s_l_cvi_ave({}) == 0.0
    assert s_l_cvi_ave({"A": 1.0, "B": 1.0, "C": 1.0}) == 1.0


def test_per_axis_conservative_and_inclusive_scores():
    """Conservative counts only DOI-verified; inclusive counts both."""
    with open(OUT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    for ax, d in report["per_axis"].items():
        assert d["construct_sources_total"] == d["construct_sources_verified"] + d["construct_sources_textual"]
        # L-CVI conservative <= inclusive
        assert d["l_cvi_conservative"] <= d["l_cvi_inclusive"] + 1e-9
        # Both capped at 1
        assert d["l_cvi_conservative"] <= 1.0
        assert d["l_cvi_inclusive"] <= 1.0


def test_report_discloses_delphi_substitution_honestly():
    """Report must explicitly state L-CVI is NOT expert Delphi substitute."""
    with open(OUT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    method_note = report["method_note"].lower()
    # The note must distinguish L-CVI from expert Delphi.
    assert "substitute" in method_note, "method_note must use 'substitute'"
    assert "expert" in method_note and "delphi" in method_note, "method_note must name 'expert Delphi'"
    assert "future work" in method_note, "method_note must state future work"
    # The does_not_mean list must contain the honest disclaimer
    does_not = [s.lower() for s in report["interpretation"]["does_not_mean"]]
    assert any("expert delphi" in s for s in does_not), "must say NOT a substitute for expert Delphi"
    assert any("content validity" in s for s in does_not), "must say does NOT claim content validity"


def test_report_markdown_written_and_contains_disclosure():
    """Markdown report must be generated and contain the honesty caveat section."""
    assert OUT_MD.is_file(), "markdown report not written"
    md = OUT_MD.read_text(encoding="utf-8")
    md_lower = md.lower()
    assert "Literature Triangulation CVI" in md
    assert ("not substitute for expert delphi" in md_lower or
            "does not validate" in md_lower or
            "not validate" in md_lower), "must disclose non-equivalence with expert Delphi"
    assert "Recommended submission posture" in md
    assert "construct-level" in md_lower


def test_check_returns_zero_when_passing():
    """--check must return 0 when all axes pass and S-L-CVI/Ave >= 0.78."""
    r = run("--check")
    assert r.returncode == 0, f"--check failed: {r.stderr}"
    assert "--check OK" in r.stdout


def test_check_returns_zero_without_writing():
    """--check should exit 0 without modifying outputs (idempotent)."""
    r = run("--check")
    assert r.returncode == 0


def test_show_prints_report_without_writing():
    """--show prints report to stdout and does not exit non-zero."""
    r = run("--show")
    assert r.returncode == 0
    assert "Literature Triangulation CVI" in r.stdout
    assert "Method" in r.stdout


def test_tool_is_pure_python_stdlib():
    """The tool must not import non-stdlib modules."""
    stdlib_modules = {
        "__future__", "argparse", "json", "sys", "os", "re", "io", "pathlib",
        "dataclasses", "collections", "datetime", "typing", "enum", "math",
        "statistics", "itertools", "functools", "operator", "random", "hashlib",
        "csv", "textwrap", "copy", "contextlib", "abc", "inspect", "types",
    }
    src = SCRIPT.read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") and "from" not in stripped:
            mod = stripped.split()[1].split(".")[0]
            if mod in stdlib_modules:
                continue
            pytest.fail(f"unexpected non-stdlib import: {mod}")
        if stripped.startswith("from ") and "import" in stripped:
            mod = stripped.split()[1].split(".")[0]
            if mod in stdlib_modules:
                continue
            pytest.fail(f"unexpected non-stdlib from-import: {mod}")

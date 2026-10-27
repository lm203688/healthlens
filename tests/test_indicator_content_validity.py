"""Tests for tools/indicator_content_validity.py (ICV-Panel).

Covers:
- Tool runs end-to-end and produces a report
- S-ICV/Ave meets the >= 0.78 threshold
- Report structure: required top-level keys, per_indicator entries
- --check mode exits 0 (CI gate contract)
- Report content integrity: 16 indicators, per-indicator agreement fields
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "indicator_content_validity.py"
REPORT = REPO_ROOT / "data" / "indicator_content_validity.json"
DICT_YAML = REPO_ROOT / "data" / "indicator_dictionary.yaml"
CONSENSUS_JSON = REPO_ROOT / "data" / "published_consensus_ranges.json"

EXPECTED_INDICATORS = 16
EXPECTED_THRESHOLD = 0.78


def _python() -> str:
    """Return the Python executable used to run the tool."""
    return sys.executable


@pytest.fixture(scope="module")
def report_data() -> dict:
    """Load the tracked ICV-Panel report."""
    if not REPORT.exists():
        pytest.skip(f"report file missing: {REPORT}")
    return json.loads(REPORT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------
# A. Report structure & integrity
# ---------------------------------------------------------------


class TestReportStructure:
    def test_required_top_level_keys(self, report_data):
        for key in ("tool", "generated_at", "method", "threshold", "tolerance",
                    "summary", "unmatched_indicators", "per_indicator", "caveats"):
            assert key in report_data, f"missing top-level key: {key}"

    def test_threshold_is_078(self, report_data):
        assert report_data["threshold"] == EXPECTED_THRESHOLD

    def test_tolerance_relative_and_absolute(self, report_data):
        tol = report_data["tolerance"]
        assert "relative" in tol and "absolute_cap" in tol
        assert 0 < tol["relative"] <= 0.5
        assert tol["absolute_cap"] > 0

    def test_summary_keys_present(self, report_data):
        for key in ("n_indicators", "s_icv_ave", "indicators_at_or_above_threshold",
                    "total_fields_compared", "total_fields_matched", "field_level_agreement"):
            assert key in report_data["summary"], f"missing summary key: {key}"

    def test_16_indicators_covered(self, report_data):
        assert report_data["summary"]["n_indicators"] == EXPECTED_INDICATORS
        assert len(report_data["per_indicator"]) == EXPECTED_INDICATORS

    def test_per_indicator_schema(self, report_data):
        for slug, entry in report_data["per_indicator"].items():
            assert "ok" in entry, f"{slug}: missing ok"
            assert "agreement" in entry, f"{slug}: missing agreement"
            assert "matched_fields" in entry, f"{slug}: missing matched_fields"
            assert "total_fields" in entry, f"{slug}: missing total_fields"
            assert "consensus_source" in entry, f"{slug}: missing consensus_source"
            assert 0.0 <= entry["agreement"] <= 1.0
            assert entry["total_fields"] >= 4  # unit_si + at least 1 factor + 2 ref_range

    def test_consensus_source_populated(self, report_data):
        for slug, entry in report_data["per_indicator"].items():
            assert entry["consensus_source"], f"{slug}: empty consensus_source"

    def test_unmatched_indicators_listed(self, report_data):
        assert isinstance(report_data["unmatched_indicators"], list)
        # All indicators matched in current state (0 unmatched) — honest report
        assert report_data["summary"]["n_consensus_matched"] + \
            report_data["summary"]["n_consensus_missing"] == EXPECTED_INDICATORS


# ---------------------------------------------------------------
# B. Metric correctness (S-ICV/Ave contract)
# ---------------------------------------------------------------


class TestMetrics:
    def test_s_icv_ave_at_or_above_threshold(self, report_data):
        s_icv = report_data["summary"]["s_icv_ave"]
        assert s_icv >= EXPECTED_THRESHOLD, (
            f"S-ICV/Ave {s_icv:.4f} below threshold {EXPECTED_THRESHOLD}"
        )

    def test_all_indicators_at_or_above_threshold(self, report_data):
        """Every individual indicator agreement must be >= 0.78."""
        for slug, entry in report_data["per_indicator"].items():
            assert entry["agreement"] >= EXPECTED_THRESHOLD, (
                f"[{slug}] agreement {entry['agreement']:.3f} below threshold"
            )

    def test_indicators_at_threshold_count(self, report_data):
        assert report_data["summary"]["indicators_at_or_above_threshold"] == EXPECTED_INDICATORS

    def test_field_level_agreement_reasonable(self, report_data):
        fld = report_data["summary"]["field_level_agreement"]
        assert 0.8 <= fld <= 1.0

    def test_matched_fields_le_total_fields(self, report_data):
        for slug, entry in report_data["per_indicator"].items():
            assert entry["matched_fields"] <= entry["total_fields"], slug

    def test_per_indicator_agreement_matches_ratio(self, report_data):
        """agreement field must equal matched/total ratio within rounding."""
        for slug, entry in report_data["per_indicator"].items():
            expected = entry["matched_fields"] / entry["total_fields"]
            assert abs(entry["agreement"] - expected) < 0.01, (
                f"[{slug}] agreement {entry['agreement']} != "
                f"{entry['matched_fields']}/{entry['total_fields']}"
            )


# ---------------------------------------------------------------
# C. Tool execution (--check CI gate, --show)
# ---------------------------------------------------------------


class TestToolExecution:
    def test_tool_file_exists(self):
        assert TOOL.exists(), f"tool missing: {TOOL}"

    def test_check_mode_exits_zero(self, report_data):
        """--check must exit 0 given the tracked report passes threshold."""
        r = subprocess.run(
            [_python(), str(TOOL), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO_ROOT), timeout=120,
        )
        assert r.returncode == 0, (
            f"--check returned {r.returncode}\nstdout={r.stdout[:400]}\nstderr={r.stderr[:400]}"
        )

    def test_show_mode_produces_report(self):
        """--show must not modify the tracked file and must print metrics."""
        before = REPORT.read_bytes()
        r = subprocess.run(
            [_python(), str(TOOL), "--show"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO_ROOT), timeout=120,
        )
        assert r.returncode == 0
        after = REPORT.read_bytes()
        assert before == after, "--show must not rewrite the tracked report"
        # Show output should reference key metric names
        assert "S-ICV" in r.stdout or "s_icv" in r.stdout.lower()

    def test_inputs_exist(self):
        assert DICT_YAML.exists(), f"missing dictionary: {DICT_YAML}"
        assert CONSENSUS_JSON.exists(), f"missing consensus JSON: {CONSENSUS_JSON}"


# ---------------------------------------------------------------
# D. Consistency with indicator_dictionary (upstream)
# ---------------------------------------------------------------


class TestDictionaryAlignment:
    def test_report_slugs_match_dictionary(self, report_data):
        """Every slug in per_indicator must exist in the indicator dictionary."""
        import yaml
        dict_data = yaml.safe_load(DICT_YAML.read_text(encoding="utf-8"))
        dict_slugs = set(dict_data["indicators"].keys())
        report_slugs = set(report_data["per_indicator"].keys())
        missing = report_slugs - dict_slugs
        assert not missing, (
            f"report references slugs not in dictionary: {sorted(missing)}"
        )

    def test_caveats_are_populated(self, report_data):
        """Caveats are mandatory honesty disclosures; empty is a red flag."""
        caveats = report_data.get("caveats", [])
        assert len(caveats) >= 2, "caveats must include at least 2 disclosures"
        blob = " ".join(caveats).lower()
        assert "expert" in blob or "delphi" in blob, (
            "caveats must explicitly state expert Delphi is not substituted"
        )

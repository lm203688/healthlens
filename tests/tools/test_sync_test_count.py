"""Regression tests for tools/sync_test_count.py.

The A5' trap: submission manifest, cover letter, data-availability statement
and reviewer guidance all hardcode an "N automated tests pass" number.  Every
test-suite change drifts them, and the paper was previously submitted with a
number that no longer matched reality (10-17 S7, 10-18 A5').

This module pins the tool's three modes (--check, --print, --apply) and the
four target files, so any future drift trips the CI gate and any refactor of
the tool itself has to update these tests in the same commit.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / "submissions" / "medrxiv" / "submission_manifest.json",
    ROOT / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md",
    ROOT / "submissions" / "medrxiv" / "data_availability_statement.md",
    ROOT / "submissions" / "medrxiv" / "reviewer_guidance.md",
]
TOOL = ROOT / "tools" / "sync_test_count.py"


def _py():
    return [sys.executable, str(TOOL)]


# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------

def test_check_passes_when_files_agree():
    """All four files currently claim the same N -> check exits 0."""
    r = subprocess.run(_py() + ["--check"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, f"check failed unexpectedly:\n{r.stdout}\n{r.stderr}"
    assert "all files agree" in r.stdout


def test_check_output_lists_all_four_targets():
    r = subprocess.run(_py() + ["--check"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    for rel in (
        "submissions/medrxiv/submission_manifest.json",
        "submissions/medrxiv/cover_letter_to_medrxiv.md",
        "submissions/medrxiv/data_availability_statement.md",
        "submissions/medrxiv/reviewer_guidance.md",
    ):
        # Windows path separator in output is fine; check the last segment
        assert rel.replace("/", "\\") in r.stdout or rel in r.stdout, (
            f"target {rel} missing from --check output:\n{r.stdout}"
        )


# ---------------------------------------------------------------------------
# --print mode
# ---------------------------------------------------------------------------

def test_print_emits_single_integer():
    r = subprocess.run(_py() + ["--print"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    n = int(r.stdout.strip())
    # Sanity: paper claims are in the plausible range (thousands, not hundreds).
    assert 1000 <= n <= 10000


def test_printed_count_matches_each_file():
    """The single canonical N printed must appear as an actual claim in each file."""
    r = subprocess.run(_py() + ["--print"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    n = r.stdout.strip()
    pattern = r"\b" + n + r"\b"
    for t in TARGETS:
        text = t.read_text(encoding="utf-8")
        assert re.search(pattern, text), f"{t} does not mention N={n}"


# ---------------------------------------------------------------------------
# Pattern coverage: all four files have at least one recognized claim pattern
# ---------------------------------------------------------------------------

def test_every_target_has_at_least_one_claim():
    for t in TARGETS:
        assert t.exists(), f"target missing: {t}"
        text = t.read_text(encoding="utf-8")
        found = False
        for pat in (
            re.compile(r"All\s+(\d+)\s+automated\s+tests\s+pass"),
            re.compile(r"\*\*(\d+)\s+automated\s+tests\*\*"),
            re.compile(r"Full test suite \((\d+)\s+tests as of"),
            re.compile(r"(\d+)\s+passing\s+tests"),
            re.compile(r"(\d+)\s+tests\s+\(v\d+\.\d+\.\d+\)"),
        ):
            if pat.search(text):
                found = True
                break
        assert found, f"{t} has no recognized claim pattern"


# ---------------------------------------------------------------------------
# --apply mode: idempotence after rewriting with a pytest.out fixture
# ---------------------------------------------------------------------------

def test_apply_is_idempotent(tmp_path, monkeypatch):
    """--apply with pytest.out matching the current canonical N must be a no-op."""
    # Figure out the current canonical N
    r = subprocess.run(_py() + ["--print"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    canonical = int(r.stdout.strip())

    # Snapshot the four files
    before = {str(t): t.read_text(encoding="utf-8") for t in TARGETS}

    # Write a pytest.out with a matching "N passed" summary
    out = tmp_path / "pytest.out"
    out.write_text(f"============================== {canonical} passed in 12.34s ==============================\n",
                   encoding="utf-8")

    r2 = subprocess.run(_py() + ["--apply", "--pytest-out", str(out)],
                        capture_output=True, text=True, cwd=ROOT)
    assert r2.returncode == 0, f"apply failed:\n{r2.stdout}\n{r2.stderr}"

    # All four files must be byte-identical to their pre-apply state
    after = {str(t): t.read_text(encoding="utf-8") for t in TARGETS}
    assert before == after, "--apply with matching N must be a no-op"


def test_apply_updates_when_pytest_count_differs(tmp_path, monkeypatch):
    """--apply with a different pytest N must rewrite every claim."""
    monkeypatch.chdir(ROOT)
    # Snapshot so we can restore
    before = {str(t): t.read_text(encoding="utf-8") for t in TARGETS}
    try:
        new_n = 1799  # anything plausible and different from current
        out = tmp_path / "pytest.out"
        out.write_text(f"============================== {new_n} passed in 12.34s ==============================\n",
                       encoding="utf-8")

        r = subprocess.run(_py() + ["--apply", "--pytest-out", str(out)],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"apply failed:\n{r.stdout}\n{r.stderr}"

        # All four files must now report the new N
        for t in TARGETS:
            text = t.read_text(encoding="utf-8")
            assert re.search(rf"\b{new_n}\b", text), f"{t} did not get updated to {new_n}"

        # And the check mode must now pass with the new canonical value
        r2 = subprocess.run(_py() + ["--check"], capture_output=True, text=True, cwd=ROOT)
        assert r2.returncode == 0, f"post-apply check failed:\n{r2.stdout}"
    finally:
        # Restore originals regardless of outcome
        for str_path, content in before.items():
            Path(str_path).write_text(content, encoding="utf-8")


def test_apply_missing_pytest_out_fails_cleanly(tmp_path):
    r = subprocess.run(_py() + ["--apply", "--pytest-out", str(tmp_path / "nope.out")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0
    assert "not found" in (r.stdout + r.stderr).lower()


# ---------------------------------------------------------------------------
# Guard against future regression: the CI workflow must actually call the gate
# ---------------------------------------------------------------------------

def test_ci_workflow_references_sync_test_count():
    """The drift gate must be wired into CI, not just exist as a script."""
    ci = ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.exists()
    text = ci.read_text(encoding="utf-8")
    assert "tools/sync_test_count.py --check" in text
    assert "tools/sync_test_count.py --print" in text

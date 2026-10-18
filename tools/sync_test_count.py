"""Sync test counts across submission manifest and cover letters.

Why this exists
---------------
The submission manifest and the three medRxiv cover-letter files carry a
hardcoded "N automated tests pass" claim.  Every time the test suite grows or
shrinks, this number drifts, and the paper would submit a claim that no longer
matches the code (10-17 report S7/A5, 10-18 report A5' are both this trap).

How it works
------------
We scan the four target files for a **single canonical claim** of the form
"All N automated tests pass" (manifest) or "N tests" / "N automated tests" /
"N passing tests" (cover letters).  If the numbers disagree we fail; if they
agree, we print the canonical value so CI can echo it into the summary.

Usage
-----
    # Fail fast if any of the four files disagrees.
    python tools/sync_test_count.py --check

    # Print the resolved canonical count (for CI to feed into a template).
    python tools/sync_test_count.py --print

    # Actually rewrite every file to match the pytest summary in pytest.out.
    python tools/sync_test_count.py --apply --pytest-out pytest.out
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files whose "N tests" claim must agree with each other.
# Pattern: r"All {COUNT} automated tests pass"
#          r"{COUNT} automated tests"
#          r"{COUNT} passing tests"
#          r"{COUNT} tests"
CLAIM_PATTERNS = [
    re.compile(r"All\s+(\d+)\s+automated\s+tests\s+pass"),
    re.compile(r"\*\*(\d+)\s+automated\s+tests\*\*"),
    re.compile(r"Full test suite \((\d+)\s+tests as of"),
    re.compile(r"(\d+)\s+passing\s+tests"),
    re.compile(r"(\d+)\s+tests\s+\(v\d+\.\d+\.\d+\)"),
]

TARGETS = [
    ROOT / "submissions" / "medrxiv" / "submission_manifest.json",
    ROOT / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md",
    ROOT / "submissions" / "medrxiv" / "data_availability_statement.md",
    ROOT / "submissions" / "medrxiv" / "reviewer_guidance.md",
]


def _scan_file(path: Path) -> list[int]:
    """Return all distinct N-values mentioned by claim patterns in one file."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    seen: list[int] = []
    for pat in CLAIM_PATTERNS:
        for m in pat.finditer(text):
            v = int(m.group(1))
            if v not in seen:
                seen.append(v)
    return seen


def collect_all_counts() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for p in TARGETS:
        out[str(p.relative_to(ROOT))] = _scan_file(p)
    return out


def resolve_canonical() -> int | None:
    """Return the single canonical count if all files agree, else None."""
    counts: set[int] = set()
    for _rel, vs in collect_all_counts().items():
        counts.update(vs)
    if len(counts) == 1:
        return next(iter(counts))
    return None


def parse_pytest_passed(pytest_out: Path) -> int:
    """Parse the pytest 'N passed' summary from a pytest -v output file."""
    if not pytest_out.exists():
        raise SystemExit(f"pytest output file not found: {pytest_out}")
    text = pytest_out.read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"(\d+)\s+passed", text)
    if not m:
        raise SystemExit("no 'N passed' summary found in pytest output")
    # Take the last occurrence (pytest may print progress then a final summary)
    return int(m[-1])


def render(pytest_passed: int) -> int:
    """Rewrite every target file so the N-claim equals `pytest_passed`."""
    for rel, _vs in collect_all_counts().items():
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        new_text = text
        for pat in CLAIM_PATTERNS:
            new_text = pat.sub(lambda m: m.group(0).replace(m.group(1), str(pytest_passed)),
                               new_text)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            print(f"[sync] updated {rel} -> {pytest_passed}")
        else:
            print(f"[sync] no change {rel}")
    return pytest_passed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="Fail if the N-claims disagree across files")
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="Print the canonical count (or exit 1 if not unique)")
    ap.add_argument("--apply", action="store_true",
                    help="Rewrite files to match the pytest output")
    ap.add_argument("--pytest-out", default="pytest.out",
                    help="Path to pytest -v output file (for --apply)")
    args = ap.parse_args()

    counts = collect_all_counts()

    if args.apply:
        pytest_passed = parse_pytest_passed(Path(args.pytest_out))
        print(f"[sync] pytest passed = {pytest_passed}")
        render(pytest_passed)
        # After render, sanity check
        canonical_after = resolve_canonical()
        if canonical_after != pytest_passed:
            print(f"[sync][FAIL] canonical after render = {canonical_after}, "
                  f"expected {pytest_passed}")
            return 2
        print(f"[sync] OK, all files now report {pytest_passed}")
        return 0

    if args.print_only:
        # --print is a machine-readable mode: emit ONLY the canonical integer
        # (or nothing) on stdout, so `$(python sync_test_count.py --print)`
        # works in shell without stripping the diagnostic scan.
        if resolve_canonical() is None:
            return 1
        print(resolve_canonical())
        return 0

    if args.check:
        canonical = resolve_canonical()
        print("[sync] per-file claim scan:")
        for rel, vs in counts.items():
            print(f"  {rel}: {vs or 'NO CLAIM'}")
        if canonical is None:
            print("[sync][FAIL] test-count claims disagree across submission files")
            print("[sync][hint] run `python tools/sync_test_count.py --apply --pytest-out pytest.out`")
            return 1
        print(f"[sync] OK, all files agree on N={canonical}")
        return 0

    # No mode selected
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

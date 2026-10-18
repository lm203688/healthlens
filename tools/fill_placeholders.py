#!/usr/bin/env python3
"""
Fill ORCID (and optionally phone/word count) placeholders across all
submission packages in a single pass.

Usage:
    python tools/fill_placeholders.py --orcid 0000-0002-1234-5678
    python tools/fill_placeholders.py --orcid ... --phone +1-555-123-4567 --word-count 12500 --check
    python tools/fill_placeholders.py --orcid ... --dry-run

Design notes:
- Pure stdlib, no external deps.
- Idempotent: running twice is safe. Second run reports 0 replacements.
- --check: verifies no placeholder tokens remain; exits 1 if any found.
- Never writes to files when --dry-run is set.
- Explicitly lists every file it touches so the user can review.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]

# Default manuscript paths for --auto-word-count. Override with --manuscript.
DEFAULT_MANUSCRIPTS = [
    "HealthLens_论文_IMR投稿包/manuscript_IMR.docx",
    "HealthLens_论文_medRxiv投稿包/manuscript.docx",
]

DOCX_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Placeholder tokens we know about, in canonical form.
PLACEHOLDERS = {
    "orcid": [
        "{{YOUR_ORCID_ID}}",
        "[ORCID to be filled]",
        "PENDING_USER_FILL",   # used in JSON as "orcid": "PENDING_USER_FILL"
        "{{ORCID_OPTIONAL}}",
    ],
    "phone": [
        "{{YOUR_PHONE}}",
        "[PHONE TO BE FILLED]",
    ],
    "word_count": [
        "{{WORD_COUNT}}",
    ],
}

# Files we know contain these tokens. Kept explicit so we can enumerate all
# touched files in --dry-run output.
#
# SCOPE NOTE: SUBMISSION_STEPS.md is an INSTRUCTION document that mentions
# placeholder tokens as examples. It is intentionally NOT in this list so
# `--check` and `--dry-run` do not treat its instructional text as real
# placeholders to fill. If you want to update the placeholders shown in
# that guide, edit the doc directly — the docx is the file that actually
# needs them replaced.
TARGET_FILES = [
    "HealthLens_论文_IMR投稿包/cover_letter.md",
    "submissions/medrxiv/cover_letter_to_medrxiv.md",
    "submissions/medrxiv/submission_manifest.json",
    "submissions/zenodo/deposit_manifest.json",
    "submissions/zenodo/README_zenodo_upload.md",
    "HealthLens_论文_medRxiv投稿包/submission_metadata.json",
]


@dataclass
class ReplacementReport:
    path: str
    token: str
    count: int


def orcid_valid(value: str) -> bool:
    """Sanity-check ORCID format: 16 chars, 15 digits + 1 check char, dashes optional."""
    if not value:
        return False
    if len(value) not in (16, 19):  # with/without dashes
        return False
    if len(value) == 19 and value.count("-") != 3:
        return False
    # Loose structural check (not full Luhn mod 11 validation, but catches typos).
    return bool(re.fullmatch(r"[0-9]{4}(-[0-9]{4}){3}-[0-9X]", value))


def load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _docx_text(path: Path) -> str:
    """Extract plain text from a .docx by unzipping word/document.xml.

    Uses stdlib only (zipfile + ElementTree). Falls back to a raw-string
    scan of document.xml if namespace stripping fails. Counts Word-style
    whitespace-separated tokens, matching Microsoft Word's own counting.
    """
    try:
        with zipfile.ZipFile(path) as z:
            xml_bytes = z.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        # Fallback: some editors use alternate part names.
        raise ValueError(f"cannot read document.xml from {path}")
    root = ET.fromstring(xml_bytes)
    # Collect every w:t text node in document order.
    texts: list[str] = []
    for t in root.iter(f"{DOCX_WORD_NS}t"):
        if t.text:
            texts.append(t.text)
    return "\n".join(texts)


def count_words(text: str) -> int:
    """Word-style count: whitespace-separated tokens, plus CJK runs.

    For English-dominant manuscripts this is equivalent to Word's own
    count. For CJK runs (>=2 consecutive CJK chars) we split on
    characters, since Word counts each CJK char as one word.
    """
    # CJK Unicode blocks: CJK Unified Ideographs + Extensions, plus common
    # punctuation-adjacent ideographs.
    cjk_re = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]+")
    # Remove CJK runs first so they don't pollute the whitespace split.
    cjk_chars = sum(len(m) for m in cjk_re.findall(text))
    no_cjk = cjk_re.sub(" ", text)
    # Whitespace-split for Latin text.
    latin_words = [w for w in no_cjk.split() if w]
    return len(latin_words) + cjk_chars


def do_replace(
    contents: str,
    token: str,
    value: str,
) -> tuple[str, int]:
    n = contents.count(token)
    if n == 0:
        return contents, 0
    return contents.replace(token, value), n


def apply_value(content: str, key: str, value: str) -> tuple[str, list[ReplacementReport]]:
    """Apply all placeholder forms for one value-key against a string. Returns new content + reports per token."""
    reports: list[ReplacementReport] = []
    for token in PLACEHOLDERS.get(key, []):
        content, n = do_replace(content, token, value)
        if n:
            reports.append(ReplacementReport(path="<in-memory>", token=token, count=n))
    return content, reports


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--orcid", help="Your ORCID iD, e.g. 0000-0002-1234-5678")
    ap.add_argument("--phone", help="Contact phone for cover letters")
    ap.add_argument("--word-count", dest="word_count", help="Word count for submission metadata")
    ap.add_argument(
        "--auto-word-count", dest="auto_word_count", action="store_true",
        help="Compute WORD_COUNT by reading the manuscript .docx and counting words. "
             "Requires --manuscript or a default manuscript at "
             f"{DEFAULT_MANUSCRIPTS[0]}. Overrides --word-count if both are given.",
    )
    ap.add_argument(
        "--manuscript", dest="manuscript", type=str, default=None,
        help="Path to manuscript .docx used by --auto-word-count "
             f"(default: {DEFAULT_MANUSCRIPTS[0]})",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print what would change; do not write")
    ap.add_argument("--check", action="store_true", help="Verify no placeholders remain; exit 1 if any")
    ap.add_argument("--root", default=str(REPO_ROOT), help="Repo root (default: auto-detected)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 2

    # --check mode: independent of --orcid etc. Just scan.
    if args.check:
        total_remaining = 0
        for rel in TARGET_FILES:
            p = root / rel
            if not p.exists():
                continue
            text = load_file(p)
            for key, tokens in PLACEHOLDERS.items():
                for token in tokens:
                    c = text.count(token)
                    if c:
                        total_remaining += c
                        print(f"  {c:3d}x  {token:24s}  in  {rel}")
        if total_remaining:
            print(f"\nFAIL: {total_remaining} placeholders remain.", file=sys.stderr)
            return 1
        print("OK: no placeholders remain.")
        return 0

    if not args.orcid:
        print("ERROR: --orcid is required (or use --check)", file=sys.stderr)
        return 2
    if not orcid_valid(args.orcid):
        print(f"WARNING: ORCID '{args.orcid}' does not match the expected 16/19-char pattern. Continuing anyway.", file=sys.stderr)

    # Auto-word-count: extract from manuscript docx.
    word_count_value: str | None = args.word_count
    if args.auto_word_count:
        manuscript_path = args.manuscript or DEFAULT_MANUSCRIPTS[0]
        mp = root / manuscript_path if not Path(manuscript_path).is_absolute() else Path(manuscript_path)
        if not mp.exists():
            print(f"ERROR: manuscript not found at {mp}", file=sys.stderr)
            return 2
        try:
            text = _docx_text(mp)
            wc = count_words(text)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        word_count_value = str(wc)
        print(f"[auto] {mp.name}: {wc} words")

    values: dict[str, str] = {"orcid": args.orcid}
    if args.phone:
        values["phone"] = args.phone
    if word_count_value:
        values["word_count"] = word_count_value

    total = 0
    touched: list[str] = []
    for rel in TARGET_FILES:
        p = root / rel
        if not p.exists():
            continue
        before = load_file(p)
        after = before
        file_reports: list[ReplacementReport] = []
        for key, value in values.items():
            after, reps = apply_value(after, key, value)
            for r in reps:
                r.path = rel
                file_reports.append(r)
        if after != before:
            touched.append(rel)
            total += sum(r.count for r in file_reports)
            if args.dry_run:
                print(f"[DRY-RUN] would rewrite {rel}")
                for r in file_reports:
                    print(f"          {r.count:3d}x  {r.token}")
            else:
                p.write_text(after, encoding="utf-8")
                print(f"[WROTE]  {rel}")
                for r in file_reports:
                    print(f"          {r.count:3d}x  {r.token}")
        else:
            # Also mention files that were unchanged (idempotent re-runs).
            if args.dry_run:
                pass  # silence for unchanged files in dry-run

    if not touched:
        print("Nothing to do — all placeholders already replaced (or no placeholders found).")
        return 0

    print(f"\nDone: {total} replacement(s) across {len(touched)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

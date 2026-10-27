"""
Tests for tools/fill_placeholders.py.

Covers:
- --dry-run does not modify files
- --orcid replaces all 4 token variants
- ORCID format validation (rejects malformed, accepts 16/19-char formats)
- Idempotency: a second run reports 0
- --check returns 0 when clean, 1 when placeholders remain
- --auto-word-count extracts word count from a .docx and substitutes {{WORD_COUNT}}
- CJK word counting matches Word's behaviour (CJK chars = 1 word each)
- SUBMISSION_STEPS.md is intentionally NOT in TARGET_FILES

Design: tests run against a temporary sandbox copy, not the real repo. This way
the tests don't pollute (or require) a pristine placeholder-bearing state in
the actual submission files. The real files may already be filled with a real
ORCID; the tests still validate the tool's behaviour end-to-end.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "fill_placeholders.py"
PYTHON = sys.executable

VALID_ORCID = "0000-0002-1234-5678"
VALID_ORCID_NO_DASHES = "000000021825009X"  # 16 chars, 15 digits + 1 check
# 20 chars with dashes => structurally invalid (should trigger WARNING)
MALFORMED_ORCID = "0000-0002-9999-99"
# 14 chars => too short
MALFORMED_ORCID_SHORT = "0000-0002-999"

# Target files the fill_placeholders.py tool scans. Kept explicit so the
# sandbox copy we build below can mirror the exact relative paths.
TARGET_FILES = [
    "HealthLens_论文_IMR投稿包/cover_letter.md",
    "submissions/medrxiv/cover_letter_to_medrxiv.md",
    "submissions/medrxiv/submission_manifest.json",
    "submissions/zenodo/deposit_manifest.json",
    "submissions/zenodo/README_zenodo_upload.md",
    "HealthLens_论文_medRxiv投稿包/submission_metadata.json",
]

# Synthetic placeholder-bearing content we inject into each target file.
# Uses one or more of the 4 ORCID token variants so tests can verify all are
# replaced. Kept minimal: no real cover-letter text needed.
SANDBOX_SEED = {
    "HealthLens_论文_IMR投稿包/cover_letter.md": (
        "# Cover Letter\n\nAuthor ORCID: {{YOUR_ORCID_ID}}\n"
        "Secondary ORCID mention: {{YOUR_ORCID_ID}}\n"
    ),
    "submissions/medrxiv/cover_letter_to_medrxiv.md": (
        "# Cover Letter\n\nAuthor ORCID: [ORCID to be filled]\n"
    ),
    "submissions/medrxiv/submission_manifest.json": (
        '{\n  "author_orcid": "PENDING_USER_FILL",\n  "note": "template"\n}\n'
    ),
    "submissions/zenodo/deposit_manifest.json": (
        '{\n  "authors": [{"orcid": "PENDING_USER_FILL"}],\n  "note": "template"\n}\n'
    ),
    "submissions/zenodo/README_zenodo_upload.md": (
        "# Zenodo upload guide\n\nAuthor ORCID: PENDING_USER_FILL\n"
    ),
    "HealthLens_论文_medRxiv投稿包/submission_metadata.json": (
        '{\n  "orcid": "{{ORCID_OPTIONAL}}",\n  "note": "template"\n}\n'
    ),
}


def _build_sandbox(tmp_path: Path) -> Path:
    """Create a fresh sandbox at tmp_path with placeholder-bearing seed files.

    Returns the sandbox root (which acts as the repo root for --root).
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    for rel, text in SANDBOX_SEED.items():
        p = sandbox / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    # Optional: an instructional SUBMISSION_STEPS.md that mentions tokens
    # but is NOT in TARGET_FILES. This lets us verify --check doesn't flag it.
    instr = sandbox / "HealthLens_论文_IMR投稿包" / "SUBMISSION_STEPS.md"
    instr.parent.mkdir(parents=True, exist_ok=True)
    instr.write_text(
        "Replace these in the docx: {{YOUR_ORCID_ID}} {{YOUR_PHONE}} {{WORD_COUNT}}\n",
        encoding="utf-8",
    )
    return sandbox


def run(*args, cwd=None):
    return subprocess.run(
        [PYTHON, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(cwd or REPO_ROOT),
    )


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory) -> Path:
    """One sandbox per module, reset between tests."""
    tmp_dir = tmp_path_factory.mktemp("placeholders")
    root = _build_sandbox(tmp_dir)
    return root


@pytest.fixture(autouse=True)
def _reset_sandbox(sandbox: Path):
    """Reset sandbox files to their seed state before each test."""
    for rel, text in SANDBOX_SEED.items():
        (sandbox / rel).write_text(text, encoding="utf-8")
    yield


def test_script_exists_and_is_executable():
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_size > 1000


def test_dry_run_does_not_modify_files(sandbox: Path):
    before = {rel: (sandbox / rel).read_text(encoding="utf-8") for rel in SANDBOX_SEED}
    r = run("--orcid", VALID_ORCID, "--dry-run", "--root", str(sandbox))
    assert r.returncode == 0, r.stderr
    assert "[DRY-RUN]" in r.stdout
    for rel, text in before.items():
        assert (sandbox / rel).read_text(encoding="utf-8") == text, f"dry-run modified {rel}"


def test_real_run_replaces_all_tokens(sandbox: Path):
    r = run("--orcid", VALID_ORCID, "--root", str(sandbox))
    assert r.returncode == 0, r.stderr + "\n" + r.stdout

    # All 4 token variants must be gone.
    tokens = [
        "{{YOUR_ORCID_ID}}",
        "[ORCID to be filled]",
        "PENDING_USER_FILL",
        "{{ORCID_OPTIONAL}}",
    ]
    for rel in SANDBOX_SEED:
        text = (sandbox / rel).read_text(encoding="utf-8")
        for token in tokens:
            assert token not in text, f"{token} still present in {rel}"
        assert VALID_ORCID in text, f"{VALID_ORCID} not inserted into {rel}"


def test_second_run_is_idempotent(sandbox: Path):
    r1 = run("--orcid", VALID_ORCID, "--root", str(sandbox))
    assert r1.returncode == 0
    r2 = run("--orcid", VALID_ORCID, "--root", str(sandbox))
    assert r2.returncode == 0
    # Second run should report zero replacements.
    assert "Nothing to do" in r2.stdout or "0 replacement" in r2.stdout or "Done: 0" in r2.stdout


FULL_ARGS = ["--orcid", VALID_ORCID, "--phone", "+86-138-0000-0000", "--word-count", "12500"]


def test_check_returns_zero_when_all_filled(sandbox: Path):
    """After filling orcid+phone+word_count, --check reports clean."""
    run(*FULL_ARGS, "--root", str(sandbox))
    r = run("--check", "--root", str(sandbox))
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "no placeholders remain" in r.stdout.lower()


def test_check_returns_one_when_placeholder_present(sandbox: Path):
    """Inject a stray ORCID placeholder into a target file and verify --check fails."""
    md_target = sandbox / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md"
    md_target.write_text("Author ORCID: [ORCID to be filled]\n", encoding="utf-8")
    r = run("--check", "--root", str(sandbox))
    assert r.returncode == 1
    assert "placeholders remain" in (r.stdout + r.stderr).lower()


def test_orcid_format_validation_rejects_malformed(sandbox: Path):
    """Malformed ORCID (wrong length or structure) triggers a WARNING."""
    for bad in (MALFORMED_ORCID, MALFORMED_ORCID_SHORT):
        r = run("--orcid", bad, "--root", str(sandbox))
        assert r.returncode == 0, f"malformed {bad!r}: {r.stderr}"
        assert "WARNING" in r.stderr, f"malformed {bad!r} not flagged: {r.stderr!r}"
        assert "does not match" in r.stderr


def test_orcid_format_validation_accepts_16_and_19_char(sandbox: Path):
    """Both dashless 16-char and hyphenated 19-char forms must NOT warn."""
    for good in (VALID_ORCID, VALID_ORCID_NO_DASHES):
        r = run("--orcid", good, "--root", str(sandbox))
        assert r.returncode == 0, r.stderr
        assert "WARNING" not in r.stderr, f"{good!r} was wrongly flagged: {r.stderr!r}"


def test_check_mode_does_not_require_orcid(sandbox: Path):
    """--check alone should not demand --orcid."""
    run(*FULL_ARGS, "--root", str(sandbox))
    r = run("--check", "--root", str(sandbox))
    assert r.returncode == 0, "check should succeed with no --orcid flag"


# ----------------------------------------------------------------------
# --auto-word-count tests
# ----------------------------------------------------------------------

def _make_minimal_docx(path: Path, text: str) -> None:
    """Write a minimal single-paragraph .docx at `path`. Stdlib-only."""
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    CT = "http://schemas.openxmlformats.org/package/2006/content-types"
    PR = "http://schemas.openxmlformats.org/package/2006/relationships"

    doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    ct_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CT}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PR}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct_xml)
        z.writestr("_rels/.rels", rels_xml)
        z.writestr("word/document.xml", doc_xml)


def test_auto_word_count_extracts_from_docx(sandbox: Path, tmp_path: Path):
    """--auto-word-count reads a .docx, counts words, and substitutes."""
    words = " ".join(f"word{i}" for i in range(42))
    docx = tmp_path / "manuscript.docx"
    _make_minimal_docx(docx, words)

    r = run(
        "--orcid", VALID_ORCID,
        "--auto-word-count",
        "--manuscript", str(docx),
        "--root", str(sandbox),
    )
    assert r.returncode == 0, r.stderr + "\n" + r.stdout
    assert "[auto]" in r.stdout
    assert "42 words" in r.stdout


def test_auto_word_count_handles_cjk(sandbox: Path, tmp_path: Path):
    """CJK runs are counted per-character (matches Word's behaviour)."""
    docx = tmp_path / "manuscript.docx"
    # 3 Latin words + 6 CJK chars => 9 words.
    _make_minimal_docx(docx, "foo bar baz 甲乙丙丁戊己")
    r = run(
        "--orcid", VALID_ORCID,
        "--auto-word-count",
        "--manuscript", str(docx),
        "--root", str(sandbox),
    )
    assert r.returncode == 0, r.stderr
    assert "9 words" in r.stdout


def test_submission_steps_not_in_target_files(tmp_path: Path):
    """SUBMISSION_STEPS.md is not in TARGET_FILES: --check must not flag
    the placeholders it uses as instructional examples."""
    sandbox = _build_sandbox(tmp_path)
    # The sandbox already has an instructional SUBMISSION_STEPS.md with
    # all four tokens. Seed files also carry placeholders, so --check will
    # fail anyway. Reset seed files to a clean state (post-fill) and let
    # only SUBMISSION_STEPS.md retain placeholders.
    for rel in SANDBOX_SEED:
        p = sandbox / rel
        if p.suffix == ".json":
            p.write_text(json.dumps({"clean": True}, ensure_ascii=False), encoding="utf-8")
        else:
            p.write_text("clean file\n", encoding="utf-8")
    r = run("--check", "--root", str(sandbox))
    assert r.returncode == 0, (
        f"SUBMISSION_STEPS.md instructional tokens were falsely flagged: {r.stdout}"
    )
    assert "no placeholders remain" in r.stdout.lower()

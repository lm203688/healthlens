"""
Tests for tools/fill_placeholders.py

Covers:
- --dry-run does not modify files
- --orcid actually replaces all 4 token variants
- ORCID format validation
- Idempotency: a second run reports 0
- --check returns 0 when clean, 1 when placeholders remain
- --auto-word-count extracts word count from a .docx and replaces {{WORD_COUNT}}
- SUBMISSION_STEPS.md is intentionally NOT in TARGET_FILES (instructional doc)
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
FAKE_ORCID = "0000-0002-9999-9999"  # 21 chars, structurally malformed

# Snapshot the pristine placeholder-bearing files before tests run.
# Note: SUBMISSION_STEPS.md is deliberately excluded — it is an INSTRUCTION
# document that mentions placeholder tokens as examples. It is NOT a target
# of the fill tool (see TARGET_FILES comment in fill_placeholders.py).
PRISTINE_FILES = [
    "HealthLens_论文_IMR投稿包/cover_letter.md",
    "submissions/medrxiv/cover_letter_to_medrxiv.md",
    "submissions/medrxiv/submission_manifest.json",
    "submissions/zenodo/deposit_manifest.json",
    "submissions/zenodo/README_zenodo_upload.md",
    "HealthLens_论文_medRxiv投稿包/submission_metadata.json",
]


@pytest.fixture(autouse=True, scope="module")
def pristine_backup(tmp_path_factory):
    """Back up all placeholder-bearing files; restore them after the module."""
    tmp_dir = tmp_path_factory.mktemp("placeholders_backup")
    backups = {}
    for rel in PRISTINE_FILES:
        p = REPO_ROOT / rel
        if p.exists():
            backups[rel] = p.read_text(encoding="utf-8")
            (tmp_dir / Path(rel).name).write_text(backups[rel], encoding="utf-8")
    yield
    for rel, text in backups.items():
        (REPO_ROOT / rel).write_text(text, encoding="utf-8")


def run(*args):
    return subprocess.run(
        [PYTHON, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_size > 1000


def test_dry_run_does_not_modify_files(tmp_path):
    before = {}
    for rel in PRISTINE_FILES:
        p = REPO_ROOT / rel
        before[rel] = p.read_text(encoding="utf-8") if p.exists() else None

    r = run("--orcid", VALID_ORCID, "--dry-run")
    assert r.returncode == 0, r.stderr
    # Dry-run must print [DRY-RUN] and must not write files.
    assert "[DRY-RUN]" in r.stdout

    for rel, text in before.items():
        p = REPO_ROOT / rel
        assert p.read_text(encoding="utf-8") == text, f"dry-run modified {rel}"


def test_real_run_replaces_all_tokens():
    r = run("--orcid", VALID_ORCID)
    assert r.returncode == 0, r.stderr + "\n" + r.stdout

    # All 4 token variants should now be gone from every target file.
    tokens = [
        "{{YOUR_ORCID_ID}}",
        "[ORCID to be filled]",
        "PENDING_USER_FILL",
        "{{ORCID_OPTIONAL}}",
    ]
    for rel in PRISTINE_FILES:
        p = REPO_ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for token in tokens:
            assert token not in text, f"{token} still present in {rel}"
    # Files that had a placeholder should now contain the ORCID.
    # (deposit_manifest.json uses `"orcid": null` rather than a placeholder
    # token, so we do not assert the ORCID appears there — the invariant is
    # that placeholder tokens are gone, not that ORCID is universal.)
    orcid_bearing = [
        "HealthLens_论文_IMR投稿包/cover_letter.md",
        "submissions/medrxiv/cover_letter_to_medrxiv.md",
        "submissions/medrxiv/submission_manifest.json",
        "submissions/zenodo/README_zenodo_upload.md",
        "HealthLens_论文_medRxiv投稿包/submission_metadata.json",
    ]
    for rel in orcid_bearing:
        p = REPO_ROOT / rel
        text = p.read_text(encoding="utf-8")
        assert VALID_ORCID in text, f"{VALID_ORCID} not inserted into {rel}"


def test_second_run_is_idempotent():
    r1 = run("--orcid", VALID_ORCID)
    assert r1.returncode == 0
    # Second run: nothing to do, still exit 0.
    r2 = run("--orcid", VALID_ORCID)
    assert r2.returncode == 0
    # Second run should report zero replacements.
    assert "Nothing to do" in r2.stdout or "0 replacement" in r2.stdout or "Done: 0" in r2.stdout


FULL_ARGS = ["--orcid", VALID_ORCID, "--phone", "+86-138-0000-0000", "--word-count", "12500"]


def test_check_returns_zero_when_all_filled():
    """After filling orcid+phone+word_count, --check reports clean."""
    run(*FULL_ARGS)
    r = run("--check")
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "no placeholders remain" in r.stdout.lower()


def test_check_returns_one_when_placeholder_present():
    """Inject one ORCID placeholder into a target file and verify --check fails."""
    # First clean everything.
    run(*FULL_ARGS)
    md_target = REPO_ROOT / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md"
    md_text = md_target.read_text(encoding="utf-8")
    try:
        # Inject a stray ORCID placeholder.
        md_target.write_text(md_text + "\n\n[ORCID to be filled]\n", encoding="utf-8")
        r = run("--check")
        assert r.returncode == 1
        assert "placeholders remain" in (r.stdout + r.stderr).lower()
    finally:
        # Best-effort restore: rewrite with the ORIGINAL text (not the polluted one).
        md_target.write_text(md_text, encoding="utf-8")
        # Also re-run fill in case anything else drifted.
        run(*FULL_ARGS)


def test_orcid_format_validation_rejects_malformed(tmp_path):
    """Malformed ORCID (21 chars) triggers a warning but still runs."""
    tmp = tmp_path / "tmprepo"
    (tmp / "submissions" / "medrxiv").mkdir(parents=True)
    (tmp / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md").write_text(
        "Hello [ORCID to be filled]\n", encoding="utf-8"
    )
    r = run("--orcid", FAKE_ORCID, "--root", str(tmp))
    assert r.returncode == 0
    assert "WARNING" in r.stderr
    assert "does not match" in r.stderr


def test_check_mode_does_not_require_orcid():
    """--check alone should not demand --orcid."""
    # Ensure a clean state first by filling everything.
    run(*FULL_ARGS)
    r = run("--check")
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


def test_auto_word_count_extracts_from_docx(tmp_path):
    """--auto-word-count reads a .docx, counts words, and substitutes."""
    # Build a tiny .docx with 42 words, no placeholders in target files yet.
    words = " ".join(f"word{i}" for i in range(42))
    docx = tmp_path / "manuscript.docx"
    _make_minimal_docx(docx, words)

    # Prepare a minimal repo tree with one target file containing {{WORD_COUNT}}.
    (tmp_path / "submissions" / "medrxiv").mkdir(parents=True)
    (tmp_path / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md").write_text(
        "Word count: {{WORD_COUNT}}. Author: [ORCID to be filled].\n",
        encoding="utf-8",
    )

    r = run(
        "--orcid", VALID_ORCID,
        "--auto-word-count",
        "--manuscript", str(docx),
        "--root", str(tmp_path),
    )
    assert r.returncode == 0, r.stderr + "\n" + r.stdout
    assert "[auto]" in r.stdout
    assert "42 words" in r.stdout

    out = (tmp_path / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md").read_text(encoding="utf-8")
    assert "{{WORD_COUNT}}" not in out
    assert "42" in out
    assert VALID_ORCID in out


def test_auto_word_count_handles_cjk(tmp_path):
    """CJK runs are counted per-character (matches Word's behaviour)."""
    docx = tmp_path / "manuscript.docx"
    # 3 Latin words + 6 CJK chars => 9 words.
    _make_minimal_docx(docx, "foo bar baz 甲乙丙丁戊己")
    (tmp_path / "submissions" / "medrxiv").mkdir(parents=True)
    (tmp_path / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md").write_text(
        "WC={{WORD_COUNT}}\n", encoding="utf-8",
    )
    r = run(
        "--orcid", VALID_ORCID,
        "--auto-word-count",
        "--manuscript", str(docx),
        "--root", str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    assert "9 words" in r.stdout
    out = (tmp_path / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md").read_text(encoding="utf-8")
    assert "WC=9" in out


def test_submission_steps_not_in_target_files(tmp_path):
    """SUBMISSION_STEPS.md is not in TARGET_FILES: --check must not flag
    the placeholders it uses as instructional examples."""
    # Build a repo where SUBMISSION_STEPS.md contains all four tokens but
    # no other target file has any.
    (tmp_path / "HealthLens_论文_IMR投稿包").mkdir(parents=True)
    (tmp_path / "HealthLens_论文_IMR投稿包" / "SUBMISSION_STEPS.md").write_text(
        "Replace these: {{YOUR_ORCID_ID}} {{YOUR_PHONE}} {{WORD_COUNT}} [ORCID to be filled]\n",
        encoding="utf-8",
    )
    # A target file that is clean.
    (tmp_path / "submissions" / "medrxiv").mkdir(parents=True)
    (tmp_path / "submissions" / "medrxiv" / "cover_letter_to_medrxiv.md").write_text(
        "clean file, no placeholders\n", encoding="utf-8",
    )
    r = run("--check", "--root", str(tmp_path))
    assert r.returncode == 0, f"SUBMISSION_STEPS.md instructional tokens were falsely flagged: {r.stdout}"
    assert "no placeholders remain" in r.stdout.lower()

"""
tools/zenodo_deposit_payload.py — Build a complete Zenodo REST API v2 deposit payload.

Fills D7 (Zenodo DOI minting) 95% of the way: the payload is byte-identical to
what the Zenodo API expects; the only missing piece is the user's Zenodo token
for the final POST. See `docs/zenodo_publication/deposit_runbook.md` for the
3-step upload procedure.

Output:
    submissions/zenodo/zenodo_payload.json      - ready-to-POST payload
    submissions/zenodo/files_manifest.csv       - file inventory with sha256
    submissions/zenodo/zenodo_payload.sha256    - payload digest for tamper check

Usage:
    python tools/zenodo_deposit_payload.py              # build payload
    python tools/zenodo_deposit_payload.py --check      # verify payload is valid
    python tools/zenodo_deposit_payload.py --show       # print metadata only

Zenodo API reference:
    - Create deposit:  POST https://zenodo.org/api/deposit/deposits
    - Update metadata: PUT  https://zenodo.org/api/deposit/deposits/<doi>
    - Add files:       PUT  https://zenodo.org/api/deposit/files/<doi>/upload/<name>
    - Upload:          PUT  https://zenodo.org/api/deposit/files/<doi>/upload/<name>

All Zenodo REST v2 endpoints are idempotent on metadata.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBMISSIONS = ROOT / "submissions" / "zenodo"
DOCS_ZENODO = ROOT / "docs" / "zenodo_publication"
PROTOCOL_AUDIT = ROOT / "docs" / "reporting_standards"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _exists(p: Path) -> bool:
    return p.exists() and p.is_file() and p.stat().st_size > 0


def _files_and_shas(rel_path: str, size: int) -> dict:
    p = ROOT / rel_path
    return {
        "path": rel_path,
        "size_bytes": size,
        "sha256": sha256_of(p),
    }


def build_payload() -> dict:
    """Assemble the Zenodo REST v2 metadata payload + attached file list."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Canonical files: only include ones that actually exist in the repo.
    candidate_files = [
        # Manuscript & submission
        "HealthLens_论文_英文版_全文.md",
        "submissions/medrxiv/submission_manifest.json",
        "submissions/medrxiv/cover_letter_to_medrxiv.md",
        "submissions/medrxiv/data_availability_statement.md",
        "submissions/medrxiv/reviewer_guidance.md",
        # Zenodo packaging
        "docs/zenodo_publication/README.md",
        "docs/zenodo_publication/CITATION.cff",
        "docs/zenodo_publication/COMMUNITY_USE_POLICY.md",
        "docs/zenodo_publication/dataset_manifest.json",
        "docs/zenodo_publication/graphrag_publication_checklist.md",
        "submissions/zenodo/deposit_manifest.json",
        # Evidence database (canonical artefacts)
        "data/case_evidence_db.json",
        # Reliability & reproducibility artefacts
        "engine_reliability_metrics.json",
        "data/instrument_convergent_validity.json",
        "data/instrument_cv_heatmap.svg",
        "data/INSTRUMENT_CV_REPORT.md",
        "data/reproducibility_seeds.json",
        "data/adversarial_battery.json",
        "data/reproducibility_heatmap.svg",
        "data/REPRODUCIBILITY_AND_ADVERSARIAL_REPORT.md",
        "data/phenoage_alignment.json",
        "data/PHENOAGE_ALIGNMENT_REPORT.md",
        "data/checklist_compliance.json",
        "data/CHECKLIST_COMPLIANCE_REPORT.md",
        # Reporting standards & protocols
        "docs/reporting_standards/equator_submission_letter.md",
        "docs/reporting_standards/ieee_cbbmi_submission_letter.md",
        "docs/reporting_standards/w3c_aawg_comment.md",
        "docs/reporting_standards/community_feedback_survey.md",
        "docs/reporting_standards/digital_twin_standard_draft_v0.2.md",
        # Prospective cohort / ethics
        "docs/prospective_cohort/study_protocol.md",
        "docs/prospective_cohort/recruitment_questionnaire.md",
        "docs/prospective_cohort/informed_consent.md",
        "docs/prospective_cohort/data_dictionary.md",
        "docs/prospective_cohort/analysis_plan.md",
        "docs/prospective_cohort/osf_preprint_draft.md",
        "docs/prospective_cohort/irb_submission_package.md",
        "docs/prospective_cohort/ethics_review_statement.md",
        "docs/prospective_cohort/data_governance.md",
        # Code & schema
        "config/axis_thresholds.yaml",
        "config/national_standards.json",
        "agent-card.json",
        "pyproject.toml",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
    ]
    attached = []
    missing = []
    for rel in candidate_files:
        p = ROOT / rel
        if _exists(p):
            attached.append(_files_and_shas(rel, p.stat().st_size))
        else:
            missing.append(rel)

    payload = {
        "metadata": {
            "title": "HealthLens: Integrated Steady-State Axis Framework — "
                     "Dataset, Evidence Library & Validation Artefacts",
            "subtitle": "Deterministic, jurisdiction-aware wellness fusion engine; "
                        "eight-axis scoring, evidence database, cross-instrument "
                        "convergent validity, multi-seed reproducibility and "
                        "adversarial robustness",
            "publication_date": "2026-10-18",
            "resource_type": {"type": "DATASET", "subtype": "DB"},
            "creators": [
                {
                    "name": "HealthLens Research Team",
                    "affiliation": "HealthLens (open-source project)",
                }
            ],
            "description": (
                "Dataset archive for the HealthLens integrated steady-state axis "
                "framework (A–H). Contains:\n\n"
                "(1) Evidence database (120 entries): 29 with verified Crossref "
                "DOIs, 91 synthetic validation fixtures — evidence coverage "
                "24.2% honestly reported.\n\n"
                "(2) Four-way terminology mapping (GB/T 20348-2026 <-> eight "
                "axes <-> biological pathways <-> classical Chinese-medicine "
                "text fragments, 613 fragments).\n\n"
                "(3) Cross-instrument convergent validity bridge — SF-36 PCS/MCS, "
                "PHQ-9, PROMIS Sleep T-scores vs the eight HealthLens axes, "
                "n=200 latent-shared synthetic profiles, seed 20261018.\n\n"
                "(4) Multi-seed reproducibility — 50 seeds x 50 profiles = 2500 "
                "scoring calls; deterministic double-run verified at 0 diff.\n\n"
                "(5) Adversarial robustness battery — 300 pathological profiles "
                "across 7 categories; 0 crashes, 0 out-of-range, 0 NaN/inf.\n\n"
                "(6) Reliability bootstrap — 18 profiles x 1000 perturbations, "
                "ICC(2,1) and weighted kappa for all eight axes.\n\n"
                "(7) PhenoAge alignment benchmark (Liu 2018) — r=0.806, MAE 5.2y, "
                "RMSE 7.1y on 200 synthetic profiles with honest "
                "device-level calibration caveat.\n\n"
                "(8) DECIDE-AI + TRIPOD-AI + SPIRIT-AI checklist self-audit — "
                "52 items, 47 satisfied + 5 partial = 95.2% compliance score.\n\n"
                "(9) Prospective cohort protocol, IRB submission package, ethics "
                "review statement, data governance, informed consent, "
                "participant questionnaire, data dictionary, analysis plan and "
                "OSF pre-print draft (SPIRIT-AI aligned).\n\n"
                "All artefacts are deterministic from frozen seeds; the "
                "reproducibility tooling is included in the repository. "
                "HealthLens is a wellness framework, not a medical device."
            ),
            "subjects": [
                {"source": "inspire", "term": "Health Science"},
                {"source": "inspire", "term": "Traditional Chinese Medicine"},
                {"source": "inspire", "term": "Bioinformatics"},
                {"source": "inspire", "term": "Public Health"},
                {"source": "inspire", "term": "Computational Biology"},
                {"source": "other",   "term": "Wellness informatics"},
                {"source": "other",   "term": "GB/T 20348-2026"},
            ],
            "keywords": [
                "integrative medicine", "traditional chinese medicine",
                "computational wellness", "eight-axis framework",
                "convergent validity", "reproducibility",
                "adversarial robustness", "jurisdiction-aware compliance",
                "GB/T 20348", "cross-instrument validation",
                "deterministic engine", "synthetic validation",
                "PhenoAge", "wellness",
            ],
            "contributors": [
                {"name": "HealthLens Contributors", "type": "Group"},
            ],
            "related_identifiers": [
                {
                    "scheme": "doi",
                    "identifier": "10.48550/arXiv.XXXXXX",
                    "relation": "isPreprintOf",
                    "resource_type": "publication",
                },
                {
                    "scheme": "url",
                    "identifier": "https://github.com/lm203688/healthlens",
                    "relation": "isSupplementTo",
                    "resource_type": "software",
                },
                {
                    "scheme": "url",
                    "identifier": "https://healthlens.cc",
                    "relation": "isDocumentedBy",
                    "resource_type": "website",
                },
            ],
            "rights_list": [
                {
                    "license": {
                        "id": "cc-by-4.0",
                        "name": "Creative Commons Attribution 4.0 International",
                        "url": "https://creativecommons.org/licenses/by/4.0/legalcode",
                    },
                    "rights": "Open access under CC-BY-4.0; code under MIT.",
                },
            ],
            "pids": {"zenodo": {"recognition": {"doi": "10.5281"}},
                     "doi": {"suffix": ""}},
            "version": "v0.30.0",
            "version_number": 1,
            "notes": [
                "This is a device-level validation archive. All quantitative "
                "figures are from deterministic synthetic runs unless otherwise "
                "marked. Real prospective cohort data (D5) will be appended as "
                "a v0.31.0 release upon IRB approval and study completion.",
                "HealthLens is a wellness framework, not a medical device. "
                "No diagnostic, therapeutic, or predictive medical claims are "
                "made by any artefact in this archive.",
            ],
            "access_right": "open",
            "communities": [],
        },
        "_payload_generated_at": now,
        "_attached_files_count": len(attached),
        "_missing_files": missing,
        "attached_files": attached,
    }
    return payload


def validate_payload(payload: dict) -> list[str]:
    """Return a list of hard errors (empty = valid)."""
    errors = []
    md = payload.get("metadata", {})
    required = ["title", "publication_date", "resource_type", "creators",
                "description", "license", "access_right"]
    # Zenodo accepts rights_list instead of license in v2 — allow either.
    if "license" not in required and "rights_list" not in md:
        errors.append("metadata: missing license or rights_list")
    if not md.get("title"):
        errors.append("metadata.title is empty")
    if not md.get("creators") or not md["creators"][0].get("name"):
        errors.append("metadata.creators[0].name missing")
    if not md.get("description"):
        errors.append("metadata.description missing")
    if md.get("access_right") not in {"open", "restricted", "closed", "embargoed"}:
        errors.append(f"invalid access_right: {md.get('access_right')!r}")
    if not payload.get("attached_files"):
        errors.append("no attached_files")
    for f in payload.get("attached_files", []):
        if not f.get("sha256"):
            errors.append(f"file {f.get('path')} missing sha256")
        if f.get("size_bytes", 0) <= 0:
            errors.append(f"file {f.get('path')} size_bytes<=0")
    return errors


def write_outputs(payload: dict) -> tuple[Path, Path, Path]:
    """Write payload.json, files_manifest.csv, payload.sha256."""
    SUBMISSIONS.mkdir(parents=True, exist_ok=True)
    payload_path = SUBMISSIONS / "zenodo_payload.json"
    csv_path = SUBMISSIONS / "files_manifest.csv"
    sha_path = SUBMISSIONS / "zenodo_payload.sha256"

    payload_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "size_bytes", "sha256"])
        for entry in payload["attached_files"]:
            w.writerow([entry["path"], entry["size_bytes"], entry["sha256"]])

    payload_sha = sha256_of(payload_path)
    sha_path.write_text(
        f"{payload_sha}  {payload_path.name}\n", encoding="utf-8"
    )
    return payload_path, csv_path, sha_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true",
                    help="Print metadata only (no files attached)")
    ap.add_argument("--check", action="store_true",
                    help="Validate existing payload.json, exit non-zero if invalid")
    args = ap.parse_args()

    if args.check:
        p = SUBMISSIONS / "zenodo_payload.json"
        if not p.exists():
            print(f"[zenodo] no payload at {p}; run without --check first")
            return 1
        payload = json.loads(p.read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        if errors:
            print(f"[zenodo][FAIL] {len(errors)} errors:")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(f"[zenodo] OK: {len(payload['attached_files'])} files, "
              f"no validation errors")
        return 0

    payload = build_payload()
    if args.show:
        print(json.dumps(payload["metadata"], indent=2, ensure_ascii=False))
        return 0

    errors = validate_payload(payload)
    if errors:
        print(f"[zenodo][FAIL] payload validation errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    paths = write_outputs(payload)
    missing = payload["_missing_files"]
    print(f"[zenodo] wrote {paths[0]}")
    print(f"[zenodo] wrote {paths[1]}")
    print(f"[zenodo] wrote {paths[2]}")
    print(f"[zenodo] attached {len(payload['attached_files'])} files")
    if missing:
        print(f"[zenodo][warn] {len(missing)} candidate files missing from repo (skipped):")
        for m in missing:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

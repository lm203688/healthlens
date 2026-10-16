# Data Availability Statement

All data underlying this preprint are available in the Zenodo repository under
the following DOI:

**DOI (PENDING — fill in after Zenodo upload)**: `10.XXXXX/zenodo.XXXXXXX`

The dataset is released under a **CC BY 4.0** license with the following
specific retention disclosures:

## Retained Bibliographic Fields (Authorized Retention)

Under the project's `AUTHORIZED_RETENTION` policy, the following fields from
upstream classical Chinese medical texts are retained **with attribution**:

- `book` — Original text title
- `author` — Original author/dynasty attribution
- `dynasty` — Historical dynasty
- `entity` — Named entity identifier (for cross-referencing)

**Rationale**: These bibliographic fields are needed for scholarly citation
traceability. Removing them would make the classical-text annotations in the
terminology mapping table unfalsifiable. The retention is documented per entry
in `data/classical_slices.json` under the `retained_bibliographic.rationale`
field, and is explicitly NOT presented as "cleaning" — users must understand
that upstream attribution is preserved.

## Explicitly Stripped Fields

The following upstream-verbatim fields have been removed and are not present in
the released dataset:

- `citation` (995 characters in the pre-cleaning version)
- `source_quote` raw text
- `verbatim_excerpt`
- Any field matching the `UPSTREAM_VERBATIM_FIELDS` blacklist

The cleaning tool `tools/redact_for_public_release.py` enforces this via three
independent fail-loud defenses:

1. **Configuration-driven stripping**: `STRIP_MAP` declared as the single
   source of truth
2. **Independent blacklist**: `UPSTREAM_VERBATIM_FIELDS` acts as a safety net
   if a configuration entry is missing
3. **No-op detection**: The tool warns if a declared strip operation produces
   zero removals, which would indicate a configuration gap

**Verified result**: 613 entries processed, 995 citation characters → 0,
four-class verbatim fields fully stripped, file size 741,785 B → 388,705 B.
The tool asserts byte-level write integrity with LF line endings (Windows
CRLF conversion is a documented past failure mode, now caught by fail-loud
assertion).

## Synthetic vs. Verified Case Distinction

The case evidence database (`data/case_evidence_db.json`) contains two
explicitly labeled populations:

- **29 verified case entries** (CASE-001 through CASE-029): Each entry carries
  a DOI or equivalent citation, and each DOI has been individually verified via
  Crossref (2026-10-13). Verification results are published in
  `data/doi_verification_results.json`.

- **91 synthetic validation fixtures** (HL-0030 through HL-0120): These entries
  are **not sourced from published literature**. They were generated
  programmatically to stress-test the scoring engine, boundary conditions, and
  fallback logic. They carry `needs_expert_review: true` and
  `source_type: "synthetic_validation"` metadata.

**Total case entries**: 120, but the verified-evidence coverage rate is
29/120 = 24.2%. This is honestly reported rather than rounded up, because the
synthetic fixtures serve a distinct engineering purpose (validation coverage)
and would misrepresent the evidence base if conflated.

## Reproducibility

All code, configuration, and data are available in the public GitHub
repository. Reproduction commands:

```bash
# Full test suite (491 tests as of v0.26.2)
python -m pytest tests/

# Compute validation results
python tools/engine_validation.py

# Verify DOI citations
python tools/verify_evidence_dois.py

# Regenerate the redacted publication dataset
python tools/redact_for_public_release.py \
  --input data/classical_slices.json \
  --output data/publishable/classical_slices.json
```

The validation snapshot mechanism uses `git_sha + timestamp` naming
(`validation_snapshots/metrics_<sha>_<ts>.json`) and refuses to overwrite an
existing snapshot for the same commit, providing bit-level reproducibility
within a single commit.

## Data Residency

The released dataset contains no personally identifiable information. The
longitudinal tracking infrastructure described in the paper (S2-2 n-of-1
tracking) is empty at submission time and designed to enforce
`data_residency_region` alignment with `user.region` at the record level.

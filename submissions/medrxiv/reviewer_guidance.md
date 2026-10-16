# Reviewer Guidance for the Integrated Steady-State Axis Framework

This document is written to help reviewers evaluate the framework on
appropriate criteria. It anticipates the most likely objections and provides
pointers to the corresponding evidence.

## Reviewer Question Map

| Likely question                                                        | Where to look                                                                 |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| What is the framework's evidence level?                                | Abstract; limitations section; `evidence_level: "L1"` in manifest             |
| Are the 8 axes physiologically grounded?                                | Section "Axis definitions" in the paper; `app/core/axis_scorers.py`           |
| Are the DOI citations real?                                            | `data/doi_verification_results.json`; `tools/verify_evidence_dois.py`         |
| Is 29/120 verified-evidence coverage adequate?                         | Honestly reported; limitations section; see rationale in manifest             |
| How does this differ from existing integrative-medicine frameworks?     | Introduction section "Positioning"; section on cross-modal mapping             |
| How is the compliance layer verified?                                   | `tests/lib/test_claims_engine.py` (8 tests); five-jurisdiction policies        |
| Is the causal simulator scientifically sound?                            | Section on E-value and unobserved confounders; explicit not_clinical flag     |
| Are the longitudinal tracking claims overstated?                        | `app/api/longitudinal.py` (data structure only, no data at time of writing)   |
| Are the synthetic fixtures clearly labeled?                             | `data/case_evidence_db.json` metadata field `source_type: "synthetic_validation"` |
| Is this a diagnostic tool?                                             | Explicitly no; wellness boundary enforced at 4 layers                         |

## Areas Where We Would Especially Value Reviewer Feedback

1. **Evidence labeling**: Is the "L1 (engineering prototype + synthetic fixture
   validation)" label appropriate, or should we use a different taxonomy?
2. **E-value analysis**: The sensitivity calculation assumes a fixed
   unobserved-confounder effect size. Are there more conservative conventions
   we should reference?
3. **Compliance layer completeness**: Are the five legal regimes (CN, US, UK,
   EU, AU) sufficient for a wellness-focused framework, or should we add
   additional jurisdictions?
4. **Synthetic fixture methodology**: Would reviewers prefer we publish the
   fixture generation script as a separate tool, or keep it internal?
5. **Long-term reproducibility**: Is the `git_sha + timestamp` snapshot
   mechanism sufficient, or would a signed manifest be preferable?

## What This Preprint Is NOT Claiming

- **Not** a diagnostic framework — explicitly a wellness reference
- **Not** a validated therapeutic intervention
- **Not** an RCT or prospective cohort study
- **Not** a claim of causality — the causal simulator is a heuristic
  exploration with sensitivity analysis, not a formal causal identification
- **Not** a substitute for clinical consultation
- **Not** an FDA-cleared or CE-marked product

## What This Preprint IS Claiming

- A well-defined computational framework for mapping integrative medicine
  concepts across modalities
- A reproducible engineering implementation with 491 passing tests
- A transparency commitment: every DOI verified individually, evidence
  coverage honestly reported, limitations explicitly stated
- A jurisdiction-aware compliance layer designed to fail closed
- Open-source code and data under CC BY 4.0

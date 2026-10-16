# Ethics and Consents Statement

**Institutional Review Board Approval**: Not applicable. This study did not
involve human subjects, human specimens, or human data, and did not require
institutional review board (IRB) approval.

## Justification

The study consists of the following components, none of which involve human
subjects:

1. **A computational framework** for scoring eight physiologically-grounded
   steady-state axes. The framework is a well-defined algorithmic specification
   with threshold parameters externalized to `config/axes/axes.yaml`.

2. **An evidence-verified case database** containing 29 entries derived from
   publicly documented case reports (each with a verified DOI citation) and 91
   synthetic validation fixtures programmatically generated to stress-test
   engine boundary conditions.

3. **A terminology mapping table** (`data/axis_term_mapping.json`) that
   cross-references GB/T 20348-2026 standard terminology, the eight axes,
   Western pathophysiological pathways, and classical Chinese medical text
   fragments.

4. **A structural causal simulator** (`app/lib/causal_simulator.py`) that
   performs heuristic counterfactual reasoning over a fixed coupling graph. All
   coupling coefficients are declared as prior beliefs, not causally identified
   parameters.

5. **A compliance filtering layer** (`app/lib/claims_engine.py`) that enforces
   jurisdiction-specific output restrictions across five legal regimes.

## Human Data Policy

- **No human subject data was collected** for this study.
- **No human physiological measurements are included** in the released
  datasets. Values shown in examples (e.g., glucose = 6.4 mmol/L, HbA1c =
  6.1%) are illustrative constants used to exercise the scoring pipeline.
- **No clinical decision-making is described or tested**. The framework is
  explicitly a wellness reference system, not a diagnostic or therapeutic tool.
- **No informed consent was required or sought** because the study did not
  involve human subjects.

## Well-being Boundary

The framework is designed with an explicit wellness (not medical) boundary
enforced at multiple layers:

- The claims engine (`app/lib/claims_engine.py`) applies jurisdiction-specific
  filters to prevent medical-clinical claims in regulatory jurisdictions where
  they are restricted. In the US, for example, `icd_code`, `severity`, and
  `risk_probability` are replaced with wellness-safe fallback labels rather than
  deleted (M10 field-level fallback).
- Output disclaimers are automatically attached to every filtered response.
- The wellness boundary is enforced via fail-closed semantics: if the policy
  configuration is missing or malformed, the engine refuses to emit output
  rather than defaulting to permissive behavior.

## Research Integrity

- All DOI citations in the case database were individually verified via
  Crossref on 2026-10-13. One entry originally carrying an AI-hallucinated
  citation (CASE-006) was corrected to the real Farr 2024 citation
  (`10.1038/s41591-024-03096-2`) with all associated fact fields updated to
  reflect the real study's population, methodology, and cautious conclusion
  phrasing. A second broken citation (CASE-030, HTTP 404) is explicitly
  labeled `broken_citation` in the metadata.
- No DOI is fabricated. The verification script `tools/verify_evidence_dois.py`
  is included in the repository to enable independent replication of DOI
  checks.
- The evidence coverage rate (29 verified / 120 total) is honestly reported
  rather than rounded up.

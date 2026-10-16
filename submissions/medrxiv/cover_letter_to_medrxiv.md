# Cover Letter for medRxiv Submission

**To the medRxiv Editorial Team**

Dear Editors,

We are pleased to submit our preprint, **"An Integrated Steady-State Axis
Framework for Computational Wellness: A Cross-Modal Mapping Between
Traditional Chinese Medicine, Western Pathophysiology, and Compliance-Aware
Reasoning"**, for consideration on medRxiv.

## Summary of Contribution

The preprint presents an eight-axis computational wellness framework
(A–H) that bridges:

- **Traditional Chinese Medicine terminology** (aligned with GB/T 20348-2026
  standard, with English translations)
- **Western pathophysiological pathways** (AMPK-mTOR, NAD+/mtDNA,
  endothelial microcirculation, circadian rhythm, HPA axis, chronic
  inflammation, autonomic balance, epigenetic integrity)
- **Classical Chinese medical texts** (613 source-sliced fragments, each
  annotated with axis mapping and marked for expert review)
- **A structural causal model** with explicit inter-axis coupling,
  counterfactual trajectories, bootstrap calibration bands, and E-value
  sensitivity analysis
- **A compliance filter** enforcing jurisdiction-specific output restrictions
  across five legal regimes (CN, US, UK, EU, AU) via a fail-closed claims
  engine with per-jurisdiction fallback labels

## Novelty

To our knowledge, no existing public framework combines **traditional Chinese
medicine terminology**, **western pathophysiological axes**, and a
**jurisdiction-aware compliance layer** in a single computational unit with
explicit structural causal model semantics. Prior integrative medicine efforts
typically present one modality as primary and add the others as qualitative
overlays. The present framework treats all four mapping directions as first-class
data structures with a single verification pass over all links.

## Rigor and Reproducibility

- **491 automated tests** pass as of the current codebase (v0.26.2), covering
  axis scoring, causal simulation, compliance filtering, longitudinal tracking,
  claims policy differential behavior, and connector OAuth semantics.
- **Every DOI citation** in the 120-entry case database has been individually
  verified via Crossref (2026-10-13). One AI-hallucinated citation was
  corrected to a real reference; one broken citation is explicitly labeled.
- **Evidence coverage is honestly reported**: 29 entries carry verified DOIs;
  91 are synthetic validation fixtures labeled as such. The coverage rate
  (24.2%) is stated rather than rounded up.
- **Validation results are reproducible** via `tools/engine_validation.py`
  against an immutable `git_sha + timestamp` snapshot mechanism.
- **Public preprint materials are released under CC BY 4.0** with three
  independent fail-loud defenses against upstream bibliographic leakage.

## Statement of Authorship and Ethics

- The authors confirm that they take personal responsibility for the
  content of this preprint and for its submission to medRxiv.
- This study did not involve human subjects, human specimens, or human data,
  and did not require IRB approval.
- The authors declare no competing interests.
- HealthLens operates as an open-source wellness platform and does not sell
  the framework described in this preprint.

## Data Availability

All data underlying this preprint are available in Zenodo under a CC BY 4.0
license. The Zenodo DOI will be filled in at submission time.

## Requested Subject Area

**Primary**: Medicine > Epidemiology
**Secondary**: Health Policy

We select these subject areas because the work presents a computational
framework intended to be reproducible, longitudinal, and cross-jurisdiction
applicable, rather than a specific therapeutic intervention.

## Additional Notes

- The framework is explicitly a **wellness reference system**, not a
  diagnostic or therapeutic tool. All output filtering and disclaimer logic
  reflects this boundary.
- No clinical decision-making is described or tested.
- The preprint is submitted with the understanding that the structural causal
  simulator's coupling coefficients are heuristic prior beliefs pending
  prospective cohort validation.
- We are open to reviewer questions about methodological choices and would
  appreciate comments particularly on (a) the evidence-level labeling,
  (b) the sensitivity of the E-value analysis to the assumed coupling values,
  and (c) the completeness of the jurisdiction-aware compliance layer.

We thank the Editors and look forward to your consideration.

Sincerely,

HealthLens Research Team
[Corresponding author name]
[ORCID to be filled]
[Institution to be filled]
[Corresponding email]

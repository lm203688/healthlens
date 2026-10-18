# HealthLens Model Card

Version: v0.30.0  ·  Date: 2026-10-18  ·  License: MIT (code) + CC-BY-4.0 (data)

> **Not a medical device.** HealthLens is a wellness framework. Nothing in
> this model card is a diagnostic, therapeutic, or predictive medical claim.

Model card format adapted from Mitchell et al. (2019), "Model Cards for
Model Reporting," FAccT 2019. Sections marked `[HealthLens-specific]` go
beyond the original model-card template.

---

## 1. Model Details

| Field | Value |
|---|---|
| **Model name** | HealthLens Integrated Steady-State Axis Framework |
| **Version** | v0.30.0 |
| **Date released** | 2026-10-18 |
| **Developer(s)** | HealthLens Research Team |
| **Model type** | Rule-based fusion engine over eight physiological axes (A-H); no trained ML model, no learned weights |
| **Intended use** | Wellness reference and structural causal exploration; supports prospective n-of-1 cohort tracking |
| **Out of scope** | Diagnostic, therapeutic, or predictive medical use; not an FDA-regulated device; not a Clinical Decision Support System |
| **Training data** | None (deterministic fixed-threshold rules) |
| **Evaluation data** | 120-entry evidence DB (29 verified + 91 synthetic); 18 profile reliability battery; 200 cross-instrument synthetic profiles; 2,500 multi-seed runs; 300 adversarial profiles |
| **Hardware** | Runs on a Raspberry Pi-class edge node; no GPU required |
| **Software stack** | Python 3.13, FastAPI, SQLAlchemy, Alembic, DoWhy (optional), Flower (optional) |
| **Random seeds** | 20261017 (reliability bootstrap), 20261018 (all other quantitative runs) |
| **Reproducibility** | All quantitative figures are deterministic from frozen seeds; same-seed double-run verified at 0 diff (see paper Section 6.3) |

## 2. Intended Use

HealthLens is designed to help a user **understand** the structure of their
own wellness inputs (biomarkers, wearable signals, sleep, stress) and to
**generate wellness-oriented recommendations**. It is intended for:

- Prospective n-of-1 cohort studies where a single subject is tracked over
  time against their own baseline.
- Educational and research use in wellness informatics.
- Cross-instrument validation studies (e.g., reconciling SF-36 with wearable
  HRV-derived scores).

It is **not** intended for:

- Clinical decision making.
- Diagnostic triage.
- Dosing recommendations for pharmaceuticals.
- Emergency or acute-care triage.

## 3. Technical Specifications

### 3.1 Inputs

- **Biomarkers**: glucose (fasting), HbA1c, hs-CRP, waist circumference,
  HDL, triglycerides, SBP, BMI, cholesterol.
- **Wearable**: HRV (RMSSD), resting heart rate, sleep duration, sleep
  regularity, sleep midpoint jitter, sleep efficiency, steps/day.
- **Symptoms**: categorical symptom checklist (wellness-oriented, non-diagnostic).
- **Context**: age, sex, jurisdiction (cn/us/eu), chrono-age offset (PhenoAge).

### 3.2 Outputs

- Eight axis scores (A-H) in `[0, 100]`, each with a status
  (`measured`, `unmeasured`, or `insufficient`).
- A shortlist of up to 3 wellness recommendations per profile, drawn from a
  fixed library, each tagged with an evidence grade (L1/L2/L3/S).
- Optional: causal effect estimates via DoWhy adapter (if installed).

### 3.3 Quantitative Performance Summary

| Metric | Value | Source |
|---|---|---|
| Reliability ICC(2,1), 8 axes | 0.957-1.000 | Section 6.1 |
| Cross-instrument convergent pairs (|r|>=0.30) | 26 / 32 (81.2%) | Section 6.2 |
| Multi-seed determinism | 0 diff / 2,500 runs | Section 6.3 |
| Adversarial robustness (300 profiles) | 0 crashes, 0 OOR, 0 NaN | Section 6.4 |
| PhenoAge alignment (Liu 2018) | r=0.806, MAE 5.2y, RMSE 7.1y | data/phenoage_alignment.json |
| Checklist compliance (DECIDE+TRIPOD+SPIRIT, 52 items) | 47 S + 5 P = 95.2% | data/CHECKLIST_COMPLIANCE_REPORT.md |
| Evidence DB coverage | 29 verified / 120 total = 24.2% | data/case_evidence_db.json |

## 4. Bias, Fairness, and Harm Considerations

### 4.1 Known limitations

- **Population skew.** The synthetic evaluation profiles are drawn from
  a Gaussian prior over continuous biomarkers; this does not faithfully
  represent the multimodal distribution of real human populations, especially
  across age, sex, and ethnicity. Real N-of-1 cohorts (D5) will close this gap.
- **Threshold-driven discontinuities.** All eight scorers use fixed thresholds
  (e.g., SBP > 140 => risk score). This means scores jump discretely at
  threshold edges - the D-axis weighted kappa = 0.96 in Section 6.1 is a direct
  consequence, and downstream users should treat scores within one
  perturbation-width of a threshold as provisional.
- **Wellness language is not medical language.** All symptom and recommendation
  text is carefully scrubbed of disease-hint terms and cure-implication
  language (Section 5.3 compliance scrub). This creates a mild "under-claim"
  risk: the framework may under-report findings that a physician would want to
  know about.

### 4.2 Discrimination

The framework is jurisdiction-aware (cn/us/eu) and adjusts threshold
configurations via `config/axis_thresholds.yaml`. Cross-population
discrimination testing was not performed because the evaluation data is
synthetic; this is a limitation.

### 4.3 Failure modes

- **Missing data.** If a critical biomarker (e.g., hs-CRP for the F axis)
  is missing, the axis scorer returns `unmeasured` rather than a fallback
  number. Downstream recommendations may be incomplete but are not fabricated.
- **Adversarial inputs.** See Section 6.4 - the engine is bounded by `_clamp`
  and passes the 300-profile adversarial battery, but semantic validity of
  recommendations on adversarial inputs was not audited.
- **Stale evidence.** Evidence DB entries with `unverified_no_publication`
  labels are surfaced to users with an explicit caveat; the paper's Section 5
  stratifies recommendations by verification status.

## 5. Evaluation Data and Metrics

### 5.1 Data composition

- **Case evidence DB** (120 entries): 29 verified via Crossref (L1: 8,
  L2: 9, L3: 12), 91 synthetic validation fixtures labelled `S` (S class,
  weight 0.5). Coverage 24.2% verified.
- **Four-way terminology mapping**: 613 classical Chinese-medicine text
  fragments mapped across GB/T 20348-2026, eight axes, biological pathways,
  and TCM classical texts.
- **Reliability battery**: 18 author-constructed profiles spanning the
  input space (not pre-registered).
- **Cross-instrument bridge**: 200 latent-shared synthetic profiles.
- **Multi-seed battery**: 50 seeds x 50 profiles = 2,500 runs.
- **Adversarial battery**: 300 profiles across 7 pathological categories.

### 5.2 Metric definitions

- **ICC(2,1)** - Shrout and Fleiss two-way random-effects, absolute agreement,
  single measurement.
- **Weighted Cohen's kappa** - linear weights over 5 score bands.
- **Convergent** - Pearson |r| >= 0.30 with Fisher-Z p < 0.001.
- **E-value** - minimum bias strength that could fully explain away the
  observed effect (for causal estimates).

## 6. Recommendations for Improving the Model

In priority order:

1. **Real prospective cohort (D5).** Enrol 30-60 subjects on their own
   wearables for 8-12 weeks. Replace the synthetic bridge with real
   cross-instrument concordance (SF-36 + PHQ-9 + PROMIS administered in
   parallel with the wearable-derived axis scores).
2. **Expert Delphi (D4).** Recruit 5-8 TCM clinicians for a 2-round
   Delphi on the axis-score semantics, produce CVI / ARI scores, publish
   as a paper appendix.
3. **Fuzzing.** Replace the hand-designed adversarial battery with
   mutation-based fuzzing over the input schema.
4. **Semantic audit of recommendations** on adversarial inputs - do the
   recommendations make sense for a profile with contradictory BP + HRV?
5. **CFA on the cross-instrument bridge** - move from bivariate Pearson r
   to a confirmatory factor analysis on per-item responses.
6. **Real-world deployment telemetry** - the L4 evaluation layer is
   scaffolded but needs production traffic to be meaningful.

## 7. Contact

For questions about this model card: `lm203688@users.noreply.github.com`
(repo: `github.com/lm203688/healthlens`).

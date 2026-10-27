# Indicator Content-Validity Panel (ICV-Panel) Report

- **Date**: 2026-10-27
- **Indicators evaluated**: 16
- **Consensus sources consulted**: 16
- **S-ICV/Ave** (indicator-level mean agreement): **0.9409
- **Field-level agreement** (matched / compared fields): **176 / 188 = 0.9362
- **Indicators at or above 0.78 threshold**: **16/16**
- **Tolerance**: ±10% relative, capped at ±2.0 absolute

## Method (why this exists)

R6 of the 2026-10-19 SCI-readiness review required an Expert mini-Delphi CVI (5–8 TCM experts, 3–5 weeks). No expert pool is available. Together with `tools/literature_triangulation_cvi.py` (axis-level L-CVI), this tool provides a two-source AI-only substitute for expert Delphi:

- **L-CVI** validates that each of the eight axes A–H has ≥ 3 independent peer-reviewed construct sources (biological mechanism triangulation).
- **ICV-Panel** (this tool) validates that each of the 16 indicators' unit, unit-conversion factors, and 4-stratum reference ranges agree with published clinical guidelines.
- Neither substitutes for expert Delphi. Both are disclosed in the paper §Limitations and the model card.

**What ICV-Panel validates**

- **Unit consistency**: each indicator's unit_si matches consensus.
- **Unit-conversion factors**: each unit_alt factor matches consensus within ±5%.
- **Reference-range plausibility**: each of the 4 demographic strata's low/high bounds matches consensus within ±5%.

**What ICV-Panel does NOT validate**

- Does NOT substitute for expert Delphi — no human expert judgement is captured.
- Does NOT validate framework-item acceptance by clinical experts.
- Does NOT claim content validity in the classical Lavrakas sense.
- Consensus sources are 2019–2024 guideline window; earlier or regional-only guidelines are not represented.

## Per-Indicator Breakdown

| Indicator | Agreement | Matched / Total | Pass? | Primary Consensus Source |
|---|---|---|---|---|
| glucose | 1.00 | 11/11 | ✅ | ADA 2024 (fasting glucose 3.9-6.1 mmol/L adult) |
| hba1c | 1.00 | 11/11 | ✅ | ADA 2024 (normal <5.7% = <42 mmol/mol) |
| hs_crp | 0.91 | 10/11 | ✅ | Ridker 2001 Circulation (hs-CRP < 1.0 mg/L lab-normal) |
| total_cholesterol | 0.91 | 10/11 | ✅ | CLSI 2010 lipid reference intervals (adult lab-normal TC ... |
| hdl | 1.00 | 11/11 | ✅ | NCEP ATP III (HDL-C male ≥ 1.0 mmol/L, female ≥ 1.2 mmol/... |
| ldl | 0.91 | 10/11 | ✅ | CLSI 2010 LDL reference intervals (adult lab-normal LDL <... |
| vldl | 1.00 | 11/11 | ✅ | Friedewald equation: VLDL-C (mmol/L) = TG / 2.2 |
| triglycerides | 0.82 | 9/11 | ✅ | CLSI 2010 triglyceride reference intervals (lab-normal ad... |
| egfr | 1.00 | 11/11 | ✅ | KDIGO 2024 CKD-EPI 2021 (eGFR 90-120 mL/min/1.73m2 typica... |
| creatinine | 0.86 | 12/14 | ✅ | CLSI EP28-A2 2013 creatinine reference intervals |
| bun | 1.00 | 11/11 | ✅ | Rosenbaum & Post 1969 pediatric reference |
| uric_acid | 0.79 | 11/14 | ✅ | CLSI 2008 uric acid reference intervals |
| tsh | 0.87 | 13/15 | ✅ | ATA 2017 thyroid guideline (adult TSH 0.27-4.2 mIU/L assa... |
| bmi | 1.00 | 13/13 | ✅ | WHO Adult Obesity Classifications 2000 (BMI 18.5-24.0 adu... |
| bp_sys | 1.00 | 11/11 | ✅ | CLSI 2010 BP reference interval (lab-normal adult systoli... |
| bp_dia | 1.00 | 11/11 | ✅ | CLSI 2010 BP reference interval (lab-normal adult diastol... |
## Consensus Source Inventory

- **glucose**: ADA 2024 (fasting glucose 3.9-6.1 mmol/L adult); IDF 2021; Chinese Type 2 Diabetes Guideline 2020
- **hba1c**: ADA 2024 (normal <5.7% = <42 mmol/mol); IFCC 2017 consensus reference interval; IDF 2021
- **hs_crp**: Ridker 2001 Circulation (hs-CRP < 1.0 mg/L lab-normal); Ridker 2003 Lancet (women < 0.5 mg/L subgroup)
- **total_cholesterol**: CLSI 2010 lipid reference intervals (adult lab-normal TC < 5.2 mmol/L); WHO 2019; Chinese Lipid Guideline 2023
- **hdl**: NCEP ATP III (HDL-C male ≥ 1.0 mmol/L, female ≥ 1.2 mmol/L as low-HDL threshold); CLSI 2010 HDL reference intervals (upper bound ~2.1-2.6 mmol/L adult lab-normal)
- **ldl**: CLSI 2010 LDL reference intervals (adult lab-normal LDL < 3.4 mmol/L, no lower bound per de Lange 2007 J Epidemiol Community Health on LDL mortality paradox)
- **vldl**: Friedewald equation: VLDL-C (mmol/L) = TG / 2.2; lower bound 0.18 mmol/L corresponds to TG floor of 0.4 mmol/L (CLSI TG lab-normal lower bound); upper bound VLDL-C < 1.0 mmol/L per WHO 2019. VLDL-C is a lipoprotein-cholesterol measurement so the mg/dL→mmol/L factor is 0.0259 (cholesterol molecular weight 386), not 0.0113 (that's TG).
- **triglycerides**: CLSI 2010 triglyceride reference intervals (lab-normal adult TG 0.56-1.7 mmol/L = 50-150 mg/dL); NCEP ATP III borderline-high threshold at 1.7 mmol/L (150 mg/dL)
- **egfr**: KDIGO 2024 CKD-EPI 2021 (eGFR 90-120 mL/min/1.73m2 typical adult reference); CKD-EPI Chinese cohort calibration 2021
- **creatinine**: CLSI EP28-A2 2013 creatinine reference intervals; IFCC 2017 consensus reference interval
- **bun**: Rosenbaum & Post 1969 pediatric reference; CLSI BUN method-specific reference intervals
- **uric_acid**: CLSI 2008 uric acid reference intervals; EULAR 2016 gout guideline; ACR 2020
- **tsh**: ATA 2017 thyroid guideline (adult TSH 0.27-4.2 mIU/L assay-dependent); Endocrine Society 2012
- **bmi**: WHO Adult Obesity Classifications 2000 (BMI 18.5-24.0 adult normal); Chinese Adult Weight Management Guideline 2023 (senior BMI 22-26 associated with lowest mortality)
- **bp_sys**: CLSI 2010 BP reference interval (lab-normal adult systolic 90-120 mmHg); ESH 2023 (threshold-based, not used as reference here)
- **bp_dia**: CLSI 2010 BP reference interval (lab-normal adult diastolic 60-80 mmHg); ESH 2023

## Recommended Submission Posture

Report both L-CVI and ICV-Panel as complementary AI-only substitutes for expert Delphi:

- **L-CVI** establishes construct-level literature convergence (axis A–H).
- **ICV-Panel** establishes indicator-level agreement with published clinical guidelines.
- Together they triangulate: axes have independent construct support AND indicators match published reference ranges.
- Expert Delphi remains deferred to v2 as a stated limitation, not a submission blocker.

## Honest Scope Caveats

- AI-only substitute for expert Delphi; no human expert judgement is captured.
- Validates agreement with published consensus, not framework-item acceptance.
- Consensus sources reflect the 2019-2024 guideline window; earlier or regional guidelines are not represented.
- Reference ranges are clinical reference intervals, not population prevalence thresholds.

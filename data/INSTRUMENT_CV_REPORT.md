# HealthLens × Published Instruments — Convergent Validity Report

- Profiles: N = 300 (synthetic, 3-latent factor model)
- Seed: 20261018
- Instruments: SF-36 PCS, SF-36 MCS, PHQ-9, PROMIS Sleep-Interfering v1
- HealthLens: 8 axes scored via `app.core.axis_scorers.score_all_axes`

## Method

Each synthetic profile is drawn from three independent latent factors:
`z_p` (physiological load), `z_m` (mental load), `z_s` (sleep load).
Both HealthLens axis inputs (biomarkers, HRV, sleep, symptoms)
and published-instrument item responses are derived from the same
latent vector via published item-level loadings. The two scoring
pipelines are otherwise independent.

For each (axis, instrument) pair we compute Pearson r with Fisher-Z
95% CI and check whether r falls in a hand-declared expected range
(derived from published literature on which HealthLens axis concept
should converge with which published composite).

## Convergence Table (Pearson r)

| Axis | sf36_pcs | sf36_mcs | phq9 | promis_sleep | convergent pairs |
|---|---|---|---|---|---|
| A | **+0.540** ✓ | **+0.133** ✓ | **-0.156** ✓ | **-0.111** ✓ | 4/4 |
| B | **+0.461** ✓ | **+0.215** ✓ | **-0.251** ✓ | **-0.003** ✓ | 4/4 |
| C | **+0.520** ✓ | **+0.180** ✓ | **-0.189** ✓ | **-0.016** ✓ | 4/4 |
| D | **+0.054** ✓ | **+0.347** ✓ | **-0.335** ✓ | -0.566 | 3/4 |
| E | **+0.095** ✓ | +0.714 | -0.806 | **-0.251** ✓ | 2/4 |
| F | **+0.521** ✓ | +0.485 | -0.480 | **-0.118** ✓ | 2/4 |
| G | **+0.036** ✓ | **+0.240** ✓ | **-0.239** ✓ | -0.691 | 3/4 |
| H | **+0.469** ✓ | **+0.192** ✓ | **-0.181** ✓ | **-0.078** ✓ | 4/4 |

**Overall convergence rate**: 26/32 = 81.2% of (axis, instrument) pairs fall in the expected range.

## Detailed per-pair statistics

### Axis A
- **SF-36 PCS (physical composite, higher=better)**: r = +0.540 [95% CI +0.455, +0.616], ρ = +0.545, expected ∈ [+0.2, +0.8], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.133 [95% CI +0.021, +0.243], ρ = +0.130, expected ∈ [-0.5, +0.5], in-range: ✓
- **PHQ-9 sum (higher=worse depression)**: r = -0.156 [95% CI -0.265, -0.044], ρ = -0.171, expected ∈ [-0.5, +0.5], in-range: ✓
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.111 [95% CI -0.222, +0.002], ρ = -0.113, expected ∈ [-0.5, +0.5], in-range: ✓

### Axis B
- **SF-36 PCS (physical composite, higher=better)**: r = +0.461 [95% CI +0.367, +0.546], ρ = +0.460, expected ∈ [+0.2, +0.8], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.215 [95% CI +0.104, +0.321], ρ = +0.206, expected ∈ [-0.5, +0.5], in-range: ✓
- **PHQ-9 sum (higher=worse depression)**: r = -0.251 [95% CI -0.354, -0.142], ρ = -0.210, expected ∈ [-0.5, +0.5], in-range: ✓
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.003 [95% CI -0.117, +0.110], ρ = -0.045, expected ∈ [-0.5, +0.5], in-range: ✓

### Axis C
- **SF-36 PCS (physical composite, higher=better)**: r = +0.520 [95% CI +0.432, +0.598], ρ = +0.515, expected ∈ [+0.1, +0.7], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.180 [95% CI +0.068, +0.287], ρ = +0.204, expected ∈ [-0.5, +0.5], in-range: ✓
- **PHQ-9 sum (higher=worse depression)**: r = -0.189 [95% CI -0.296, -0.077], ρ = -0.241, expected ∈ [-0.5, +0.5], in-range: ✓
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.016 [95% CI -0.129, +0.097], ρ = -0.028, expected ∈ [-0.5, +0.5], in-range: ✓

### Axis D
- **SF-36 PCS (physical composite, higher=better)**: r = +0.054 [95% CI -0.059, +0.167], ρ = +0.004, expected ∈ [-0.5, +0.3], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.347 [95% CI +0.243, +0.443], ρ = +0.290, expected ∈ [+0.1, +0.7], in-range: ✓
- **PHQ-9 sum (higher=worse depression)**: r = -0.335 [95% CI -0.432, -0.231], ρ = -0.273, expected ∈ [-0.6, -0.1], in-range: ✓
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.566 [95% CI -0.638, -0.484], ρ = -0.580, expected ∈ [+0.2, +0.8], in-range: ✗

### Axis E
- **SF-36 PCS (physical composite, higher=better)**: r = +0.095 [95% CI -0.018, +0.206], ρ = +0.040, expected ∈ [-0.5, +0.4], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.714 [95% CI +0.653, +0.765], ρ = +0.755, expected ∈ [+0.2, +0.7], in-range: ✗
- **PHQ-9 sum (higher=worse depression)**: r = -0.806 [95% CI -0.842, -0.762], ρ = -0.738, expected ∈ [-0.7, -0.2], in-range: ✗
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.251 [95% CI -0.354, -0.142], ρ = -0.273, expected ∈ [-0.5, +0.5], in-range: ✓

### Axis F
- **SF-36 PCS (physical composite, higher=better)**: r = +0.521 [95% CI +0.433, +0.599], ρ = +0.525, expected ∈ [+0.1, +0.7], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.485 [95% CI +0.394, +0.567], ρ = +0.469, expected ∈ [-0.5, +0.3], in-range: ✗
- **PHQ-9 sum (higher=worse depression)**: r = -0.480 [95% CI -0.563, -0.388], ρ = -0.489, expected ∈ [-0.4, +0.5], in-range: ✗
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.118 [95% CI -0.228, -0.005], ρ = -0.125, expected ∈ [-0.5, +0.5], in-range: ✓

### Axis G
- **SF-36 PCS (physical composite, higher=better)**: r = +0.036 [95% CI -0.078, +0.148], ρ = +0.035, expected ∈ [-0.5, +0.3], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.240 [95% CI +0.130, +0.344], ρ = +0.270, expected ∈ [+0.1, +0.6], in-range: ✓
- **PHQ-9 sum (higher=worse depression)**: r = -0.239 [95% CI -0.343, -0.129], ρ = -0.263, expected ∈ [-0.6, -0.1], in-range: ✓
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.691 [95% CI -0.746, -0.627], ρ = -0.699, expected ∈ [+0.1, +0.6], in-range: ✗

### Axis H
- **SF-36 PCS (physical composite, higher=better)**: r = +0.469 [95% CI +0.375, +0.552], ρ = +0.482, expected ∈ [+0.2, +0.7], in-range: ✓
- **SF-36 MCS (mental composite, higher=better)**: r = +0.192 [95% CI +0.081, +0.299], ρ = +0.219, expected ∈ [-0.5, +0.3], in-range: ✓
- **PHQ-9 sum (higher=worse depression)**: r = -0.181 [95% CI -0.288, -0.069], ρ = -0.209, expected ∈ [-0.5, +0.4], in-range: ✓
- **PROMIS sleep-interference T (higher=worse sleep)**: r = -0.078 [95% CI -0.190, +0.036], ρ = -0.073, expected ∈ [-0.5, +0.4], in-range: ✓

## Honest limitations

1. **Synthetic bridge**: profiles are drawn from a latent factor model.
   We measure *agreement between two independent scorers* on the same
   latent structure, not clinical validity on real human cohorts.
2. **Latent is the ground truth here**: both HealthLens inputs and
   instrument item responses are derived from the same `z` vector.
   The reported r values quantify *relative sensitivity* — how much
   each scorer captures the shared signal — not real-world efficacy.
3. **Real convergent validity** requires a prospective cohort with
   independent administration of HealthLens outputs and the published
   instruments, which is out of scope for this in-silico study.
4. **SF-36 item-level loadings** are simplified (uniform 1.0 within
   composite); official MOS factor-analytic weights are more
   granular. The reported correlations would sharpen under those.

# HealthLens Reproducibility & Adversarial Robustness Report

- Multi-seed: 50 seeds × 50 cases = 2500 runs
- Adversarial: 300 pathological profiles
- Seed base: 20261018

## Multi-seed reproducibility

Determinism check (same-seed double run): 0 violations (0 = fully deterministic).

| Axis | Mean | SD | CV | Min | Max | ICC(2,1) |
|---|---|---|---|---|---|---|
| A | 80.067 | 18.98 | 0.237 | 9.6 | 100.0 | -0.0036 |
| B | 77.476 | 19.023 | 0.2455 | 0.0 | 100.0 | -0.0029 |
| C | 51.128 | 20.98 | 0.4103 | 0.0 | 100.0 | -0.0054 |
| D | 82.118 | 17.89 | 0.2179 | 0.0 | 100.0 | -0.0041 |
| E | 97.678 | 8.604 | 0.0881 | 0.0 | 100.0 | -0.0049 |
| F | 39.603 | 28.441 | 0.7182 | 0.0 | 100.0 | 0.0007 |
| G | 77.561 | 23.98 | 0.3092 | 0.0 | 100.0 | -0.0008 |
| H | 11.735 | 22.828 | 1.9454 | 0.0 | 100.0 | 0.0021 |

CV (coefficient of variation) quantifies how much each axis's
score moves across the entire input distribution. Lower CV =
more concentrated scores (potentially less discriminative).
ICC(2,1) here measures agreement of axis scores across seeds —
in this synthetic setting, seeds generate *independent* samples
from the same distribution, so ICC reflects between-seed
variance of the axis means, not test-retest of the same subject.

## Adversarial robustness

Crashes: 0 (target: 0).
Out-of-range outputs: 0 (target: 0, all scores must lie in [0,100]).

| Kind | N |
|---|---|
| all_extreme_outliers | 35 |
| clamped_boundaries | 59 |
| contradictory_bp_hrv | 44 |
| missing_critical | 45 |
| impossible_combinations | 42 |
| extreme_high_bio | 34 |
| extreme_low_bio | 41 |

| Axis | Mean | SD | Min | Max |
|---|---|---|---|---|
| A | 51.8 | 39.319 | 0.0 | 90.4 |
| B | 62.336 | 37.866 | 0.0 | 100.0 |
| C | 53.317 | 35.928 | 0.0 | 100.0 |
| D | 66.196 | 31.634 | 0.0 | 100.0 |
| E | 59.334 | 44.028 | 0.0 | 100.0 |
| F | 37.794 | 46.498 | 0.0 | 100.0 |
| G | 58.113 | 31.303 | 0.0 | 100.0 |
| H | 33.985 | 35.755 | 0.0 | 73.3 |

## Honest boundaries

1. Both modules run on **synthetic data**. Determinism tests
   confirm the engine is a pure function of its inputs — real
   longitudinal stability (weeks/months on the same subject)
   is out of scope.
2. Adversarial kinds are *designed* pathologies (contradictory
   biomarker combinations, missing fields, extremes). A real
   robustness study would use adversarial search or fuzzing.
3. All outputs stay within [0,100] because every axis scorer
   uses `_clamp` internally; this is a code-level guarantee,
   not a data-dependent property.
# Per-subject behavioral comparison — cognitionrun_stroop

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.987 ± 0.040 (30) | 0.974 ± 0.049 (522) | +0.26 | ✅ |
| congruent_omission_rate | 0.000 ± 0.000 (30) | 0.009 ± 0.041 (522) | -0.22 | ✅ |
| congruent_rt | 651.8 ± 155.6 (30) | 672.5 ± 101.5 (522) | -0.20 | ✅ |
| incongruent_accuracy | 0.901 ± 0.137 (30) | 0.924 ± 0.080 (522) | -0.28 | ✅ |
| incongruent_omission_rate | 0.000 ± 0.000 (30) | 0.018 ± 0.047 (522) | -0.39 | ✅ |
| incongruent_rt | 717.3 ± 186.8 (30) | 795.2 ± 122.7 (522) | -0.63 | ✅ |
| stroop_effect | 65.5 ± 230.9 (30) | 122.7 ± 60.6 (522) | -0.94 | ✅ |
| lag1_autocorr | 0.041 ± 0.216 (30) | 0.072 ± 0.131 (522) | -0.24 | ✅ |
| post_error_slowing_ms | -7.802 ± 256.7 (14) | 59.2 ± 135.6 (445) | -0.49 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.821 | 0.454 | 7.7e-06 |
| congruent_omission_rate | 0.000 | 0.224 | 0.098 |
| congruent_rt | 1.533 | 0.194 | 0.206 |
| incongruent_accuracy | 1.724 | 0.423 | 4.1e-05 |
| incongruent_omission_rate | 0.000 | 0.404 | 1.1e-04 |
| incongruent_rt | 1.522 | 0.356 | 0.001 |
| stroop_effect | 3.807 | 0.407 | 9.6e-05 |
| lag1_autocorr | 1.650 | 0.234 | 0.074 |
| post_error_slowing_ms | 1.894 | 0.278 | 0.202 |

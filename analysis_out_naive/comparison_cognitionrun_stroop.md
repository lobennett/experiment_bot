# Per-subject behavioral comparison — cognitionrun_stroop

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.994 ± 0.030 (30) | 0.974 ± 0.049 (522) | +0.41 | ✅ |
| congruent_omission_rate | 0.000 ± 0.000 (30) | 0.009 ± 0.041 (522) | -0.22 | ✅ |
| congruent_rt | 817.0 ± 142.1 (30) | 672.5 ± 101.5 (522) | +1.42 | ❌ |
| incongruent_accuracy | 0.878 ± 0.126 (30) | 0.924 ± 0.080 (522) | -0.57 | ✅ |
| incongruent_omission_rate | 0.000 ± 0.000 (30) | 0.018 ± 0.047 (522) | -0.39 | ✅ |
| incongruent_rt | 923.9 ± 134.5 (30) | 795.2 ± 122.7 (522) | +1.05 | ❌ |
| stroop_effect | 106.9 ± 148.4 (30) | 122.7 ± 60.6 (522) | -0.26 | ✅ |
| lag1_autocorr | -0.047 ± 0.233 (30) | 0.072 ± 0.131 (522) | -0.91 | ✅ |
| post_error_slowing_ms | 51.2 ± 148.3 (18) | 59.2 ± 135.6 (445) | -0.06 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.622 | 0.520 | 1.2e-07 |
| congruent_omission_rate | 0.000 | 0.224 | 0.098 |
| congruent_rt | 1.400 | 0.531 | 5.6e-08 |
| incongruent_accuracy | 1.579 | 0.374 | 4.6e-04 |
| incongruent_omission_rate | 0.000 | 0.404 | 1.1e-04 |
| incongruent_rt | 1.096 | 0.444 | 1.3e-05 |
| stroop_effect | 2.447 | 0.196 | 0.197 |
| lag1_autocorr | 1.781 | 0.395 | 1.7e-04 |
| post_error_slowing_ms | 1.094 | 0.175 | 0.604 |

# Per-subject behavioral comparison — stroop_rdoc

_Generated 2026-07-19. Bot N=5 sessions (5 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.973 ± 0.015 (5) | 0.974 ± 0.049 (522) | -0.02 | ✅ |
| congruent_omission_rate | 0.017 ± 0.020 (5) | 0.009 ± 0.041 (522) | +0.20 | ✅ |
| congruent_rt | 817.9 ± 46.0 (5) | 672.5 ± 101.5 (522) | +1.43 | ❌ |
| incongruent_accuracy | 0.913 ± 0.030 (5) | 0.924 ± 0.080 (522) | -0.13 | ✅ |
| incongruent_omission_rate | 0.027 ± 0.019 (5) | 0.018 ± 0.047 (522) | +0.18 | ✅ |
| incongruent_rt | 914.6 ± 53.3 (5) | 795.2 ± 122.7 (522) | +0.97 | ✅ |
| stroop_effect | 96.7 ± 26.0 (5) | 122.7 ± 60.6 (522) | -0.43 | ✅ |
| lag1_autocorr | -0.048 ± 0.068 (5) | 0.072 ± 0.131 (522) | -0.91 | ✅ |
| post_error_slowing_ms | 12.3 ± 48.0 (5) | 59.2 ± 135.6 (445) | -0.35 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.305 | 0.446 | 0.206 |
| congruent_omission_rate | 0.504 | 0.376 | 0.385 |
| congruent_rt | 0.453 | 0.835 | 2.8e-04 |
| incongruent_accuracy | 0.374 | 0.498 | 0.118 |
| incongruent_omission_rate | 0.407 | 0.431 | 0.237 |
| incongruent_rt | 0.434 | 0.690 | 0.007 |
| stroop_effect | 0.429 | 0.502 | 0.113 |
| lag1_autocorr | 0.519 | 0.665 | 0.011 |
| post_error_slowing_ms | 0.354 | 0.384 | 0.362 |

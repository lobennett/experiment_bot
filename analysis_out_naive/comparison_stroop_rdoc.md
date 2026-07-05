# Per-subject behavioral comparison — stroop_rdoc

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.976 ± 0.025 (30) | 0.974 ± 0.049 (522) | +0.04 | ✅ |
| congruent_omission_rate | 0.002 ± 0.005 (30) | 0.009 ± 0.041 (522) | -0.17 | ✅ |
| congruent_rt | 737.2 ± 71.5 (30) | 672.5 ± 101.5 (522) | +0.64 | ✅ |
| incongruent_accuracy | 0.916 ± 0.042 (30) | 0.924 ± 0.080 (522) | -0.09 | ✅ |
| incongruent_omission_rate | 0.008 ± 0.011 (30) | 0.018 ± 0.047 (522) | -0.21 | ✅ |
| incongruent_rt | 802.3 ± 84.5 (30) | 795.2 ± 122.7 (522) | +0.06 | ✅ |
| stroop_effect | 65.1 ± 32.4 (30) | 122.7 ± 60.6 (522) | -0.95 | ✅ |
| lag1_autocorr | 0.011 ± 0.098 (30) | 0.072 ± 0.131 (522) | -0.47 | ✅ |
| post_error_slowing_ms | 8.144 ± 78.1 (30) | 59.2 ± 135.6 (445) | -0.38 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.503 | 0.154 | 0.468 |
| congruent_omission_rate | 0.125 | 0.224 | 0.098 |
| congruent_rt | 0.704 | 0.469 | 3.1e-06 |
| incongruent_accuracy | 0.523 | 0.350 | 0.001 |
| incongruent_omission_rate | 0.243 | 0.304 | 0.008 |
| incongruent_rt | 0.688 | 0.131 | 0.662 |
| stroop_effect | 0.534 | 0.523 | 1.0e-07 |
| lag1_autocorr | 0.750 | 0.287 | 0.015 |
| post_error_slowing_ms | 0.576 | 0.301 | 0.009 |

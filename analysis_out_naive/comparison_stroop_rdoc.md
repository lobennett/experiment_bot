# Per-subject behavioral comparison — stroop_rdoc

_Generated 2026-07-19. Bot N=20 sessions (20 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.972 ± 0.024 (20) | 0.974 ± 0.049 (522) | -0.05 | ✅ |
| congruent_omission_rate | 0.019 ± 0.021 (20) | 0.009 ± 0.041 (522) | +0.26 | ✅ |
| congruent_rt | 732.5 ± 88.3 (20) | 672.5 ± 101.5 (522) | +0.59 | ✅ |
| incongruent_accuracy | 0.927 ± 0.042 (20) | 0.924 ± 0.080 (522) | +0.05 | ✅ |
| incongruent_omission_rate | 0.023 ± 0.015 (20) | 0.018 ± 0.047 (522) | +0.11 | ✅ |
| incongruent_rt | 829.1 ± 101.4 (20) | 795.2 ± 122.7 (522) | +0.28 | ✅ |
| stroop_effect | 96.7 ± 32.3 (20) | 122.7 ± 60.6 (522) | -0.43 | ✅ |
| lag1_autocorr | -0.029 ± 0.082 (20) | 0.072 ± 0.131 (522) | -0.77 | ✅ |
| post_error_slowing_ms | 8.649 ± 93.1 (20) | 59.2 ± 135.6 (445) | -0.37 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.483 | 0.246 | 0.162 |
| congruent_omission_rate | 0.522 | 0.326 | 0.025 |
| congruent_rt | 0.870 | 0.419 | 0.001 |
| incongruent_accuracy | 0.527 | 0.314 | 0.034 |
| incongruent_omission_rate | 0.315 | 0.446 | 5.3e-04 |
| incongruent_rt | 0.826 | 0.296 | 0.054 |
| stroop_effect | 0.533 | 0.394 | 0.003 |
| lag1_autocorr | 0.628 | 0.505 | 4.5e-05 |
| post_error_slowing_ms | 0.687 | 0.238 | 0.193 |

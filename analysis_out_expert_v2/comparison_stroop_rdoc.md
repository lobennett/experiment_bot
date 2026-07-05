# Per-subject behavioral comparison — stroop_rdoc

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.967 ± 0.047 (30) | 0.974 ± 0.049 (522) | -0.16 | ✅ |
| congruent_omission_rate | 0.006 ± 0.008 (30) | 0.009 ± 0.041 (522) | -0.08 | ✅ |
| congruent_rt | 631.1 ± 54.9 (30) | 672.5 ± 101.5 (522) | -0.41 | ✅ |
| incongruent_accuracy | 0.938 ± 0.039 (30) | 0.924 ± 0.080 (522) | +0.18 | ✅ |
| incongruent_omission_rate | 0.013 ± 0.015 (30) | 0.018 ± 0.047 (522) | -0.11 | ✅ |
| incongruent_rt | 690.9 ± 68.0 (30) | 795.2 ± 122.7 (522) | -0.85 | ✅ |
| stroop_effect | 59.7 ± 39.1 (30) | 122.7 ± 60.6 (522) | -1.04 | ❌ |
| lag1_autocorr | 0.274 ± 0.121 (30) | 0.072 ± 0.131 (522) | +1.55 | ❌ |
| post_error_slowing_ms | 46.0 ± 101.1 (26) | 59.2 ± 135.6 (445) | -0.10 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.959 | 0.232 | 0.080 |
| congruent_omission_rate | 0.197 | 0.224 | 0.098 |
| congruent_rt | 0.541 | 0.310 | 0.006 |
| incongruent_accuracy | 0.485 | 0.177 | 0.299 |
| incongruent_omission_rate | 0.316 | 0.171 | 0.339 |
| incongruent_rt | 0.554 | 0.489 | 9.6e-07 |
| stroop_effect | 0.645 | 0.475 | 2.1e-06 |
| lag1_autocorr | 0.924 | 0.692 | 5.6e-14 |
| post_error_slowing_ms | 0.746 | 0.162 | 0.487 |

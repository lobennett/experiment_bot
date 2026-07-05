# Per-subject behavioral comparison — stroop_rdoc

_Generated 2026-07-02. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.978 ± 0.022 (30) | 0.974 ± 0.049 (522) | +0.08 | ✅ |
| congruent_omission_rate | 0.007 ± 0.008 (30) | 0.009 ± 0.041 (522) | -0.05 | ✅ |
| congruent_rt | 635.0 ± 20.1 (30) | 672.5 ± 101.5 (522) | -0.37 | ✅ |
| incongruent_accuracy | 0.934 ± 0.032 (30) | 0.924 ± 0.080 (522) | +0.13 | ✅ |
| incongruent_omission_rate | 0.011 ± 0.013 (30) | 0.018 ± 0.047 (522) | -0.16 | ✅ |
| incongruent_rt | 683.6 ± 26.4 (30) | 795.2 ± 122.7 (522) | -0.91 | ✅ |
| stroop_effect | 48.6 ± 10.2 (30) | 122.7 ± 60.6 (522) | -1.22 | ❌ |
| lag1_autocorr | 0.220 ± 0.120 (30) | 0.072 ± 0.131 (522) | +1.13 | ❌ |
| post_error_slowing_ms | 11.7 ± 101.0 (30) | 59.2 ± 135.6 (445) | -0.35 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | 0.440 | 0.220 | 0.109 |
| congruent_omission_rate | 0.205 | 0.224 | 0.098 |
| congruent_rt | 0.198 | 0.427 | 3.3e-05 |
| incongruent_accuracy | 0.402 | 0.298 | 0.010 |
| incongruent_omission_rate | 0.271 | 0.238 | 0.068 |
| incongruent_rt | 0.215 | 0.688 | 8.9e-14 |
| stroop_effect | 0.169 | 0.804 | 6.3e-20 |
| lag1_autocorr | 0.918 | 0.529 | 6.6e-08 |
| post_error_slowing_ms | 0.745 | 0.291 | 0.013 |

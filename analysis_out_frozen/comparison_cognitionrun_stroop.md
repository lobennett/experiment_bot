# Per-subject behavioral comparison — cognitionrun_stroop

_Generated 2026-07-01. Bot N=15 sessions (15 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.936 ± 0.098 (15) | 0.974 ± 0.049 (522) | -0.78 | ✅ |
| congruent_omission_rate | 0.000 ± 0.000 (15) | 0.009 ± 0.041 (522) | -0.22 | ✅ |
| congruent_rt | 614.5 ± 29.8 (15) | 672.5 ± 101.5 (522) | -0.57 | ✅ |
| incongruent_accuracy | 0.914 ± 0.102 (15) | 0.924 ± 0.080 (522) | -0.12 | ✅ |
| incongruent_omission_rate | 0.000 ± 0.000 (15) | 0.018 ± 0.047 (522) | -0.39 | ✅ |
| incongruent_rt | 754.5 ± 325.5 (15) | 795.2 ± 122.7 (522) | -0.33 | ✅ |
| stroop_effect | 140.1 ± 314.4 (15) | 122.7 ± 60.6 (522) | +0.29 | ✅ |
| lag1_autocorr | 0.028 ± 0.237 (15) | 0.072 ± 0.131 (522) | -0.34 | ✅ |
| post_error_slowing_ms | -40.6 ± 182.4 (9) | 59.2 ± 135.6 (445) | -0.74 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

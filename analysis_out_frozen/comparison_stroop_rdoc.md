# Per-subject behavioral comparison — stroop_rdoc

_Generated 2026-07-01. Bot N=15 sessions (15 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.977 ± 0.018 (15) | 0.974 ± 0.049 (522) | +0.05 | ✅ |
| congruent_omission_rate | 0.008 ± 0.009 (15) | 0.009 ± 0.041 (522) | -0.02 | ✅ |
| congruent_rt | 633.7 ± 13.1 (15) | 672.5 ± 101.5 (522) | -0.38 | ✅ |
| incongruent_accuracy | 0.939 ± 0.028 (15) | 0.924 ± 0.080 (522) | +0.19 | ✅ |
| incongruent_omission_rate | 0.014 ± 0.014 (15) | 0.018 ± 0.047 (522) | -0.08 | ✅ |
| incongruent_rt | 682.2 ± 19.2 (15) | 795.2 ± 122.7 (522) | -0.92 | ✅ |
| stroop_effect | 48.5 ± 8.665 (15) | 122.7 ± 60.6 (522) | -1.22 | ❌ |
| lag1_autocorr | 0.176 ± 0.121 (15) | 0.072 ± 0.131 (522) | +0.79 | ✅ |
| post_error_slowing_ms | 11.8 ± 126.0 (15) | 59.2 ± 135.6 (445) | -0.35 | ✅ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

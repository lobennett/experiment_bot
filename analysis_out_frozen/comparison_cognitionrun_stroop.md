# Per-subject behavioral comparison — cognitionrun_stroop

_Generated 2026-07-02. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | 0.959 ± 0.079 (30) | 0.974 ± 0.049 (522) | -0.31 | ✅ |
| congruent_omission_rate | 0.000 ± 0.000 (30) | 0.009 ± 0.041 (522) | -0.22 | ✅ |
| congruent_rt | 683.3 ± 203.7 (30) | 672.5 ± 101.5 (522) | +0.11 | ✅ |
| incongruent_accuracy | 0.902 ± 0.099 (30) | 0.924 ± 0.080 (522) | -0.27 | ✅ |
| incongruent_omission_rate | 0.000 ± 0.000 (30) | 0.018 ± 0.047 (522) | -0.39 | ✅ |
| incongruent_rt | 765.4 ± 341.9 (30) | 795.2 ± 122.7 (522) | -0.24 | ✅ |
| stroop_effect | 82.1 ± 408.5 (30) | 122.7 ± 60.6 (522) | -0.67 | ✅ |
| lag1_autocorr | -0.022 ± 0.252 (30) | 0.072 ± 0.131 (522) | -0.72 | ✅ |
| post_error_slowing_ms | -100.7 ± 212.5 (19) | 59.2 ± 135.6 (445) | -1.18 | ❌ |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

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

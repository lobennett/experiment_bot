# Per-subject behavioral comparison — stop_signal_rdoc

_Generated 2026-07-01. Bot N=15 sessions (15 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.934 ± 0.028 (15) | 0.935 ± 0.052 (522) | -0.02 | ✅ |
| go_omission_rate | 0.023 ± 0.011 (15) | 0.014 ± 0.027 (522) | +0.34 | ✅ |
| go_rt | 566.7 ± 10.4 (15) | 584.7 ± 84.8 (522) | -0.21 | ✅ |
| go_rt_all_responses | 566.0 ± 10.7 (15) | 584.8 ± 85.7 (522) | -0.22 | ✅ |
| mean_stop_failure_RT | 537.1 ± 21.5 (15) | 541.4 ± 147.8 (470) | -0.03 | ✅ |
| stop_accuracy | 0.462 ± 0.031 (15) | 0.498 ± 0.095 (522) | -0.38 | ✅ |
| max_SSD | 546.7 ± 64.0 (15) | 519.6 ± 144.6 (522) | +0.19 | ✅ |
| mean_SSD | 314.1 ± 90.4 (15) | 282.2 ± 106.5 (522) | +0.30 | ✅ |
| min_SSD | 100.0 ± 103.5 (15) | 87.0 ± 77.5 (522) | +0.17 | ✅ |
| final_SSD | 213.3 ± 151.7 (15) | 291.7 ± 154.7 (522) | -0.51 | ✅ |
| ssrt | 252.6 ± 93.7 (15) | 302.6 ± 76.3 (522) | -0.65 | ✅ |
| lag1_autocorr | -0.024 ± 0.072 (15) | -0.001 ± 0.044 (522) | -0.52 | ✅ |
| post_error_slowing_ms | 22.2 ± 22.5 (15) | 7.835 ± 24.7 (522) | +0.58 | ✅ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

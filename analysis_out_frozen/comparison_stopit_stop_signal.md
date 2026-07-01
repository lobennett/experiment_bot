# Per-subject behavioral comparison — stopit_stop_signal

_Generated 2026-07-01. Bot N=15 sessions (15 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.958 ± 0.018 (15) | 0.935 ± 0.052 (522) | +0.43 | ✅ |
| go_omission_rate | 0.016 ± 0.013 (15) | 0.014 ± 0.027 (522) | +0.07 | ✅ |
| go_rt | 575.1 ± 11.8 (15) | 584.7 ± 84.8 (522) | -0.11 | ✅ |
| go_rt_all_responses | 575.2 ± 11.9 (15) | 584.8 ± 85.7 (522) | -0.11 | ✅ |
| mean_stop_failure_RT | 1515.1 ± 4076.8 (15) | 541.4 ± 147.8 (470) | +6.59 | ❌ |
| stop_accuracy | 0.481 ± 0.043 (15) | 0.498 ± 0.095 (522) | -0.18 | ✅ |
| max_SSD | 450.0 ± 103.5 (15) | 519.6 ± 144.6 (522) | -0.48 | ✅ |
| mean_SSD | 236.6 ± 80.1 (15) | 282.2 ± 106.5 (522) | -0.43 | ✅ |
| min_SSD | 73.3 ± 49.5 (15) | 87.0 ± 77.5 (522) | -0.18 | ✅ |
| final_SSD | 276.7 ± 138.7 (15) | 291.7 ± 154.7 (522) | -0.10 | ✅ |
| ssrt | 338.5 ± 80.8 (15) | 302.6 ± 76.3 (522) | +0.47 | ✅ |
| lag1_autocorr | 0.114 ± 0.091 (15) | -0.001 ± 0.044 (522) | +2.63 | ❌ |
| post_error_slowing_ms | -166.5 ± 790.0 (15) | 7.835 ± 24.7 (522) | -7.05 | ❌ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

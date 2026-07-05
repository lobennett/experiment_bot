# Per-subject behavioral comparison — stop_signal_rdoc

_Generated 2026-07-02. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.935 ± 0.026 (30) | 0.935 ± 0.052 (522) | -0.00 | ✅ |
| go_omission_rate | 0.022 ± 0.011 (30) | 0.014 ± 0.027 (522) | +0.30 | ✅ |
| go_rt | 570.1 ± 11.5 (30) | 584.7 ± 84.8 (522) | -0.17 | ✅ |
| go_rt_all_responses | 569.3 ± 11.8 (30) | 584.8 ± 85.7 (522) | -0.18 | ✅ |
| mean_stop_failure_RT | 535.6 ± 19.6 (30) | 541.4 ± 147.8 (470) | -0.04 | ✅ |
| stop_accuracy | 0.464 ± 0.029 (30) | 0.498 ± 0.095 (522) | -0.36 | ✅ |
| max_SSD | 533.3 ± 68.6 (30) | 519.6 ± 144.6 (522) | +0.09 | ✅ |
| mean_SSD | 305.2 ± 97.8 (30) | 282.2 ± 106.5 (522) | +0.22 | ✅ |
| min_SSD | 101.7 ± 98.7 (30) | 87.0 ± 77.5 (522) | +0.19 | ✅ |
| final_SSD | 223.3 ± 144.3 (30) | 291.7 ± 154.7 (522) | -0.44 | ✅ |
| ssrt | 264.9 ± 98.9 (30) | 302.6 ± 76.3 (522) | -0.49 | ✅ |
| lag1_autocorr | -0.022 ± 0.079 (30) | -0.001 ± 0.044 (522) | -0.47 | ✅ |
| post_error_slowing_ms | 25.3 ± 23.2 (30) | 7.835 ± 24.7 (522) | +0.70 | ✅ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

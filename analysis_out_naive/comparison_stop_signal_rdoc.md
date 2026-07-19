# Per-subject behavioral comparison — stop_signal_rdoc

_Generated 2026-07-19. Bot N=20 sessions (20 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.954 ± 0.024 (20) | 0.935 ± 0.052 (522) | +0.36 | ✅ |
| go_omission_rate | 0.017 ± 0.012 (20) | 0.014 ± 0.027 (522) | +0.10 | ✅ |
| go_rt | 558.2 ± 51.7 (20) | 584.7 ± 84.8 (522) | -0.31 | ✅ |
| go_rt_all_responses | 558.2 ± 51.4 (20) | 584.8 ± 85.7 (522) | -0.31 | ✅ |
| mean_stop_failure_RT | 480.8 ± 50.6 (20) | 541.4 ± 147.8 (470) | -0.41 | ✅ |
| stop_accuracy | 0.477 ± 0.016 (20) | 0.498 ± 0.095 (522) | -0.22 | ✅ |
| max_SSD | 480.0 ± 65.7 (20) | 519.6 ± 144.6 (522) | -0.27 | ✅ |
| mean_SSD | 312.2 ± 64.7 (20) | 282.2 ± 106.5 (522) | +0.28 | ✅ |
| min_SSD | 185.0 ± 79.6 (20) | 87.0 ± 77.5 (522) | +1.26 | ❌ |
| final_SSD | 290.0 ± 78.8 (20) | 291.7 ± 154.7 (522) | -0.01 | ✅ |
| ssrt | 245.9 ± 32.0 (20) | 302.6 ± 76.3 (522) | -0.74 | ✅ |
| lag1_autocorr | 0.084 ± 0.152 (20) | -0.001 ± 0.044 (522) | +1.94 | ❌ |
| post_error_slowing_ms | 24.2 ± 34.6 (20) | 7.835 ± 24.7 (522) | +0.66 | ✅ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.472 | 0.266 | 0.108 |
| go_omission_rate | 0.449 | 0.513 | 3.2e-05 |
| go_rt | 0.609 | 0.226 | 0.240 |
| go_rt_all_responses | 0.600 | 0.228 | 0.231 |
| mean_stop_failure_RT | 0.342 | 0.376 | 0.006 |
| stop_accuracy | 0.174 | 0.258 | 0.127 |
| max_SSD | 0.454 | 0.251 | 0.148 |
| mean_SSD | 0.608 | 0.254 | 0.138 |
| min_SSD | 1.027 | 0.549 | 5.6e-06 |
| final_SSD | 0.509 | 0.169 | 0.584 |
| ssrt | 0.419 | 0.428 | 0.001 |
| lag1_autocorr | 3.471 | 0.464 | 2.6e-04 |
| post_error_slowing_ms | 1.401 | 0.213 | 0.299 |

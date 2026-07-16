# Per-subject behavioral comparison — stop_signal_rdoc

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.947 ± 0.030 (30) | 0.935 ± 0.052 (522) | +0.22 | ✅ |
| go_omission_rate | 0.028 ± 0.022 (30) | 0.014 ± 0.027 (522) | +0.50 | ✅ |
| go_rt | 674.8 ± 79.8 (30) | 584.7 ± 84.8 (522) | +1.06 | ❌ |
| go_rt_all_responses | 675.5 ± 80.2 (30) | 584.8 ± 85.7 (522) | +1.06 | ❌ |
| mean_stop_failure_RT | 571.4 ± 68.8 (30) | 541.4 ± 147.8 (470) | +0.20 | ✅ |
| stop_accuracy | 0.497 ± 0.018 (30) | 0.498 ± 0.095 (522) | -0.02 | ✅ |
| max_SSD | 546.7 ± 103.3 (30) | 519.6 ± 144.6 (522) | +0.19 | ✅ |
| mean_SSD | 400.3 ± 91.8 (30) | 282.2 ± 106.5 (522) | +1.11 | ❌ |
| min_SSD | 245.0 ± 94.1 (30) | 87.0 ± 77.5 (522) | +2.04 | ❌ |
| final_SSD | 410.0 ± 112.5 (30) | 291.7 ± 154.7 (522) | +0.76 | ✅ |
| ssrt | 274.5 ± 46.1 (30) | 302.6 ± 76.3 (522) | -0.37 | ✅ |
| lag1_autocorr | -0.048 ± 0.074 (30) | -0.001 ± 0.044 (522) | -1.07 | ❌ |
| post_error_slowing_ms | 74.3 ± 36.8 (30) | 7.835 ± 24.7 (522) | +2.69 | ❌ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.580 | 0.195 | 0.204 |
| go_omission_rate | 0.813 | 0.530 | 6.4e-08 |
| go_rt | 0.941 | 0.507 | 3.0e-07 |
| go_rt_all_responses | 0.936 | 0.507 | 3.0e-07 |
| mean_stop_failure_RT | 0.465 | 0.377 | 4.3e-04 |
| stop_accuracy | 0.187 | 0.434 | 2.2e-05 |
| max_SSD | 0.715 | 0.202 | 0.170 |
| mean_SSD | 0.861 | 0.589 | 7.3e-10 |
| min_SSD | 1.214 | 0.593 | 5.2e-10 |
| final_SSD | 0.727 | 0.445 | 1.3e-05 |
| ssrt | 0.604 | 0.177 | 0.299 |
| lag1_autocorr | 1.689 | 0.456 | 6.8e-06 |
| post_error_slowing_ms | 1.489 | 0.695 | 4.3e-14 |

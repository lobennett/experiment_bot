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

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.504 | 0.302 | 0.009 |
| go_omission_rate | 0.409 | 0.630 | 2.4e-11 |
| go_rt | 0.135 | 0.393 | 1.9e-04 |
| go_rt_all_responses | 0.138 | 0.377 | 3.9e-04 |
| mean_stop_failure_RT | 0.133 | 0.491 | 8.8e-07 |
| stop_accuracy | 0.305 | 0.477 | 1.9e-06 |
| max_SSD | 0.475 | 0.251 | 0.046 |
| mean_SSD | 0.918 | 0.239 | 0.066 |
| min_SSD | 1.273 | 0.093 | 0.945 |
| final_SSD | 0.933 | 0.231 | 0.081 |
| ssrt | 1.297 | 0.382 | 3.2e-04 |
| lag1_autocorr | 1.789 | 0.249 | 0.048 |
| post_error_slowing_ms | 0.940 | 0.354 | 0.001 |

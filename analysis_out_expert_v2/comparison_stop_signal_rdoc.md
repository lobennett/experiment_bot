# Per-subject behavioral comparison — stop_signal_rdoc

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.936 ± 0.042 (30) | 0.935 ± 0.052 (522) | +0.01 | ✅ |
| go_omission_rate | 0.023 ± 0.015 (30) | 0.014 ± 0.027 (522) | +0.31 | ✅ |
| go_rt | 574.8 ± 40.9 (30) | 584.7 ± 84.8 (522) | -0.12 | ✅ |
| go_rt_all_responses | 575.0 ± 41.5 (30) | 584.8 ± 85.7 (522) | -0.11 | ✅ |
| mean_stop_failure_RT | 506.9 ± 45.3 (30) | 541.4 ± 147.8 (470) | -0.23 | ✅ |
| stop_accuracy | 0.509 ± 0.021 (30) | 0.498 ± 0.095 (522) | +0.12 | ✅ |
| max_SSD | 646.7 ± 61.5 (30) | 519.6 ± 144.6 (522) | +0.88 | ✅ |
| mean_SSD | 503.9 ± 48.2 (30) | 282.2 ± 106.5 (522) | +2.08 | ❌ |
| min_SSD | 355.0 ± 67.4 (30) | 87.0 ± 77.5 (522) | +3.46 | ❌ |
| final_SSD | 516.7 ± 98.6 (30) | 291.7 ± 154.7 (522) | +1.45 | ❌ |
| ssrt | 70.8 ± 22.2 (30) | 302.6 ± 76.3 (522) | -3.04 | ❌ |
| lag1_autocorr | 0.004 ± 0.101 (30) | -0.001 ± 0.044 (522) | +0.12 | ✅ |
| post_error_slowing_ms | 15.6 ± 31.7 (30) | 7.835 ± 24.7 (522) | +0.31 | ✅ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.818 | 0.102 | 0.898 |
| go_omission_rate | 0.558 | 0.503 | 3.7e-07 |
| go_rt | 0.482 | 0.190 | 0.224 |
| go_rt_all_responses | 0.485 | 0.194 | 0.206 |
| mean_stop_failure_RT | 0.306 | 0.277 | 0.021 |
| stop_accuracy | 0.220 | 0.720 | 2.8e-15 |
| max_SSD | 0.425 | 0.599 | 3.3e-10 |
| mean_SSD | 0.452 | 0.880 | 1.1e-25 |
| min_SSD | 0.869 | 0.900 | 1.5e-27 |
| final_SSD | 0.637 | 0.675 | 3.2e-13 |
| ssrt | 0.291 | 1.000 | 6.5e-50 |
| lag1_autocorr | 2.304 | 0.255 | 0.041 |
| post_error_slowing_ms | 1.282 | 0.128 | 0.693 |

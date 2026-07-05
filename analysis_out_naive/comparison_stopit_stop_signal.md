# Per-subject behavioral comparison — stopit_stop_signal

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.951 ± 0.029 (30) | 0.935 ± 0.052 (522) | +0.29 | ✅ |
| go_omission_rate | 0.011 ± 0.013 (30) | 0.014 ± 0.027 (522) | -0.10 | ✅ |
| go_rt | 1063.3 ± 2258.2 (30) | 584.7 ± 84.8 (522) | +5.64 | ❌ |
| go_rt_all_responses | 1173.8 ± 2864.5 (30) | 584.8 ± 85.7 (522) | +6.87 | ❌ |
| mean_stop_failure_RT | 1528.0 ± 5303.0 (30) | 541.4 ± 147.8 (470) | +6.67 | ❌ |
| stop_accuracy | 0.524 ± 0.013 (30) | 0.498 ± 0.095 (522) | +0.27 | ✅ |
| max_SSD | 518.3 ± 81.5 (30) | 519.6 ± 144.6 (522) | -0.01 | ✅ |
| mean_SSD | 369.6 ± 67.1 (30) | 282.2 ± 106.5 (522) | +0.82 | ✅ |
| min_SSD | 185.0 ± 32.6 (30) | 87.0 ± 77.5 (522) | +1.26 | ❌ |
| final_SSD | 373.3 ± 89.8 (30) | 291.7 ± 154.7 (522) | +0.53 | ✅ |
| ssrt | 693.8 ± 2271.2 (30) | 302.6 ± 76.3 (522) | +5.13 | ❌ |
| lag1_autocorr | 0.020 ± 0.089 (30) | -0.001 ± 0.044 (522) | +0.49 | ✅ |
| post_error_slowing_ms | -108.2 ± 1064.5 (30) | 7.835 ± 24.7 (522) | -4.69 | ❌ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.557 | 0.195 | 0.204 |
| go_omission_rate | 0.475 | 0.263 | 0.032 |
| go_rt | 26.6 | 0.533 | 4.9e-08 |
| go_rt_all_responses | 33.4 | 0.530 | 6.4e-08 |
| mean_stop_failure_RT | 35.9 | 0.379 | 3.9e-04 |
| stop_accuracy | 0.133 | 0.824 | 2.6e-21 |
| max_SSD | 0.563 | 0.184 | 0.257 |
| mean_SSD | 0.630 | 0.479 | 1.7e-06 |
| min_SSD | 0.420 | 0.627 | 3.1e-11 |
| final_SSD | 0.580 | 0.406 | 1.0e-04 |
| ssrt | 29.8 | 0.147 | 0.526 |
| lag1_autocorr | 2.016 | 0.309 | 0.007 |
| post_error_slowing_ms | 43.1 | 0.421 | 4.5e-05 |

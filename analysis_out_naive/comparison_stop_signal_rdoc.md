# Per-subject behavioral comparison — stop_signal_rdoc

_Generated 2026-07-19. Bot N=5 sessions (5 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.958 ± 0.024 (5) | 0.935 ± 0.052 (522) | +0.44 | ✅ |
| go_omission_rate | 0.018 ± 0.016 (5) | 0.014 ± 0.027 (522) | +0.16 | ✅ |
| go_rt | 548.4 ± 64.0 (5) | 584.7 ± 84.8 (522) | -0.43 | ✅ |
| go_rt_all_responses | 550.2 ± 64.2 (5) | 584.8 ± 85.7 (522) | -0.40 | ✅ |
| mean_stop_failure_RT | 469.2 ± 66.2 (5) | 541.4 ± 147.8 (470) | -0.49 | ✅ |
| stop_accuracy | 0.477 ± 0.009 (5) | 0.498 ± 0.095 (522) | -0.23 | ✅ |
| max_SSD | 440.0 ± 41.8 (5) | 519.6 ± 144.6 (522) | -0.55 | ✅ |
| mean_SSD | 292.7 ± 47.9 (5) | 282.2 ± 106.5 (522) | +0.10 | ✅ |
| min_SSD | 170.0 ± 75.8 (5) | 87.0 ± 77.5 (522) | +1.07 | ❌ |
| final_SSD | 240.0 ± 54.8 (5) | 291.7 ± 154.7 (522) | -0.33 | ✅ |
| ssrt | 255.7 ± 31.1 (5) | 302.6 ± 76.3 (522) | -0.61 | ✅ |
| lag1_autocorr | 0.160 ± 0.203 (5) | -0.001 ± 0.044 (522) | +3.67 | ❌ |
| post_error_slowing_ms | 21.5 ± 41.0 (5) | 7.835 ± 24.7 (522) | +0.55 | ✅ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.470 | 0.316 | 0.606 |
| go_omission_rate | 0.595 | 0.463 | 0.174 |
| go_rt | 0.754 | 0.276 | 0.761 |
| go_rt_all_responses | 0.750 | 0.278 | 0.754 |
| mean_stop_failure_RT | 0.448 | 0.468 | 0.166 |
| stop_accuracy | 0.096 | 0.358 | 0.446 |
| max_SSD | 0.289 | 0.431 | 0.238 |
| mean_SSD | 0.449 | 0.238 | 0.883 |
| min_SSD | 0.978 | 0.460 | 0.178 |
| final_SSD | 0.354 | 0.328 | 0.561 |
| ssrt | 0.407 | 0.433 | 0.234 |
| lag1_autocorr | 4.625 | 0.600 | 0.031 |
| post_error_slowing_ms | 1.657 | 0.200 | 0.963 |

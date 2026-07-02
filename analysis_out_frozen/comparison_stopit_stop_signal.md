# Per-subject behavioral comparison — stopit_stop_signal

_Generated 2026-07-02. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.954 ± 0.017 (30) | 0.935 ± 0.052 (522) | +0.36 | ✅ |
| go_omission_rate | 0.017 ± 0.011 (30) | 0.014 ± 0.027 (522) | +0.12 | ✅ |
| go_rt | 575.1 ± 9.614 (30) | 584.7 ± 84.8 (522) | -0.11 | ✅ |
| go_rt_all_responses | 575.0 ± 9.618 (30) | 584.8 ± 85.7 (522) | -0.11 | ✅ |
| mean_stop_failure_RT | 991.5 ± 2882.2 (30) | 541.4 ± 147.8 (470) | +3.04 | ❌ |
| stop_accuracy | 0.485 ± 0.041 (30) | 0.498 ± 0.095 (522) | -0.14 | ✅ |
| max_SSD | 476.7 ± 104.0 (30) | 519.6 ± 144.6 (522) | -0.30 | ✅ |
| mean_SSD | 252.1 ± 82.6 (30) | 282.2 ± 106.5 (522) | -0.28 | ✅ |
| min_SSD | 71.7 ± 46.8 (30) | 87.0 ± 77.5 (522) | -0.20 | ✅ |
| final_SSD | 283.3 ± 144.6 (30) | 291.7 ± 154.7 (522) | -0.05 | ✅ |
| ssrt | 323.0 ± 81.7 (30) | 302.6 ± 76.3 (522) | +0.27 | ✅ |
| lag1_autocorr | 0.110 ± 0.091 (30) | -0.001 ± 0.044 (522) | +2.54 | ❌ |
| post_error_slowing_ms | -70.8 ± 557.7 (30) | 7.835 ± 24.7 (522) | -3.18 | ❌ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.335 | 0.317 | 0.005 |
| go_omission_rate | 0.408 | 0.463 | 4.5e-06 |
| go_rt | 0.113 | 0.412 | 7.3e-05 |
| go_rt_all_responses | 0.112 | 0.408 | 8.9e-05 |
| mean_stop_failure_RT | 19.5 | 0.531 | 6.4e-08 |
| stop_accuracy | 0.427 | 0.353 | 0.001 |
| max_SSD | 0.719 | 0.211 | 0.139 |
| mean_SSD | 0.775 | 0.271 | 0.025 |
| min_SSD | 0.603 | 0.338 | 0.002 |
| final_SSD | 0.935 | 0.131 | 0.662 |
| ssrt | 1.071 | 0.295 | 0.011 |
| lag1_autocorr | 2.083 | 0.649 | 4.1e-12 |
| post_error_slowing_ms | 22.6 | 0.465 | 4.1e-06 |

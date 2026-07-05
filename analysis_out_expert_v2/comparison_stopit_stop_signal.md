# Per-subject behavioral comparison — stopit_stop_signal

_Generated 2026-07-05. Bot N=30 sessions (30 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | 0.955 ± 0.025 (30) | 0.935 ± 0.052 (522) | +0.37 | ✅ |
| go_omission_rate | 0.013 ± 0.019 (30) | 0.014 ± 0.027 (522) | -0.03 | ✅ |
| go_rt | 4850.7 ± 15068.9 (30) | 584.7 ± 84.8 (522) | +50.31 | ❌ |
| go_rt_all_responses | 4896.3 ± 15379.6 (30) | 584.8 ± 85.7 (522) | +50.32 | ❌ |
| mean_stop_failure_RT | 4984.6 ± 21926.4 (30) | 541.4 ± 147.8 (470) | +30.05 | ❌ |
| stop_accuracy | 0.541 ± 0.014 (30) | 0.498 ± 0.095 (522) | +0.45 | ✅ |
| max_SSD | 646.7 ± 90.0 (30) | 519.6 ± 144.6 (522) | +0.88 | ✅ |
| mean_SSD | 480.9 ± 72.3 (30) | 282.2 ± 106.5 (522) | +1.87 | ❌ |
| min_SSD | 188.3 ± 31.3 (30) | 87.0 ± 77.5 (522) | +1.31 | ❌ |
| final_SSD | 503.3 ± 97.3 (30) | 291.7 ± 154.7 (522) | +1.37 | ❌ |
| ssrt | 4369.8 ± 15071.0 (30) | 302.6 ± 76.3 (522) | +53.31 | ❌ |
| lag1_autocorr | 0.163 ± 0.104 (30) | -0.001 ± 0.044 (522) | +3.74 | ❌ |
| post_error_slowing_ms | -1851.6 ± 7853.4 (30) | 7.835 ± 24.7 (522) | -75.23 | ❌ |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-registered as exploratory (docs/preregistration.md §Analysis), not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | 0.485 | 0.255 | 0.041 |
| go_omission_rate | 0.709 | 0.130 | 0.680 |
| go_rt | 177.7 | 0.159 | 0.428 |
| go_rt_all_responses | 179.5 | 0.164 | 0.385 |
| mean_stop_failure_RT | 148.3 | 0.111 | 0.838 |
| stop_accuracy | 0.146 | 0.891 | 1.3e-26 |
| max_SSD | 0.622 | 0.502 | 4.0e-07 |
| mean_SSD | 0.678 | 0.824 | 3.1e-21 |
| min_SSD | 0.404 | 0.693 | 5.0e-14 |
| final_SSD | 0.629 | 0.772 | 5.1e-18 |
| ssrt | 197.6 | 0.900 | 1.5e-27 |
| lag1_autocorr | 2.365 | 0.836 | 3.9e-22 |
| post_error_slowing_ms | 317.7 | 0.164 | 0.388 |

# Per-subject behavioral comparison — stopit_stop_signal

_Generated 2026-07-19. Bot N=0 sessions (0 with the expected trial count); human reference = `data/human/stop_signal_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| go_accuracy | — ± — (0) | 0.935 ± 0.052 (522) | — | — |
| go_omission_rate | — ± — (0) | 0.014 ± 0.027 (522) | — | — |
| go_rt | — ± — (0) | 584.7 ± 84.8 (522) | — | — |
| go_rt_all_responses | — ± — (0) | 584.8 ± 85.7 (522) | — | — |
| mean_stop_failure_RT | — ± — (0) | 541.4 ± 147.8 (470) | — | — |
| stop_accuracy | — ± — (0) | 0.498 ± 0.095 (522) | — | — |
| max_SSD | — ± — (0) | 519.6 ± 144.6 (522) | — | — |
| mean_SSD | — ± — (0) | 282.2 ± 106.5 (522) | — | — |
| min_SSD | — ± — (0) | 87.0 ± 77.5 (522) | — | — |
| final_SSD | — ± — (0) | 291.7 ± 154.7 (522) | — | — |
| ssrt | — ± — (0) | 302.6 ± 76.3 (522) | — | — |
| lag1_autocorr | — ± — (0) | -0.001 ± 0.044 (522) | — | — |
| post_error_slowing_ms | — ± — (0) | 7.835 ± 24.7 (522) | — | — |

**Notes.** SSRT is the *mean method* (`go_rt − mean_SSD`), an emergent product of the platform's SSD staircase, not a bot-controlled quantity. Human QC: 496/522 workers have p(respond|signal) within the Verbruggen [0.25, 0.75] band (`stop_acc_in_band` column); the abstract's N=447 used an exclusion that does not reproduce from this data — workers are exported unfiltered with the transparent flag.

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| go_accuracy | — | — | — |
| go_omission_rate | — | — | — |
| go_rt | — | — | — |
| go_rt_all_responses | — | — | — |
| mean_stop_failure_RT | — | — | — |
| stop_accuracy | — | — | — |
| max_SSD | — | — | — |
| mean_SSD | — | — | — |
| min_SSD | — | — | — |
| final_SSD | — | — | — |
| ssrt | — | — | — |
| lag1_autocorr | — | — | — |
| post_error_slowing_ms | — | — | — |

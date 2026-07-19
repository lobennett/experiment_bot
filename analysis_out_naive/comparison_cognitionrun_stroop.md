# Per-subject behavioral comparison — cognitionrun_stroop

_Generated 2026-07-19. Bot N=0 sessions (0 with the expected trial count); human reference = `data/human/stroop_eisenberg.csv`._

**Estimators (current / abstract-matching):** RT = mean of correct-trial RTs; SSRT = mean method (`go_rt − mean_SSD`); post-error slowing = mean(RT|prev error) − mean(RT|prev correct), within-block, omissions excluded; lag-1 = within-block Pearson autocorrelation of valid RTs. Bot and human use the identical functions.

| metric | bot mean ± SD (n) | human mean ± SD (n) | z | within 1 SD |
|---|---|---|---|---|
| congruent_accuracy | — ± — (0) | 0.974 ± 0.049 (522) | — | — |
| congruent_omission_rate | — ± — (0) | 0.009 ± 0.041 (522) | — | — |
| congruent_rt | — ± — (0) | 672.5 ± 101.5 (522) | — | — |
| incongruent_accuracy | — ± — (0) | 0.924 ± 0.080 (522) | — | — |
| incongruent_omission_rate | — ± — (0) | 0.018 ± 0.047 (522) | — | — |
| incongruent_rt | — ± — (0) | 795.2 ± 122.7 (522) | — | — |
| stroop_effect | — ± — (0) | 122.7 ± 60.6 (522) | — | — |
| lag1_autocorr | — ± — (0) | 0.072 ± 0.131 (522) | — | — |
| post_error_slowing_ms | — ± — (0) | 59.2 ± 135.6 (445) | — | — |

**Notes.** `lag1_autocorr` has no canonical human range in the literature; it is reported descriptively. The per-subject CSVs (`*_bot.csv`, `*_human.csv`) carry the full distributions for any further test (KS / equivalence).

## Exploratory: distribution-level comparison

_Pre-specified as exploratory in the frozen design document, not part of the confirmatory mean-location design above. SD ratio = bot between-subject SD / human between-subject SD (1.0 = human-like dispersion); KS = two-sample Kolmogorov–Smirnov test of the per-subject distributions. A cohort can pass the within-1-SD mean gate while failing these — matched means with far too little between-subject variability._

| metric | SD ratio | KS D | KS p |
|---|---|---|---|
| congruent_accuracy | — | — | — |
| congruent_omission_rate | — | — | — |
| congruent_rt | — | — | — |
| incongruent_accuracy | — | — | — |
| incongruent_omission_rate | — | — | — |
| incongruent_rt | — | — | — |
| stroop_effect | — | — | — |
| lag1_autocorr | — | — | — |
| post_error_slowing_ms | — | — | — |

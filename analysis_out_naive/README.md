# Analysis output

Per-subject measures and bot-versus-human comparisons, written by
`experiment-bot-per-subject`.

| File pattern | Contents |
|---|---|
| `per_subject_<task>_<cohort>.csv` | one row per session (bot) or per person (human), with reaction times and accuracies by condition, omissions, task effects, stop-signal reaction time, trial-to-trial correlation, and post-error slowing |
| `comparison_<task>.md` | the bot cohort placed inside the spread of human individuals, plus distribution-level checks |

The same estimator code runs on both cohorts. That parity is the point —
any difference in the numbers is a difference in behavior, not in method.

Files derived from the restricted RDoC raw exports are not committed; they
regenerate from the raw data. See `data/human/README.md`.

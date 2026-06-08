# Metric walkthrough notebooks

One [marimo](https://marimo.io) notebook per dev paradigm. Each reproduces — from first
principles, against the **real bot session data** in `output/` — every metric the validation
oracle computes, and asserts the hand-rolled value equals both the library function
(`experiment_bot.effects.validation_metrics`) and `validate_session_set`. They are the
"show your work" companion to `docs/validation-results.md`.

| notebook | label | class | gating metrics | descriptive / not-computable |
|---|---|---|---|---|
| `stroop_rdoc_metrics.py` | `stroop_rdoc` | conflict | rt_distribution (mu/sigma/tau), post_error_slowing | cse (no contrast labels), lag1 |
| `cognitionrun_stroop_metrics.py` | `stroop_online_(cognition.run)` | conflict | rt_distribution | post_error_slowing = NaN (offline accuracy unrecoverable) |
| `stop_signal_rdoc_metrics.py` | `stop_signal_rdoc` | interrupt | post_error_slowing, ssrt | rt_distribution (no canonical interrupt range) |
| `stopit_stop_signal_metrics.py` | `stop_signal_kywch_jspsych` | interrupt | post_error_slowing, ssrt | rt_distribution |

## Running

```bash
uv run marimo edit notebooks/stroop_rdoc_metrics.py     # interactive
uv run marimo run  notebooks/stroop_rdoc_metrics.py     # read-only app
# headless execution (also how CI could check the assertions still hold):
uv run marimo export ipynb notebooks/stroop_rdoc_metrics.py -o /tmp/out.ipynb --include-outputs
```

Each notebook locates `output/` relative to the installed `experiment_bot` package, so it runs
from any CWD. It pools the same cohort the oracle does (gross-undercount exclusion at
`0.6 * median` trials).

## What each notebook contains

1. The data on disk + a table describing every **raw export column** the adapter reads.
2. The **adapter** (`platform_adapters.py`) mapping raw rows → the 4-field canonical trial
   (`condition`, `rt`, `correct`, `omission`[, `ssd`]), with a derivation table.
3. The cohort completeness filter.
4. Each metric: a prose description of the computation, a hand-rolled recomputation, and an
   assertion that it equals the library + oracle.
5. A cross-check against `validate_session_set` and the published norm ranges.
6. A code-review verdict.

## Code review — findings

**Verdict: the analysis is faithful to the shipped oracle.** In every notebook the hand-rolled
recomputation equals both the library functions and `validate_session_set` to floating-point
tolerance (the `assert` cells pass on execution; cumulative-N values below).

| label | n_used | mu / sigma / tau | PES (ms) | SSRT (ms) |
|---|---|---|---|---|
| stroop_rdoc | 45 | 496.6 / 53.2 / 161.7 | 45.7 | — |
| stop_signal_rdoc | 41 | 473.1 / 59.4 / 92.1 (descriptive) | 30.3 | 257.9 |
| stroop_online_(cognition.run) | 43 | 499.0 / 42.8 / 137.6 | NaN (not computable) | — |
| stop_signal_kywch_jspsych | 41 | 465.9 / 54.5 / 97.8 (descriptive) | 18.5 | 281.6 |

Subtleties a reviewer should know (each is demonstrated in the relevant notebook):

- **One RT-plausibility window, shared.** `fit_ex_gaussian`, `post_error_slowing_magnitude`, and
  `ssrt_integration` all drop RTs outside `[150, 5000] ms` (`RT_PLAUSIBLE_{MIN,MAX}_MS`). The
  STOP-IT notebook shows the before/after concretely: a single multi-second timer-glitch
  post-error trial drove the *unwindowed* pooled PES to ~225 ms; windowed it is ~18.5 ms.
- **PES order-of-operations.** `_compute_pes` removes `rt is None` trials **before** sequencing,
  so omissions — including *successful stop* trials in the stop-signal tasks — are dropped from
  the adjacency and "post-error" pairs across them. On Stroop (few omissions) this is nearly a
  no-op; on stop-signal it is intentional and material.
- **cognition.run PES is structurally NaN.** The offline adapter cannot recover true accuracy
  (key→colour map lives only on the live page), so every responded trial is marked `correct` →
  no errors to condition on. Reported as a non-gating "not computable" entry, not a failure.
- **Interrupt rt_distribution is descriptive.** `norms/interrupt.json` has `null` ex-Gaussian
  ranges (no canonical meta-analytic source), so it is computed but never gates.
- **SSRT is not framework-controlled (scope-of-validity L20).** It is an emergent product of the
  platform's SSD staircase; its marginal pass/fail wobbles batch-to-batch independent of bot
  behavior, and the plausibility window barely moves it.
- **Authoritative source (G4).** Every metric is scored from the platform export
  (`experiment_data.{csv,json}`), never from `bot_log.json`.

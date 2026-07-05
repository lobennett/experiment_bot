# Pre-registration — frozen bot dataset & behavioral comparison

_Drafted 2026-06-30, **before** the confirmatory data collection it governs.
This is the in-repo plan; co-authors should review and (if desired) register a
timestamped copy on OSF before treating the run as confirmatory. The dataset
the abstract reported is **not reproducible** from committed data (see
`docs/paper-roadmap.md` §2 and the verified reproduction check); this frozen,
provenance-clean run replaces it as the paper's primary dataset._

## Goal

Generate a frozen, reproducible bot dataset across four task implementations
and compare per-subject behavior to a human reference, to test the abstract's
claims that an agentic bot produces human-like behavior in **means** (C2) and
**temporal effects** (C3).

## Design

- **Paradigms / platforms / pinned TaskCards** (hermetic — loaded by content
  hash via `--taskcard-sha256`):

  | label | platform | URL | TaskCard hash | trials/session |
  |---|---|---|---|---|
  | expfactory_stroop | expfactory RDoC | deploy.expfactory.org/preview/10 | `45751cfe` | 120 |
  | expfactory_stop_signal | expfactory RDoC | deploy.expfactory.org/preview/9 | `e29f22de` | 180 |
  | cognitionrun_stroop | cognition.run | strooptest.cognition.run | `b16c7891` | 15 |
  | stopit_stop_signal | kywch STOP-IT | kywch.github.io/STOP-IT/.../experiment-transformed-first.html | `6fc729c3` | 288 |

- **N = 30 sessions/paradigm, uniform across all four implementations.**
  Each session uses an explicit, recorded `--seed` (paradigm offset + index) so
  the dataset is regenerable from `scripts/frozen_run.sh`. (History: an initial
  N=15 subset was collected first when per-session runtime made larger N look
  impractical; the collection then extended cleanly to a balanced N=30 across all
  four implementations, keeping the original 15 seeds and adding 16–30.)
- **Calibration disabled (`--no-calibration`).** The startup keypress-latency
  calibration pass is behaviorally inert on every supported platform (it
  reports `too_few_events` and applies an identity adjustment; scope L21) and,
  on cognition.run (no pre-trial idle window), its ~27 s runtime was recorded
  by the platform as the first trial's RT, corrupting it (7.6% of RTs, root-
  caused 2026-06-30). It is disabled for the frozen dataset. cognition.run was
  fully re-collected with it off; because the pass is inert, on-vs-off sessions
  are behaviorally equivalent, and each session's calibration status is
  recorded in `run_metadata.json`.
- **Provenance:** `run_metadata.json` records `session_seed` + `taskcard_sha256`
  per session; URLs are live as of the run date (expfactory previews are
  ephemeral — re-deploy + update the script if expired).

## Measures (estimators are FROZEN in tested code)

All metrics are computed by `experiment_bot.analysis.per_subject` (tested),
identically for bot and human:

- **Means:** go RT / congruent RT / incongruent RT = mean RT of *correct*
  trials; go/stop/condition accuracy; omission rate; Stroop effect = incongruent
  − congruent RT; mean SSD; stop accuracy; stop-failure RT.
- **SSRT = mean method** (`go_rt − mean_SSD`). Reported descriptively; SSRT is
  an emergent product of the platform SSD staircase, **not** a bot-controlled
  quantity (scope L20). The integration method is a deferred, exploratory
  upgrade (paper-roadmap P1-4), not part of this confirmatory plan.
- **Temporal effects:** lag-1 RT autocorrelation (within-block Pearson r of
  valid RTs) and post-error slowing (`mean(RT|prev error) − mean(RT|prev
  correct)`, within-block, omissions excluded).

## Human reference

Eisenberg et al. (2019) trial-level data (`data/human/*_eisenberg.csv`),
`exp_stage == 'test'`, per worker, same estimators. The abstract's human
stop-signal N=447 used an exclusion that does not reproduce; we export **all**
workers and flag `stop_acc_in_band` (p(respond|signal) ∈ [0.25, 0.75], the
Verbruggen criterion) for transparent, documented filtering.

## Exclusions (cohort selection)

- Sessions with a `.incomplete` save marker are excluded.
- Sessions are KEPT regardless of trial count but flagged `complete` (== the
  expected count above); the primary analysis uses `complete` sessions, with an
  all-sessions sensitivity check reported.

## Analysis

- **Primary (confirmatory, descriptive):** per-subject CSVs + a comparison
  report per task (`experiment-bot-per-subject`): bot cohort mean ± SD vs human
  mean ± SD, with z = (bot − human_mean)/human_sd and a within-1-SD flag, per
  metric. This is the abstract's framing, now reproducible.
- **Exploratory (planned, not yet confirmatory):** the adversarial harness in
  `docs/paper-roadmap.md` §5 — per-subject KS / Mann-Whitney, TOST equivalence,
  Benjamini-Hochberg FDR, a bot-vs-human classifier, and an unconfigured-effect
  probe. These will be added and labeled exploratory until pre-registered
  separately.

## What this run does and does not establish

It tests **output-distribution** similarity between bot and human per-subject
behavior. It does **not** test mechanism equivalence — the bot samples RTs from
configured parameters and does not perceive stimuli (the simulate-vs-solve
distinction, scope L1). Conclusions are framed accordingly.

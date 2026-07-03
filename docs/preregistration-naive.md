# Pre-registration — naive-builder experiment (naive vs expert-v2 arms)

_Drafted 2026-07-02, **before** any generation call. Per SP21 design
(`docs/superpowers/specs/2026-07-02-naive-builder-experiment-design.md`):
**this document is committed BEFORE any generation call; generation
transcripts are data.** Nothing about the naive arm's behavioral model
exists yet — not a program, not a transcript, not a simulation-gate report
— at the time this file is committed._

## Goal

Test whether a frontier LLM given **no cognitive-control scaffolding** (no
mechanism menu, no RT-distribution family list, no expert-authored priors —
just page source, protocol signatures, and mechanical facts) can produce a
participant behavioral model whose platform-recorded data is as human-like
as the expert pipeline's, on the same four dev paradigms and against the
same human reference used in `docs/preregistration.md`.

Either outcome is informative: naive ≈ expert (both compared to the human
reference, never to each other) would strengthen the generalizability claim
and motivate shrinking the expert scaffolding; naive < expert would
quantify what the scaffolding contributes, and the four generated programs
become design evidence for a future generative-TaskCard grammar.

## Design

- **Paradigms / platforms / pinned structural TaskCards** — identical dev-4
  set and identical structural cards as `docs/preregistration.md` (hermetic,
  loaded by content hash via `--taskcard-sha256`). Only `response_distributions`,
  `temporal_effects`, `between_subject_jitter`, and `performance` are
  replaced by the naive arm's generated program; navigation, stimulus
  detection, and data capture are the same pinned structural TaskCard used
  by the expert arm:

  | label | platform | URL | TaskCard hash | trials/session |
  |---|---|---|---|---|
  | expfactory_stroop | expfactory RDoC | deploy.expfactory.org/preview/10 | `45751cfe` | 120 |
  | expfactory_stop_signal | expfactory RDoC | deploy.expfactory.org/preview/9 | `e29f22de` | 180 |
  | cognitionrun_stroop | cognition.run | strooptest.cognition.run | `b16c7891` | 15 |
  | stopit_stop_signal | kywch STOP-IT | kywch.github.io/STOP-IT/.../experiment-transformed-first.html | `6fc729c3` | 288 |

  Expfactory preview URLs are ephemeral — re-verify before the live run
  (`reference_dev_paradigm_urls`); redeploy and update the collection script
  if expired. Because both arms load the same structural TaskCard hashes,
  a URL change affects both arms identically.

- **Arms:**
  - **naive** — behavior supplied by a Fable-generated Python program (see
    "Generation" below), executed via `--behavior-program`, on the
    SP20-fixed executor. Output to `output_naive/`.
  - **expert-v2** — the existing pinned Opus-4.8 TaskCards, unchanged,
    **re-collected** under the same SP20-fixed executor so both arms run on
    identical executor code. Output to `output_expert_v2/`, via
    `scripts/frozen_run.sh 30 output_expert_v2` (re-using the original
    frozen seed offsets below).

  Arms are never gated against each other. The Eisenberg human reference is
  the yardstick for both, independently.

- **N = 30 sessions/paradigm/arm**, explicit recorded `--seed`, hermetic and
  idempotent by seed (re-running the collection script skips completed
  seeds).

- **Seed scheme.** `SEED_BASE = 730000` for both arms (matches
  `docs/preregistration.md`'s frozen scheme). Seeds are `SEED_BASE + offset
  + i` for `i` in `1..30`.

  | arm | label | offset |
  |---|---|---|
  | naive | expfactory_stroop | 5000 |
  | naive | expfactory_stop_signal | 6000 |
  | naive | cognitionrun_stroop | 7000 |
  | naive | stopit_stop_signal | 8000 |
  | expert-v2 | expfactory_stroop | 1000 (frozen-run original) |
  | expert-v2 | expfactory_stop_signal | 2000 (frozen-run original) |
  | expert-v2 | cognitionrun_stroop | 3000 (frozen-run original) |
  | expert-v2 | stopit_stop_signal | 4000 (frozen-run original) |

  The naive-arm offsets (5000-8000) are disjoint from the expert arm's
  original offsets (1000-4000, re-used verbatim for expert-v2) and from each
  other, so no seed collides across paradigm or arm.

- **Calibration disabled (`--no-calibration`)** for both arms, for the same
  reason documented in `docs/preregistration.md` (the pass is behaviorally
  inert and corrupts cognition.run's first-trial RT when left on).

- **Provenance.** `run_metadata.json` records `session_seed`,
  `taskcard_sha256`, and — naive arm only — the behavior-program's content
  hash, per session. The naive arm additionally archives, per paradigm,
  `naive_programs/<label>/<sha>.py`, `<sha>.transcript.json` (full
  generation prompt, model id, raw response), and `<sha>.simgate.json`
  (simulation-gate report) — the complete generation provenance trail,
  committed as data alongside (not instead of) this pre-registration.

## Generation (naive arm only)

- **Model:** `claude-fable-5` (fixed; not selected post-hoc).
- **Cardinality:** **one program per paradigm.** The program is generated
  once, content-hashed, and archived with its full generation transcript;
  all 30 seeded sessions for that paradigm execute the single pinned
  program. Between-subject variance must come from inside the program
  (it receives the seed as its only source of per-participant variation).
- **No behavioral iteration (pre-registered):** the first program per
  paradigm that passes the simulation gate (`experiment-bot-naive-sim`) IS
  the program used for data collection. Regeneration is permitted **only**
  on mechanical gate failure (crash, protocol violation, non-determinism,
  disallowed imports) — never because the behavior "looks wrong" or
  unhuman. Regeneration is capped at **2 retries** (3 attempts total per
  paradigm); every attempt, including failed ones, is archived under its
  own content hash with its own transcript and gate report.
- **Neutrality of the generation prompt** is enforced by invariant tests
  scanning the prompt template against the live `EFFECT_REGISTRY` and a
  banned-terms list; the prompt contains no mechanism names, no
  distribution-family names, no phenomenon names (post-error slowing,
  congruency sequence, SSRT, ...), and no numeric behavioral priors. This
  is a code-level, testable guarantee, not a review-only claim.

## Measures

The frozen battery is unchanged: all metrics are computed by the same
tested `experiment_bot.analysis.per_subject` code, with the same
estimators, applied identically to bot (both arms) and human data. See
`docs/preregistration.md` ("Measures", "Human reference") for the full
estimator definitions (go/congruent/incongruent RT, accuracy, omission
rate, Stroop effect, SSRT = mean method, lag-1 RT autocorrelation,
post-error slowing) and the human reference (Eisenberg et al., 2019). No
new estimators are introduced for this experiment.

## Exclusions (cohort selection)

All exclusion rules from `docs/preregistration.md` apply unchanged
(`.incomplete` marker exclusion; `complete` flag by expected trial count;
primary analysis on `complete` sessions with an all-sessions sensitivity
check), plus two rules specific to the naive arm:

- **Live program crash → hard-fail, excluded and counted.** A behavior
  program that passes the simulation gate but crashes, or produces a
  protocol violation (key outside the available set, NaN/negative RT), at
  runtime during a live session causes that session to hard-fail. The
  session is excluded from analysis and counted in the failure tally for
  that paradigm. No silent coercion.
- **≥3 live failures for a paradigm after gate pass → paradigm-failure,
  not retried into submission.** If a paradigm's generated program
  accumulates 3 or more live-session failures (after having already passed
  the simulation gate), that paradigm is reported as a naive-arm failure
  for that paradigm — not patched, not regenerated, not retried until it
  passes. This follows the SP3 honest-failure precedent: a documented
  limitation, not a softened partial success.

## Analysis

- **Primary (confirmatory, descriptive):** each arm compared independently
  to the Eisenberg human reference, per paradigm, per metric — bot cohort
  mean ± SD vs human mean ± SD, z = (bot − human_mean) / human_sd, and a
  within-1-SD flag. Same estimators, same code, same framing as
  `docs/preregistration.md`'s primary analysis. Run via
  `experiment-bot-per-subject --label all --output-dir output_naive ...`
  and the same invocation against `output_expert_v2`.
- **Exploratory:** SD ratio (bot/human), two-sample Kolmogorov-Smirnov
  (bot vs human), and a naive-vs-expert contrast — within-1-SD counts and
  dispersion compared descriptively between the two arms. This
  naive-vs-expert comparison is exploratory only: **arms are never gated
  against each other**; the human reference is the sole confirmatory
  yardstick for both.

## What this run does and does not establish

It tests, for the naive arm, whether removing all expert cognitive-control
scaffolding from the *behavioral* layer (RT distributions, temporal
effects, between-subject jitter, performance targets) changes
output-distribution similarity to human per-subject behavior, relative to
the expert-v2 arm re-collected under the identical fixed executor. It does
**not** test mechanism equivalence for either arm — neither the naive
program nor the expert sampler perceives stimuli (the simulate-vs-solve
distinction, scope L1). It does not establish that the naive program's
*internal* generative logic resembles a cognitive model of any kind; only
its platform-recorded output distribution is compared. A single program
per paradigm (not resampled across generation calls) means this run
speaks to *one* Fable-generated hypothesis per paradigm about human-like
behavior, not to the distribution of programs Fable could produce.

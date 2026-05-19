# SP11 Phase 3 deliverable — calibration pass infrastructure

**Date:** 2026-05-18
**Branch:** `sp11/playwright-recommit`
**Commits:** `3cc865b` (once-gated deprecation), `ce1c283` (cognition.run probe), `f898c05` (calibration package)
**Phase status:** complete, awaiting approval to start Phase 4

## What landed

Phase 3 built the calibration infrastructure that Phase 7 will exercise
against the four dev paradigms. Per Phase 3 user notes, the
infrastructure is delivery-channel-agnostic — the estimator and runner
see a `KeypressDeliverer` abstraction, never a Playwright API. Phase 4
will provide the concrete implementations.

**Sub-task completion (in order):**

| Sub-task | Status | Verdict |
|---|---|---|
| 3.0 — once-gate deprecation warnings (Phase 3 user note) | ✓ | Both warnings now fire once per process |
| 3.1 — cognition.run data-export probe (FIRST, per user note 2) | ✓ | Calibration **feasible** — jsPsych 7.3.1 under the hood |
| 3.2 — KeypressDeliverer abstraction | ✓ | Abstract + MockDeliverer in `src/experiment_bot/calibration/deliverer.py` |
| 3.3 — calibration offset estimator | ✓ | `estimate_calibration()` in `estimator.py` |
| 3.4 — bimodality detection | ✓ | k=2 means + separation + mass + within-SD ratio gates |
| 3.5 — per-trial regression fallback | ✓ | OLS fit triggered automatically when SD > 30 ms |
| 3.6 — pre-trial gate handling | ✓ | `GateDismisser` abstraction in `runner.py` |
| 3.7 — scope-of-validity disclosure + deliverable doc | ✓ | This doc + L9 + L10 in `docs/scope-of-validity.md` |

## cognition.run probe finding (Phase 3.1)

The probe was a kill-switch run on day one of Phase 3, per user note 2.
If cognition.run's data export had been unusable, Phase 3 would have
needed rescoping (e.g., DOM-text parsing, POST interception, or
dropping the paradigm).

**Finding:** cognition.run is jsPsych 7.3.1 under the hood. Scripts
load from `static.cognition.run/js/jspsych-7.3.1/`, and `window.jsPsych`
exposes the standard v7 API (`getCurrentTrial`, `data.get()`,
`getProgress`, etc.). The data accessor is `jsPsych.data.get().values()`
— same as expfactory paradigms. **The calibration estimator does NOT
need a platform-specific data-read function.**

Full probe report: `docs/sp11-phase3-cognitionrun-probe.md`.

This makes the four SP11 paradigms uniformly addressable through
jsPsych's data API for the calibration read-back. Phase 4's
`CDPDeliverer` and `PlaywrightKeyboardDeliverer` will both terminate
in `jsPsych.data.get().values()` for the read-back, modulo the
delivery channel for the fire.

## Calibration model selection (Phase 3.3-3.4)

`estimate_calibration()` picks one of four models from the filtered
event list. Filtering rule: only events with
`platform_recorded_key == bot.key AND platform_recorded_key != None`
count toward the estimate. Per SP7 layer-d, the platform sometimes
records a different key entirely; including those events would
pollute the offset.

| Model | Trigger | Trial-time application |
|---|---|---|
| `fixed_offset` | filtered SD ≤ 30 ms (absolute), unimodal | `bot_intended_rt = sampler_target − mean` |
| `regression` | filtered SD > 30 ms, unimodal | `bot_intended_rt = (sampler_target − intercept) / slope` |
| `escalate` | offset distribution is bimodal | No adjustment; Phase 7 reports un-calibrated z-score |
| `too_few_events` | < 5 correctly-recorded events | Same as escalate |

### Bimodality detection (Phase 3.4 — refined per user feedback)

The spec's original criterion was "two cluster means separated by
>50 ms AND smaller cluster has ≥20% of mass." Implementation surfaced
a false-positive case: k=2 means on a *unimodal-but-high-SD*
distribution always finds two clusters with means separated by ~1.6σ,
which can exceed 50 ms even when the distribution is unimodal. To
prevent this, the implementation adds a third gate:
**separation / within-cluster-SD ≥ 3.0**.

Empirically:
- Unimodal Gaussian with SD = 50 ms: k-means finds centroids at ±40
  ms (separation 80), within-cluster SD ≈ 30 ms, ratio ≈ 2.7 — does
  NOT trigger bimodal (correctly).
- Bimodal mixture (means 0 and 100, each SD 5): centroids 0 and 100,
  within-cluster SD 5, ratio 20 — triggers bimodal (correctly).

Tests cover both edge cases. The three-gate criterion is documented
in scope-of-validity §L9.

## Sample size + filtering (Phase 3 user-note 3 derivative)

Minimum 30 calibration keypresses by default
(`_DEFAULT_KEYS` / `_DEFAULT_INTERVALS_MS` in `runner.py`). Below 5
correctly-recorded events the estimator returns `too_few_events`.
Between 5 and 30 the estimator still runs but the resulting `(mean,
sd)` has a wide CI; Phase 7 should call out these cases descriptively.

## KeypressDeliverer abstraction (Phase 3 user-note 1)

The runner and estimator never reference Playwright. They depend on:
- `KeypressDeliverer.deliver_sequence(keys, intervals) -> list[KeypressEvent]`
- `GateDismisser.dismiss() -> bool`

Phase 3 ships `MockDeliverer` + `MockGateDismisser` + `NoGateDismisser`
for tests. Phase 4 will add `CDPDeliverer`, `PlaywrightKeyboardDeliverer`,
`PlaywrightGateDismisser`.

The mock deliverer is parameterized:
- `recording_offset_mean_ms`, `recording_offset_sd_ms` — Gaussian
  recording offset per event
- `drop_rate` — fraction of events the platform fails to record
- `misrecording_rate` — fraction where platform records a different key
- `bimodal_second_mode` — optional `(second_mean, second_prob)` for
  a Gaussian mixture; tests bimodality detection
- `seed` — for reproducibility

The mock fires "instantly" (no real time elapses); the
`target_intervals_ms` argument controls the bot's RECORDED intended
RT, not real wall-clock time. This keeps tests fast and deterministic.

## Test count

| Stage | pytest count |
|---|---|
| Phase 2 final | 611 collected, 608 passed, 3 skipped |
| Phase 3.0 once-gate deprecation | 613 (+2 once-gate tests) |
| Phase 3.2 deliverer | 623 (+10) |
| Phase 3.3-3.5 estimator | 638 (+15) |
| Phase 3.6 runner | 645 (+7) — **642 passed, 3 skipped** |

Net Phase 3 addition: **+34 tests**, all passing. The 3 skips remain
the same env-gated tests from Phase 1.

## What's now in place for Phase 4

- `experiment_bot.calibration.deliverer.KeypressDeliverer` — abstract
  interface Phase 4 implementations subclass.
- `experiment_bot.calibration.runner.GateDismisser` — abstract gate
  dismisser Phase 4 implementations subclass.
- `experiment_bot.calibration.runner.run_calibration(deliverer, gate)`
  — orchestrator; Phase 4 wires the real deliverers in.
- `experiment_bot.calibration.estimator.CalibrationResult.adjust()` —
  trial-time application (used by the executor in Phase 4+).
- Per-event `delivery.channel` field plumbing in `KeypressEvent.metadata`
  — Phase 4's CDP vs fallback deliverers populate this for the
  bot_log channel breakdown.

## What did NOT change in Phase 3

- The executor: Phase 4 wires calibration into the session-start
  flow.
- The sampler: trial-time RT-adjustment using `CalibrationResult.adjust()`
  is Phase 4's job.
- The Reasoner / Stage 1 prompt: no LLM calls in Phase 3. The live-
  LLM-gated test will run during Phase 5 per spec.
- The validation oracle: unchanged. Phase 7 scoring uses the existing
  `effects/validation_metrics.py`.
- Any TaskCard: regeneration is Phase 5.

## Spec freeze status

§6 pre-registered criteria — UNCHANGED in Phase 3.
Appendix C baseline metrics table — UNCHANGED in Phase 3.
The only spec-adjacent additions are L9 and L10 in `scope-of-validity.md`,
which document Phase 3 calibration behavior. Both are descriptive
not gating.

## Ready for Phase 4?

- Calibration infrastructure landed and tested with mocks.
- Day-one cognition.run probe surfaced a positive verdict; no
  Phase 3 rescoping needed.
- Delivery-channel-agnostic per user note 1 — Phase 4 plugs in CDP +
  page.keyboard.press without touching estimator/runner.
- Once-gated deprecation warnings prevent stderr noise in Phase 7's
  180 sequential sessions.

**Awaiting approval to start Phase 4 (CDP-level keypress + focus
management).** Phase 4a is the kill-switch feasibility spike: 50
CDP keypresses into expfactory Stroop, measure
`bot_pressed == platform_recorded`, escalate if < 60%.

# SP11 Phase 5a deliverable — executor + sampler + pilot-time alignment

**Date:** 2026-05-18
**Branch:** `sp11/playwright-recommit`
**Phase status:** complete, awaiting approval to start Phase 5b

## What landed

Phase 5a wires Phase 4b's CDP delivery channel + paradigm-configurable
dwell into the TaskExecutor's response-press path, plumbs the
calibration result into the ResponseSampler, exposes a calibration-
pass method on the executor (not auto-invoked yet — Phase 5b/7
decides policy), and runs the long-deferred Phase 2 live-LLM pilot
test end-to-end against the regenerated SP11 pipeline.

**Sub-task completion (in approved order from Phase 5 user notes):**

| Sub-task | Status | Touchpoint |
|---|---|---|
| 5a.0 — stopit jsPsych-6 marker probe (CRITICAL PATH) | ✓ | `docs/sp11-phase5a-stopit-probe.md`: `works_with_swap` |
| 5a.1 — TaskCard schema: `runtime.timing.cdp_dwell_ms` + marker overrides | ✓ | `src/experiment_bot/core/config.py`, `src/experiment_bot/prompts/schema.json`, `src/experiment_bot/prompts/system.md` |
| 5a.2 — Executor: CDP session + KeypressDeliverer instantiation | ✓ | `TaskExecutor._setup_keypress_deliverer`, `_run_calibration_pass` |
| 5a.3 — Executor: main-session delivery via `_fire_response_key` | ✓ | Two response-press call sites replaced |
| 5a.4 — Sampler: `CalibrationResult.adjust()` adjustment | ✓ | `ResponseSampler.set_calibration_result`, `_apply_calibration_adjustment` |
| 5a.5 — Pilot-time alignment check (live LLM) | ✓ | Deferred Phase 2 test PASSED in 6:22; 122 CDP dispatches, 0 skips |
| 5a.6 — scope-of-validity L13 + L14 + this doc | ✓ | `docs/scope-of-validity.md`, this file |

## 5a.0 stopit verdict — NOT an escalation

The Phase 4a smoke skip was diagnosed as "jsPsych v6 progress API
differs," not as a categorical CDP delivery failure. The Phase 5a.0
probe confirmed:
- stopit exposes `jsPsych.progress()` (function accessor, v6 style)
- `progress().current_trial_global` returns the monotonic per-trial
  marker we need
- `jsPsych.data.get().values()` returns records carrying `trial_index`
- Pairing is functionally identical via `trial_index`

**Decision:** stopit stays in scope for sp11. Its regenerated TaskCard
(5b) will pin `runtime.timing.trial_marker_js` to the v6 alternative
documented in `docs/sp11-phase5a-stopit-probe.md`. No §11 scope-limit
disclosure needed.

## TaskCard schema additions

Three new fields on `runtime.timing`:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `cdp_dwell_ms` | number | 200.0 | Bot dwell before firing each response keypress (four-step protocol step 2) |
| `trial_marker_js` | string | "" → jsPsych v7 `getProgress().current_trial_global` | JS arrow returning the trial marker |
| `records_js` | string | "" → jsPsych v7 `data.get().values()` | JS arrow returning platform records |

Plus one new field on `RuntimeConfig`:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `delivery_channel` | string | `"cdp"` | `"cdp"` / `"keyboard"` / `"none"` (legacy SP10 path) |

Stage 1 prompt's §5 (Timing Configuration) documents the new fields.
The defaults are jsPsych v7-correct, so unmodified TaskCards continue
to work. Per-paradigm overrides land in 5b (stopit's v6 marker JS;
stop-signal's 100 ms dwell).

## Executor wiring

### Setup
`TaskExecutor.run` now opens a CDP session and constructs the
configured `KeypressDeliverer` after `page.goto` and before navigation.
If CDP isn't available (Firefox, WebKit, mocked tests), it falls
through to the legacy `page.keyboard.press` path so existing tests
keep passing.

### Per-trial fire
Two response-press call sites in `_execute_trial` (the normal-trial
path at line ~1125 and the interrupt-failure path at line ~1073) now
route through `_fire_response_key`, which:
1. Delegates to `deliverer.deliver_at_trial_start(key, dwell_ms=0.0)`
   when a deliverer is configured — this performs the four-step
   verify-and-fire protocol without extra dwell (the executor's
   existing `await asyncio.sleep(remaining)` already supplied the
   bot's intended RT).
2. Falls back to `page.keyboard.press(key)` if no deliverer.
3. Records the channel name, trial marker at fire, and skip status
   into a per-trial `delivery` payload in `bot_log`.
4. Tallies channel counts on `self._delivery_channel_log` for the
   end-of-session metadata block.

### Calibration pass (infrastructure only, NOT auto-invoked)
`_run_calibration_pass(page, n_keys=30)` runs the canonical
`run_calibration(deliverer, gate_dismisser, keys, intervals)` flow
and installs the result on the sampler via
`set_calibration_result(result)`. Phase 5a does NOT invoke this
automatically — Phase 5b's regenerated TaskCards + Phase 7's
measurement runs will decide whether to call it (e.g., as part of
the session-start flow consuming the first N test trials as
calibration trials). Phase 4b's existing tests cover the calibration
machinery; this method is the executor's surface for it.

### Run-metadata enrichment
`run_metadata.json` now carries:
```jsonc
{
  "delivery": {
    "configured_channel": "cdp",
    "channel_counts": {"cdp_dispatchKeyEvent": 122},
    "fire_skip_count": 0,
    "fire_skip_samples": []
  },
  "calibration": { /* present iff calibration ran */ }
}
```
The Phase 6 audit script reads these alongside per-trial `delivery`
fields in `bot_log`.

## Sampler wiring

`ResponseSampler.set_calibration_result(result)` installs a model
that subsequent `sample_rt` / `sample_rt_with_fallback` calls apply
via `result.adjust(rt)` AFTER temporal effects. The adjustment:
- For `fixed_offset` model: `bot_target = sampler_rt - mean_offset`
- For `regression` model: `bot_target = (sampler_rt - intercept) / slope`
- For `escalate` / `too_few_events`: no-op (returns unchanged)

The result is re-floored at `runtime.timing.rt_floor_ms` so an
aggressive offset cannot push fires below physiological-floor cutoffs.

## Pilot-time alignment check (5a.5)

The deferred Phase 2 test
(`test_live_executor_runs_against_regenerated_taskcard`) ran end-to-end
against the SP11 Phase 5a executor in 6:22 minutes (`RUN_LIVE_LLM=1`).
Outcome:

- Bot completed the full Stroop session via CDP delivery.
- `delivery.channel_counts`: `{"cdp_dispatchKeyEvent": 122}`
- `delivery.fire_skip_count`: `0`
- Per-trial `delivery` payload populated on all 122 trial rows in
  `bot_log.json`.

**Implication:** No API drift since the deferred Phase 2 test was
written. The Stage 1 → Stage 5 reasoner pipeline, sampler, navigator,
SessionAgent, executor, and CDP delivery channel all interoperate.
This is the long-deferred sanity check landing as Phase 5a's
correctness anchor.

## Test count

| Stage | pytest count |
|---|---|
| Phase 4b final | 678 passed, 3 skipped |
| Phase 5a.3 executor wiring tests | 688 (+10) |
| Phase 5a.4 sampler calibration tests | 696 (+8) — **all passing** |

Live tests still gate on `RUN_LIVE_LLM=1` / `RUN_LIVE_SMOKE=1`;
default suite runs in ~17s.

## What's now in place for Phase 5b

- Executor uses `CDPDeliverer` per response press (3 of 4 paradigms
  verified live via Phase 4b smokes; pilot test confirms the
  end-to-end on Stroop).
- Sampler can be calibrated per session.
- TaskCard schema accepts paradigm-configurable dwell + marker JS.
- Stopit's jsPsych-6 marker JS resolved at deliverer construction
  via TaskCard's `trial_marker_js` field (no Python code change
  needed in 5b — just the Reasoner-emitted TaskCard pinning the v6
  string).
- Per-trial `delivery` field in `bot_log` ready for Phase 6 audit
  script consumption.

## What did NOT change in Phase 5a

- No TaskCard regeneration. That's Phase 5b.
- No spec edits. §6 / Appendix C remain frozen at `a31487e`.
- Calibration pass not auto-invoked. The infrastructure is there;
  Phase 5b's regenerated TaskCards or Phase 7's measurement script
  will turn it on.
- No new norm files.

## Spec freeze status

§6 pre-registered criteria — UNCHANGED.
Appendix C baseline metrics — UNCHANGED.
Scope-of-validity additions L13 + L14 are descriptive disclosures,
not gating thresholds.

## Pending for Phase 5b

1. Regenerate all 4 dev paradigms' TaskCards via the SP11 pipeline.
2. Pin `runtime.timing.cdp_dwell_ms` per paradigm:
   - Stroop / cognition.run Stroop / expfactory stop-signal: 200 ms default
   - Stopit (jsPsych 6): keep 200 ms default
   - Stop-signal STOP-trial branch (any paradigm): consider 100 ms
3. Pin `runtime.timing.trial_marker_js` for stopit to the v6 form.
4. Decide on calibration auto-invocation policy for Phase 7
   (consume first N test trials, drop them at analysis).
5. Phase 6 audit script generalization can begin once 5b TaskCards
   produce bot_logs with the new `delivery` field at scale.

## Ready for Phase 5b?

- CDP delivery channel landed and live-validated on Stroop.
- Stopit verdict surfaced day-one: NOT an escalation.
- Pilot alignment check passed; pipeline is healthy.
- Sampler+executor wired for calibration but not auto-invoked
  (preserves explicit policy choice for Phase 5b).

**Awaiting approval to start Phase 5b (TaskCard regeneration on
all four paradigms).**

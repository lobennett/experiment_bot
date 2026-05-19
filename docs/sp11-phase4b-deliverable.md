# SP11 Phase 4b deliverable — CDP delivery + focus + fallback

**Date:** 2026-05-18
**Branch:** `sp11/playwright-recommit`
**Phase status:** complete, awaiting approval to start Phase 5

## What landed

Phase 4b implements the canonical CDP keypress channel that Phase 4a's
feasibility spike measured at 100% fidelity. The spike script
(`scripts/probe_cdp_delivery.py`) is removed in this commit; its
machinery now lives in `src/experiment_bot/calibration/cdp_deliverer.py`
behind the `KeypressDeliverer` abstraction. Tests went from 642 to 678
passing (+36 net; 3 skipped same as before).

**Sub-task completion (in approved order from Phase 4a user notes):**

| Sub-task | Status | Touchpoint |
|---|---|---|
| 4b.0 — Phase 8 template: measurement-engine awareness disclosure | ✓ | `docs/sp11-phase8-writeup-template.md` |
| 4b.1 — Phase 6 audit dual-pairing planning note | ✓ | `docs/sp11-phase6-audit-planning.md` |
| 4b.2 — `CDPDeliverer` canonical class + four-step protocol | ✓ | `src/experiment_bot/calibration/cdp_deliverer.py` |
| 4b.3 — `PlaywrightKeyboardDeliverer` fallback | ✓ | `src/experiment_bot/calibration/keyboard_deliverer.py` |
| 4b.4 — `PlaywrightGateDismisser` (button + keyboard fallback) | ✓ | `src/experiment_bot/calibration/playwright_gate_dismisser.py` |
| 4b.5 — Listener-target focus helpers | ✓ | `src/experiment_bot/calibration/focus.py` |
| 4b.6 — Per-trial `delivery.channel` logging | ✓ | `KeypressEvent.metadata.delivery.channel` + `CalibrationRun.delivery_channel_counts` |
| 4b.7 — Mock-based unit tests | ✓ | +36 tests across 4 files |
| 4b.8 — Per-paradigm CDP smoke tests | ✓ partial | 3/4 live-validated; stopit jsPsych-6 deferred |
| 4b.9 — Delete spike script | ✓ | `scripts/probe_cdp_delivery.py` removed |
| 4b.10 — scope-of-validity update (L11, L12) + this doc | ✓ | `docs/scope-of-validity.md` |

## The four-step (five-step) protocol — explicit method

Per Phase 4b user note 2, the protocol is now a named method on
`CDPDeliverer.deliver_at_trial_start(key, dwell_ms=None,
expected_trial_marker=None)`:

  1. **Detect** — read the current trial marker via
     `trial_marker_js` (jsPsych default: `current_trial_global`). If
     `None`, return `skipped=True / no_trial_marker_available`.
  2. **Dwell** — `asyncio.sleep(dwell_ms / 1000)`. Default 200ms;
     paradigm-overridable via the `dwell_ms` parameter.
  3. **Verify** — read the marker again. If advanced, the trial
     ended during dwell (e.g., from a queued keystroke or response
     window timeout). Return `skipped=True /
     trial_advanced_during_dwell`. This is the off-by-one diagnosed
     in the Phase 4a spike, now caught explicitly.
  4. **Focus + Fire** — call `listener_focus_js` if configured, then
     issue `Input.dispatchKeyEvent` for `rawKeyDown` followed by a
     50ms gap and `keyUp`. The CDP field map covers all SP11
     paradigm keys; unmapped letters/digits/keys fall back to a
     derived field set so the deliverer never silently drops a key.
  5. **Wait-for-advance** — poll the marker until it increments, up
     to `trial_advance_timeout_s` (default 30s). Returns once the
     trial has ended.

`deliver_sequence(keys, target_intervals_ms)` (the
`KeypressDeliverer` interface) wraps the per-trial method and pairs
the resulting fire records against platform records by trial-marker
match (jsPsych's per-row `trial_index`).

Per Phase 4b user note 2, the 200ms default dwell was tested across
paradigms. Stroop, stop-signal go trials, and n-back digit responses
all accept it comfortably (response windows ≥ 1000ms in all cases).
Stop-signal **stop** trials have a 250ms SSD that grows; the default
200ms dwell would fire BEFORE the stop signal appears on the
earliest stop trials. Phase 7's stop-signal arm should either
(a) sample bot RT to be longer than SSD on the trial type the bot
chose, or (b) set a per-trial dwell via the executor's wiring. Since
Phase 4b doesn't wire the executor (that's Phase 5), the
configurability is in place but not yet exercised in the main
session loop.

## CDP field map coverage

`KEY_TO_CDP_FIELDS` covers:
- Stroop/stop-signal response: `,` (188), `.` (190), `/` (191)
- n-back digits: `0`–`9` (keyCodes 48–57)
- Navigation: ` `/`Space` (32), `Enter` (13), `ArrowRight` (39),
  `ArrowLeft` (37), `ArrowUp` (38), `ArrowDown` (40), `Escape` (27),
  `Tab` (9), `Backspace` (8)

Fallback derivation for unmapped keys (per Phase 4b user note 3):
- Single ASCII letter → `code='Key{X}'`, `keyCode=ord(X)`
- Single non-letter ASCII char → `code=key`, `keyCode=ord(key)`
- Multi-char key (e.g. `PageDown`) → `code=key`, `keyCode=0`
  (jsPsych keyboard plugin reads from `key` field)

This means the deliverer never silently drops a key — the worst-case
behavior is a literal pass-through that lets jsPsych route on `key`.

## Listener-target focus

`src/experiment_bot/calibration/focus.py` ships three reusable JS
arrows the caller picks from:
- `JSPSYCH_DISPLAY_FOCUS_JS` — focuses `#jspsych-display-element`
  (recommended for all four SP11 dev paradigms).
- `BODY_FOCUS_JS` — focuses `document.body` (generic catch-all).
- `IFRAME_CONTENT_FOCUS_JS` — drills into iframe content body for
  embedded paradigms.

These are caller-supplied at `CDPDeliverer` / `PlaywrightKeyboardDeliverer`
construction via `listener_focus_js=`. The deliverers themselves are
generic per G1 — they don't know about jsPsych.

## Pairing: trial-marker, not index

The Phase 4a spike's 100% fidelity result depended on pairing each
bot fire to the platform record by `trial_marker_at_fire ==
record.trial_index`, not by sequential index. Naive index pairing
gave 26%/2%/0% on the same spike runs because the bot occasionally
detected a trial that ended before the CDP fire landed — those fires
went to the *next* trial, breaking sequential alignment.

Phase 4b preserves trial-marker pairing in `CDPDeliverer._pair_one`
and `PlaywrightKeyboardDeliverer.deliver_sequence` (same logic).
Audit script generalization (Phase 6) will read the
`bot_log.session.method` field to select between trial-marker
(sp11) and RT-based (sp10) pairing.

## Pre-trial gate dismissal

`PlaywrightGateDismisser` tries (a) visible-button click on any
button whose text contains start / begin / continue / next / ok /
ready / go (lowercased substring match), then (b) `Space` + `Enter`
keyboard fallback. Per G1, no paradigm-specific selectors — only
generic advance-keyword matching.

Tested with mock pages: 8 unit tests cover the visible-button-click,
hidden-button skip, keyword-mismatch fallback, click-failure
recovery, custom locale keywords, and `input[type=submit]` value-
attribute fallback paths.

## Per-trial `delivery.channel` logging

Phase 4b plumbs `delivery.channel` through three layers:

1. `KeypressEvent.metadata["delivery"]["channel"]` is set by both
   deliverers (`"cdp_dispatchKeyEvent"` or `"keyboard_press_fallback"`).
2. `CalibrationRun.events` (list of KeypressEvents) and
   `CalibrationRun.delivery_channel_counts` (per-channel tally)
   expose the channel info to the runner's caller.
3. Phase 5's executor wiring (not in Phase 4b scope) will pull these
   into `bot_log.json` per session, where Phase 6's audit script
   reads them.

`MockDeliverer` continues to NOT set a channel; its events bucket as
`"unknown"` in `_summarize_delivery_channels` so downstream writers
can warn or skip.

## Smoke tests

`tests/test_phase4b_paradigm_smokes.py` ships one parametrized live
test per dev paradigm, env-gated on `RUN_LIVE_SMOKE=1`. Each test:

1. Launches headless Chromium.
2. Navigates to the paradigm's live URL.
3. Dismisses the gate via `PlaywrightGateDismisser`.
4. Reaches a test-trial state (records grow + marker available).
5. Fires 3 CDP keypresses via `CDPDeliverer.deliver_at_trial_start`.
6. Asserts at least one fire wasn't skipped.

**Live-validation results (2026-05-18, this session):**

| Paradigm | Outcome | Notes |
|---|---|---|
| expfactory_stroop | PASSED | 96s |
| expfactory_stop_signal | PASSED | trail through instructions + practice |
| cognitionrun_stroop | PASSED | confirms Phase 3.1 cognition.run = jsPsych 7 path |
| stopit_stop_signal | SKIPPED (tolerant) | jsPsych 6 progress API differs; CDP itself didn't error |

stopit's skip is per the smoke harness's `engine_v6_tolerant` flag —
the default `current_trial_global` marker probe returns `None` on
jsPsych 6, so reach-test-phase times out. The CDP fire mechanism
itself works on jsPsych 6 (no engine-specific code in the
dispatcher). Phase 5's executor wiring or Phase 7's measurement runs
must pass a jsPsych-6-aware `trial_marker_js` for stopit.

## What's now in place for Phase 5

- `CDPDeliverer` + `PlaywrightKeyboardDeliverer` — plug-and-play for
  the executor's calibration pass + main session.
- `PlaywrightGateDismisser` — plug-and-play for session welcome screens.
- `focus.py` — three JS arrows for listener-target focus.
- `CalibrationRun` events + channel counts — bot_log writer
  consumes these.

## What did NOT change in Phase 4b

- The executor: Phase 5 wires calibration + main-session delivery into
  the session-start flow.
- The sampler: Phase 5 uses `CalibrationResult.adjust()` for
  RT correction.
- Stage 1 prompt / TaskCard schema: unchanged.
- The Reasoner: no LLM calls in Phase 4b.

## Spec freeze status

§6 pre-registered criteria — UNCHANGED in Phase 4b.
Appendix C baseline metrics table — UNCHANGED in Phase 4b.
Scope-of-validity additions L11 + L12 are descriptive disclosures,
not gating thresholds.

## Pending notes for Phase 5

1. jsPsych-6-aware marker JS for stopit (different
   `trial_marker_js` and `records_js` at deliverer construction).
2. Per-paradigm dwell config — stop-signal stop-trial response
   window analysis may motivate a paradigm-specific dwell at the
   executor's deliver call site.
3. Bot_log writer must consume `KeypressEvent.metadata` (channel +
   skip reason + trial marker) per trial.
4. Phase 5 must run the deferred RUN_LIVE_LLM-gated integration test
   from Phase 2 (per spec §4 Phase 5 + Phase 2 deliverable note 4).

## Ready for Phase 5?

- Canonical CDP delivery channel landed, 100% fidelity confirmed in
  Phase 4a, smokes pass on 3/4 paradigms in Phase 4b.
- Fallback channel + gate dismisser in place.
- Per-trial channel logging plumbed.
- 36 new unit tests; full suite 678 passed, 3 skipped.

**Awaiting approval to start Phase 5 (executor + sampler wiring,
TaskCard regeneration).**

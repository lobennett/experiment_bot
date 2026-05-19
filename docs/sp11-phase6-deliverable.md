# SP11 Phase 6 deliverable — audit-script generalization

**Date:** 2026-05-19
**Branch:** `sp11/playwright-recommit`
**Phase status:** complete, awaiting approval to start Phase 7

## What landed

Phase 6 makes `scripts/audit_alignment.py` paradigm-aware: a
`--label` argument picks the per-paradigm test-row predicate from
`platform_adapters.TEST_ROW_PREDICATES`, and pairing-method
auto-detection routes SP11 input-layer logs through trial-counter
pairing while keeping rt-match pairing as the fallback for legacy
SP10 driver logs. The Phase 5a executor wiring already populates
the fields the audit script needs (verified in 6.0); no executor
changes required.

**Sub-task completion:**

| Sub-task | Status | Touchpoint |
|---|---|---|
| 6.0 — Verify `trial_marker_at_fire` exists in `bot_log.json` | ✓ | Confirmed: present on every CDP-fire trial in the Phase 5a pilot session |
| 6.1 — Phase 5b methodology-honesty note + openalex backlog | ✓ | `docs/sp11-phase5b-deliverable.md`, `docs/sp11-backlog.md` |
| 6.2 — Refactor `audit_alignment.py` (paradigm dispatch + dual pairing) | ✓ | `scripts/audit_alignment.py`, new `TEST_ROW_PREDICATES` in `platform_adapters.py` |
| 6.3 — Parametrized audit tests (20) | ✓ | `tests/test_audit_alignment_phase6.py` |
| 6.4 — scope-of-validity L18 + this doc | ✓ | `docs/scope-of-validity.md`, this file |

## 6.0 — bot_log field verification

Inspected the Phase 5a live-LLM pilot session
(`output/stroop_rdoc/2026-05-18_23-22-37-874596/`):

- 122/124 trial rows carry a `delivery` block with
  `trial_marker_at_fire`, `channel`, `skipped`, and `skip_reason`.
- `run_metadata.delivery.configured_channel` is the session-level
  signal (`"cdp"` / `"keyboard"` / `"none"`).
- `run_metadata.delivery.channel_counts` aggregates per-channel
  fire tallies.

**Verdict:** Phase 6 scope is the audit refactor only — no executor
change. The Phase 5a wiring covered everything the audit script
needs to dispatch correctly.

## 6.2 — Audit-script refactor

### Per-paradigm test-row predicates

Added `TEST_ROW_PREDICATES` in
`experiment_bot.validation.platform_adapters`. Each paradigm has a
predicate that applies its trial-row filter logic to raw
experiment_data rows:

| Predicate | Used for |
|---|---|
| `_is_real_test_trial_expfactory_jspsych7` | expfactory_stroop, expfactory_flanker, expfactory_n_back (trial_id == 'test_trial', excluding fixation/ITI/feedback/attention_check) |
| `_is_real_test_trial_expfactory_stop_signal` | expfactory_stop_signal (trial_type='poldracklab-stop-signal' AND exp_stage='test') |
| `_is_real_test_trial_stopit` | stopit_stop_signal (block_i ∈ {1,2,3,4}; block 0 is practice) |
| `_is_real_test_trial_cognitionrun_stroop` | cognitionrun_stroop (trial_type='html-keyboard-response' + non-null rt + text/colour fields) |

Dispatch is via `test_row_predicate_for_label(label)`; both
task.name keys (historical) and URL-label keys (SP11+) are
registered. Unknown labels raise loudly.

### Pairing-method dispatch

`detect_pairing_method(bot_log)` returns:
- `trial_counter` if any bot trial has
  `delivery.trial_marker_at_fire`. SP11 input-layer path.
- `rt_match` otherwise. SP10 driver-legacy fallback.

CLI `--pairing` flag overrides auto-detection for forensic re-
pairing.

### Type coercion (gotcha)

CSV reads return `trial_index` as strings (`"245"`); JSON reads
return ints (`245`); bot-side markers are always ints. The audit
script normalizes both sides via `_normalize_marker(value)` before
set-membership lookup. **This was a one-line bug at first run** —
without normalization, all 122 paired fires showed as
`plat_no_match`. After fix: 118/118 paired = **100%
pressed_eq_recorded** on the Phase 5a pilot.

### Per-channel breakdown

Audit output decomposes paired fires by
`bot_log[*].delivery.channel`. Three values supported:
- `cdp_dispatchKeyEvent` (SP11 canonical)
- `keyboard_press_fallback` (SP11 non-Chromium fallback)
- `page_keyboard_press` (legacy / no-deliverer path)
- `rt_legacy` (synthetic bucket for rt-match-paired SP10 logs)

Phase 8 §7's channel-fidelity table reads directly from this
breakdown.

## Empirical anchor — Phase 5a pilot rerun under new audit

Re-running the new audit against the Phase 5a pilot session:

```
=== expfactory_stroop: 2026-05-18_23-22-37-874596  (pairing=trial_counter) ===
  bot_trials=124, plat_test=120
  paired by trial_marker: 118
  pressed_eq_recorded:    118/118 (100.0%)
  pressed_eq_expected:    111/118 (94.1%)
  skipped fires:          0
  bot fires w/o platform: 4
  per-channel breakdown:
    cdp_dispatchKeyEvent           118/118 (100.0%)
```

**This is the SP11 input-layer claim landing empirically:** when
the bot fires via CDP with trial-marker pairing, the platform
records the bot's intended key 100% of the time (118 paired
trials). The SP7 layer-d gap (44% page→platform) is closed by the
SP11 delivery channel; the §6 H1 hard gate is on track. Phase 7's
N=30-per-paradigm sweep will produce the authoritative number.

The 4 unpaired bot fires (122 fired − 118 paired) correspond to
trials where the bot fired into an interstitial state — likely
between trial_index transitions. Phase 7 reports will surface
this as a residual ~3% drop signal worth tracking.

## Test count

| Stage | pytest count |
|---|---|
| Phase 5c final | 726 passed, 3 skipped |
| Phase 6.3 audit tests (+20) | **746 passed, 3 skipped** |

The Phase 6 tests cover pairing-method auto-detection, type
coercion, trial-counter pairing including mis-recording and
unpaired cases, per-channel breakdown, rt-match pairing on
legacy logs, per-paradigm dispatch for all 6 supported labels,
and end-to-end CSV+bot_log integration.

## What's now in place for Phase 7

- Audit script accepts every supported paradigm via `--label`.
- Pairing auto-detects from bot_log shape; explicit `--pairing`
  override for cross-arm forensics.
- Channel breakdown ready for Phase 8 §7.
- Loud failure on unregistered labels (no silent fall-through).

## What did NOT change in Phase 6

- The executor: Phase 5a wiring already covered the bot_log
  fields the audit script needs.
- TaskCard schema / norms / Reasoner prompts.
- Phase 7's measurement script (separate piece; the audit script
  is one input to Phase 7's report pipeline).

## Pending notes for Phase 7

1. Phase 7's per-session loop should pipe each session dir through
   `scripts/audit_alignment.py --label <label>` and aggregate the
   JSON output across sessions for the §6 hard-gate table.
2. The 4-fires-without-platform-record signal in the pilot
   session is worth a Phase 7 monitoring threshold (flag if a
   session has > 10% bot_no_match rate — suggests CDP fired into
   ITIs at scale, possibly due to a paradigm-specific dwell
   misconfiguration).
3. For paradigms whose `runtime.timing.cdp_dwell_ms` was floor-
   clipped to 50 ms (expfactory_stop_signal, stopit), watch for
   elevated `bot_skipped` counts in audit output — would mean the
   four-step protocol's verify step is catching trial boundaries
   that the bot would otherwise fire past.

## Ready for Phase 7?

- All 4 dev paradigms supported via the audit dispatch.
- Empirical anchor (100% on the pilot) confirms the claim is
  measurable end-to-end.
- §6 hard gates (H1 ≥85% mean, H2 ≥75% per-paradigm floor) read
  cleanly off the new audit output.
- scope-of-validity L18 documents the audit semantics.

**Awaiting approval to start Phase 7 (N=30 sequential
measurement sweep × 4 paradigms × 2 calibration arms).**

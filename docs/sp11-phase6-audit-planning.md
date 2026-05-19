# SP11 Phase 6 audit-script generalization — planning note

**Status:** PLANNING (not implemented).
**Added:** 2026-05-18 during Phase 4b, per Phase 4a user note 5.

## Why this doc exists

The Phase 4a feasibility spike surfaced a pairing issue that Phase 6's
audit script needs to handle correctly: **the bot's fire index does
not always equal the platform's record index.** Naive sequential
pairing
(`bot_log[i] ↔ platform_record[n_before + i]`) gave 26%/2%/0% fidelity
on otherwise-clean spike runs; trial-counter-based pairing (matching
on `jsPsych.getProgress().current_trial_global` at fire time) gave
100% on the same runs.

This means audit_alignment.py (currently SP10-shaped, index-based)
needs two pairing methods, with Phase 6 selecting between them.

## The two pairing methods

### (a) trial-counter pairing (sp11 input-layer path)

Bot records `trial_global` at fire time (the value of
`jsPsych.getProgress().current_trial_global` immediately before the
CDP / `keyboard.press` call). Platform records `trial_index` as part of
each row. Pair by exact match on these integers.

Used when:
- `bot_log[i].delivery.channel ∈ {cdp_dispatchKeyEvent,
  keyboard_press_fallback}`, OR
- Top-level `bot_log.session.method == 'sp11_input_layer'` (set by the
  Phase 4b executor wiring).

This is the canonical Phase 7 path.

### (b) RT-based pairing (sp10 driver path)

Bot records intended `rt_ms` at fire time. Platform records `rt` in ms.
Pair by minimum |bot_rt - platform_rt| within a small candidate window
(typically a 3-trial sliding window of platform records).

Used when:
- `bot_log` carries sp10 driver metadata (e.g., a
  `monkey_patch_signature` field), OR
- `bot_log.session.method == 'sp10_driver'`.

Retained so historical sp10 sessions remain auditable. Should NOT be
added to sp11's Phase 7 measurement runs.

## Phase 6 work

1. Refactor `scripts/audit_alignment.py`:
   - `--label <paradigm_url_label>` argument loads the per-paradigm
     test-row filter via `experiment_bot.validation.platform_adapters
     .adapter_for_label(...)`.
   - Pairing-method selection: read top-level `bot_log.session.method`;
     if absent, infer from per-event `delivery.channel`; if still
     ambiguous, error with a clear message ("pass --pairing
     {trial_counter|rt_match|index_legacy}").
   - Add explicit `--pairing` override for forensic re-pairing.
2. Channel breakdown: report
   `pressed == platform_recorded` per `delivery.channel`. This is the
   §7 Phase 8 channel-fidelity number.
3. Tests parametrized over the four dev paradigms, each pairing
   method, mocked fixtures.

## Pre-registration guard

The pairing method is a measurement choice, not a hypothesis-driven
choice. Phase 7 commits to trial-counter pairing for new sessions;
Phase 6's RT-fallback is for backward compatibility with sp10
artifacts, not for "the trial-counter result wasn't flattering, let's
try RT pairing instead." Audit script should make this distinction
visible by emitting `pairing_method` in its output and refusing to
silently switch methods.

## Not in Phase 4b scope

This doc is the planning note. The actual refactor happens in Phase 6
per the spec. Phase 4b's job is only to ensure the bot writes the
`bot_log.session.method` + `delivery.channel` fields the Phase 6
script will read.

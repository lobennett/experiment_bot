# SP11 complete — Playwright recommit + N=5 measurement

**Tag:** `sp11-complete` (pending; tagged at end of SP12 Phase 4 deliverable)
**Branch:** `sp11/playwright-recommit`
**Goal:** return the bot to a Playwright input-layer path, validate
cross-deployment generalization on 4 paradigms, measure post-calibration
behavior.

## What SP11 produced

- **Phase 1:** branch creation, file inventory, cherry-picks from sp10
  (audit_alignment.py + CSE label fix + writer microsecond), URL-label
  adapter aliases.
- **Phase 2:** effects-library gap-fill (practice_effect,
  vigilance_decrement, pink_noise alpha convention, condition_repetition
  deprecation).
- **Phase 3:** calibration pass infrastructure (KeypressDeliverer
  abstraction, estimator, bimodality detection, regression fallback;
  cognition.run probe verified jsPsych 7.3.1).
- **Phase 4a:** CDP feasibility spike — 100% fidelity on expfactory Stroop.
- **Phase 4b:** canonical CDPDeliverer + PlaywrightKeyboardDeliverer +
  PlaywrightGateDismisser + four-step protocol + per-trial delivery.channel
  logging.
- **Phase 5a:** executor wiring + sampler integration + pilot-time
  alignment via deferred Phase 2 live-LLM test (PASSED in 6:22).
- **Phase 5b:** TaskCard regeneration on 4 paradigms + calibration policy
  (auto-invocation default-on, --no-calibration for Phase 7 pre-cal arm),
  drop-from-scope machinery (sp11_supported field), parameter drift report.
- **Phase 5c:** Stroop variance characterization (3 additional regens) +
  scope-of-validity L17 (§6.2 reinterpretation as absolute |z| against
  human reference, not deltas from sp9c).
- **Phase 6:** audit-script generalization — `scripts/audit_alignment.py`
  paradigm-aware via `--label`, trial-counter pairing for sp11
  input-layer logs, rt-match fallback for sp10 legacy. Empirical anchor:
  118/120 paired × 118/118 within-pair = 98.3% effective fidelity on
  the Phase 5a pilot session.
- **Phase 7 N=30 sweep:** Stroop 60/60 perfect, expfactory_stop_signal
  30/30 + 2/30 (network outage overnight), stopit + cognitionrun
  re-runs landed via targeted N=5 sweeps. Final results in
  `docs/sp12-deliverable.md` (SP12 re-measurement supersedes Phase 7
  results).
- **Phase 7 N=5 results (pre-SP12 cleanup baseline):** see git history
  at commit `ffb9f07` (`docs/sp11-phase7-results.md`).

## Scope-of-validity additions accumulated in SP11

L9–L18 in `docs/scope-of-validity.md`. Each is a small disclosure of
a concrete capability or limitation:

- L9: calibration variance ceiling
- L10: calibration channels (CDP primary, keyboard fallback)
- L11: four-step protocol
- L12: trial-marker pairing
- L13: executor delivery + paradigm-configurable dwell
- L14: calibration-adjusted sampling
- L15: drop-from-scope policy
- L16: pre-cal vs post-cal experimental arms
- L17: §6.2 absolute |z| reinterpretation
- L18: audit-script generalization

## Generalization status at SP11 close

3 of 4 paradigms support a cautious cross-deployment claim with
structurally humanlike patterns (Stroop effect, race-model SSRT,
Gratton CSE within norm on expfactory Stroop). Absolute parameters
drift above human norms on Stroop (RTs +200-400 ms) and stopit
(SSRT > 280 ms). cognitionrun shows the Stroop effect but fails on
the sequence-dependency metric (Gratton CSE too negative) and has
an operational calibration defect.

## Backlog rolled into SP12

- Codebase simplification (this SP)
- cognitionrun calibration-pass defect (per `docs/sp11-backlog.md`)
- jsPsych platform-recording gap (memory:
  [[project_jspsych_keypress_layer_d]])

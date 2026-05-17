# SP10 — Driver-based platform architecture

**Date:** 2026-05-15
**Parent tag:** `sp9c-investigation-complete` (to be tagged at current `sp9c/layer-d-investigation` HEAD `9886362` before SP10 work begins)
**Worktree:** `.worktrees/sp10` off `sp9c-investigation-complete`
**Target tag:** `sp10-complete`

## 1. Motivation

SP6 validated PES on Flanker. Every subsequent SP (SP7, SP8, SP9a, SP9c) has been chasing the layer beneath: why per-trial alignment between the bot's intended response and the platform's recorded response stays at ~50% for paradigms with counterbalanced keymaps. Each SP fixed one observed symptom and surfaced the next.

The recurring failure mode is structural, not symptomatic. The bot has been:

1. Extracting platform-specific JS at Reasoner time (`response_key_js`, `stimulus.detection`, `navigation.phases`, `phase_detection`) — every extraction has had reliability issues, with SP3/SP4/SP7/SP8 each documenting different failure modes for the same general extraction problem.
2. Delivering responses via synthetic keystrokes (`page.keyboard.press`) — SP9c Phase B.3 showed these events land on `document.activeElement` and don't bubble to jsPsych's listener at `#jspsych-display-element`, explaining the ~50% pressed-to-recorded gap.
3. Treating platform-specific knowledge as a generic-with-config layer in the bot library — but the bot's `_resolve_response_key`, `phase_detection`, `_navigator.execute_all`, etc. effectively encode jsPsych-shaped behaviors with TaskCard knobs.

The user's framing (raised during the SP9c user-checkpoint): the bot's goal is to demonstrate that online behavioral-data platforms (Prolific, mTurk) cannot reliably distinguish bot data from human data. Credibility for that claim requires per-trial fidelity, not aggregate-only. Iterating on the synthetic-keystroke path has reached diminishing returns.

## 2. Hypothesis

Restructure the bot into:
- **A slim, paradigm-agnostic bot library** (trial-loop coordination, RT sampling, effect application, accuracy logic) — the parts SP1-SP6 got right.
- **Platform drivers** — per-platform classes that own all page-touching concerns: identification, phase recognition, stimulus detection, navigation, response delivery, data export retrieval. One driver per supported platform. Each driver hooks the platform's own response-handler so the bot's responses are recorded with 100% fidelity.
- **A driver registry** — at session start, identify the platform via cheap heuristic (`window.jsPsych`, etc.), pick the matching driver. No match → DiagnosticDriver writes a `driver_needed.md` report.
- **A shrunken Reasoner pipeline** — Stage 1 produces a simplified TaskCard: paradigm metadata, condition labels, literature-derived behavioral parameters, recommended driver. No more brittle platform-specific JS extraction.

**Falsifiable claim:** under the new architecture, `pressed == platform_recorded` lifts from current ~50% to ≥ 90% on all 4 dev paradigms, while preserving SP5 (Flanker rt_distribution within published norms) and SP6 (Flanker PES within 25-55ms) validation gates.

## 3. Approach

Five phases. Each phase ends with a deliverable + user checkpoint. The phased structure lets you pull the plug at any phase boundary without losing prior work.

### Phase 1 — Driver infrastructure (no platform-specific code)

- New `src/experiment_bot/drivers/` package.
  - `base.py`: `PlatformDriver` Protocol + types (`TrialLoopState`, `TrialContext`, `DeliveryResult`, `NavigationOutcome`, `ExperimentData`, `DriverError`, `UnsupportedVersionError`).
  - `registry.py`: `REGISTERED_DRIVERS: list[type[PlatformDriver]]` (initially empty), `identify_driver(page) -> PlatformDriver`.
  - `diagnostic.py`: `DiagnosticDriver` — last-resort fallback. Two construction paths: `for_unknown_platform(page)` and `for_version_mismatch(page, err)`. Writes a `driver_needed.md` report in the session directory and raises `DiagnosticError`.
- `vendor/` directory at repo root + `vendor/LICENSES.md`.
- Unit tests for the registry mechanism (mock drivers with stubbed `can_handle`; verify `identify_driver` picks first match, falls through to `DiagnosticDriver` for no match and version mismatch).
- **Deliverable:** registry works with mocked drivers; DiagnosticDriver writes a structured report.

### Phase 2 — Bot library refactor

- Refactor `core/executor.py` to use the driver protocol:
  - `run_session(driver, taskcard)` follows the slim trial loop from spec §2:
    ```
    await driver.setup(page)
    while True:
      state = await driver.loop_state(page)
      if state == COMPLETE: break
      if state == NEEDS_NAVIGATION:
        outcome = await driver.navigate(page); bot_log.record(outcome); continue
      ctx = await driver.get_trial_context(page)
      rt = sampler.sample(ctx.condition, history)
      intended_correct = py_rng.random() < taskcard.accuracy_for(ctx.condition)
      response = resolve_response(ctx, intended_correct, taskcard)
      result = await driver.deliver_response(page, response, rt)
      bot_log.record_trial(ctx, response, rt, result)
      history.append(ctx, intended_correct)
      await driver.wait_for_trial_end(page)
    await driver.wait_for_completion(page)
    data = await driver.retrieve_data(page)
    writer.save_platform_data(data)
    ```
  - `resolve_response(ctx, intended_correct, taskcard)` is paradigm-agnostic — uses `ctx.expected_correct` when driver provides it; falls back to `taskcard.task_specific.key_map[condition]` for backward compat; random choice from `ctx.allowed_responses` as last resort.
- Delete SP9a-era `_invoke_session_agent`, `_runtime_key_mapping`, `_session_agent_directive`, `_KEY_ALIASES`, `_normalize_key`. The driver subsumes runtime intelligence properly.
- Stop reading `task_specific.response_key_js`, `task_specific.key_map` (except as the backward-compat fallback in `resolve_response`), `navigation.phases`, `runtime.phase_detection.*`, `runtime.advance_behavior.*`, `runtime.attention_check.*`, `runtime.data_capture.*`, `runtime.trial_interrupt.*`.
- Update `cli.py` to invoke `identify_driver(page)` at session start; delete `_build_session_agent`.
- Adapt existing tests: those exercising platform-touching mechanics (phase_detection, navigation, response_key_js) get rewritten to test driver mocks instead.
- **Deliverable:** bot library uses the driver protocol cleanly; against any real URL, the bot reaches DiagnosticDriver (no real driver registered yet) and writes `driver_needed.md`; existing test suite passes (modulo the platform-touching tests that get reframed).

### Phase 3 — JsPsychDriver (first real driver)

- Vendor `vendor/jspsych/<version>/` anchor files for ONE jsPsych version (whichever expfactory currently uses; identify via WebFetch + live page inspection). Files include `KeyboardListenerAPI.ts`, the plugin lifecycle entry, the data-export module, with provenance comments.
- Build `src/experiment_bot/drivers/jspsych/`:
  - `driver.py`: `JsPsychDriver` class implementing every method of `PlatformDriver`.
  - `responses.py`: callback-hook installation. The driver monkey-patches `pluginAPI.getKeyboardResponse` so when the platform calls it, the driver intercepts; it stores the callback and `valid_responses` for the trial; later when `deliver_response(page, key, rt)` is called, the driver invokes the captured callback directly with `{key, rt}` as if a real keypress had fired. The platform records the response normally. If the monkey-patch turns out to be too fragile (e.g., closure scoping), fallback is `page.dispatch_event` targeted at the vendored `#jspsych-display-element` selector (rootElement from SP9c Phase B.3).
  - `phases.py`: phase recognition. `loop_state` reads `window.jsPsych?.getCurrentTrial?.()` and inspects `type` — `instructions` / `html-button-response` → NEEDS_NAVIGATION; `html-keyboard-response` (or paradigm-specific keyboard plugin) → READY_FOR_TRIAL; experiment-end marker → COMPLETE.
  - `navigation.py`: `navigate(page)` advances jsPsych's current trial. For `instructions`: press Space. For attention-check plugins: respond appropriately. For inter-trial-feedback: dismiss.
  - `data_export.py`: `retrieve_data(page)` invokes `jsPsych.data.get().csv()` (or `.json()`) and parses; writes alongside `bot_log.json` in the session dir.
- Unit tests with `AsyncMock` page + stubbed jsPsych runtime state.
- One end-to-end smoke run on stroop_expfactory (manual, not in CI).
- **Deliverable:** JsPsychDriver completes one stroop session end-to-end; `experiment_data.json` retrieved; bot_log shows trial flow; per-trial fidelity ≥ ~90% on the smoke session.

### Phase 4 — Reasoner pipeline simplification

- Update `src/experiment_bot/prompts/system.md` (Stage 1 system prompt):
  - Remove guidance about `response_key_js`, `navigation.phases`, `phase_detection`, `attention_check`, `advance_behavior`, `data_capture`. These are now driver-internal.
  - Add a section: "Recommended driver detection" — Stage 1 examines the page source for platform markers (e.g., `<script src=".../jspsych/dist/...">`, `import { initJsPsych } from "jspsych"`, etc.) and emits `recommended_driver: "JsPsychDriver"` (or `"CognitionRunDriver"`, `"PsychoJsDriver"`, `"unknown"`).
  - Reduce `REQUIRED_FIELDS_CHECKLIST` to: task metadata, stimuli (id + condition + brief description only), performance.accuracy/omission, pilot_validation_config. Stage 2 fills response_distributions + temporal_effects + between_subject_jitter (unchanged).
- Update `core/config.py` `TaskConfig` schema: keep `task`, `stimuli` (slimmed), `response_distributions`, `temporal_effects`, `between_subject_jitter`, `performance`, `pilot`. Add `recommended_driver: str`, `driver_hints: dict`. Mark obsolete fields (`task_specific`, `navigation`, the verbose `runtime.*`) as deprecated but tolerated for backward compat (Phase 6).
- Update Stage 1 validator (`reasoner/validate.py`) to reflect the smaller required-fields set.
- Stage 6 pilot becomes: "Build a session via Phase 2's `run_session`, run 5 trials, confirm `retrieve_data` returns non-empty data." Same shape, smaller failure surface.
- Migrate the 3 existing jsPsych TaskCards (committed in `b06122e` on the sp8 branch): one-line addition `recommended_driver: JsPsychDriver`. No regeneration needed.
- **Deliverable:** Stage 1 produces simplified TaskCards on a held-out paradigm; migrated existing TaskCards work with the new architecture.

### Phase 5 — Empirical validation

12 sessions across the 4 dev paradigms (3 jsPsych + 1 best-effort cognitionrun). Run order: stroop first (biggest signal), n-back (regression check), stop-signal expfactory (label-mismatch test), stop-it (different jsPsych port).

Per-paradigm: 3 sessions × seeds spaced from prior SP audits to allow before/after comparison.

**Hard gates (must pass to declare SP10 complete):**

| Gate | Source | Target |
|---|---|---|
| Stroop pressed==recorded | SP9a baseline 48.6% | ≥ 90% |
| N-back pressed==recorded | SP8 baseline ~64% | ≥ 90% (no regression) |
| Stop-signal pressed==recorded | SP9a baseline 37.3% | ≥ 90% |
| Stop-it pressed==recorded | SP8 baseline ~37% | ≥ 90% |
| Flanker rt_distribution | SP5 gate | within `norms/conflict.json` ranges |
| Flanker PES | SP6 gate | within 25-55ms |
| Bot completes session | currently fragile | All 12 sessions complete with platform data retrieved |

**Soft gates (descriptive, not blockers):**

- Stroop Gratton effect (CSE) magnitude extractable and within published ranges.
- Stop-signal SSRT estimate from the bot's adaptive-SSD trajectory is in physiologically plausible range (~200-300ms).
- No platform shows visible "incorrect / please respond" feedback during practice when the bot is responding (the user-observable indicator of layer-d failure).

If any hard gate fails → results report frames the gap honestly; SP10 ships as MIXED with explicit remaining work in SP10b/SP11.

### Phase 6 — Documentation + tag (no code)

- Write `docs/sp10-results.md` summarizing Phase 5 outcomes.
- Update `CLAUDE.md` sub-project history with SP10 entry.
- Update `docs/reviewer-1-charter.md` "Last reviewed at" + threat-model probes.
- The CLAUDE.md edits proposed in §6 of this spec (adversarial framing, driver architecture, bot_log diagnostic-only) land EARLIER — as the first commit on the SP10 branch (Phase 1, Step 1).
- Tag `sp10-complete` on the commit landing `docs/sp10-results.md`.

## 4. Out of scope

- **CognitionRunDriver in initial scope.** Cognitionrun_stroop has no working TaskCard (SP8 Stage 6 pilot exhausted). Phase 5 records this as "tested, blocked at Reasoner stage; driver implementation deferred."
- **PsychoJsDriver.** When/if user adds a PsychoPy task to scope.
- **Multi-browser support.** Chromium only.
- **Browser/OS fingerprint stealth.** User-Agent strings, mouse-curve naturalism, screen resolution patterns — out of scope. SP10 targets the keyboard-response layer.
- **Stop-signal SSD-trajectory matching to specific human cohorts.** SP10 verifies the bot CAN produce SSD trajectories; whether they match specific demographic patterns is parameter-tuning, not architecture.
- **Multi-session bot identity.** No within-bot-across-sessions persistence claims.
- **Real-time auto-adaptation to new platform versions.** Vendored versions only; unanchored versions → DiagnosticDriver.

## 5. Deliverables

### Workspace

Worktree: `.worktrees/sp10`, branch `sp10/driver-architecture`, branched off `sp9c-investigation-complete` (a tag to be applied at `sp9c/layer-d-investigation` HEAD `9886362` before SP10 begins).

### Code files (new)

- `src/experiment_bot/drivers/__init__.py`
- `src/experiment_bot/drivers/base.py` — Protocol + types
- `src/experiment_bot/drivers/registry.py` — REGISTERED_DRIVERS + identify_driver()
- `src/experiment_bot/drivers/diagnostic.py` — DiagnosticDriver
- `src/experiment_bot/drivers/jspsych/__init__.py`
- `src/experiment_bot/drivers/jspsych/driver.py`
- `src/experiment_bot/drivers/jspsych/responses.py`
- `src/experiment_bot/drivers/jspsych/phases.py`
- `src/experiment_bot/drivers/jspsych/navigation.py`
- `src/experiment_bot/drivers/jspsych/data_export.py`
- `vendor/LICENSES.md`
- `vendor/jspsych/<version>/` — selective anchor files per Section 1.5 of brainstorm

### Code files (modified)

- `src/experiment_bot/core/executor.py` — slim trial loop, delete SP9a SessionAgent integration
- `src/experiment_bot/cli.py` — invoke `identify_driver()`, delete `_build_session_agent`
- `src/experiment_bot/core/config.py` — schema slim-down (deprecate `task_specific`, `navigation`, parts of `runtime`)
- `src/experiment_bot/prompts/system.md` — Stage 1 prompt simplification
- `src/experiment_bot/reasoner/stage1_structural.py` + `validate.py` — shrink required fields
- `src/experiment_bot/reasoner/stage6_pilot.py` — pilot via driver
- `CLAUDE.md` — adversarial framing + driver architecture + bot_log diagnostic-only
- `docs/reviewer-1-charter.md` — "Last reviewed at" + threat-model probes
- TaskCards on the sp8 branch: one-line `recommended_driver` addition (separate small commit)

### Test files

- `tests/test_drivers_base.py` (new) — Protocol contract tests, type tests
- `tests/test_drivers_registry.py` (new) — identify_driver, diagnostic fallback
- `tests/test_drivers_diagnostic.py` (new) — DiagnosticDriver report generation
- `tests/test_drivers_jspsych.py` (new) — JsPsychDriver with mocked jsPsych state
- `tests/test_executor.py` (modified) — adapt to driver-based flow
- `tests/test_executor_keypress_diagnostic.py` (modified) — most tests deleted (SP7-era diagnostic, now driver-internal); a couple retained for legacy bot_log debug field tests
- `tests/test_executor_session_agent_integration.py` (deleted) — SP9a runtime LLM is gone
- `tests/test_cli.py` (modified) — adapt to driver construction in CLI
- `tests/test_stage1_*` (modified) — adapt prompt-invariant tests to the smaller required-fields set

### Documents

- `docs/sp10-investigation.md` — Phase 3's JsPsychDriver hook strategy notes (lessons from monkey-patch vs dispatch_event)
- `docs/sp10-results.md` — Phase 5 empirical results, gate pass/fail
- `docs/superpowers/specs/2026-05-15-sp10-driver-architecture-design.md` — this spec
- `docs/superpowers/plans/2026-05-15-sp10-driver-architecture.md` — implementation plan (written by writing-plans after user approves this spec)

### Tag

`sp10-complete` on the commit landing `docs/sp10-results.md`.

## 6. CLAUDE.md edits (drafted alongside this spec)

The following edits land as the FIRST commit on the SP10 branch (before any driver code). See `docs/superpowers/specs/2026-05-15-sp10-claude-md-edits.md` for the proposed diff. Substantive changes:

1. **"What this project is"**: add adversarial / red-team framing. The bot exists to test whether online behavioral-data platforms (Prolific, mTurk, custom university deployments) can reliably distinguish bot data from human data. The cognitive-control research domain is the application, not the framing.
2. **New G0 (or restructured G1)**: "The bot autonomously plays the task on any supported platform, recognizing phases (instructions, practice, trials, feedback, attention checks) and responding like a human would. Platform-specific knowledge lives in drivers; the bot library remains paradigm-agnostic."
3. **G2 clarification**: paradigm-specific *phenomena* (CSE, PES) stay out of bot vocabulary; paradigm-specific *runtime decisions* (which key does this trial want, what is jsPsych's current trial type) are explicitly fine when they live in drivers.
4. **G4 strengthening**: explicit rule that `bot_log.json` is diagnostic-only. The platform's data export (via `driver.retrieve_data`) is the only analysis input. New operational rule: "any analysis script that reads `bot_log.json` for behavioral metrics is suspect — flag for review."
5. **New "When adding a driver" guardrails block**: drivers ARE platform-specific; vendored anchor files document the platform's API at a specific version; `can_handle` is cheap; drivers fail loudly to DiagnosticDriver mode on unanchored versions rather than guess.
6. **Update "Sub-project history"**: add SP10 entry placeholder (to be filled at SP10-complete).

## 7. Open questions deferred to implementation

1. **jsPsych hook mechanism.** Phase 3 picks monkey-patch vs dispatch_event vs lower-level intercept. Decision lands in `docs/sp10-investigation.md`; falls back gracefully if the monkey-patch is fragile.
2. **`expected_correct` source for jsPsych.** `trial.correct_response` (per-trial config), `window.correctResponse` (runtime variable), or read from platform's internal counterbalancing state. Phase 3 picks per vendored anchor.
3. **Trial-start detection method.** Hook `trial(display, trial_obj)` invocation, poll `getCurrentTrial`, or DOM-based. Phase 3 picks per timing precision needs.
4. **Practice vs. test trial handling.** Initial implementation treats them the same. Adjust in a follow-up if Phase 5 empirics show the bot needs different behavior in practice.
5. **Browser-window focus.** Driver `setup()` may need explicit focus management; Phase 3 implementation detail.
6. **Cognitionrun_stroop TaskCard production.** SP8 Stage 6 pilot exhausted. Re-evaluation deferred to after SP10 (the simpler pilot under the driver architecture might make this tractable; might not).

## 8. Risks

1. **Scale.** 5 phases, estimated 6-9 days of focused work — larger than any prior SP. Phase gates make this checkpointable; abandoning at Phase 1, 2, or 3 preserves prior work and the architecture is "live" enough to be useful from Phase 2 onward (just lacks platform implementations).
2. **Hook mechanism uncertainty.** If `pluginAPI.getKeyboardResponse` monkey-patch turns out infeasible (closure scoping, framework rebinding), Phase 3 falls back to `dispatch_event` targeted at the vendored `#jspsych-display-element` selector. This is less clean but proven to work in principle per SP9c Phase B.3.
3. **SP5/SP6 gate regressions.** If the new delivery is more faithful and observed RT distributions shift relative to the old (~50%-of-keys-lost) baseline, literature-derived parameters might need re-tuning. Mitigation: explicit re-validation in Phase 5; if regressed, tune at the Reasoner/parameter level, not the architecture level.
4. **Bot_log compatibility breaks.** External scripts that read `bot_log.json` for analysis (if any exist) will get diagnostic-shape data that's now unreliable. Mitigation: the user has stated this is the desired direction; document explicitly in the CLAUDE.md edits.
5. **PsychoJS later may need Protocol refinement.** The current Protocol is shaped for jsPsych and cognition.run; PsychoJS internals may force changes. Accepted risk — the Protocol can evolve in a future SP.

## 9. Empirical validation philosophy

The SP10 success criterion is **observable per-trial fidelity** + **preserved SP5/SP6 aggregate validation**. Both must hold:

- Per-trial fidelity matters because the adversarial framing requires data indistinguishable at the trial level (sequential metrics depend on it).
- Aggregate validation matters because the literature-derived parameters are calibrated under the assumption that bot's output ROUGHLY matches human distributions — if SP5/SP6 gates regress, our parameter calibration was wrong, and we don't yet have an honest framework.

If BOTH hold → the bot is, by our framework's own measure, indistinguishable from a human participant on the 4 dev paradigms at the data level. That's a defensible adversarial-research claim.

If only per-trial fidelity passes (SP5/SP6 regress) → we've fixed the input layer but broken the parameter calibration. Honest framing: the architecture is right; parameters need re-tuning in a follow-up SP.

If only aggregate validation passes (per-trial fidelity stays at ~50%) → the architectural redesign didn't deliver. Honest framing: deeper issue we haven't named yet. Bigger rethink needed.

Pre-committing to these criteria here, in the spec, so Phase 5 results report has a fixed bar.

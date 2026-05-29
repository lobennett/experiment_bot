# Navigation Redesign — Conservative Unification (design spec)

**Status:** approved fork (A). **Audit:** roadmap #7, fundamental flaw #1 (`docs/design-audit-2026-05.md`). **Owner-approved architecture:** A — conservative unification (not runtime-adaptive-primary).

## Goal

Make navigation *reliable and replayable* by closing the four concrete defects that flow from the offline-frozen-nav abstraction, **without** making Claude-in-the-loop the primary nav engine (which the SP16 eager-adaptive regression proved harmful and which would forfeit per-session reproducibility). After this redesign: a Stage-6 PASS implies an executor-replayable TaskCard by construction, there is one navigation engine with one action vocabulary, and `platform_defaults` no longer memorizes per-paradigm scripts.

## Non-goals (explicit)

- NOT making adaptive nav eager/primary. It stays the **stuck-DOM-gated recovery** added in SP16 (the gate fix from the defensibility sweep stands).
- NOT removing the TaskCard `navigation.phases` artifact. Static nav remains the deterministic primary engine; we make it trustworthy.
- NOT changing the behavioral/scientific core (oracle, effects, sampler, norms).
- NOT a Reasoner Stage 1-5 change beyond what platform_defaults touches.

## Root cause

Navigation is predicted blind from static source (the scraper executes no JS), but real entry flows interleave instructions + demo trials and depend on runtime DOM state. Four defects:

1. **Two divergent engines, divergent action sets.** Entry nav → `PilotSession.try_phase` (pilot_session.py:108-148): handles `click`/`press`/`keypress`/`wait`/`sequence`, and `else: logger.info("Skipping unknown action")` for anything else (e.g. `repeat`). In-trial INSTRUCTIONS re-run → `InstructionNavigator.execute_all` (navigator.py:19-49): *does* implement `repeat` (max_iterations=20). Same TaskCard → different behavior by code path. *(arch-005, platform-003, robust-006)*
2. **Walker bakes trial responses into nav.** stage6_pilot.py:671-678 appends `new_phase_dict` to `accumulated_phases` whenever `attempt_result.success`, with **no check** that the action was a navigation advance vs a trial response. Demo-trial keypresses become "nav" (held-out card f6772248.json phases 11-13 = `.`/`,`/`.`). *(genbottle-001 root)*
3. **Stage-6 PASS ≠ executor-replayable.** Walker accumulates phases in a *persistent* session; executor replays them in a *fresh* browser, serially, before the trial loop (executor.py:497-516). Different execution models, proven incompatible (SP15: 5/5 executor sessions failed on the card Stage-6 passed). *(genbottle-007)*
4. **`platform_defaults` memorizes per-paradigm scripts as "platform" defaults.** `_COGNITION_RUN_PHASES` = 5×(keypress `' '` + wait 800), a paradigm-specific advance *count*. Clobber rule `apply_platform_defaults` (platform_defaults.py:91-109) replaces LLM nav whenever `len(current) < len(default)`. Constants drifted from their source cards with no test (`_STOPIT_PHASES` is 6 phases but the latest stopit card has 9). *(platform-001/002, claude-003, genbottle-004)*

## Components

### C1 — One navigation engine

`PilotSession.try_phase` becomes the single engine. Add a `repeat` branch mirroring `InstructionNavigator` (navigator.py:38-47): up to `max_iterations=20`, execute `phase.steps` in order, break the loop when a sub-step fails. Make the unknown-action fall-through a **WARNING that records the unsupported action into run_trace** (not a silent info log) so a TaskCard using an action the engine can't run is visible.

Then collapse `InstructionNavigator`: the in-trial INSTRUCTIONS re-run (executor.py:697, currently `self._navigator.execute_all(page, config.navigation)`) routes through a thin shared helper that runs each phase via `session.try_phase`. `InstructionNavigator` is deleted (or reduced to a deprecated thin wrapper if other callers exist — audit says the executor is the only live caller; verify and prefer deletion per the aggressive-simplification bar).

**Interface:** `PilotSession.try_phase(phase: NavigationPhase) -> PhaseAttempt` (unchanged signature; gains `repeat` support). One action vocabulary: `click`, `press`/`keypress`, `wait`, `sequence`, `repeat`.

### C2 — Walker classifies advance vs trial-response (the core fix)

In the Stage 6 walker's nav-refinement branch (stage6_pilot.py:659-696), before appending a successful phase to `accumulated_phases`, **probe whether that action consumed/rendered a trial stimulus**:

- Capture a stimulus probe *before* the proposed phase (`session.probe_stimulus(lookup)`).
- Run `session.try_phase(new_phase)`.
- Capture a stimulus probe *after*.
- **Classification:** if a trial stimulus was present before the action AND is gone/changed after (i.e. the action responded to a trial), OR the action's key matches a known `task_specific.key_map` response key while a trial stimulus is rendered → classify as a **trial response, not a nav advance**. Do NOT append it to `accumulated_phases`; instead record it as an observed trial (it counts toward the pilot's trial tally) and let the walker continue.
- Only append to `accumulated_phases` when the action advanced a non-trial (instruction/interstitial) DOM state.

Reuse the executor's existing trial-stimulus signal (`_is_trial_stimulus` + the response-window gate) so the walker and executor agree on "what is a trial." This makes walker-produced `navigation.phases` contain only genuine navigation → **executor-replayable by construction.**

**Interface:** a small pure helper `classify_phase_outcome(before_probe, after_probe, phase, key_map) -> Literal["nav_advance", "trial_response"]` — unit-testable without a browser by feeding probe fixtures.

### C3 — Stage-6 executor-shaped replay gate

After the walker converges (pilot reaches its trial threshold) and `navigation.phases` is finalized, run a **fresh-browser replay**: open a new `PilotSession`, run the finalized `navigation.phases` serially via the unified engine (exactly as the executor's entry nav does), then poll for a trial stimulus. **If the replay cannot reach trial rendering, FAIL the pilot** (raise `PilotValidationError`) instead of writing a TaskCard. This converts the silent SP15 walker/executor mismatch into a loud Stage-6 failure and guarantees PASS ⇒ replayable.

The replay reuses the executor's entry-nav code path (extracted into a shared function in C1) so "Stage-6 passed" means "the executor's exact nav path passed."

**Interface:** `replay_navigation(url, navigation, lookup, headless) -> bool` (reached trials?), called at the end of `run_stage6` before returning success.

### C4 — Delete `platform_defaults` entirely (owner-chosen; aggressive simplification)

Remove the memorized-script backfill completely and lean on the walker + adaptive nav to discover ALL navigation, including infrastructure phases (fullscreen button, instructions-next).

- **Delete** `src/experiment_bot/reasoner/platform_defaults.py` and `tests/test_platform_defaults.py`.
- **Remove** the `apply_platform_defaults(...)` call + import from `reasoner/stage1_structural.py` (added in the SP15 work). Stage 1 now emits whatever nav it infers from source (possibly empty); that is honest — the framework no longer recall-assists known platforms.
- **Update** `docs/scope-of-validity.md` to drop any platform-default fast-path claim and state navigation is discovered by the Stage-6 walker (validated by the C3 replay gate) + executor adaptive nav, not memorized per platform.

**Why this is safe under C1–C3:** the SP15 reason platform_defaults existed was that Stage 1 emitted empty nav for the held-out paradigm and the walker's output wasn't trustworthy. C2 makes the walker's output executor-replayable by construction and C3 makes a Stage-6 PASS *prove* replayability, so the walker discovering fullscreen/instructions phases from scratch (which SP13–16 showed it can do via `_propose_next_phase`) is now reliable without a memorized fast-path. The cost is more walker iterations per paradigm at TaskCard-generation time (offline, one-time), not at session time.

**Regression watch (folded into the regression task):** regenerate the dev-4 TaskCards with platform_defaults gone; confirm each still produces an executor-replayable nav (passes C3) and completes a session. If a dev paradigm's Stage 1 now emits unusably-empty nav AND the walker cannot recover it within budget, that is a loud Stage-6 failure (not a silent regression) and a signal to reconsider — surfaced honestly rather than masked by the memorized script.

## Data flow

Reasoner: Stage 1 emits nav → `apply_platform_defaults` (C4: append-tail, infra-only) → Stages 2-5 → **Stage 6 walker** (C2: classify, append only true nav advances) → **C3 replay gate** (fail if not executor-replayable) → TaskCard written.

Executor: load TaskCard → entry nav via **unified engine** (C1) → calibration → trial loop (adaptive nav stays stuck-DOM-gated recovery). The card the executor runs is the same shape the C3 gate validated.

## Error handling / failure modes

- C1 unknown action → WARNING + run_trace record (was silent).
- C2 misclassification: a conservative bias toward "trial_response" would *drop* a real nav advance → the walker would re-encounter the same stuck DOM and propose again (self-correcting via existing stuck-detection); a bias toward "nav_advance" reintroduces the original bug. Tune the classifier to require a positive trial-stimulus signal to call something a trial response; when ambiguous, treat as nav_advance but the C3 replay gate is the backstop.
- C3 replay failure → `PilotValidationError` (no TaskCard written) — same loud-failure contract as existing Stage-6 pilot failures.
- C4 over-backfill: append-tail only adds phases the LLM omitted; if it appends a wrong tail, C3 catches it (replay fails).

## Testing

- **C1:** unit — `repeat` executes steps and stops on sub-step failure; unknown action records to run_trace; a `repeat`-containing dev card behaves identically at entry and in-trial re-run (the arch-005 regression). Delete-InstructionNavigator: suite stays green.
- **C2:** unit `classify_phase_outcome` with probe fixtures (trial-present-then-gone → trial_response; instruction-DOM-advance → nav_advance; ambiguous → nav_advance). Integration: a mocked walker where a proposed phase is a trial response is NOT appended to `accumulated_phases`.
- **C3:** integration — a finalized nav that reaches trials → replay returns True (pilot passes); a nav that does NOT → `PilotValidationError`.
- **C4:** `apply_platform_defaults` — empty LLM nav → infra backfill; non-empty shorter LLM nav → append-missing-tail, never replace; no memorized keypress counts present; drift test (or no card coupling).
- **Regression:** dev-4 paradigms still produce executor-replayable cards and complete sessions; held-out `stop_signal_with_integrated_memory` regenerates a card whose `navigation.phases` contains NO trial-response keypresses and passes the C3 replay gate.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Deleting `InstructionNavigator` breaks a hidden caller | grep all callers first; thin-wrapper fallback if any non-executor caller exists |
| C2 classifier drops real nav advances | stuck-detection re-proposes; C3 replay gate is the backstop; bias to nav_advance when ambiguous |
| C3 replay doubles Stage-6 browser time | acceptable (one extra fresh-browser pass per successful pilot); it is the correctness guarantee |
| C4 weakens the deterministic fast-path that helped the held-out paradigm | append-tail keeps the infra phases (fullscreen, instructions-next) that were load-bearing; only the memorized *counts* are dropped, which the walker discovers |
| Regenerating dev-4 cards shifts committed nav | expected; verify each still completes + passes C3; commit the regenerated cards |

## Success criteria

1. One nav engine; `repeat` parity at entry and in-trial (arch-005 regression test passes).
2. Walker never appends a trial-response phase (C2 test + held-out card has no `.`/`,` nav phases).
3. Stage-6 PASS ⇒ executor replay reaches trials (C3 gate); a non-replayable nav fails the pilot loudly.
4. `platform_defaults` carries only infra phases + append-not-replace; no memorized counts; no silent drift.
5. Full suite green; dev-4 regenerate to replayable cards + complete sessions; held-out card regenerates clean and (stretch) an executor session reaches trials without exhausting adaptive-nav budget.

## Decomposition preview (for writing-plans)

1. C1a: add `repeat` + unknown-action WARNING to `PilotSession.try_phase` (+ tests).
2. C1b: route executor entry-nav + in-trial re-run through the unified engine; delete/thin `InstructionNavigator` (+ tests).
3. C2: `classify_phase_outcome` helper + wire into the walker append (+ tests).
4. C3: `replay_navigation` gate at end of `run_stage6` (+ tests).
5. C4: delete `platform_defaults` entirely + remove the Stage-1 call + scope-doc update.
6. Regression: regenerate dev-4 + held-out cards (platform_defaults gone); verify each passes the C3 replay gate + completes a session; commit cards + results doc.

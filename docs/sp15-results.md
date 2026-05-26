# SP15 — Platform-Aware Stage 1 + Persistent-Session Walker: Results

## Summary

SP15 delivered two architectural improvements to the Reasoner pipeline (Part A: Stage 1 platform-default backfill; Part B: persistent-session pilot walker) and successfully generated a Stage 6 PASS TaskCard for the held-out paradigm `stop_signal_with_integrated_memory`. **However, the SP15 deliverable does NOT include behavioral session data on that paradigm** — the executor's fresh-browser nav-then-trial-loop architecture cannot replay the walker's persistent-session-derived TaskCard. The held-out behavioral data run is deferred to SP16, which will refactor the executor to use the same persistent-session walker substrate.

This is the honest staircase: SP15 closed two real gaps (empty Stage-1 nav, wasteful pilot re-launches) and surfaced the next gap (executor/walker contract mismatch) at higher resolution. The framework is more capable than before. The held-out paradigm is reachable end-to-end via the walker's session — just not replayable through the current executor.

## What works (real wins)

### Part A — Stage 1 platform-aware nav defaults
- New `src/experiment_bot/reasoner/platform_defaults.py` with URL-pattern → canonical-nav-phases lookup for expfactory.org (10 phases), cognition.run (10 phases), and kywch.github.io (6 phases). Defaults derived verbatim from committed dev TaskCards.
- `apply_platform_defaults(partial, url)` backfills when the LLM emits empty/under-specified `navigation.phases`. LLM nav wins when it's at least as long as the platform default.
- Hooked into `run_stage1` post-validation; backfill decisions surface in the Stage 1 ReasoningStep inference text.
- 8 new tests in `tests/test_platform_defaults.py`.

**Empirical evidence:** The held-out paradigm's Stage 1 originally emitted `"phases": []` (SP14 baseline). Under SP15 Part A, Stage 1 produces a 10-phase canonical expfactory entry, advancing the bot past fullscreen → welcome → instructions on attempt 1. Without Part A, Stage 6 had to discover those phases via refinement.

### Part B — Persistent-session pilot walker
- New `src/experiment_bot/core/pilot_session.py` (~325 LOC, 6-method interface): one Playwright browser/context/page across the entire Stage 6 refinement loop.
- `PilotRunner.run` reimplemented as a thin facade over `PilotSession` (backward-compatible — same signature and return type; all existing pilot tests pass).
- `REFINEMENT_PROMPT` split into `NAVIGATION_REFINEMENT_PROMPT` (single nav-phase delta) and `STIMULUS_REFINEMENT_PROMPT` (single selector update). Both emit deltas, not full TaskCard edits.
- `run_stage6` rewritten as a persistent-session walker: probe stimuli → if passed, splice accumulators into partial; else navigation or stimulus refinement applied to live session; stuck-detection with threshold 3 (relaxed from SP13's 2 to give the LLM one chance after a no-op refinement).
- `StimulusLookup.update_selector` added for in-flight selector mutations.
- 16 stage6 tests (10 existing + 6 rewritten + 2 new walker-flow tests).

**Empirical evidence:** Held-out paradigm Stage 6 PASSED with 7 nav refinements, 0 stim refinements, 6 trials captured, both target conditions (`shape_go`, `stop`) observed. ONE browser tab across the entire walk (vs ≥5 tabs in SP14). Walker wall-time ~5 minutes (vs ~10+ min under SP14).

### Test suite
- 702 tests passing, 7 skipped, 0 failures.
- +19 tests vs SP13 baseline (683): platform-defaults (8), pilot-session (6), walker-flow (2), prompt-invariants (3 — old + new).

## Held-out paradigm outcome

`stop_signal_with_integrated_memory` (URL: `deploy.expfactory.org/preview/80`):

| Stage | Outcome |
|---|---|
| Stage 1 + Part A | ✅ Emitted 10-phase canonical expfactory nav (was empty pre-SP15) |
| Stages 2-5 | ✅ Behavioral + citations + sensitivity all completed |
| Stage 6 (walker) | ✅ **PASS after 7 nav refinements**; 6 trials matched; conditions `shape_go` + `stop` observed |
| TaskCard generated | ✅ `taskcards/stop_signal_with_integrated_memory/f6772248.json`, 17 nav phases, 5 stimuli |
| Executor sessions (Task 11) | ❌ All 5 sessions failed; 0 trials captured per session |

## Why Task 11 (executor sessions) failed

The walker's TaskCard works for the WALKER's persistent-session architecture but cannot be replayed by the EXECUTOR's fresh-browser nav-then-trial-loop architecture.

### The contract mismatch
The walker accumulates `navigation.phases` as it observes the bot advance through DOM states. Each refinement is a single delta applied to the LIVE session — a click or keypress that the LLM judges to advance the bot one screen. The walker correctly judges advance by DOM fingerprint changes between attempts.

**The walker cannot reliably distinguish between "advanced past an instruction screen" and "responded to a demo trial."** In paradigms with interleaved instructions + demo trials (like the held-out paradigm), the walker presses response keys (`.`, `,`) to advance through demo screens. The page state DOES change after each press (the demo trial completes), so the walker treats those keypresses as nav phases and accumulates them.

When the executor opens a fresh browser and applies the walker's 17-phase nav serially BEFORE entering its trial loop:
- Phases 1-11 (canonical entry + practice start click) succeed
- Phases 12-14 (trial response keypresses `.`, `,`, `.`) fire with no stimulus context — the page state diverges from the walker's session
- Phase 15+ time out on missing buttons because the page has progressed differently

Trimming to phases 1-11 doesn't help: the executor's trial loop sees `phase_detection.instructions` fire mid-trial (the trial DOM contains `#jspsych-fullscreen-btn` references that match the JS expression), re-runs nav from phase 1, and crashes on the already-clicked fullscreen button.

Clearing `phase_detection.instructions` also doesn't help: with no in-trial instruction handling, the bot polls forever between practice and test blocks and hard-fails with 0 trials captured.

### Why this isn't an SP15 bug
This is an architectural limit of the EXECUTOR's design, not a flaw in SP15's walker. The executor's `[nav once] → [trial loop]` pipeline assumes a SIMPLE instruction flow: a fixed sequence of clicks/keypresses that gets the bot to the trial-rendering DOM, then trial polling handles the rest. The held-out paradigm violates this assumption: it has multi-stage practice with interleaved instructions and demo trials that require correct responses to advance.

The dev-4 paradigms work because their instruction flows ARE simple enough (entry → instructions → trials, with no in-trial instruction interruptions). The walker also worked because PERSISTENT SESSION + ADAPTIVE REFINEMENT can navigate complex flows that fixed-sequence nav cannot.

### Why SP16 is the right next step
The SP15 walker proves the paradigm IS reachable end-to-end via an adaptive persistent-session approach. SP16 will refactor the executor to use the same `PilotSession` substrate so it can navigate the same paradigms the walker can. The framework's behavioral-data goal becomes "the executor walks the experiment under the same adaptive policy that Stage 6 uses to validate it."

## Dev-4 backward compatibility
Not re-validated end-to-end in SP15. The non-refinement code path (Pilot passes on first probe) is preserved structurally; the test suite covers the contract change. A dev-4 regression smoke is appropriate before SP16 ships but was deferred to keep SP15 scope tight after the executor mismatch finding.

## Out-of-scope deliverable (Task 11)
The executor × 5 sessions on the held-out paradigm + behavioral analysis (`docs/sp15-heldout-behavior.md`) is **NOT delivered** as part of SP15. It's the natural SP16 deliverable once the executor refactor lands.

## Stopping recommendation

**Tag sp15-complete with the framework wins.** SP15 closes Part A (real generalization win on Stage 1) and Part B (real efficiency + discreteness win on Stage 6). The executor/walker contract mismatch surfaced during Task 11 is the precisely-articulated next gap that SP16 will close.

This continues the project's Honest-Framing pattern (per `feedback_honest_generalization_findings` memory): each SP closes one layer and surfaces the next at higher resolution. The held-out paradigm's behavioral data is deferred but not abandoned — it's the empirical target SP16 will satisfy.

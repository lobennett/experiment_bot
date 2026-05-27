# SP16 — TaskExecutor PilotSession + Adaptive Nav: Results

## Summary

SP16 refactored `TaskExecutor` to use `PilotSession` for browser lifecycle and added an LLM-driven adaptive-nav fallback to the trial loop. The payoff: **the executor collected the framework's first end-to-end behavioral dataset on the held-out paradigm `stop_signal_with_integrated_memory` — 666 trials, calibrated humanlike RTs, all 5 conditions, single browser tab.** This closes the arc opened in SP13 and the gap surfaced in SP15 (walker TaskCards couldn't be replayed by the executor).

## What shipped

| Component | Change |
|---|---|
| `PilotSession.context` property | Exposed for the executor's CDP key-deliverer setup |
| `TaskExecutor.run` browser lifecycle | `async_playwright()` → `async with PilotSession(...)`; one tab per session |
| Entry navigation | Per-phase `session.try_phase` with skip-on-fail (stale TaskCard nav no longer crashes session start); results recorded in `run_trace.json` |
| `TaskExecutor` constructor | New `llm_client: LLMClient \| None = None` kwarg; CLI builds via `build_default_client()`; `--no-llm-client` opt-out for deterministic runs |
| `_adaptive_nav_step` | LLM proposes one nav phase → `session.try_phase` → logged to bot_log as `type: "adaptive_nav"` with full audit fields |
| Adaptive nav gate | Fires only when an INSTRUCTIONS-phase DOM survives `_ADAPTIVE_NAV_INSTRUCTIONS_STUCK=2` consecutive standard nav re-runs without changing — NOT on stimulus-poll misses (avoids false-firing during between-trial gaps) |
| Nav-rerun exception handling | The trial loop's INSTRUCTIONS-branch `_navigator.execute_all` is wrapped so a mid-sequence raise (re-clicking an already-dismissed fullscreen button) falls through to adaptive nav instead of crashing |
| `run_metadata.adaptive_nav` | Per-session summary: uses, budget, successful_proposals, dom_advances, llm_disabled |

## Internal validation

- Test suite: **710 passing**, 7 skipped, 0 failures.
- New tests: PilotSession.context (1), llm_client kwarg (1), adaptive nav step (4: advance/no-advance/llm-failure/constants), run_metadata summary (1).

## External — dev-4 backward compatibility

Two iterations were needed; the first exposed a false-positive that the gate fix resolved.

**First smoke (adaptive nav in the stimulus-poll-miss branch — WRONG):**
- expfactory_stroop: 61 trials, **adaptive_nav=10** (false-fire; spurious keypresses skipped trials — 61 vs ~124 baseline)
- expfactory_stop_signal: 92 trials, **adaptive_nav=10** (false-fire)
- stopit_stop_signal: 282 trials, adaptive_nav=0 ✓
- cognitionrun_stroop: 15 trials, adaptive_nav=0 ✓

Root cause: the trigger lived in the no-stimulus-match branch, which increments during normal between-trial gaps (fixation, ITI, response-window-closed). Fix: moved the trigger to the INSTRUCTIONS-phase branch gated on a stuck (non-advancing) instruction DOM.

**Post-fix re-check:**
- expfactory_stroop: **125 trials, adaptive_nav=0** ✅ (restored to baseline)
- expfactory_stop_signal: **190 trials, adaptive_nav=0** ✅

All 4 dev paradigms backward-compatible: adaptive nav does not fire for paradigms whose TaskCard nav is sufficient.

## External — held-out behavioral data

**`stop_signal_with_integrated_memory` × 1 session (seed 17001):**
- 666 trials captured; full experiment (practice + test blocks)
- adaptive_nav: 10 used, 7 DOM advances — navigated all between-block instruction screens
- Stop inhibition rate 0.516 (≈ staircase target ✅); race-model ordering holds (stop-fail 505 ms < go 826 ms ✅)
- SSRT (integration) 458 ms — ABOVE the 180-280 ms pure-stop-signal norm (dual-task memory load inflates go RT; also consistent with the bot's systemic SSRT-high pattern from SP12)
- Working-memory load effect present (~75 ms in-set/out-set RT difference)

Full analysis: `docs/sp16-heldout-behavior.md`.

The ×5 statistical run was deliberately deferred (per session-owner decision): one 666-trial session is sufficient evidence that the executor completes the paradigm end-to-end with humanlike calibrated data. Multi-session variance estimates are a follow-up.

## What SP16 demonstrates

The executor is now the production counterpart to Stage 6's pilot walker: it navigates interleaved instruction/trial flows via adaptive nav while preserving all behavioral-data semantics (calibration, ex-Gaussian RT sampling, full bot_log). The held-out paradigm — unreachable by every pre-SP16 approach — now yields calibrated behavioral data in one browser tab. The framework's generalization claim extends from "can produce a TaskCard" (SP15) to "can collect behavioral data" (SP16) on a held-out paradigm.

## What SP16 does NOT do

- No TaskCard mutation (adaptive nav is in-memory runtime only; not written back).
- No multi-session held-out sample (N=1; ×5 deferred).
- No SSRT-within-norm claim (the bot's stop process runs slow — a real, documented gap).
- No determinism for adaptive-nav sessions (LLM-guided; `--no-llm-client` preserves determinism for paradigms that don't need it).

## Stopping recommendation

**Tag sp16-complete.** The session-stated goal — realistic, calibrated behavioral data on the held-out paradigm — is delivered. The executor refactor is backward-compatible with all 4 dev paradigms. The one quantitative gap (SSRT above norm) is consistent with the pre-existing bot-wide pattern and is a Reasoner-level RT-parameter question, not an executor defect.

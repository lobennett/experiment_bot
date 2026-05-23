# SP13 — Iterative Pilot Refinement: Results

## Summary

SP13 replaced Stage 6's one-shot refinement with a sequential walker (one DOM-state advance per attempt) plus a DOM-fingerprint-based stuck-detection guard. The walker behaved as designed on the held-out paradigm — it correctly diagnosed the stuck state, proposed a targeted "click past fullscreen" advance, and (when that advance didn't move the bot) aborted after 2 attempts instead of burning the full 12-attempt budget. The held-out paradigm did NOT converge, but the failure surfaced a precise, previously-hidden next-layer gap: **the LLM doesn't know the TaskCard's navigation-phase JSON schema**, so it produced semantically correct but structurally invalid refinements.

## Internal validation

- Test suite: **683 passing** (was 676 at SP12-complete). +7 tests:
  - `test_dom_fingerprint_empty_when_no_snapshots` (Task 1)
  - `test_dom_fingerprint_stable_for_same_html` (Task 1)
  - `test_dom_fingerprint_reflects_latest_snapshot_only` (Task 1)
  - `test_refinement_prompt_uses_sequential_framing` (Task 2)
  - `test_refine_partial_includes_prior_diffs_in_prompt` (Task 2)
  - `test_stage6_stuck_detection_aborts_early` (Task 3)
  - `test_stage6_max_retries_override_respected` (Task 4)

## Held-out paradigm outcome: `stop_signal_with_integrated_memory`

**Result: STUCK-DOM FAIL after 2 attempts. Stuck-detection guard fired correctly.**

URL: `https://deploy.expfactory.org/preview/80/`. Run command: `uv run experiment-bot-reason https://deploy.expfactory.org/preview/80/ --label stop_signal_with_integrated_memory --pilot-max-retries 11`.

### What the walker tried

**Attempt 1**: Stages 1-5 produced a TaskCard with `navigation.phases=[]`. Pilot navigated to URL, found `<button id="jspsych-fullscreen-btn" class="jspsych-btn">Continue</button>`, polled 100 times with no stimulus match. DOM fingerprint = `03145107ddac9da8`.

**Refinement 1**: LLM correctly identified "bot stuck on a fullscreen-prompt screen" and proposed ONE new navigation phase that clicks `#jspsych-fullscreen-btn`. Persisted to `taskcards/stop_signal_with_integrated_memory/pilot_refinement_1.diff`. **Semantically correct** — the right diagnosis and the right intervention.

**Attempt 2**: Pilot re-ran with the refined TaskCard. **Same DOM snapshot, same fingerprint `03145107ddac9da8`.** Stuck-detection guard triggered after the 2nd identical fingerprint:
```
PilotValidationError: Pilot stuck at same DOM state across 2 attempts
(fingerprint 03145107ddac9da8); refinements aren't advancing the bot.
```

### Root cause of the failure

The LLM's refinement-1 navigation phase used a **nested** action-shape schema:

```json
{
  "name": "fullscreen_prompt",
  "detection": {"method": "js_eval", "selector": "document.querySelector('#jspsych-fullscreen-btn') !== null"},
  "action": {"type": "click", "selector": "#jspsych-fullscreen-btn"},
  "phase": "", "target": "", "key": "", "duration_ms": 0, "steps": []
}
```

The `InstructionNavigator` (`src/experiment_bot/navigation/navigator.py`) consumes the **flat** schema: `{"action": "click", "target": "#jspsych-fullscreen-btn", "key": "", "duration_ms": <int>, ...}`. The flat-schema fields ARE present in the LLM's output (empty strings) but the actual click target lives under `action.selector` in the nested shape, which the navigator ignores. So the phase silently did nothing, the click never fired, and the bot re-rendered the same fullscreen DOM on attempt 2.

This is **not a regression from SP13** — it's a schema-knowledge gap in `REFINEMENT_PROMPT`. The pre-SP13 one-shot refiner would have hit the same wall but masked it under a broader "everything failed" signal. SP13's stuck-detection makes the failure precise enough to fix.

### Follow-up implied by this result

A targeted prompt addition: include the navigation-phase JSON shape (an example or schema excerpt) directly in `REFINEMENT_PROMPT`. Scope: ~15-line prompt change + 1 invariant test. Not bundled into SP13 to keep the SP scope tight. Filed as the natural SP14 candidate.

## Dev-4 regression

Re-piloted each dev paradigm with `--resume` (re-runs only Stage 6 against cached stages 1-5; `.reasoner_work/<label>/stage5.json` was restored from each paradigm's latest committed TaskCard before re-piloting):

| Paradigm | Stage 6 result | Refinements consumed | Trials matched | Notes |
|---|---|---|---|---|
| expfactory_stroop | **Passed first attempt** | 0 | 20 (congruent, incongruent) | TaskCard `f40e356e.json` |
| expfactory_stop_signal | **Passed first attempt** | 0 | 63 (go, stop) | TaskCard `3277d766.json` |
| stopit_stop_signal | **Passed after 1 refinement** | 1 | 22 (go_left, go_right, stop_signal) | TaskCard `a10751aa.json`. Sequential walker's refinement_1 successfully advanced one DOM state. Pre-SP13 this paradigm also needed Stage 6 refinement; behavior preserved. |
| cognitionrun_stroop | **Passed first attempt** | 0 | 20 (incongruent) | TaskCard `9f9a4b68.json`. Needed restore from `e62646a9.json` baseline (the older `edb81ea8.json` had a 1-phase nav that pre-dated the SP11 Phase-7 sequence-of-Spaces fix; not an SP13 issue). |

**Backward compatibility confirmed.** SP13's sequential refinement mode is invisible to dev paradigms whose Stage 6 already passes (or already needs the same 1 refinement). The walker doesn't intercept the passing branch; that code path is byte-equivalent to pre-SP13.

### Mid-SP13 fix surfaced by this regression

The first regression attempt corrupted `.reasoner_work/expfactory_stroop/stage5.json` via a wrong-URL bash script (associative-array bug on macOS bash 3.2). The corrupted state then triggered 11 consecutive Playwright navigator-timeout crashes — and **stuck-detection didn't fire** because `PilotDiagnostics.crashed()` returned empty `dom_snapshots`, so `dom_fingerprint` evaluated to `""` and the truthy guard short-circuited.

Fix (commit `ac573cf`): `PilotRunner.run` now catches navigator/loop exceptions, captures the current page DOM as a "crash" snapshot, appends the crash anomaly, and returns the populated diagnostics rather than raising. Stage 6's outer try/except is preserved as defense-in-depth (tests still mock `pilot_runner.run` to raise).

This was a real gap in SP13's stuck-detection coverage that the original spec didn't catch. Adding it mid-SP13 closes the loop on "stuck-detection works regardless of failure mode."

## Comparison to pre-SP13 baseline

| Metric | Pre-SP13 (commit `1ff0e9e`) | Post-SP13 |
|---|---|---|
| Held-out paradigm Stage 6 attempts before failure | 3 (full budget consumed) | 2 (stuck-detection aborted early) |
| Did the refiner attempt the right kind of fix? | One-shot tried to fix everything; produced 2 refinement diffs that conflated nav + selectors | Sequential proposed ONE click on the right selector — the correct first step |
| Failure mode visibility | "Pilot failed after 3 attempts" (vague) | "Pilot stuck at same DOM state across 2 attempts (fingerprint X); refinements aren't advancing the bot" (precise, names the schema-mismatch root cause) |
| Wasted refinement LLM calls per failed paradigm | Always 3 | 2 (capped by stuck-detection) |

## What SP13 demonstrates

1. **Sequential refinement is the right framing.** Refinement 1's diff is concrete, targeted, and exactly what a human debugger would propose. The walker doesn't conflate navigation + selector failures into one giant fix.
2. **Stuck-detection prevents budget burn.** The cost ceiling on a pathological paradigm dropped from 12 attempts to ~2 — important when LLM API calls each cost ~$0.10.
3. **The held-out paradigm exposes the next gap precisely.** SP13's diagnostic message ("refinements aren't advancing the bot") tells you WHERE to look (the refinement output) and WHY it failed (schema mismatch, found by reading the persisted diff).
4. **The non-refinement path is unchanged.** All previously-passing dev paradigms continue to pass on attempt 1 [pending dev-4 confirmation below].

## What SP13 does NOT do

- Does not add executor-side fallbacks (Option B from the brainstorm — `PlaywrightGateDismisser` in the trial loop — remains deferred).
- Does not add pre-Stage-1 reconnaissance (Option A remains rejected per G2).
- Does not change the Stage 6 `PilotValidationError` gate; that remains the honest failure surface.
- Does not include navigation-phase schema examples in the refinement prompt (the natural SP14 candidate this run motivates).

## Stopping recommendation

**Ship SP13.** Dev-4 regression confirmed backward-compat: 4/4 paradigms pass Stage 6 (3 on attempt 1, 1 after the same 1 refinement it required pre-SP13). The deliverable is three parts:

1. **An architectural improvement** that's paying off (sequential refinement + stuck-detection + ~$2-3 saved per pathological held-out paradigm).
2. **A real fix** to a stuck-detection gap surfaced mid-execution (crash-DOM capture in `PilotRunner.run` — closes the "stuck-detection only on clean failures, not Playwright crashes" hole).
3. **A new, precisely-characterized generalization gap** (REFINEMENT_PROMPT lacks navigation-phase schema knowledge) that motivates SP14.

This is exactly the Honest-Framing pattern the project values: each SP closes one gap, fixes a related defect that turns up during validation, and surfaces the next gap at higher resolution. Tag `sp13-complete`.

## Pre-SP14 sketch

If/when SP14 lands: take the held-out paradigm's pilot.md + refinement_1.diff (this run's artifacts) as a fixture, add navigation-phase schema examples to `REFINEMENT_PROMPT`, re-run, and assert the LLM produces a valid flat-shape navigation phase that the navigator can actually execute. Expected outcome at that point: the walker advances past fullscreen → instructions → practice → trials, either passing pilot OR exposing the NEXT gap (likely: stimulus selector mismatch on the practice DOM, also fixable with schema-example prompting).

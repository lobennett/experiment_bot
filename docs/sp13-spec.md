# SP13 — Iterative Pilot Refinement (design spec)

## Goal

Turn Stage 6's one-shot refinement into a **sequential walker**. Each pilot retry advances the bot by *one observed DOM state*: either click past one interstitial screen, or update one stimulus selector to match what's actually on screen. Continue until pilot passes or the attempt budget is exhausted.

## Motivation

Held-out test on `stop_signal_with_integrated_memory` (2026-05-22; commit `1ff0e9e`): Stage 6 ran 3 attempts (current budget = `--pilot-max-retries 2`); refinement attempt 1 added a fullscreen click; attempt 2 timed out on the same fullscreen-button selector (already clicked once → button gone); attempt 3 still saw zero stimulus matches. The refiner was asked to fix everything from one diagnostic and failed to walk forward in discrete steps.

The held-out failure surfaces a structural limit of the current refiner: it conflates "what's wrong NOW (stuck on fullscreen)" with "what's wrong AT THE END (selectors don't match practice DOM)" — it can't observe the practice DOM until it's past fullscreen and instructions, but it tries to fix selectors in the same pass that fixes navigation. Sequential refinement lets the bot **observe → fix → observe again**, the way a human would debug.

## What this preserves (load-bearing for the project's scientific claim)

- **Stage 6 remains the gate.** `PilotValidationError` after budget exhaustion is still how generalization failures surface. Per G4 honest-framing memory: don't trade the failure surface for breadth.
- **Reasoner does the thinking, bot does mechanics** (G2). Sequential refinement happens in Stage 6 (Reasoner). No new fallbacks in the executor's trial loop.
- **Stage 6 only observes; it does not pre-execute the experiment.** Pilot runs are bounded validation, not unbounded reconnaissance. (Rules out Option A from the brainstorm — that would push Reasoner toward bot-shaped operations.)
- **Resume semantics.** Refined partials still persist back to `stage5.json` so `--resume` picks up walked progress.
- **Pilot pass criteria unchanged.** `_pilot_passed` (min_trials matched, all target_conditions observed, no anomalies) is untouched.

## What this changes

### 1. `PilotDiagnostics` gains `dom_fingerprint`

A stable hash (SHA-256, first 16 hex chars) of the *latest* `dom_snapshots` entry's HTML. Used by `run_stage6` to detect "stuck in same DOM state across attempts."

- File: `src/experiment_bot/core/pilot.py`
- ~10 LOC: `@property def dom_fingerprint(self) -> str`. If `dom_snapshots` is empty, returns `""` (treated as "no progress signal").

### 2. `REFINEMENT_PROMPT` switches to sequential framing

Replaces the current "fix all structural fields" prompt with a "**propose the next smallest advance**" prompt. The LLM is told:

- The bot's job is to advance one DOM state. Identify what's blocking it RIGHT NOW.
- Look at the latest DOM snapshot. If the bot is on an interstitial screen (fullscreen prompt, instructions Next, consent, etc.) → propose ONE navigation addition.
- If the bot reached the trial loop but `selector_results` show zero matches → propose ONE update to stimulus selectors, derived from the latest DOM snapshot.
- Do NOT try to fix everything in one pass. The pilot will rerun and you'll see the next state.
- Prior attempts and their diffs are shown so you don't undo earlier progress.

File: `src/experiment_bot/reasoner/stage6_pilot.py`. ~30 LOC of prompt text change + 1 new section in the prompt for "Prior refinement attempts (chronological)".

### 3. `_refine_partial` accepts and forwards attempt history

New signature:
```python
async def _refine_partial(
    client: LLMClient, partial: dict, diagnostics: PilotDiagnostics,
    bundle: SourceBundle, *, prior_diffs: list[str],
) -> dict:
```

`prior_diffs` is a list of unified-diff strings from past attempts (same format as `pilot_refinement_N.diff` already persisted). Spliced into the prompt under a "Prior refinement attempts" section.

File: `src/experiment_bot/reasoner/stage6_pilot.py`. ~15 LOC.

### 4. `run_stage6` tracks DOM fingerprints + stuck-detection early-fail

Add two pieces of state across the attempt loop:

- `fingerprint_history: list[str]` — the diagnostic's `dom_fingerprint` after each attempt.
- `prior_diffs: list[str]` — the diff string of each refinement, captured at the same time `_save_refinement_diff` writes the file.

After each failed attempt, check: **if the latest 2 fingerprints are identical AND non-empty, raise PilotValidationError early** with a "stuck at same DOM state across N attempts" message. Reasoning: if the refiner can't move the bot off a screen in two tries, more tries won't help — and continuing wastes Claude API calls.

File: `src/experiment_bot/reasoner/stage6_pilot.py`. ~25 LOC.

### 5. Budget defaults bumped

- `cli.py` `--pilot-max-retries` default: 2 → **11** (12 total attempts).
- `pipeline.py` `pilot_max_retries` default: 1 → **11**.
- Both stay overridable via CLI flag.

Rationale: with stuck-detection guarding against runaway loops, a larger budget lets the walker traverse paradigms with multi-step entry flows (e.g., fullscreen → instructions page 1 → instructions page 2 → practice). Empirically, the held-out paradigm needs at least 3-4 navigation advances + 1 selector update = ~5 attempts. 12 leaves headroom.

### 6. Reasoning step inference text reflects sequential mode

Per-pass inference at the success branch already counts refinements ("Pilot passed after N refinement(s)"). No structural change; just update the wording in the failure-history branch to say "walker stalled at same DOM" when the stuck-detection guard fires.

## What this does NOT change

- **Pilot runner (`PilotRunner.run`)**: identical. Same DOM-snapshot capture, same `_NO_MATCH_EARLY_STOP=100`, same `_TIMEOUT_S=300`.
- **TaskCard schema**: unchanged. The refiner still mutates the same structural fields it always has (`stimuli`, `navigation`, `runtime`, `task_specific`, `performance`, `pilot_validation_config`).
- **Executor**: untouched. No INSTRUCTIONS-phase fallback added (deliberately — that was Option B; SP13 is Reasoner-only).
- **Norms / validation oracle**: untouched.
- **Held-out paradigm prompts/configs**: untouched (G5 memory: never iterate against held-out paradigms).

## Pass / fail criteria for SP13 itself

### Internal (unit/integration tests)
1. `test_dom_fingerprint_stable` — same `dom_snapshots[-1].html` → same fingerprint; empty snapshots → empty string.
2. `test_refinement_includes_prior_diffs` — second-attempt prompt contains the first attempt's diff.
3. `test_sequential_smallest_advance_prompt` — prompt invariant: contains the literal "smallest advance" phrase and "Prior refinement attempts" header.
4. `test_stuck_detection_early_fail` — two consecutive identical fingerprints → PilotValidationError without consuming remaining budget.
5. `test_dev_paradigm_passes_first_attempt` — feed a known-good partial + a stubbed PilotRunner that returns "passed" on first try; assert no refinements happen (sequential mode is backward-compatible).
6. Suite must remain green (currently 530+ tests post-SP12).

### External (held-out validation)
1. **Re-run held-out paradigm** `stop_signal_with_integrated_memory`: `uv run experiment-bot-reason https://deploy.expfactory.org/preview/80/ --label stop_signal_with_integrated_memory --pilot-max-retries 12`. **Target: pilot converges (Stage 6 PASS) within budget**, OR fails with a clearly-articulated stuck-DOM message at a state the refiner genuinely cannot resolve from observation alone (e.g., custom-canvas stimulus rendering). Either outcome is acceptable — convergence is the upside, an honest failure is the floor.
2. **Dev 4 regression**: `uv run experiment-bot-reason` against each of `expfactory_stroop`, `expfactory_stop_signal`, `stopit_stop_signal`, `cognitionrun_stroop`. **Target: each passes Stage 6 on attempt 1** (no refinements needed → sequential mode does not regress behavior on paradigms the bot already handles).
3. **New held-out** (optional, time permitting): one additional paradigm from `expfactory` not in the dev set. **Target: report pass/fail honestly in the deliverable; no claims about specific success rate.**

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM proposes "fix everything" diffs despite the smallest-advance prompt | Prompt examples + the prior_diffs evidence ("you already did X; the bot is now at Y"). If empirically the LLM still over-fixes, fold a `max_changes` budget into the prompt in a follow-up. |
| Refinement oscillates (revert prior fix, re-add it) | `prior_diffs` evidence in the prompt + stuck-detection guard (same fingerprint twice = abort). |
| Budget exhaustion on paradigms that genuinely cannot be solved by observation alone (canvas-rendered stimuli, non-DOM trial markers, etc.) | This is the honest failure surface. PilotValidationError fires, paradigm marked `sp11_supported=False` per Phase 5b L15 drop-from-scope policy. |
| Higher Claude API cost (up to 12 refinement calls per failed paradigm) | Stuck-detection caps oscillation. Most paradigms either succeed on attempt 1 (no refinement cost) or fail fast (stuck-detection after ≤2 attempts). Worst case: ~12 refinement LLM calls × ~$0.10 each = ~$1.20 per pathological paradigm. Acceptable. |
| Resume semantics: budget restarts on resume | Acceptable. User can bump `--pilot-max-retries` manually if they want a longer continued walk after a resume. Documented in CLI help text. |

## Out of scope (deliberate)

- **Option A (eager DOM reconnaissance before Stage 1)** — rejected in the brainstorm: blurs G2 by making Reasoner partially execute the experiment, weakens Stage 6's epistemic role.
- **Option B (PlaywrightGateDismisser in executor's trial loop)** — rejected for SP13. If, after SP13 ships, dev-paradigm sessions still hit navigation edge cases at runtime, B can be reconsidered as a separate small SP. Not bundled here because it doesn't address the root cause that motivated this work.
- **TaskCard schema changes** — none. Refiner mutates the same fields it always has.

## Decomposition (preview for the plan)

1. Add `dom_fingerprint` to `PilotDiagnostics` + test.
2. Refactor `_refine_partial` to accept `prior_diffs` + test.
3. Rewrite `REFINEMENT_PROMPT` to sequential framing + prompt-invariant test.
4. Add fingerprint tracking + stuck-detection guard in `run_stage6` + test.
5. Bump budget defaults in CLI + pipeline + test backward compatibility.
6. Update `docs/pipeline-flow.md` Stage 6 section (1-2 paragraphs).
7. Held-out validation: re-run `stop_signal_with_integrated_memory` + dev-4 regression smoke + write `docs/sp13-results.md`.
8. Update `CLAUDE.md` SP-history entry with SP13 outcome.

## What success looks like at SP13 close

A clean tag `sp13-complete` with: (a) all internal tests passing, (b) the held-out `stop_signal_with_integrated_memory` either converging or failing with a defensible stuck-DOM message, (c) dev-4 paradigms unchanged on Stage 6 attempt 1, (d) `docs/sp13-results.md` reporting outcomes honestly per Honest-Framing memory. If the held-out paradigm fails despite SP13, the conclusion is "iterative refinement is necessary but not sufficient; some paradigms require richer recon than DOM snapshots alone provide" — that's a publishable scope-of-validity refinement, not a project failure.

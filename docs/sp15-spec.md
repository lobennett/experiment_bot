# SP15 — Persistent-Session Pilot Walker (design spec)

## Goal

Replace Stage 6's per-attempt fresh-browser pattern with a **single persistent Playwright session** that walks the experiment one DOM advance at a time, across BOTH the navigation phase and the stimulus-matching phase. Each LLM refinement produces a single delta (one new nav phase OR one updated stimulus selector) applied to the live session, not a full TaskCard re-write.

## Motivation

SP13 + SP14 made the walker semantically correct (sequential refinement, append-only nav phases, schema-aware prompts). But the OPERATIONAL pattern is wasteful and slightly dangerous:

- Each attempt launches a fresh Chromium (~3-5s overhead).
- Each attempt re-runs ALL prior nav phases from scratch (linear-growth wall time).
- Each `page.goto` re-renders the experiment → re-randomization, re-init JS, lost session state. A bot that "fixed" itself at attempt N may see a different page at attempt N+1 just because the experiment re-randomized.
- The "smallest advance" mental model is fictional internally — every attempt is "redo everything + one more thing."

SP14's held-out re-run made this visible: the walker took ~6 minutes to traverse 4 DOM states, most of it spent re-clicking already-clicked buttons. With persistent session, the SAME 4-state walk should finish in <1 minute.

## What this preserves

- **Stage 6 PilotValidationError gate.** Still the honest failure surface; SP15 keeps the same stuck-detection + budget-exhaustion abort conditions.
- **TaskCard schema.** The emitted TaskCard's `navigation.phases` and `stimuli[].detection` fields are unchanged. Only how they're CONSTRUCTED changes.
- **Resume semantics.** `save_partial` callback still fires after each successful advance; `.reasoner_work/<label>/stage5.json` accumulates the refined state for `--resume`.
- **Executor.** Zero changes; downstream still consumes the same TaskCard format.
- **Reasoner Stages 1-5.** Unchanged.
- **G2 separation.** All session state lives in Stage 6 (Reasoner); the bot's runtime executor still doesn't know what it's looking at — it just executes TaskCards.

## What this changes

### 1. New module: `core/pilot_session.py`

A `PilotSession` async context manager that owns the browser/context/page for the walker's lifetime:

```python
@dataclass
class PhaseAttempt:
    """Result of trying a single nav phase against the live session."""
    success: bool          # True if Playwright executed without error
    dom_after: str         # Page DOM after the attempt
    error: str | None      # Crash message if any

@dataclass
class StimulusProbe:
    """Result of polling stimuli once."""
    match: StimulusMatch | None
    dom_at_probe: str

class PilotSession:
    async def __aenter__(self) -> "PilotSession": ...
    async def __aexit__(self, *exc) -> None: ...

    async def goto(self, url: str) -> str:
        """Navigate to URL; return initial DOM snapshot."""

    async def try_phase(self, phase: NavigationPhase) -> PhaseAttempt:
        """Execute ONE nav phase against the live page."""

    async def probe_stimulus(self, lookup: StimulusLookup) -> StimulusProbe:
        """Single poll over all stimulus selectors; no advancement."""

    async def poll_stimuli(self, lookup: StimulusLookup, *,
                          max_polls: int, advance_keys: list[str]) -> PilotDiagnostics:
        """Multi-poll stimulus matching with the existing diagnostic semantics."""

    async def dom_snapshot(self, container_selector: str = "body") -> str: ...
    async def press(self, key: str) -> None: ...
```

The session is reusable across many attempts. Browser launches ONCE.

### 2. Refactor `PilotRunner.run` to wrap PilotSession

The existing `PilotRunner.run(config, url, headless)` keeps the same signature and return type (`PilotDiagnostics`) but is reimplemented as:

```python
async def run(self, config, url, headless=False) -> PilotDiagnostics:
    async with PilotSession(headless=headless) as session:
        await session.goto(url)
        # Run all nav phases serially
        for phase in config.navigation.phases:
            attempt = await session.try_phase(phase)
            if not attempt.success:
                # collect crash + early-return
                ...
        # Then run the stimulus polling loop
        return await session.poll_stimuli(lookup, ...)
```

This keeps backward compatibility for any test/caller that uses `PilotRunner.run` directly (most existing pilot tests).

### 3. New stage 6 flow: `run_stage6` becomes a persistent-session walker

The walker owns one PilotSession for the entire refinement loop:

```python
async with PilotSession(headless=headless) as session:
    await session.goto(bundle.url)

    accumulated_phases = list(partial['navigation']['phases'])
    accumulated_stim_overrides: dict[str, str] = {}

    # Apply initial phases (from --resume state)
    for phase in accumulated_phases:
        await session.try_phase(phase)

    fingerprint_history: list[str] = []
    prior_diffs: list[str] = []

    for attempt in range(max_retries + 1):
        # Try a final stimulus probe — are we in trial-rendering phase?
        diag = await session.poll_stimuli(lookup, max_polls=100, ...)
        if _pilot_passed(diag, config):
            # SUCCESS: emit accumulated state into TaskCard
            partial['navigation']['phases'] = accumulated_phases
            for sid, sel in accumulated_stim_overrides.items():
                _patch_stim_selector(partial, sid, sel)
            return partial, ReasoningStep(...)

        # Failed. Look at the post-probe DOM.
        current_dom = await session.dom_snapshot()
        fp = sha256(current_dom)[:16]

        # Stuck-detection (same as SP13)
        if len(fingerprint_history) >= 1 and fp == fingerprint_history[-1] and fp:
            raise PilotValidationError(...stuck at fingerprint...)
        fingerprint_history.append(fp)

        if attempt == max_retries:
            raise PilotValidationError(...budget exhausted...)

        # Decide refinement type from the diagnostic
        if diag.trials_completed > 0 and diag.trials_with_stimulus_match == 0:
            # Bot reached trial-rendering but selectors don't match
            update = await _propose_stimulus_selector(client, current_dom,
                                                     lookup, prior_diffs)
            accumulated_stim_overrides[update.stim_id] = update.new_selector
            lookup.update_selector(update.stim_id, update.new_selector)
            prior_diffs.append(_format_stim_diff(update))
        else:
            # Bot stuck on an interstitial; propose next nav phase
            new_phase = await _propose_next_phase(client, current_dom,
                                                  accumulated_phases, prior_diffs)
            attempt_result = await session.try_phase(new_phase)
            if attempt_result.success:
                accumulated_phases.append(new_phase)
                prior_diffs.append(_format_phase_diff(new_phase))
                partial['navigation']['phases'] = accumulated_phases
                save_partial(partial)
            else:
                # Phase crashed; don't accumulate. Loop and let stuck-detection
                # decide if we're going in circles.
                prior_diffs.append(f"(failed) {_format_phase_diff(new_phase)}")
```

Key design notes:
- **One browser per walker**, opened at session entry, closed at session exit.
- **Phases accumulate in memory** (`accumulated_phases`) and are appended to the TaskCard via `save_partial` only after they execute successfully on the live page.
- **Stimulus selector updates** are applied in-place to a mutable `StimulusLookup` and tracked in `accumulated_stim_overrides`; on success they're spliced into the TaskCard.
- **`save_partial` granularity is per successful advance** (not per attempt), so `--resume` picks up from the latest verified state.

### 4. New refinement prompts

Two narrower prompts replace the single `REFINEMENT_PROMPT`:

**`NAVIGATION_REFINEMENT_PROMPT`** — given current DOM + accumulated phases + prior diffs → output ONE new navigation phase JSON object (flat schema). Retains SP14's schema examples + APPEND ordering rule. Output format: a single JSON dict matching one `NavigationPhase`.

**`STIMULUS_REFINEMENT_PROMPT`** — given current DOM (which contains a rendered but un-matched stimulus) + current stimulus configurations + prior diffs → output ONE selector update: `{"stim_id": "...", "new_selector": "..."}`. Used when the bot reaches the test phase but `selector_results` show 0 matches.

### 5. Test changes

**New tests** (`tests/test_pilot_session.py`):
1. `test_pilot_session_context_manager_closes_cleanly` — even on exception
2. `test_pilot_session_try_phase_returns_success_when_visible` — fake page with a button, click works
3. `test_pilot_session_try_phase_returns_failure_on_timeout` — phase crash captured, session still usable
4. `test_pilot_session_dom_snapshot_idempotent` — multiple calls return same DOM if page unchanged
5. `test_pilot_session_probe_stimulus_no_match` — stim not present → None
6. `test_pilot_session_probe_stimulus_match` — stim present → match returned

**Rewritten tests** (`tests/test_reasoner_stage6.py`):
- `test_stage6_passes_when_pilot_meets_criteria` → use mocked PilotSession that returns a passing diagnostic on first probe
- `test_stage6_refines_on_failure_then_passes` → mocked session where first probe fails, refinement appends one phase, second probe passes
- `test_stage6_raises_after_max_retries_exhausted` → mocked session that always fails
- `test_stage6_stuck_detection_aborts_early` → mocked session where DOM doesn't change between attempts
- `test_stage6_navigation_refinement_appends_phase` (new) — verify accumulator semantics
- `test_stage6_stimulus_refinement_updates_lookup` (new) — verify selector update path
- `test_navigation_refinement_prompt_invariants` — SP14's schema + APPEND assertions transfer
- `test_stimulus_refinement_prompt_invariants` (new) — new prompt has expected structure

**Existing tests preserved unchanged** (`tests/test_pilot.py` PilotDiagnostics tests — none depend on the session architecture).

### 6. Held-out re-validation

Re-run `stop_signal_with_integrated_memory`. Expected outcome under SP15:
- Walker advances past fullscreen → welcome → instructions → practice in ~5 nav refinements (one per visible screen) WITHOUT re-launching the browser.
- Each refinement takes ~1-3 seconds (no Chromium re-launch).
- If trial DOM is reached: poll stimuli; if 0 matches, propose stimulus-selector update; re-probe.
- Pass: TaskCard emitted with accumulated nav + stim overrides.
- Fail: stuck-detection or budget exhaustion, same as before.

### 7. Dev-4 regression

All 4 dev paradigms should still pass Stage 6 under SP15 (the non-refinement passing path is the same diagnostic check, just on the PilotSession's first probe). Pre-existing `taskcards/<label>/<latest>.json` baselines used; check via `--resume`.

## Pass / fail criteria for SP15

### Internal (must all hold)
1. All new + rewritten tests pass.
2. Existing tests that aren't intentionally rewritten continue to pass (PilotDiagnostics tests, executor tests, etc.).
3. `uv run pytest -x -q` reports 0 failures.
4. `PilotRunner.run` keeps its signature; no executor-facing changes.

### External
1. Dev-4 regression: all 4 paradigms pass Stage 6 under SP15 (most on first probe; stopit_stop_signal may need its same 1 refinement, now via the new walker).
2. Held-out paradigm: walker either CONVERGES (best case — TaskCard written), or FAILS with a precisely-articulated stuck or budget message at a state genuinely beyond observation-via-snapshot.
3. **Wall-time benchmark**: held-out walker completes in <5 minutes (was ~10+ minutes under SP14).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Stateful session is harder to mock | Build `PilotSession` with a small, focused interface (~6 methods); mock at that layer rather than at Playwright. New `test_pilot_session.py` uses real Playwright against a static HTML fixture for the 6 unit tests. |
| One bad refinement poisons the session (e.g., navigates somewhere unexpected) | `try_phase` returns `PhaseAttempt(success=False, ...)` on crash; accumulator only appends on success. If the page genuinely got lost, stuck-detection fingerprint check catches the divergence within 1-2 attempts. |
| Browser leak if walker raises mid-loop | `async with PilotSession(...)` context manager ensures cleanup. New test verifies `__aexit__` runs even when the loop body raises. |
| `PilotRunner.run` backward compat breaks executor or other callers | The existing `PilotRunner.run(config, url, headless)` keeps its signature; only its implementation moves to delegate to PilotSession. All ~6 existing pilot tests still hold. |
| Resume state mismatch (stage5.json says "navigation has 3 phases" but session has only run 2) | When `--resume`-ing, the walker applies ALL accumulated phases at session start before entering the refinement loop. The cost is one-time, paid at resume entry. |
| Stimulus refinement path interferes with the polling loop | Stimulus refinement happens BETWEEN polling-loops; while the loop is running, no refinements are made. Selector updates apply to a mutable `StimulusLookup` (not the TaskCard partial directly) until the walker exits successfully. |

## Out of scope

- Changing the LLM provider, model, or prompt-caching strategy.
- Stage 1-5 changes (the refinement prompts evolve but Stage 1's structural inference is unchanged).
- Executor changes.
- Adding new TaskCard fields.

## Decomposition (preview)

1. **PilotSession class** with try_phase/probe_stimulus/dom_snapshot + unit tests.
2. **PilotRunner.run reimplemented via PilotSession** (backward-compatible refactor); existing pilot tests still pass.
3. **Split REFINEMENT_PROMPT** into NAVIGATION_REFINEMENT_PROMPT + STIMULUS_REFINEMENT_PROMPT with delta-shaped outputs.
4. **Rewrite `run_stage6`** to use the persistent-session walker.
5. **Update stage6 tests** for new contract.
6. **Held-out re-validation** + dev-4 regression.
7. **Docs**: `sp15-results.md`, `pipeline-flow.md` Stage 6 update, `CLAUDE.md` SP15 entry.

## What success looks like at SP15 close

A clean `sp15-complete` tag with:
- All internal tests passing
- Dev-4 backward-compatible
- Held-out walker either converging OR failing in <5 min wall time with a precise diagnostic
- A `docs/sp15-results.md` reporting honestly per the project's Honest-Framing pattern
- Browser launches reduced from "one per attempt" to "one per walker" — visible in the held-out wall-time metric

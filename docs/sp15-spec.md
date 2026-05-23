# SP15 — Platform-Aware Stage 1 + Persistent-Session Pilot Walker (design spec)

## Goal

**Enable realistic behavioral data collection on held-out paradigms hosted on known platforms** (expfactory, cognition.run, kywch.github.io) by closing two compounding gaps:

1. **Part A**: Stage 1 fails to extract canonical navigation phases for known hosting platforms, producing TaskCards with empty `navigation.phases` that force Stage 6 into a long refinement walk. Add platform-aware defaults so Stage 1 emits the right nav sequence on first generation.
2. **Part B**: Stage 6's per-attempt fresh-browser pattern is wasteful and detectable (multiple Chromium tabs in rapid succession) for cases where refinement IS still needed. Replace with a single persistent Playwright session that walks the experiment one DOM advance at a time.

After both parts land, held-out paradigms on supported platforms should pass Stage 6 on attempt 1 (Part A), and paradigms that DO need refinement should walk efficiently and discretely in a single browser session (Part B).

## Motivation

### The compounding diagnosis

The held-out paradigm `stop_signal_with_integrated_memory` (deploy.expfactory.org/preview/80) exposed two distinct failure modes that compounded:

**1. Stage 1 omission.** For dev paradigms hosted on expfactory (Stroop, stop_signal), Stage 1 emits a complete 10-phase nav sequence (fullscreen click → Enter → instructions-next × N → Enter). For the held-out paradigm, despite identical hosting platform and identical jsPsych plugin manifest, Stage 1 emitted `"phases": []`. Stage 1's prompt failed to extract the standard expfactory flow on a paradigm it had never seen.

**2. Stage 6 walker inefficiency.** Forced to discover the entire nav sequence from scratch via refinement, the SP14 walker took 5 attempts and ~6 minutes, opening Chromium 5 times in rapid succession. The "discrete bot" goal (avoiding platform detection) is compromised by this pattern. The "smallest advance" mental model was also fictional — each attempt re-ran ALL prior nav phases from scratch, causing linear wall-time growth and re-randomizing the experiment between attempts.

### Why a single SP

Part A is the higher-leverage fix: it eliminates the walker invocation entirely for held-out paradigms on supported platforms. Part B is the safety net for paradigms that still need refinement (genuinely novel platforms, custom stimulus DOM) AND fixes the discreteness problem in any walker invocation. Done together they cover both the root cause and the residual failure mode.

## What this preserves

- **Stage 6 PilotValidationError gate.** Still the honest failure surface; SP15 keeps the same stuck-detection + budget-exhaustion abort conditions.
- **TaskCard schema.** The emitted TaskCard's `navigation.phases` and `stimuli[].detection` fields are unchanged. Only how they're CONSTRUCTED changes.
- **Resume semantics.** `save_partial` callback still fires after each successful advance; `.reasoner_work/<label>/stage5.json` accumulates the refined state for `--resume`.
- **Executor.** Zero changes; downstream still consumes the same TaskCard format.
- **Reasoner Stages 1-5.** Unchanged.
- **G2 separation.** All session state lives in Stage 6 (Reasoner); the bot's runtime executor still doesn't know what it's looking at — it just executes TaskCards.

## What this changes

### PART A: Stage 1 platform-aware nav defaults

#### A1. New module: `reasoner/platform_defaults.py`

A static lookup from URL pattern → canonical `navigation.phases` array for known hosting platforms. Each entry encodes the *infrastructure* navigation for that platform (fullscreen handling, instructions plugin advances, consent screens), NOT paradigm-specific stimulus or response logic.

```python
# Pseudo-shape; concrete JSON in the implementation
PLATFORM_NAV_DEFAULTS: list[PlatformDefault] = [
    PlatformDefault(
        name="expfactory",
        url_patterns=[r"deploy\.expfactory\.org/", r"expfactory\.org/preview/"],
        # The canonical expfactory entry flow: fullscreen → wait → Enter → wait → next × N → wait → Enter
        phases=[
            {"action": "wait",     "duration_ms": 1000, ...},
            {"action": "click",    "target": "#jspsych-fullscreen-btn", ...},
            {"action": "wait",     "duration_ms": 1000, ...},
            {"action": "keypress", "key": "Enter", ...},
            {"action": "wait",     "duration_ms": 1000, ...},
            {"action": "click",    "target": "#jspsych-instructions-next", ...},
            {"action": "wait",     "duration_ms": 1000, ...},
            {"action": "click",    "target": "#jspsych-instructions-next", ...},
            {"action": "wait",     "duration_ms": 1000, ...},
            {"action": "keypress", "key": "Enter", ...},
        ],
    ),
    PlatformDefault(
        name="cognition.run",
        url_patterns=[r"\.cognition\.run"],
        # The canonical cognition.run entry flow (per taskcards/cognitionrun_stroop/e62646a9.json)
        phases=[ {"action": "sequence", "steps": [...5 space-presses with waits...]} ],
    ),
    PlatformDefault(
        name="kywch.github.io",
        url_patterns=[r"kywch\.github\.io"],
        # The canonical kywch stop-it entry flow (per taskcards/stopit_stop_signal/*.json)
        phases=[ ... ],
    ),
]
```

Each entry derived directly from the dev-paradigm TaskCards that already pass Stage 6. This is *infrastructure recognition*, not paradigm overfitting (per [[avoid-paradigm-overfitting]] memory): the same canonical phases work for every paradigm on the same platform.

#### A2. Hook platform-defaults into Stage 1

After `run_stage1` produces its partial, a post-processing step in `reasoner/stage1_structural.py` (or pipeline.py) matches the URL against `PLATFORM_NAV_DEFAULTS`. If a match is found AND the LLM-emitted `navigation.phases` is empty or shorter than the platform default, the platform defaults are spliced in.

```python
def apply_platform_defaults(partial: dict, url: str) -> dict:
    """If the URL matches a known platform AND the LLM emitted an empty or
    sub-default navigation, use the platform's canonical phases.
    LLM-emitted nav takes precedence ONLY when it's at least as long as the
    platform default (assumption: LLM has extra paradigm-specific knowledge)."""
    default = _match_platform(url)
    if default is None:
        return partial
    current_phases = partial.get("navigation", {}).get("phases", [])
    if len(current_phases) >= len(default.phases):
        # LLM may have paradigm-specific knowledge; trust it
        return partial
    # Backfill with platform default
    partial.setdefault("navigation", {})["phases"] = default.phases
    return partial
```

The decision rule "LLM emit takes precedence if at least as long" is conservative: the LLM is allowed to do better than the platform default but never to under-emit silently. For the held-out paradigm, LLM emitted 0 phases → platform default (10 phases) backfills.

#### A3. Tests for platform defaults

1. `test_platform_default_matches_expfactory_url` — URLs like `deploy.expfactory.org/preview/80` → expfactory default
2. `test_platform_default_matches_cognition_run_url` — `https://strooptest.cognition.run/` → cognition.run default
3. `test_platform_default_no_match_returns_partial_unchanged` — unknown platform → no-op
4. `test_platform_default_does_not_clobber_richer_llm_nav` — LLM emitted 12 phases, platform default has 10 → LLM wins
5. `test_platform_default_backfills_empty_llm_nav` — LLM emitted 0 phases → platform default applies

#### A4. Held-out validation for Part A

Re-run the Reasoner against `stop_signal_with_integrated_memory`. Stage 1 should now emit the expfactory canonical nav, Stage 6 pilot should pass on attempt 1 with NO walker invocation. The success criterion for Part A: TaskCard generated, Stage 6 PASS, 0 refinements, 1 browser tab opened total.

If Part A succeeds, Part B becomes a quality improvement rather than a blocker. Even if a future held-out paradigm needs walker refinement, Part B ensures it remains discrete.

---

### PART B: Persistent-Session Pilot Walker

#### 1. New module: `core/pilot_session.py`

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
1. All new + rewritten tests pass (platform-defaults, PilotSession, refactored Stage 6).
2. Existing tests that aren't intentionally rewritten continue to pass (PilotDiagnostics tests, executor tests, etc.).
3. `uv run pytest -x -q` reports 0 failures.
4. `PilotRunner.run` keeps its signature; no executor-facing changes.

### External (Part A — root-cause fix)
1. **Held-out paradigm `stop_signal_with_integrated_memory`**: Stage 1 emits the expfactory canonical nav (10 phases), Stage 6 pilot passes on attempt 1, **0 refinements consumed**, **1 browser tab opened total**.
2. **Dev-4 regression**: all 4 paradigms continue to pass on attempt 1 (Part A doesn't override their LLM-emitted nav since the LLM already produces ≥10 phases for those).

### External (Part B — walker quality)
3. **Wall-time benchmark for refinement-requiring paradigms**: any future paradigm that DOES trigger the walker completes in **<5 minutes** wall-time and opens **1 browser tab** total (was ~10+ min, 5+ tabs under SP14).
4. **Discreteness**: per-session bot behavior under the new walker should be indistinguishable from a single human session at the platform level (one tab, reading delays preserved, no rapid-launch pattern).

### External (the actual goal)
5. **Behavioral data on the held-out paradigm**: with a working TaskCard from Part A, the executor produces ≥5 sessions of stop_signal_with_integrated_memory trial data; SSRT, go-RT, accuracy validated against published stop-signal + working-memory norms. This is the deliverable SP15 unblocks; the data-generation runs are a follow-up phase (SP15-validation) after SP15 ships.

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

**Part A first** (most leverage; held-out paradigm likely passes after task 3):
1. `platform_defaults.py` module — URL pattern → canonical nav phases lookup; tests.
2. Hook `apply_platform_defaults` into Stage 1 post-LLM step; tests.
3. **Part A held-out validation**: re-run Reasoner against `stop_signal_with_integrated_memory`; expect Stage 6 PASS on attempt 1, 0 refinements.

**Part B** (walker efficiency + discreteness, needed for novel-platform held-outs):
4. `PilotSession` class with try_phase/probe_stimulus/dom_snapshot + unit tests.
5. `PilotRunner.run` reimplemented via `PilotSession` (backward-compatible refactor); existing pilot tests still pass.
6. Split `REFINEMENT_PROMPT` into `NAVIGATION_REFINEMENT_PROMPT` + `STIMULUS_REFINEMENT_PROMPT` with delta-shaped outputs.
7. Rewrite `run_stage6` to use the persistent-session walker.
8. Update stage6 tests for the new contract.

**Validation** (the SP15 deliverable):
9. Dev-4 regression: all 4 paradigms still pass Stage 6 on attempt 1.
10. Held-out paradigm: confirm Part A makes Stage 6 pass on first attempt; document wall-time.
11. **Behavioral data run**: executor × 5 sessions against the held-out paradigm using the new TaskCard; analyze SSRT, go-RT, accuracy vs published norms. Deliver as `docs/sp15-heldout-behavior.md`.

**Docs**:
12. `docs/sp15-results.md` (held-out + dev-4 outcomes + wall-time benchmarks).
13. `docs/pipeline-flow.md` Stage 6 + Stage 1 platform-defaults updates.
14. `CLAUDE.md` SP15 entry; tag `sp15-complete`.

## What success looks like at SP15 close

A clean `sp15-complete` tag with:
- All internal tests passing
- Dev-4 backward-compatible
- Held-out walker either converging OR failing in <5 min wall time with a precise diagnostic
- A `docs/sp15-results.md` reporting honestly per the project's Honest-Framing pattern
- Browser launches reduced from "one per attempt" to "one per walker" — visible in the held-out wall-time metric

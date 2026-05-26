# SP16 — TaskExecutor refactor with adaptive nav (design spec)

## Goal

Refactor `TaskExecutor` to use `PilotSession` for browser lifecycle AND add an LLM-driven adaptive-nav fallback to the trial loop. The executor becomes the *production* counterpart to Stage 6's pilot walker: it preserves all current behavioral-data semantics (calibration, session_seed, ex-Gaussian RT sampling, full bot_log) while gaining the ability to navigate interleaved instruction + trial flows like the held-out paradigm `stop_signal_with_integrated_memory`.

**Concretely:** when the trial loop's standard nav re-run (existing INSTRUCTIONS-phase handling) doesn't advance the bot, an adaptive nav step (LLM proposes one phase + applies it live) takes over. The executor logs every adaptive action so sessions remain auditable.

## Motivation

SP15's held-out test surfaced a clean architectural finding: the walker's persistent-session adaptive nav can navigate paradigms the executor's fixed-nav-then-trial-loop cannot. The executor's `_trial_loop` already handles INSTRUCTIONS by re-running `navigation.phases` from scratch — but on paradigms with paradigm-specific between-block instruction screens (practice → test transitions, demo trials in the practice block, etc.), the fixed nav phases either crash on missing targets or fail to advance. SP15 ships the walker for Stage 6; SP16 brings the same adaptive capability into the executor's session-time loop so the framework can collect humanlike, calibrated behavioral data on complex paradigms.

## What this preserves

- **All trial-loop semantics**: phase detection, stimulus matching via `StimulusLookup`, ex-Gaussian RT sampling from `session_params`, response key delivery via CDP/Playwright, `bot_log.json` per-trial logging.
- **Calibration pass**: still runs once after entry navigation, measures key→record latency, applies offset to sampled RTs. Preserved end-to-end.
- **Run-output format**: `bot_log.json`, `run_metadata.json`, `run_trace.json`, `config.json`, `screenshots/` — all unchanged in shape. Adaptive-nav events appear as new entries in a separate `bot_log` channel (`type: "adaptive_nav"`).
- **`taskcard.types.TaskCard` schema**: unchanged. The TaskCard's `navigation.phases` is still the planned entry sequence; adaptive nav is a session-time runtime augmentation, not a TaskCard mutation.
- **Dev-4 paradigm behavior**: their TaskCards already make the trial loop advance correctly. Adaptive nav fires only when the standard re-run path FAILS to advance — so dev-4 paradigms shouldn't trigger it. Re-validation confirms this.
- **G2 separation**: the Reasoner still produces TaskCards; the bot still executes them. Adaptive nav is a *recovery mechanism* the bot invokes when the TaskCard's nav doesn't suffice at runtime — not a substitute for Stage 6's design-time TaskCard generation.

## What this changes

### 1. Browser lifecycle migrates to `PilotSession`

Currently `TaskExecutor.run` opens its own `async_playwright()` context. SP16 wraps the same lifetime in a `PilotSession`:

```python
async def run(self, task_url: str) -> None:
    task_name = self._config.task.name.replace(" ", "_").lower()
    run_dir = self._writer.create_run(task_name, self._config)

    async with PilotSession(
        headless=self._headless,
        viewport=self._config.runtime.timing.viewport,
        reading_delay_range=(3.0, 8.0),  # executor uses humanlike reading delays
    ) as session:
        page = session.page
        # ... rest of run() uses page + session ...
```

Key constraint: the existing CDP setup (`context.new_cdp_session(page)` in `_setup_keypress_deliverer`) needs `context`. `PilotSession` exposes `context` and `page` as properties.

### 2. Entry navigation via `session.try_phase`

`navigator.execute_all(page, config.navigation)` is replaced with a per-phase loop that uses `session.try_phase`. Failures (timeouts on non-existent click targets) are logged and skipped rather than raised, so a slightly-stale TaskCard nav doesn't crash session start. This matches the walker's behavior.

```python
# Phase 1: Navigate instructions (one phase at a time, skip-on-fail)
for phase in self._config.navigation.phases:
    attempt = await session.try_phase(phase)
    if not attempt.success:
        logger.info(f"Nav phase {phase.phase or '<unnamed>'} skipped: {attempt.error}")
```

### 3. Adaptive nav in the trial loop

The existing `_trial_loop` INSTRUCTIONS-phase branch calls `_navigator.execute_all` (re-runs ALL TaskCard nav phases). SP16 adds a *fallback*: if the post-nav-rerun state doesn't advance for `_ADAPTIVE_NAV_STUCK_POLLS=20` consecutive polls, an adaptive nav step fires.

```python
# Inside _trial_loop, when phase == INSTRUCTIONS:
if phase in (TaskPhase.FEEDBACK, TaskPhase.INSTRUCTIONS):
    probe = await self._lookup.identify(page)
    if probe is None or not self._is_trial_stimulus(probe):
        if phase == TaskPhase.FEEDBACK:
            await self._handle_feedback(page)
        else:
            # Try the TaskCard's fixed nav first (existing behavior)
            await self._try_taskcard_nav(session, page)
        consecutive_misses = 0
        post_nav_polls = 0
        continue

# When stimulus polling fails for >= _ADAPTIVE_NAV_STUCK_POLLS AND we have
# LLM client + adaptive budget remaining:
if (
    consecutive_misses >= _ADAPTIVE_NAV_STUCK_POLLS
    and self._llm_client is not None
    and self._adaptive_nav_uses < _ADAPTIVE_NAV_BUDGET
):
    advanced = await self._adaptive_nav_step(session, page)
    if advanced:
        consecutive_misses = 0
        continue
```

The `_adaptive_nav_step` helper:

```python
async def _adaptive_nav_step(self, session: PilotSession, page: Page) -> bool:
    """LLM-driven one-step nav. Returns True if the bot advanced."""
    dom_before = await session.dom_snapshot()
    fp_before = _fingerprint(dom_before)

    from experiment_bot.reasoner.stage6_pilot import _propose_next_phase
    phase_dict = await _propose_next_phase(
        self._llm_client, dom_before,
        self._runtime_nav_phases, self._adaptive_nav_diffs,
    )
    # Defensive fill (same as walker)
    phase_dict.setdefault("steps", [])
    phase_dict.setdefault("key", "")
    phase_dict.setdefault("target", "")
    phase_dict.setdefault("duration_ms", 0)
    phase_dict.setdefault("phase", "adaptive")
    new_phase = NavigationPhase.from_dict(phase_dict)
    attempt = await session.try_phase(new_phase)

    self._adaptive_nav_uses += 1
    self._runtime_nav_phases.append(phase_dict)
    self._adaptive_nav_diffs.append(f"Adaptive {self._adaptive_nav_uses}: {phase_dict}")

    dom_after = await session.dom_snapshot()
    fp_after = _fingerprint(dom_after)
    advanced = fp_before != fp_after

    # Log to bot_log for auditability
    self._bot_log.append({
        "type": "adaptive_nav",
        "step": self._adaptive_nav_uses,
        "phase": phase_dict,
        "session_t": time.monotonic() - self._session_start,
        "success": attempt.success,
        "advanced": advanced,
        "error": attempt.error,
        "dom_fingerprint_before": fp_before,
        "dom_fingerprint_after": fp_after,
    })

    return advanced
```

### 4. `TaskExecutor` constructor accepts an `LLMClient`

The CLI builds one via the existing `build_default_client()` factory:

```python
# In cli.py, where TaskExecutor is constructed:
llm_client = build_default_client()  # for adaptive nav
executor = TaskExecutor(
    ...existing args...,
    llm_client=llm_client,
)
```

If `llm_client` is None (e.g., a test or a CI run that wants determinism), adaptive nav is disabled and the executor falls back to current behavior. This is a graceful degradation.

### 5. Adaptive nav budget + telemetry

- `_ADAPTIVE_NAV_BUDGET = 10` adaptive steps per session (configurable via TaskCard runtime field if needed later; constant for SP16).
- `_ADAPTIVE_NAV_STUCK_POLLS = 20` consecutive no-match polls before adaptive nav fires (≈ 1 second at 50ms poll interval).
- `run_metadata.json` gains an `adaptive_nav` field summarizing: total adaptive steps used, success count, dom-advance count, total LLM tokens (if available).

### 6. Bot log gains `adaptive_nav` event type

Existing trial entries have `type: "trial"`. Adaptive nav events get `type: "adaptive_nav"` (shape above). `validation/platform_adapters.py` already ignores unknown bot_log entry types, so no changes there. `scripts/analyze_sessions.py` will be updated to surface adaptive-nav counts in its per-paradigm summary.

## What this does NOT do

- **No TaskCard mutation**: adaptive nav is in-memory only. The TaskCard's `navigation.phases` is the planned entry sequence; adaptive additions don't get written back. This keeps the TaskCard a clean spec; if the held-out paradigm reliably needs the same N adaptive steps, that's a separate question for follow-up SPs (could be auto-promoted to TaskCard after N successful sessions, etc.).
- **No fundamental trial-loop redesign**: phase detection, stimulus matching, RT sampling — unchanged. Adaptive nav only intercepts the "stuck on instructions" failure mode.
- **No new TaskCard schema fields**: SP16 lives entirely in the executor + CLI.
- **No SessionAgent revival**: SP9a's per-trial LLM-driven key resolution was empirically not supported by behavior data and removed in SP12. SP16's adaptive nav fires *between* trials (when the bot is stuck on instructions), not per-trial.
- **No determinism guarantees**: sessions invoking adaptive nav are NOT bit-reproducible (LLM may decide differently). For paradigms needing reproducibility, run with `--no-llm-client` (new flag) to disable adaptive nav.

## Pass / fail criteria

### Internal (must hold)
1. All existing tests pass after refactor.
2. New tests: PilotSession-integrated executor (3 tests), adaptive nav step (3 tests), bot_log adaptive_nav entries (1 test).
3. `uv run pytest -x -q` 0 failures.
4. `TaskExecutor`'s public constructor + `run` method signature are backward-compatible (new kwargs are optional).

### External — dev-4 backward compat
5. Each of 4 dev paradigms × 1 smoke session under SP16: completes successfully, captures >0 trials, **adaptive_nav_uses == 0** (their TaskCards' nav is sufficient; adaptive nav doesn't fire).
6. Per-paradigm trial counts within ±10% of SP12 baseline (5-session means).

### External — held-out behavioral data
7. `stop_signal_with_integrated_memory` × 5 sessions: each captures ≥ 40 trials (practice + at least early test). Adaptive nav fires some number of times per session (target: ≤ 5 per session; if higher, the walker's TaskCard nav is under-specified — fixable in a follow-up).
8. Aggregate metrics computable: go-RT mean ± SD, accuracy, SSRT (integration method), stop-signal-delay (SSD) staircase mean.
9. Comparison vs published stop-signal norms surfaced honestly in `docs/sp16-heldout-behavior.md` per the project's [[honest-generalization-findings]] memory.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Refactor breaks dev-4 behavior | Test 5 covers this; if any paradigm regresses, fall back to non-PilotSession path for that paradigm (TaskCard runtime flag). |
| Adaptive nav fires when it shouldn't (e.g., misinterprets feedback as instructions) | `_ADAPTIVE_NAV_STUCK_POLLS = 20` is conservative; nav doesn't fire until the bot is genuinely stuck. Bot_log entries make this auditable post-hoc. |
| LLM latency adds 2-5s per adaptive step | Acceptable in absolute terms (≤50s extra per session at max budget); doesn't compound. |
| Sessions become non-deterministic | Documented; `--no-llm-client` flag preserves determinism for paradigms that don't need adaptive nav. |
| `_runtime_nav_phases` accumulates phases that don't help (e.g., LLM proposes wrong action repeatedly) | Budget cap (10) + advance-check (only counts as a step if DOM changed) bound the damage. If budget exhausts without success, existing hard-fail-on-0-trials catches it. |
| CDP setup interferes with PilotSession's context lifecycle | Add an integration test (PilotSession's context + new CDP session + key delivery); verify deliverer functions correctly. |

## Decomposition (preview)

1. **`PilotSession` exposes `context` + `page` properties** + integration test.
2. **`TaskExecutor.run` migrates browser lifecycle to PilotSession** — same entry-nav, same calibration, same trial-loop, but using `session.page`/`session.context` instead of locally-created Playwright objects.
3. **Entry-nav switches to `session.try_phase` + skip-on-fail** — replaces `navigator.execute_all` at session start.
4. **`TaskExecutor` constructor accepts `llm_client: LLMClient | None = None`** + CLI builds and passes one.
5. **`_adaptive_nav_step` helper** + integration into `_trial_loop` (fires after `_ADAPTIVE_NAV_STUCK_POLLS` consecutive misses).
6. **`bot_log` "adaptive_nav" entry type** + `run_metadata.adaptive_nav` summary block.
7. **Tests**: PilotSession-based executor (3), adaptive nav step (3), bot_log integration (1) — total +7 tests.
8. **Dev-4 regression**: 4 paradigms × 1 session smoke; assert adaptive_nav_uses == 0 + trial counts within ±10% of baseline.
9. **Held-out behavioral data**: stop_signal_with_integrated_memory × 5 sessions.
10. **`docs/sp16-results.md`** + **`docs/sp16-heldout-behavior.md`** (per-session and aggregate metrics + literature comparison).
11. **`docs/pipeline-flow.md` updates** for the new executor architecture.
12. **`CLAUDE.md` SP16 entry** + tag `sp16-complete`.

## Out of scope (deliberate)

- TaskCard schema additions.
- Walker → executor TaskCard promotion (auto-saving adaptive phases back to TaskCard).
- Changes to Stage 1-6 of the Reasoner.
- Other paradigm regressions (n-back, Flanker — those are SP3/SP5 territory).
- SessionAgent-style per-trial LLM (SP9a; empirically not supported).

## Success criteria at SP16 close

A clean tag `sp16-complete` with:
- All internal tests passing
- Dev-4 backward-compatible behavior (criteria 5-6)
- Held-out paradigm produces 5 sessions of calibrated behavioral data (criteria 7-9)
- `docs/sp16-heldout-behavior.md` reporting honestly: where the bot's stop-signal metrics fall vs published norms, with both wins and gaps surfaced explicitly

The user's session-stated goal — *realistic behavioral data on the held-out paradigm* — is delivered at this point.

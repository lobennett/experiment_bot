# SP16 — TaskExecutor PilotSession + Adaptive Nav — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Spec-compliance reviewer per task; SKIP code-quality reviewer (per `feedback_skip_code_quality_reviewer` memory).

**Goal:** Refactor `TaskExecutor` to use `PilotSession` for browser lifecycle AND add LLM-driven adaptive nav that fires when the trial loop is stuck on interleaved instruction/trial flows.

**Architecture:** `TaskExecutor.run`'s `async_playwright()` block migrates to `async with PilotSession(...)`. Entry nav uses `session.try_phase` (skip-on-fail). When trial-loop polling stalls for ≥20 consecutive misses, `_adaptive_nav_step` invokes the same `_propose_next_phase` helper SP15 uses for Stage 6 refinement. Bot_log gains `type: "adaptive_nav"` audit entries. Budget = 10 adaptive steps per session.

**Tech stack:** Python 3.12, async Playwright via `PilotSession`, Claude LLM via `experiment_bot.llm.protocol.LLMClient` (mocked in tests).

**Spec:** `docs/sp16-spec.md` (commit `fab4870`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/experiment_bot/core/pilot_session.py` | Modify | Expose `context` + `page` as properties (currently only `page` is exposed via the `page` property) |
| `src/experiment_bot/core/executor.py` | Modify | `run` uses PilotSession; constructor accepts `llm_client`; `_trial_loop` invokes `_adaptive_nav_step` on stuck-poll; bot_log gains adaptive_nav entries |
| `src/experiment_bot/cli.py` | Modify | Build `LLMClient` via factory; pass to TaskExecutor; add `--no-llm-client` opt-out flag |
| `tests/test_pilot_session.py` | Modify | +1 test for `context` property |
| `tests/test_executor.py` (or similar) | Modify | +3 tests for PilotSession integration |
| `tests/test_executor_adaptive_nav.py` | Create | 4 tests for adaptive nav step + bot_log integration |
| `scripts/analyze_sessions.py` | Modify (small) | Surface adaptive-nav counts in per-session summary |
| `docs/sp16-results.md` | Create | Dev-4 smoke + held-out × 5 results |
| `docs/sp16-heldout-behavior.md` | Create | Held-out behavioral analysis vs published norms |
| `docs/pipeline-flow.md` | Modify | Executor architecture update (PilotSession + adaptive nav callout) |
| `CLAUDE.md` | Modify | Append SP16 sub-project entry; tag `sp16-complete` |

---

## Task 1: PilotSession exposes `context` + `page` properties

**Files:**
- Modify: `src/experiment_bot/core/pilot_session.py` (add `context` property)
- Test: `tests/test_pilot_session.py` (+1 test)

**Why:** TaskExecutor needs `context` for CDP setup (`context.new_cdp_session(page)`). Today PilotSession exposes `page` via the `page` property; expose `context` similarly.

- [ ] **Step 1: Write failing test**

Append to `tests/test_pilot_session.py`:

```python
@pytest.mark.asyncio
async def test_pilot_session_exposes_context(fixture_url):
    """SP16 prerequisite: PilotSession.context returns the BrowserContext
    so callers (TaskExecutor) can create CDP sessions on it."""
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        ctx = session.context
        assert ctx is not None
        # Smoke: context can spawn a CDP session
        cdp = await ctx.new_cdp_session(session.page)
        assert cdp is not None
        await cdp.detach()
```

Run: `uv run pytest tests/test_pilot_session.py::test_pilot_session_exposes_context -v`
Expected: FAIL with `AttributeError: 'PilotSession' object has no attribute 'context'`.

- [ ] **Step 2: Add the `context` property**

In `src/experiment_bot/core/pilot_session.py`, find the existing `page` property and add `context` next to it:

```python
@property
def context(self) -> BrowserContext:
    if self._context is None:
        raise RuntimeError("PilotSession not entered")
    return self._context

@property
def page(self) -> Page:
    if self._page is None:
        raise RuntimeError("PilotSession not entered")
    return self._page
```

- [ ] **Step 3: Run tests**

`uv run pytest tests/test_pilot_session.py -v` — all 7 PASS (6 existing + 1 new).

- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/core/pilot_session.py tests/test_pilot_session.py
git commit -m "$(cat <<'EOF'
feat(sp16): PilotSession exposes context property for CDP setup

TaskExecutor needs context.new_cdp_session(page) for its CDP-based key
deliverer. Currently PilotSession exposes only `page`; SP16 makes
`context` available too. +1 unit test verifying the CDP session can be
created on the exposed context.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `TaskExecutor.run` browser lifecycle migrates to `PilotSession`

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (`run` method, ~lines 434-540)

**Why:** Replace the `async with async_playwright() as p:` block with `async with PilotSession(...) as session:`. Inside, use `session.page` and `session.context` everywhere the current code uses locally-created `page` and `context`. NO behavior changes other than lifecycle: same entry-nav, same calibration, same trial-loop. Pure refactor for now; adaptive nav comes in Task 5.

- [ ] **Step 1: Replace the lifecycle block**

In `src/experiment_bot/core/executor.py`, find the `run` method (line 434). Replace the `async with async_playwright() as p: browser = await p.chromium.launch(...); context = await browser.new_context(...); page = await context.new_page()` setup with:

```python
from experiment_bot.core.pilot_session import PilotSession

async def run(self, task_url: str) -> None:
    """Execute the full task."""
    task_name = self._config.task.name.replace(" ", "_").lower()
    run_dir = self._writer.create_run(task_name, self._config)

    async with PilotSession(
        headless=self._headless,
        viewport=self._config.runtime.timing.viewport,
        reading_delay_range=(3.0, 8.0),  # executor uses humanlike reading delays
    ) as session:
        page = session.page
        context = session.context

        try:
            logger.info(f"Navigating to {task_url}")
            _t0 = time.monotonic()
            await page.goto(task_url, wait_until="networkidle")
            self._narrate("navigate", f"loaded {task_url}")
            self._writer.record_trace(
                "navigate", {"url": task_url},
                duration_s=time.monotonic() - _t0,
            )

            await self._setup_keypress_deliverer(page, context)
            # ... rest of run() unchanged from here ...
```

Drop the `browser`, `context`, `page` local creation; they come from `session`.

The existing `try / except / finally` structure stays — exceptions are still caught and screenshots saved; cleanup happens via `PilotSession.__aexit__` automatically when the `async with` block exits.

- [ ] **Step 2: Run a smoke pytest pass to ensure no syntax errors**

`uv run pytest tests/test_executor*.py -x -q` — existing tests should still pass (none of the new behavior yet).

- [ ] **Step 3: Manual smoke — quick dev-4 paradigm**

```bash
uv run experiment-bot https://deploy.expfactory.org/preview/10/ \
    --label expfactory_stroop --headless --seed 42 2>&1 | tail -10
```

Expected: completes successfully, captures trials. (Don't worry about specific trial count; this is a smoke.)

- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/core/executor.py
git commit -m "$(cat <<'EOF'
refactor(sp16): TaskExecutor.run browser lifecycle via PilotSession

Replaces local async_playwright()/browser/context/page creation in
TaskExecutor.run with `async with PilotSession(...) as session:`. Same
entry navigation, same calibration pass, same trial loop — pure
lifecycle refactor. CDP setup uses session.context. Adaptive nav comes
in a later task.

Smoke: expfactory_stroop dev paradigm session completes under SP16
PilotSession-backed executor without regression.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Entry nav via `session.try_phase` + skip-on-fail

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (replace the single `_navigator.execute_all(page, config.navigation)` at session start with per-phase loop)

**Why:** Currently the navigator raises on missing-click-target timeouts (1.5s). For paradigms with slightly-stale TaskCard nav phases, this crashes session start. Replacing with `session.try_phase` (skip-on-fail) matches the walker's behavior and lets sessions tolerate the kind of minor nav drift the held-out paradigm exhibits.

- [ ] **Step 1: Replace the `_navigator.execute_all` call**

In `TaskExecutor.run`, find:

```python
# Phase 1: Navigate instructions
logger.info("Navigating instructions...")
await self._navigator.execute_all(page, self._config.navigation)
```

Replace with:

```python
# Phase 1: Navigate instructions (per-phase with skip-on-fail)
logger.info("Navigating instructions...")
self._entry_nav_phase_results: list[dict] = []
for nav_phase in self._config.navigation.phases:
    attempt = await session.try_phase(nav_phase)
    self._entry_nav_phase_results.append({
        "phase": nav_phase.phase or "<unnamed>",
        "action": nav_phase.action,
        "target": nav_phase.target,
        "key": nav_phase.key,
        "success": attempt.success,
        "error": attempt.error,
    })
    if not attempt.success:
        logger.info(
            f"Entry nav phase '{nav_phase.phase or '<unnamed>'}' "
            f"skipped: {attempt.error}"
        )
```

NOTE: also keep the `_navigator.execute_all` import in place — it's still used by `_trial_loop`'s existing INSTRUCTIONS-phase handling for the in-trial nav re-run. That path is unchanged by SP16 (task 5 adds adaptive nav on top of it, not in place of it).

- [ ] **Step 2: Persist nav results into run_metadata**

In the `_writer.record_trace("navigate", ...)` call, attach the nav-phase results so post-hoc diagnostics show which entry phases succeeded:

Find the existing `record_trace` for "navigate" at the top of `run`:

```python
self._writer.record_trace(
    "navigate", {"url": task_url},
    duration_s=time.monotonic() - _t0,
)
```

Add a SECOND trace AFTER the entry nav loop:

```python
self._writer.record_trace(
    "entry_navigation",
    {"phases": self._entry_nav_phase_results},
    duration_s=time.monotonic() - _t1,  # define _t1 right before the for loop
)
```

Where `_t1` is captured immediately before the for loop:

```python
_t1 = time.monotonic()
for nav_phase in self._config.navigation.phases:
    ...
```

- [ ] **Step 3: Run smoke + commit**

```bash
uv run experiment-bot https://deploy.expfactory.org/preview/10/ \
    --label expfactory_stroop --headless --seed 42 2>&1 | tail -10
```

Expected: completes, trials captured. Verify the new run_dir has `entry_navigation` in `run_trace.json`.

```bash
git add src/experiment_bot/core/executor.py
git commit -m "$(cat <<'EOF'
feat(sp16): entry-nav via session.try_phase + skip-on-fail + run_trace

Entry navigation in TaskExecutor.run iterates per-phase via
session.try_phase (skip-on-failure) instead of navigator.execute_all
(raise-on-failure). Per-phase results recorded into run_trace.json
under "entry_navigation" so post-hoc diagnostics show which TaskCard
nav phases successfully executed at session start.

In-trial INSTRUCTIONS-phase handling in _trial_loop still uses
_navigator.execute_all unchanged (no SP16 behavior shift there yet;
adaptive nav fallback comes in Task 5).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: TaskExecutor accepts `llm_client` + CLI builds + opt-out flag

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (constructor)
- Modify: `src/experiment_bot/cli.py` (build LLMClient + pass + flag)

**Why:** Adaptive nav needs an LLMClient. Constructor accepts one (None disables adaptive nav — graceful degradation). CLI builds via existing factory; new `--no-llm-client` flag for determinism-required runs.

- [ ] **Step 1: Add `llm_client` kwarg to TaskExecutor.__init__**

In `src/experiment_bot/core/executor.py`, find `def __init__(...)` (line 63). Add a new kwarg at the end:

```python
def __init__(
    self,
    config: TaskConfig,
    *,
    headless: bool = False,
    seed: int | None = None,
    session_params: dict | None = None,
    llm_client: "LLMClient | None" = None,  # SP16: enables adaptive nav
) -> None:
    ...existing body...
    self._llm_client = llm_client
    self._adaptive_nav_uses = 0
    self._adaptive_nav_diffs: list[str] = []
    self._runtime_nav_phases: list[dict] = []
```

Add the import at the top:

```python
from experiment_bot.llm.protocol import LLMClient  # type-only ok if you prefer TYPE_CHECKING
```

- [ ] **Step 2: Update CLI**

In `src/experiment_bot/cli.py`:

Add an import:

```python
from experiment_bot.llm.factory import build_default_client
```

Add a new option to `main`:

```python
@click.option("--no-llm-client", is_flag=True, default=False,
              help="Disable adaptive nav (run deterministic). "
                   "By default the executor builds an LLM client for adaptive "
                   "nav fallback when the trial loop gets stuck.")
```

Update `main`'s signature + `_run_task` to thread it through:

```python
def main(url, label, headless, taskcards_dir, seed, verbose, no_llm_client):
    _setup_logging(verbose)
    asyncio.run(_run_task(url, label, headless, Path(taskcards_dir), seed, no_llm_client))


async def _run_task(url, label, headless, taskcards_dir, seed, no_llm_client):
    ...existing body...
    llm_client = None if no_llm_client else build_default_client()
    executor = TaskExecutor(
        taskcard, headless=headless,
        seed=seed, session_params=sampled,
        llm_client=llm_client,
    )
    await executor.run(url)
```

- [ ] **Step 3: Add tests**

Append to whichever test file covers TaskExecutor construction (likely `tests/test_executor.py` or `tests/test_integration.py`; create `tests/test_executor_adaptive_nav.py` if neither has appropriate fixtures):

```python
def test_taskexecutor_accepts_llm_client_kwarg(minimal_taskcard):
    """TaskExecutor.__init__ accepts an optional llm_client kwarg without
    breaking existing callers."""
    from experiment_bot.core.executor import TaskExecutor
    e1 = TaskExecutor(minimal_taskcard, headless=True, seed=42, session_params={})
    assert e1._llm_client is None  # default
    assert e1._adaptive_nav_uses == 0
    from unittest.mock import AsyncMock
    fake = AsyncMock()
    e2 = TaskExecutor(minimal_taskcard, headless=True, seed=42, session_params={}, llm_client=fake)
    assert e2._llm_client is fake
```

The `minimal_taskcard` fixture should be a TaskConfig with the minimum needed fields (use an existing fixture from `tests/fixtures/` or `tests/test_executor.py`).

- [ ] **Step 4: Smoke + commit**

```bash
uv run experiment-bot https://deploy.expfactory.org/preview/10/ \
    --label expfactory_stroop --headless --seed 42 --no-llm-client 2>&1 | tail -5
```

Expected: completes normally (no adaptive nav fires because flag disables it).

```bash
git add src/experiment_bot/core/executor.py src/experiment_bot/cli.py tests/
git commit -m "$(cat <<'EOF'
feat(sp16): TaskExecutor accepts llm_client + CLI builds + --no-llm-client flag

TaskExecutor.__init__ gains llm_client: LLMClient | None = None kwarg.
None disables adaptive nav (graceful degradation). CLI builds an LLM
client via build_default_client() by default; --no-llm-client opt-out
for deterministic / no-LLM runs.

Adaptive nav state initialized (_adaptive_nav_uses, _adaptive_nav_diffs,
_runtime_nav_phases) but not yet wired into the trial loop — that's Task 5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `_adaptive_nav_step` + trial loop integration

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (new helper + integration in `_trial_loop`)
- Create: `tests/test_executor_adaptive_nav.py` (4 tests)

**Why:** The core SP16 behavioral change. When `consecutive_misses >= 20` in `_trial_loop` AND the executor has an LLM client AND adaptive budget remains, fire one adaptive nav step: ask LLM for one phase → try_phase → continue.

- [ ] **Step 1: Add module-level constants in executor.py**

Near the top of `executor.py`:

```python
_ADAPTIVE_NAV_STUCK_POLLS = 20
_ADAPTIVE_NAV_BUDGET = 10
```

- [ ] **Step 2: Add `_adaptive_nav_step` helper to TaskExecutor**

Place after `_handle_feedback` (around line 1107). The session arg is passed from `_trial_loop`:

```python
async def _adaptive_nav_step(self, session, page) -> bool:
    """LLM-driven one-step adaptive nav. Returns True if the bot's DOM
    advanced after the proposed phase executed. Logs the attempt into
    bot_log with type 'adaptive_nav' for full auditability.

    The LLM call is bounded by self._adaptive_nav_uses < _ADAPTIVE_NAV_BUDGET;
    the caller is responsible for checking that gate before invoking.
    """
    import hashlib
    import time
    from experiment_bot.core.config import NavigationPhase
    from experiment_bot.reasoner.stage6_pilot import _propose_next_phase

    dom_before = await session.dom_snapshot()
    fp_before = hashlib.sha256(dom_before.encode()).hexdigest()[:16] if dom_before else ""

    try:
        phase_dict = await _propose_next_phase(
            self._llm_client, dom_before,
            self._runtime_nav_phases, self._adaptive_nav_diffs,
        )
    except Exception as e:
        logger.warning("Adaptive nav: LLM proposal failed: %s", e)
        self._adaptive_nav_uses += 1
        return False

    phase_dict.setdefault("steps", [])
    phase_dict.setdefault("key", "")
    phase_dict.setdefault("target", "")
    phase_dict.setdefault("duration_ms", 0)
    phase_dict.setdefault("phase", f"adaptive_{self._adaptive_nav_uses + 1}")
    new_phase = NavigationPhase.from_dict(phase_dict)

    attempt = await session.try_phase(new_phase)
    self._adaptive_nav_uses += 1

    dom_after = await session.dom_snapshot()
    fp_after = hashlib.sha256(dom_after.encode()).hexdigest()[:16] if dom_after else ""
    advanced = bool(fp_before and fp_after and fp_before != fp_after)

    self._runtime_nav_phases.append(phase_dict)
    self._adaptive_nav_diffs.append(
        f"Adaptive {self._adaptive_nav_uses}: "
        f"{phase_dict} (success={attempt.success}, advanced={advanced})"
    )

    # Bot_log audit entry
    self._bot_log.append({
        "type": "adaptive_nav",
        "step": self._adaptive_nav_uses,
        "session_t": time.monotonic() - self._session_start,
        "phase": phase_dict,
        "success": attempt.success,
        "advanced": advanced,
        "error": attempt.error,
        "dom_fingerprint_before": fp_before,
        "dom_fingerprint_after": fp_after,
    })

    logger.info(
        f"Adaptive nav step {self._adaptive_nav_uses}: "
        f"action={phase_dict.get('action')} success={attempt.success} advanced={advanced}"
    )
    return advanced
```

- [ ] **Step 3: Integrate into `_trial_loop`**

In `_trial_loop`, find the "no stimulus match" branch (where `consecutive_misses` is incremented). Currently this branch increments `consecutive_misses` and presses advance keys. Add the adaptive nav fallback BEFORE the existing advance-key press:

Locate the block around line 657-680 (the "match is None" branch). Add at the top of that branch, RIGHT AFTER `consecutive_misses += 1`:

```python
if (
    consecutive_misses >= _ADAPTIVE_NAV_STUCK_POLLS
    and self._llm_client is not None
    and self._adaptive_nav_uses < _ADAPTIVE_NAV_BUDGET
    and consecutive_misses % _ADAPTIVE_NAV_STUCK_POLLS == 0  # fire at 20, 40, 60, ... not every poll
):
    advanced = await self._adaptive_nav_step(session, page)
    if advanced:
        consecutive_misses = 0
        continue
```

NOTE: `session` is needed in `_trial_loop`. Currently `_trial_loop(self, page)` takes only `page`. Update the signature to `_trial_loop(self, session, page)` and update the call site in `run`:

```python
await self._trial_loop(session, page)
```

- [ ] **Step 4: Pass `session` through `_trial_loop`**

Update `_trial_loop` signature:

```python
async def _trial_loop(self, session, page: Page) -> None:
```

Update the call site in `run`:

```python
await self._trial_loop(session, page)
```

- [ ] **Step 5: Write 4 tests**

Create `tests/test_executor_adaptive_nav.py`:

```python
"""Tests for SP16 adaptive nav step in TaskExecutor's trial loop."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.core.executor import (
    TaskExecutor, _ADAPTIVE_NAV_BUDGET, _ADAPTIVE_NAV_STUCK_POLLS,
)
from experiment_bot.llm.protocol import LLMResponse


# Helper to construct a minimal-but-valid TaskExecutor. Use an existing
# fixture (from tests/test_executor.py or tests/fixtures/) if available.
# Implementer: reuse existing _make_executor() pattern from the test suite.


@pytest.mark.asyncio
async def test_adaptive_nav_step_advances_dom(make_executor):
    """When LLM proposes a valid phase and DOM changes, _adaptive_nav_step
    returns True and logs to bot_log."""
    executor = make_executor(with_llm_client=True)
    executor._llm_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "next", "action": "click", "target": "#next",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    session_mock = AsyncMock()
    session_mock.dom_snapshot = AsyncMock(side_effect=["<div>before</div>", "<div>after</div>"])
    session_mock.try_phase = AsyncMock(return_value=MagicMock(success=True, error=None, dom_after=""))

    advanced = await executor._adaptive_nav_step(session_mock, MagicMock())
    assert advanced is True
    assert executor._adaptive_nav_uses == 1
    log_entries = [e for e in executor._bot_log if e.get("type") == "adaptive_nav"]
    assert len(log_entries) == 1
    assert log_entries[0]["advanced"] is True
    assert log_entries[0]["success"] is True


@pytest.mark.asyncio
async def test_adaptive_nav_step_no_advance_on_same_dom(make_executor):
    """When DOM doesn't change after try_phase, advanced=False."""
    executor = make_executor(with_llm_client=True)
    executor._llm_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "x", "action": "keypress", "target": "", "key": " ",
        "duration_ms": 0, "steps": []
    }"""))
    session_mock = AsyncMock()
    session_mock.dom_snapshot = AsyncMock(return_value="<div>same</div>")
    session_mock.try_phase = AsyncMock(return_value=MagicMock(success=True, error=None, dom_after=""))

    advanced = await executor._adaptive_nav_step(session_mock, MagicMock())
    assert advanced is False
    assert executor._adaptive_nav_uses == 1
    # Still logged
    assert len([e for e in executor._bot_log if e.get("type") == "adaptive_nav"]) == 1


@pytest.mark.asyncio
async def test_adaptive_nav_step_llm_failure_counted_against_budget(make_executor):
    """If the LLM proposal raises, the step counts against the budget (no infinite
    loop), and the function returns False."""
    executor = make_executor(with_llm_client=True)
    with patch(
        "experiment_bot.reasoner.stage6_pilot._propose_next_phase",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        session_mock = AsyncMock()
        session_mock.dom_snapshot = AsyncMock(return_value="<div>x</div>")
        result = await executor._adaptive_nav_step(session_mock, MagicMock())
    assert result is False
    assert executor._adaptive_nav_uses == 1


@pytest.mark.asyncio
async def test_taskexecutor_constants_match_spec():
    """SP16 budget constants match the spec values."""
    assert _ADAPTIVE_NAV_STUCK_POLLS == 20
    assert _ADAPTIVE_NAV_BUDGET == 10
```

The `make_executor` fixture should be in `tests/conftest.py` (or in the test file directly). Use the simplest possible TaskConfig + sampled session_params dict; the test only exercises `_adaptive_nav_step`, not `run`. Mock LLMClient via AsyncMock.

- [ ] **Step 6: Run all relevant tests**

```bash
uv run pytest tests/test_executor_adaptive_nav.py tests/test_pilot_session.py tests/test_executor.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_adaptive_nav.py
git commit -m "$(cat <<'EOF'
feat(sp16): _adaptive_nav_step in TaskExecutor trial loop

When consecutive_misses >= _ADAPTIVE_NAV_STUCK_POLLS (20) AND the executor
has an LLMClient AND budget remains (< _ADAPTIVE_NAV_BUDGET=10), the
trial loop fires _adaptive_nav_step: ask LLM for one nav phase → try_phase
against the live session → continue if DOM advanced.

The helper logs a "type": "adaptive_nav" entry to bot_log with
{step, session_t, phase, success, advanced, error, fingerprints} for
full auditability. _trial_loop signature gains `session` so the helper
can call session.try_phase and session.dom_snapshot directly.

+4 unit tests covering: DOM-advance returns True, no-DOM-change returns
False, LLM failure consumes budget without crash, constants match spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `run_metadata.adaptive_nav` summary

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (`run` finalization)

**Why:** Per-session summary of adaptive nav usage. Aggregated into `run_metadata.json` so analysis scripts can surface counts without iterating bot_log entries.

- [ ] **Step 1: Compute summary at run end**

In `TaskExecutor.run`, find the `run_metadata.json` writing step (look for where `total_trials`, `headless`, `session_seed` etc. are written, likely via `self._writer.finalize` or `self._writer.write_run_metadata`). Add an `adaptive_nav` block to the metadata:

```python
# Compute adaptive_nav summary
adaptive_entries = [e for e in self._bot_log if e.get("type") == "adaptive_nav"]
adaptive_summary = {
    "uses": self._adaptive_nav_uses,
    "budget": _ADAPTIVE_NAV_BUDGET,
    "successful_proposals": sum(1 for e in adaptive_entries if e.get("success")),
    "dom_advances": sum(1 for e in adaptive_entries if e.get("advanced")),
    "llm_disabled": self._llm_client is None,
}
```

Add this dict to the run_metadata payload. The writer's API is likely something like:

```python
self._writer.write_run_metadata(
    task_name=task_name,
    task_url=task_url,
    total_trials=self._trial_count,
    headless=self._headless,
    session_seed=self._seed,
    session_params=self._session_params,
    taskcard_sha256=...,
    delivery=...,
    calibration=...,
    adaptive_nav=adaptive_summary,  # NEW
)
```

Implementer: locate the exact call in `executor.py` and add the new field. If `write_run_metadata` doesn't accept arbitrary kwargs, either extend its signature or write the metadata via the lower-level path.

- [ ] **Step 2: Add a test for run_metadata payload**

Append to `tests/test_executor_adaptive_nav.py`:

```python
@pytest.mark.asyncio
async def test_run_metadata_has_adaptive_nav_summary(make_executor):
    """run_metadata.json's adaptive_nav block summarizes per-session
    adaptive nav usage."""
    executor = make_executor(with_llm_client=False)  # llm_disabled=True
    # Simulate _bot_log having a couple adaptive_nav entries
    executor._bot_log = [
        {"type": "adaptive_nav", "success": True, "advanced": True},
        {"type": "adaptive_nav", "success": True, "advanced": False},
        {"type": "trial", "trial_index": 1},
    ]
    executor._adaptive_nav_uses = 2
    summary = executor._compute_adaptive_nav_summary()  # helper for testing
    assert summary["uses"] == 2
    assert summary["successful_proposals"] == 2
    assert summary["dom_advances"] == 1
    assert summary["llm_disabled"] is True
```

Implementer: extract the summary computation into a method `_compute_adaptive_nav_summary(self) -> dict` for testability, called from `run` finalization.

- [ ] **Step 3: Run + commit**

```bash
uv run pytest tests/test_executor_adaptive_nav.py tests/test_executor.py -v
git add src/experiment_bot/core/executor.py tests/test_executor_adaptive_nav.py
git commit -m "$(cat <<'EOF'
feat(sp16): run_metadata.adaptive_nav summary block

Per-session adaptive nav usage aggregated into run_metadata.json under
"adaptive_nav": {uses, budget, successful_proposals, dom_advances,
llm_disabled}. Analysis scripts can surface counts without iterating
bot_log entries. +1 unit test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Dev-4 regression smoke (1 session per paradigm)

**Files:** None modified; produces session outputs.

- [ ] **Step 1: Run each paradigm × 1 session**

```bash
declare -a labels_urls=(
  "expfactory_stroop:https://deploy.expfactory.org/preview/10/"
  "expfactory_stop_signal:https://deploy.expfactory.org/preview/9/"
  "stopit_stop_signal:https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html"
  "cognitionrun_stroop:https://strooptest.cognition.run/"
)
for lu in "${labels_urls[@]}"; do
  label="${lu%%:*}"; url="${lu#*:}"
  echo "=== $label ==="
  uv run experiment-bot "$url" --label "$label" --headless --seed 1 \
      > "/tmp/sp16-smoke-${label}.log" 2>&1
  rc=$?
  [[ $rc -eq 0 ]] && echo "$label: PASS" || echo "$label: FAIL"
done
```

Note: `--no-llm-client` is NOT passed — adaptive nav is available but should NOT fire (TaskCard nav for these is sufficient).

- [ ] **Step 2: Assert adaptive_nav_uses == 0 for each**

```bash
for label in expfactory_stroop expfactory_stop_signal stopit_stop_signal cognitionrun_stroop; do
  sd=$(ls -dt output/${label}/*/ | head -1)
  python3 -c "
import json
m = json.load(open('${sd}/run_metadata.json'))
an = m.get('adaptive_nav', {})
print(f'${label}: trials={m[\"total_trials\"]}, adaptive_nav.uses={an.get(\"uses\", \"missing\")}')
"
done
```

Expected output for each: `adaptive_nav.uses=0`, `trials > 0` for each.

If ANY paradigm shows `uses > 0`, that's a regression worth investigating before continuing. Most likely cause: a between-block feedback screen tripping the 20-poll threshold.

- [ ] **Step 3: Commit any new TaskCard timestamp artifacts (if any) + dev-4 smoke summary**

```bash
# Smoke does NOT modify TaskCards (uses existing) — just check git status for the
# committed run_dir artifacts. If output/ is gitignored (it is per .gitignore),
# nothing to commit. Move on.
git status --short
```

---

## Task 8: Held-out × 5 sessions

**Files:** None modified; produces session outputs in `output/stop_signal_with_integrated_memory/`.

The actual SP16 deliverable.

- [ ] **Step 1: Run 5 sessions**

```bash
for i in 1 2 3 4 5; do
    seed=$((SP16 + i * 1000))
    echo "=== Session $i (seed=$seed) ==="
    uv run experiment-bot https://deploy.expfactory.org/preview/80/ \
        --label stop_signal_with_integrated_memory \
        --headless --seed "$seed" \
        > "/tmp/sp16-heldout-session-${i}.log" 2>&1
    rc=$?
    [[ $rc -eq 0 ]] && echo "Session $i: PASS" || echo "Session $i: FAIL"
done
```

Each session is expected to take ~20-30 min (including calibration + practice + test blocks + adaptive nav steps).

- [ ] **Step 2: Inspect per-session outcomes**

```bash
for sd in $(ls -dt output/stop_signal_with_integrated_memory/* | head -5); do
    python3 -c "
import json
m = json.load(open('$sd/run_metadata.json'))
bot = json.load(open('$sd/bot_log.json'))
trials = [e for e in bot if e.get('type') == 'trial']
adaptives = [e for e in bot if e.get('type') == 'adaptive_nav']
print(f'$sd: trials={len(trials)}, adaptive_nav={len(adaptives)} ({m.get(\"adaptive_nav\", {})})')
"
done
```

- [ ] **Step 3: Commit session outputs (gitignored — verify)**

`output/` is gitignored. Sessions don't get committed. Move on to Task 9.

---

## Task 9: `docs/sp16-heldout-behavior.md`

**Files:** Create `docs/sp16-heldout-behavior.md`.

**Why:** The behavioral analysis. Per-session and aggregate metrics; comparison to published stop-signal + working-memory norms; honest framing.

- [ ] **Step 1: Compute aggregate metrics**

Use the existing `scripts/analyze_sessions.py` pattern (adapter for the held-out paradigm may be needed; see Task 9b below):

```bash
uv run scripts/analyze_sessions.py \
    --label stop_signal_with_integrated_memory \
    --output /tmp/sp16-heldout-behavior.json
```

Computed metrics (target):
- Go mean RT ± SD per session
- Stop-failure mean RT
- Go accuracy
- Stop inhibition rate (P(inhibit | stop))
- SSRT (integration method)
- Mean SSD (staircase)

If `scripts/analyze_sessions.py` doesn't have an adapter for this paradigm's CSV/JSON shape, add one to `validation/platform_adapters.py` (small additive change). The held-out paradigm is on expfactory deploy/preview/80; the data file shape should match expfactory_stop_signal.

- [ ] **Step 2: Write the report**

Create `docs/sp16-heldout-behavior.md` with structure:

```markdown
# SP16 held-out behavioral data: stop_signal_with_integrated_memory

## Aggregate

5 sessions × stop_signal_with_integrated_memory under SP16 TaskExecutor.

| Metric | Session-mean ± SD (range) | Published norm | Verdict |
|---|---|---|---|
| Go mean RT (ms) | ... | ... | ... |
| Stop-failure RT (ms) | ... | ... | ... |
| Go accuracy | ... | ... | ... |
| Stop inhibition rate | ... | ... | ... |
| SSRT (integration ms) | ... | [180, 280] | ... |
| Mean SSD (ms) | ... | — | n/a |

## Per-session

| Session | Seed | Trials | Adaptive nav uses | DOM advances |
|---|---|---|---|---|
| 1 | ... | ... | ... | ... |
...

## Adaptive nav patterns (across sessions)

Aggregate of `bot_log` adaptive_nav entries: most common proposed phases,
mean success rate, mean DOM-advance rate. Surfaces whether the LLM
converged on a consistent pattern across sessions or kept exploring.

## Comparison to published norms

[Per honest-framing memory: surface where the bot matches, where it
diverges, and what that suggests. SSRT in range = race-model-consistent
performance; SSRT out of range = bot is too fast/slow at the stop process.]

## What SP16 demonstrates

[Connects back to spec criteria 7-9.]

## What SP16 does NOT demonstrate

[Limitations / scope-of-validity honest statement.]
```

Fill in the actual numbers from Step 1.

- [ ] **Step 3: Commit**

```bash
git add docs/sp16-heldout-behavior.md validation/platform_adapters.py
git commit -m "$(cat <<'EOF'
docs(sp16): held-out behavioral data — stop_signal_with_integrated_memory × 5 sessions

5 sessions × calibrated RTs + SSRT under the SP16 TaskExecutor.
Adaptive nav fired N times per session on average; bot completed
practice + test blocks. Comparison to published stop-signal norms in
the doc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `docs/sp16-results.md`

Standard SP-results format. Sections:
- Internal CI numbers (test counts)
- Dev-4 regression: 4 paradigms passed, adaptive_nav_uses==0 per session
- Held-out: 5 sessions completed; see sp16-heldout-behavior.md
- Wall-time / cost notes (LLM calls per session)
- What SP16 demonstrates
- What SP16 does NOT do
- Stopping recommendation

Implementer fills in from actual run outcomes. Pattern: `docs/sp13-results.md`, `docs/sp15-results.md` are precedents.

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add docs/sp16-results.md
git commit -m "docs(sp16): results — dev-4 backward compat + held-out × 5 sessions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: `docs/pipeline-flow.md` updates

Add an Executor section update reflecting:
- Browser lifecycle via PilotSession
- Entry nav: per-phase skip-on-fail
- Trial loop's adaptive nav fallback (when + budget + audit)

```bash
# Implementer edits docs/pipeline-flow.md sections 2-4 (TaskExecutor).
git add docs/pipeline-flow.md
git commit -m "docs(sp16): pipeline-flow.md TaskExecutor architecture update

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: `CLAUDE.md` SP16 entry + tag

```bash
# Implementer appends SP16 entry to the sub-project history list in
# CLAUDE.md, similar to existing entries (SP13, SP14, SP15).
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(sp16): append SP16 to sub-project history in CLAUDE.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git tag sp16-complete
git push
git push --tags
```

---

## Self-Review

**1. Spec coverage:**
- PilotSession exposes context → Task 1 ✓
- Browser lifecycle migrates → Task 2 ✓
- Entry nav via try_phase → Task 3 ✓
- llm_client kwarg + CLI + flag → Task 4 ✓
- _adaptive_nav_step + trial loop integration → Task 5 ✓
- bot_log adaptive_nav + run_metadata summary → Tasks 5 + 6 ✓
- Dev-4 smoke → Task 7 ✓
- Held-out × 5 → Tasks 8 + 9 ✓
- Docs → Tasks 10, 11, 12 ✓

**2. Placeholder scan:** Task 8's seed expression uses `$((SP16 + i * 1000))`; that's a deliberate sentinel that the implementer should replace with an actual integer base (e.g., `$((16000 + i * 1000))`). Otherwise `$SP16` is undefined and evaluates to 0 — still valid but the seeds collide with other potential runs. Implementer fixes inline.

**3. Type consistency:**
- `llm_client: LLMClient | None` everywhere (constructor, CLI build, helper checks).
- `_adaptive_nav_uses: int` initialized to 0.
- `_adaptive_nav_diffs: list[str]`, `_runtime_nav_phases: list[dict]`.
- `bot_log` entries: existing `{"type": "trial", ...}` + new `{"type": "adaptive_nav", ...}`.
- `_trial_loop` signature change: `(self, page)` → `(self, session, page)`.

**4. Backward compat:**
- `TaskExecutor.__init__`: new `llm_client` kwarg defaults to `None` — existing tests + callers unchanged.
- `PilotSession`: new `context` property is additive, doesn't change existing tests.
- Dev-4 paradigms run through the same code path; adaptive nav has a gate (`consecutive_misses >= 20` + budget + non-None client); should not fire for them. Task 7 verifies.

Plan ready.

---

## Execution Handoff

Plan complete. Per `feedback_skip_code_quality_reviewer`: subagent-driven-development with spec-compliance reviewer per task; skip code-quality reviewer.

**Suggested execution order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 (dev-4 smoke; halt if regression) → 8 (held-out × 5; ~2 hours wall time) → 9 → 10 → 11 → 12.

If Task 7 shows ANY dev-4 regression, halt and investigate before continuing to held-out sessions.

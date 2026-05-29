# Navigation Redesign (Conservative Unification) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Spec-compliance reviewer per task; SKIP code-quality reviewer (per `feedback_skip_code_quality_reviewer`). Tasks are SEQUENTIAL (heavy `executor.py` + `stage6_pilot.py` contention) — one implementer at a time, each commits before the next. Steps use `- [ ]` tracking.

**Goal:** Make navigation reliable and replayable by unifying on one nav engine, making the Stage-6 walker produce executor-replayable TaskCards by construction, gating Stage-6 PASS on an executor-shaped replay, and deleting the memorized `platform_defaults` — without making adaptive nav eager/primary (preserves reproducibility).

**Architecture:** One engine (`PilotSession.try_phase`) drives both entry-nav and the in-trial INSTRUCTIONS re-run; `InstructionNavigator` is deleted. The walker classifies each proposed phase as a nav-advance vs a trial-response (probing the live stimulus before/after) and appends only true nav advances. A fresh-browser replay gate at the end of Stage 6 fails the pilot unless the finalized nav reaches trial rendering. `platform_defaults` is removed; Stage 1 + the (now-trustworthy) walker discover all nav.

**Tech Stack:** Python 3.12, async Playwright, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-28-navigation-redesign-design.md`.

**Guardrails:** keep SP16 adaptive nav as the stuck-DOM-gated recovery (do NOT make it eager — proven regressive). Preserve per-session reproducibility. Do not touch the behavioral/scientific core.

---

## File Structure

| File | Action | Responsibility after this plan |
|---|---|---|
| `src/experiment_bot/core/pilot_session.py` | Modify | The ONE nav engine: `try_phase` gains `repeat` + `pre_js`-on-press + loud unknown-action |
| `src/experiment_bot/core/executor.py` | Modify | In-trial INSTRUCTIONS re-run routes through `session.try_phase`; `InstructionNavigator` construction removed |
| `src/experiment_bot/navigation/navigator.py` | Delete | (engine unified into PilotSession) |
| `src/experiment_bot/reasoner/stage6_pilot.py` | Modify | Walker classifies advance-vs-trial-response (C2); replay gate at end (C3) |
| `src/experiment_bot/reasoner/nav_classify.py` | Create | Pure `classify_phase_outcome` helper (C2) |
| `src/experiment_bot/reasoner/platform_defaults.py` | Delete | (C4) |
| `src/experiment_bot/reasoner/stage1_structural.py` | Modify | Remove `apply_platform_defaults` import + call (C4) |
| `tests/test_pilot_session.py` | Modify | `repeat` + unknown-action tests |
| `tests/test_navigator.py` | Delete/retarget | navigator gone; move any still-relevant assertions to test_pilot_session |
| `tests/test_nav_classify.py` | Create | classifier unit tests |
| `tests/test_reasoner_stage6.py` | Modify | walker-classify + replay-gate tests |
| `tests/test_platform_defaults.py` | Delete | (C4) |
| `docs/scope-of-validity.md` | Modify | drop platform-default fast-path claim (C4) |

---

## Task 1: Unify the nav engine — `PilotSession.try_phase` gains `repeat`, `pre_js`-on-press, loud unknown-action

**Files:**
- Modify: `src/experiment_bot/core/pilot_session.py` (`try_phase`, ~108-148)
- Test: `tests/test_pilot_session.py`

**Why:** `PilotSession.try_phase` is the entry-nav engine but lacks `repeat` (silently dropped) and `pre_js`-on-press, which `InstructionNavigator` has — so the two engines diverge (arch-005/platform-003/robust-006). Make `try_phase` a strict superset so it can be the single engine.

- [ ] **Step 1: Write failing tests** in `tests/test_pilot_session.py` (reuse the local-HTML-fixture harness already in that file):

```python
@pytest.mark.asyncio
async def test_try_phase_repeat_runs_steps_until_substep_fails(fixture_url):
    """`repeat` runs its steps repeatedly, stopping when a sub-step fails
    (mirrors InstructionNavigator semantics, max 20 iterations)."""
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        # fixture has a button that exists once; a repeat of click+wait should
        # click it then fail on the second iteration (button gone) and stop.
        phase = NavigationPhase.from_dict({
            "action": "repeat", "phase": "advance_all", "target": "", "key": "",
            "duration_ms": 0,
            "steps": [
                {"action": "click", "target": "#one-shot-btn", "key": "", "duration_ms": 0, "steps": []},
                {"action": "wait", "target": "", "key": "", "duration_ms": 10, "steps": []},
            ],
        })
        result = await s.try_phase(phase)
        assert result.success is True  # repeat itself never raises; it stops on sub-fail


@pytest.mark.asyncio
async def test_try_phase_unknown_action_records_to_run_trace(fixture_url):
    """An unsupported action is a loud WARNING + recorded, not a silent info log."""
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "action": "teleport", "phase": "x", "target": "", "key": "",
            "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is False
        assert "unknown action" in (result.error or "").lower()
```

The `fixture_url` HTML must include `<button id="one-shot-btn" onclick="this.remove()">x</button>` so the repeat clicks once then the target disappears. Add it to the existing `FIXTURE_HTML` constant.

Run: `uv run pytest tests/test_pilot_session.py::test_try_phase_repeat_runs_steps_until_substep_fails tests/test_pilot_session.py::test_try_phase_unknown_action_records_to_run_trace -v` → expect FAIL.

- [ ] **Step 2: Implement in `try_phase`.** Add a `repeat` branch and a `pre_js`-on-press, and make the unknown-action branch return `success=False` with an error. Replace the existing dispatch body:

```python
            if phase.action == "click":
                await self._inject_reading_delay()
                loc = self.page.locator(phase.target).first
                await loc.wait_for(state="visible", timeout=1500)
                await loc.click()
            elif phase.action in ("press", "keypress"):
                await self._inject_reading_delay()
                if getattr(phase, "pre_js", ""):
                    try:
                        await self.page.evaluate(phase.pre_js)
                    except PlaywrightError:
                        pass  # page context may be torn down by prior nav
                await self.page.keyboard.press(phase.key)
            elif phase.action == "wait":
                await asyncio.sleep(phase.duration_ms / 1000.0)
            elif phase.action == "sequence":
                for step in phase.steps:
                    sub = NavigationPhase.from_dict(step)
                    sub_result = await self.try_phase(sub)
                    if not sub_result.success:
                        return PhaseAttempt(
                            success=False, dom_after=await self.dom_snapshot(),
                            error=f"sequence step failed: {sub_result.error}",
                        )
            elif phase.action == "repeat":
                max_iterations = 20
                for _ in range(max_iterations):
                    stop = False
                    for step in phase.steps:
                        sub = NavigationPhase.from_dict(step)
                        sub_result = await self.try_phase(sub)
                        if not sub_result.success:
                            stop = True  # a sub-step failed → stop repeating
                            break
                    if stop:
                        break
            else:
                logger.warning("Unsupported navigation action %r (recorded)", phase.action)
                return PhaseAttempt(
                    success=False, dom_after=await self.dom_snapshot(),
                    error=f"unknown action: {phase.action}",
                )
```

Note: `repeat` itself returns `success=True` (it ran to its natural stop); only a genuinely unknown action returns `success=False`. Confirm `NavigationPhase` has a `pre_js` field (check `core/config.py`); if not, use `getattr(phase, "pre_js", "")` as shown (safe either way).

- [ ] **Step 3:** Run `uv run pytest tests/test_pilot_session.py -v` → all pass.
- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/core/pilot_session.py tests/test_pilot_session.py
git commit -m "$(cat <<'EOF'
feat(nav): PilotSession.try_phase becomes the superset engine (repeat, pre_js, loud unknown)

try_phase now supports `repeat` (mirroring InstructionNavigator: run steps up to
20× until a sub-step fails) and `pre_js` on press, and returns success=False with
a recorded error for unsupported actions instead of a silent info log. This makes
try_phase a strict superset of InstructionNavigator so it can be the single nav
engine. Spec C1a; audit arch-005/platform-003/robust-006.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Route the in-trial re-run through the unified engine; delete `InstructionNavigator`

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (the in-trial INSTRUCTIONS re-run; `__init__` navigator construction)
- Delete: `src/experiment_bot/navigation/navigator.py`
- Modify/Delete: `tests/test_navigator.py`
- Test: `tests/test_executor_completeness.py` (or the executor test file)

**Why:** After Task 1, `InstructionNavigator` is redundant. The executor's in-trial INSTRUCTIONS re-run (`self._navigator.execute_all(page, config.navigation)`, wrapped in try/except from the defensibility sweep) is its only live caller; entry-nav already uses `session.try_phase`. Unify so a TaskCard's nav semantics are identical at entry and re-run (arch-005/robust-006).

- [ ] **Step 1: Grep all callers** to confirm scope: `grep -rn "InstructionNavigator\|_navigator\|execute_all" src/ tests/`. The expected live caller is the executor in-trial re-run + `self._navigator` in `__init__`. If `pilot.py` or anything else references it, include those in this task. Record findings before editing.

- [ ] **Step 2: Write the failing test** in `tests/test_executor_completeness.py`: a TaskCard whose `navigation.phases` contains a `repeat` phase behaves identically when run at entry vs the in-trial re-run (both via `session.try_phase`). Concretely, assert the executor no longer constructs an `InstructionNavigator` and the in-trial re-run path calls `session.try_phase`:

```python
def test_executor_has_no_instruction_navigator(minimal_taskcard):
    """After unification, the executor does not construct InstructionNavigator;
    nav runs through the PilotSession engine only."""
    from experiment_bot.core import executor as ex_mod
    assert not hasattr(ex_mod, "InstructionNavigator"), \
        "InstructionNavigator import should be gone from executor"
    e = TaskExecutor(minimal_taskcard, headless=True, seed=1, session_params={})
    assert not hasattr(e, "_navigator"), "executor should not hold an InstructionNavigator"
```

Run → expect FAIL (executor still imports/holds it).

- [ ] **Step 3: Edit `executor.py`.**
  - Remove `from experiment_bot.navigation.navigator import InstructionNavigator` and `self._navigator = InstructionNavigator()` in `__init__`.
  - Replace the in-trial INSTRUCTIONS re-run. Find the block (added/modified in the defensibility sweep) that currently does:
    ```python
    try:
        await self._navigator.execute_all(page, self._config.navigation)
    except Exception as _nav_err:
        logger.info("Nav re-run raised mid-sequence (...): %s", _nav_err)
    ```
    Replace with a per-phase loop through the unified engine (skip-on-fail, mirroring entry nav):
    ```python
    for _nav_phase in self._config.navigation.phases:
        _attempt = await session.try_phase(_nav_phase)
        if not _attempt.success:
            logger.info(
                "In-trial nav re-run phase %r skipped: %s",
                _nav_phase.phase or "<unnamed>", _attempt.error,
            )
    ```
  (The DOM-fingerprint stuck-detection + adaptive-nav gate that follow this block in the INSTRUCTIONS branch stay unchanged.)

- [ ] **Step 4: Delete `src/experiment_bot/navigation/navigator.py`.** If `tests/test_navigator.py` only tests the deleted class, delete it too; if it asserts `repeat` semantics worth keeping, move those assertions to `tests/test_pilot_session.py` (Task 1 already covers `repeat`, so deletion is the likely outcome). Check `src/experiment_bot/navigation/__init__.py` for an `InstructionNavigator` export and remove it.

- [ ] **Step 5:** Run `uv run pytest -x -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(nav): one engine — in-trial re-run uses session.try_phase; delete InstructionNavigator

The executor's in-trial INSTRUCTIONS re-run now iterates phases through the
unified PilotSession engine (skip-on-fail), identical to entry nav, so a
TaskCard's nav semantics no longer depend on code path. InstructionNavigator
(and its test) are deleted now that try_phase is a superset. Spec C1b; audit
arch-005/robust-006.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Walker classifies advance vs trial-response (the core fix)

**Files:**
- Create: `src/experiment_bot/reasoner/nav_classify.py`
- Create: `tests/test_nav_classify.py`
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py` (nav-refinement branch, ~659-696)
- Test: `tests/test_reasoner_stage6.py`

**Why:** The walker appends ANY successful `try_phase` to `accumulated_phases` (stage6_pilot.py:672-678), so demo-trial response keypresses become "nav," producing executor-unreplayable cards (genbottle-001). Classify each proposed phase by probing the live trial stimulus before/after; append only true nav advances.

- [ ] **Step 1: Create the pure classifier + failing tests.** `tests/test_nav_classify.py`:

```python
from experiment_bot.reasoner.nav_classify import classify_phase_outcome


def _phase(action, key=""):
    return {"action": action, "key": key, "target": "", "duration_ms": 0, "steps": []}


def test_trial_response_when_stimulus_present_then_consumed():
    # A trial stimulus was on screen before; after a keypress it's gone → trial response.
    assert classify_phase_outcome(
        before_match=object(), after_match=None,
        phase=_phase("keypress", key="f"), response_keys={"f", "j"},
    ) == "trial_response"


def test_trial_response_when_keypress_matches_response_key_during_stimulus():
    # Stimulus present and the pressed key is a known response key → trial response,
    # even if a (different) stimulus is still present after.
    assert classify_phase_outcome(
        before_match=object(), after_match=object(),
        phase=_phase("keypress", key="j"), response_keys={"f", "j"},
    ) == "trial_response"


def test_nav_advance_when_no_stimulus_before():
    # No trial stimulus before the action → it advanced an interstitial → nav advance.
    assert classify_phase_outcome(
        before_match=None, after_match=None,
        phase=_phase("click"), response_keys={"f", "j"},
    ) == "nav_advance"


def test_nav_advance_when_ambiguous():
    # Stimulus present before AND after, action is NOT a response key (e.g. a click
    # or a non-response keypress) → ambiguous → bias to nav_advance (C3 backstops).
    assert classify_phase_outcome(
        before_match=object(), after_match=object(),
        phase=_phase("click"), response_keys={"f", "j"},
    ) == "nav_advance"
```

Run → expect ImportError/FAIL.

- [ ] **Step 2: Implement `src/experiment_bot/reasoner/nav_classify.py`:**

```python
"""Classify a walker-proposed navigation phase as a genuine nav advance vs a
trial response, so the Stage-6 walker never bakes demo-trial keypresses into
navigation.phases (which would make the TaskCard unreplayable by the executor).

Pure + browser-free: takes the stimulus-probe matches before/after the action.
"""
from __future__ import annotations


def classify_phase_outcome(before_match, after_match, phase: dict, response_keys: set[str]) -> str:
    """Return "trial_response" or "nav_advance".

    A configured (trial) stimulus is identified by `before_match`/`after_match`
    being non-None (the walker's StimulusLookup matched a configured stimulus).

    Rules (require a positive trial signal to call something a trial response;
    bias to nav_advance when ambiguous — the Stage-6 replay gate is the backstop):
      - Trial stimulus present before AND the action is a keypress whose key is a
        known response key  -> trial_response.
      - Trial stimulus present before AND gone/changed after a keypress
        -> trial_response.
      - Otherwise -> nav_advance.
    """
    action = phase.get("action", "")
    key = phase.get("key", "")
    is_keypress = action in ("press", "keypress")
    stim_before = before_match is not None

    if stim_before and is_keypress and key in response_keys:
        return "trial_response"
    if stim_before and is_keypress and after_match is None:
        return "trial_response"
    return "nav_advance"
```

- [ ] **Step 3:** Run `uv run pytest tests/test_nav_classify.py -v` → all pass.

- [ ] **Step 4: Wire into the walker.** In `stage6_pilot.py` nav-refinement branch (~659-696), before the `if attempt_result.success: accumulated_phases.append(...)`, probe before/after and classify. Read the current block first; transform it to:

```python
                    # Probe the live trial stimulus before/after so we can tell a
                    # genuine nav advance from a demo-trial RESPONSE (which must NOT
                    # be baked into navigation.phases — that produces executor-
                    # unreplayable cards). Spec C2 / audit genbottle-001.
                    before_probe = await session.probe_stimulus(lookup)
                    new_phase = _NavPhase.from_dict(new_phase_dict)
                    attempt_result = await session.try_phase(new_phase)
                    after_probe = await session.probe_stimulus(lookup)
                    response_keys = set((partial.get("task_specific", {}).get("key_map", {}) or {}).values())
                    from experiment_bot.reasoner.nav_classify import classify_phase_outcome
                    outcome = classify_phase_outcome(
                        before_match=before_probe.match, after_match=after_probe.match,
                        phase=new_phase_dict, response_keys=response_keys,
                    )
                    if attempt_result.success and outcome == "nav_advance":
                        accumulated_phases.append(new_phase_dict)
                        partial.setdefault('navigation', {})['phases'] = accumulated_phases
                        nav_refinement_count += 1
                        prior_diffs.append(f"Nav phase {nav_refinement_count}: {new_phase_dict}")
                        if save_partial is not None:
                            save_partial(partial)
                    elif attempt_result.success and outcome == "trial_response":
                        # Executed a demo-trial response, not a nav advance: do NOT
                        # append to navigation.phases. The action still advanced the
                        # pilot through a practice trial; the loop continues.
                        prior_diffs.append(f"(trial-response, not nav) {new_phase_dict}")
                    else:
                        prior_diffs.append(
                            f"(failed) Nav phase: {new_phase_dict}; error={attempt_result.error}"
                        )
```

Keep the existing per-attempt `.diff` file write below it; include the `outcome` in that file's header for provenance.

- [ ] **Step 5: Add a walker integration test** in `tests/test_reasoner_stage6.py`: with a mocked `PilotSession` where `probe_stimulus` returns a trial match before AND the proposed phase is a response-key keypress, assert the phase is NOT appended to `partial["navigation"]["phases"]`. (Reuse the existing PilotSession-mock harness in that file.)

- [ ] **Step 6:** Run `uv run pytest tests/test_reasoner_stage6.py tests/test_nav_classify.py -v` → all pass.

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/reasoner/nav_classify.py tests/test_nav_classify.py src/experiment_bot/reasoner/stage6_pilot.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(nav): walker classifies advance-vs-trial-response so cards are replayable

The Stage-6 walker now probes the live trial stimulus before/after each proposed
phase and classifies it via the pure classify_phase_outcome helper. A demo-trial
RESPONSE keypress (stimulus present + response-key, or stimulus consumed) is no
longer appended to navigation.phases — only genuine nav advances are. This makes
walker-produced TaskCards executor-replayable by construction, fixing the SP15
defect where '.'/',' trial responses were baked into nav. Ambiguous cases bias to
nav_advance; the C3 replay gate backstops. Spec C2; audit genbottle-001.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Stage-6 executor-shaped replay gate

**Files:**
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py` (`run_stage6` success path)
- Test: `tests/test_reasoner_stage6.py`

**Why:** Walker accumulates phases in a persistent session; the executor replays them in a fresh browser. A Stage-6 PASS doesn't currently imply executor-replayability (SP15: 5/5 executor sessions failed on a "passed" card) (genbottle-007). Add a fresh-browser replay that fails the pilot unless the finalized nav reaches trial rendering.

- [ ] **Step 1: Write the failing test** in `tests/test_reasoner_stage6.py`: with `replay_navigation` mocked to return False, `run_stage6` raises `PilotValidationError`; mocked True → returns normally. (Use the existing PilotSession-mock harness; mock the new `replay_navigation` symbol.)

```python
@pytest.mark.asyncio
async def test_stage6_fails_when_replay_cannot_reach_trials(tmp_path, monkeypatch):
    # ... build a passing walker (existing harness) ...
    import experiment_bot.reasoner.stage6_pilot as s6
    async def _replay_fail(*a, **k):
        return False
    monkeypatch.setattr(s6, "replay_navigation", _replay_fail)
    with pytest.raises(PilotValidationError, match="replay"):
        await run_stage6(... existing passing args ...)
```

Run → expect FAIL (no replay gate yet).

- [ ] **Step 2: Implement `replay_navigation`** in `stage6_pilot.py`:

```python
async def replay_navigation(url, navigation, lookup, *, headless=True, viewport=None,
                            max_polls=_NO_MATCH_EARLY_STOP) -> bool:
    """Fresh-browser, executor-shaped replay: run the finalized navigation.phases
    serially via the unified PilotSession engine (exactly as the executor's entry
    nav does), then poll for a trial stimulus. Returns True iff a trial stimulus
    was reached. This makes a Stage-6 PASS imply an executor-replayable card.
    """
    from experiment_bot.core.pilot_session import PilotSession
    async with PilotSession(headless=headless, viewport=viewport) as session:
        await session.goto(url)
        for phase in navigation.phases:
            await session.try_phase(phase)  # skip-on-fail, like the executor
        for _ in range(max_polls):
            probe = await session.probe_stimulus(lookup)
            if probe.match is not None:
                return True
        return False
```

(`navigation` is a `NavigationConfig`; build it from the finalized `partial` the same way `_partial_to_pilot_config` does, or pass the already-built pilot config's `.navigation` + `.` — reuse `_partial_to_pilot_config(partial)` to get a config and pass `config.navigation` + a fresh `StimulusLookup(config)`.)

- [ ] **Step 3: Call the gate** at the END of `run_stage6`, on the success path, just before it returns the passing result. Read the success-return site first; insert:

```python
        # C3: prove the finalized nav is executor-replayable (fresh browser).
        replay_config = _partial_to_pilot_config(partial)
        from experiment_bot.core.stimulus import StimulusLookup
        reached = await replay_navigation(
            bundle.url, replay_config.navigation, StimulusLookup(replay_config),
            headless=headless, viewport=replay_config.runtime.timing.viewport,
        )
        if not reached:
            raise PilotValidationError(
                "Stage-6 replay gate: finalized navigation.phases did not reach "
                "trial rendering in a fresh-browser executor-shaped replay. The "
                "walker's nav is not executor-replayable. See pilot.md."
            )
```

Place it so the walker has already converged (pilot reached its trial threshold) and `partial["navigation"]["phases"]` is final. Guard against double browser cost: only run the replay once, on success.

- [ ] **Step 4:** Run `uv run pytest tests/test_reasoner_stage6.py -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/stage6_pilot.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(nav): Stage-6 executor-shaped replay gate (PASS implies replayable)

After the walker converges, run a fresh-browser replay of the finalized
navigation.phases via the unified engine and poll for a trial stimulus; fail the
pilot (PilotValidationError) if trials aren't reached. Converts the silent
SP15 walker/executor mismatch (5/5 executor sessions failed on a 'passed' card)
into a loud Stage-6 failure. Spec C3; audit genbottle-007.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Delete `platform_defaults` entirely

**Files:**
- Delete: `src/experiment_bot/reasoner/platform_defaults.py`, `tests/test_platform_defaults.py`
- Modify: `src/experiment_bot/reasoner/stage1_structural.py` (remove import + call)
- Modify: `docs/scope-of-validity.md`

**Why:** The memorized per-paradigm scripts are paradigm-specific (cognition.run "5× space" is an advance count, not a platform invariant), the clobber rule overwrote correct shorter LLM nav, and constants drifted from source cards (platform-001/002, claude-003, genbottle-004). With C2/C3 making the walker trustworthy, the memorized fast-path is no longer needed.

- [ ] **Step 1:** `grep -rn "platform_defaults\|apply_platform_defaults\|_match_platform\|PLATFORM_NAV_DEFAULTS" src/ tests/` to find every reference. Expected: `stage1_structural.py` (import + call + the inference-text branch that mentions the backfill), `tests/test_platform_defaults.py`, and the module itself.

- [ ] **Step 2: Write/adjust a failing test** asserting the deletion: in `tests/test_reasoner_stage1.py` (or wherever Stage 1 is tested), assert `apply_platform_defaults` is no longer importable and that Stage 1 returns the LLM's nav unchanged (no backfill). If a Stage-1 test currently asserts the expfactory 10-phase backfill, update it to assert the LLM nav passes through verbatim.

```python
def test_platform_defaults_module_removed():
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("experiment_bot.reasoner.platform_defaults")
```

- [ ] **Step 3:** In `stage1_structural.py`, remove `from experiment_bot.reasoner.platform_defaults import apply_platform_defaults, _match_platform`, the `apply_platform_defaults(...)` call, and the inference-text branch that reports the backfill (the `pre/post_backfill_phase_count` / `platform` logic added in the SP15 work). Stage 1's `inference` reverts to the paradigm + stimuli + validator-retry summary.

- [ ] **Step 4: Delete** `src/experiment_bot/reasoner/platform_defaults.py` and `tests/test_platform_defaults.py`. Also delete the integration test `test_stage1_applies_platform_default_when_llm_emits_empty_nav` (it lived in `tests/test_platform_defaults.py`).

- [ ] **Step 5:** Update `docs/scope-of-validity.md`: remove any platform-default fast-path claim; state navigation is discovered by the Stage-6 walker (validated by the C3 replay gate) + executor adaptive nav, not memorized per platform.

- [ ] **Step 6:** Run `uv run pytest -x -q` → all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(nav): delete platform_defaults entirely (lean on walker + adaptive nav)

Removes the memorized per-paradigm nav scripts (the cognition.run keypress count
was paradigm-specific, not a platform invariant; the clobber rule overwrote
correct shorter LLM nav; constants had drifted from source cards). With C2
(walker classifies advance-vs-trial-response → replayable-by-construction) and C3
(replay gate proves replayability), the memorized fast-path is no longer needed.
Stage 1 emits its inferred nav; the walker + executor adaptive nav discover the
rest. Spec C4; audit platform-001/002/claude-003/genbottle-004.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Regression — regenerate dev-4 + held-out, verify replayability + completion

**Files:** none modified (generates TaskCards + a results doc).

**Why:** Verify the redesign didn't regress the dev paradigms and that the held-out card is now clean (no trial-response phases) and passes the C3 replay gate.

- [ ] **Step 1: Restore each paradigm's `.reasoner_work/<label>/stage5.json`** from its latest committed TaskCard (per `project_reasoner_work_staleness` memory), so `--resume` re-pilots from a clean Stage-5 state. (Use the restore snippet from `docs/superpowers/plans/2026-05-28-defensibility-sweep.md` Task pattern, or the inline python the controller has used before.)

- [ ] **Step 2: Re-pilot the held-out paradigm from scratch** (no --resume; platform_defaults is gone so Stage 1 nav must be re-derived + walked):

```bash
uv run experiment-bot-reason https://deploy.expfactory.org/preview/80/ \
    --label stop_signal_with_integrated_memory --pilot-max-retries 11 \
    > /tmp/navredesign-heldout.log 2>&1; echo "exit=$?"; tail -20 /tmp/navredesign-heldout.log
```

Expected: either a TaskCard whose `navigation.phases` contains NO trial-response keypresses (verify by inspecting the card) and which passed the C3 replay gate, OR a loud Stage-6 `PilotValidationError` (replay gate / budget) — both acceptable; record which. Inspect the card:

```bash
python3 -c "import json,glob; d=json.load(open(sorted(glob.glob('taskcards/stop_signal_with_integrated_memory/*.json'))[-1])); print('nav phases:', len(d['navigation']['phases'])); [print(p.get('action'), p.get('key'), p.get('target','')[:30]) for p in d['navigation']['phases']]"
```

- [ ] **Step 3: Dev-4 regression** — re-pilot each dev paradigm with `--resume` and the restored stage5:

```bash
# expfactory_stroop, expfactory_stop_signal, stopit_stop_signal, cognitionrun_stroop
# (URLs in scripts/launch.sh). Each must reach a Stage-6 PASS (which now includes
# the C3 replay gate) OR fail loudly. Record pass/fail per paradigm.
```

- [ ] **Step 4: Write `docs/navigation-redesign-results.md`** — per-paradigm outcome (Stage-6 pass/fail, nav phase count, any trial-response phases eliminated, C3 replay result), held-out outcome, and an honest statement of whether deleting platform_defaults cost any dev paradigm (per the spec's regression-watch). Follow the `docs/sp*-results.md` precedent.

- [ ] **Step 5: Commit** regenerated cards + results doc.

```bash
git add taskcards/ docs/navigation-redesign-results.md
git commit -m "$(cat <<'EOF'
chore(nav): regenerate dev-4 + held-out under unified nav; results

Held-out stop_signal_with_integrated_memory card regenerated without
platform_defaults: navigation.phases contains no trial-response keypresses and
passes the C3 replay gate [or: fails loudly — see doc]. Dev-4 outcomes recorded.
Spec C1-C4 regression. See docs/navigation-redesign-results.md.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:** C1 → Tasks 1+2; C2 → Task 3; C3 → Task 4; C4 → Task 5; regression → Task 6. All spec components covered. ✓

**Placeholder scan:** Task 6's dev-4 loop references `scripts/launch.sh` URLs rather than inlining them — acceptable (they're a known, stable registry the controller has used repeatedly this session); the restore snippet references a prior plan's pattern. No code step lacks code.

**Type consistency:** `classify_phase_outcome(before_match, after_match, phase, response_keys)` signature is identical in Task 3's helper, tests, and walker call. `replay_navigation(url, navigation, lookup, *, headless, viewport, max_polls)` consistent between Task 4 definition + call. `PhaseAttempt(success, dom_after, error)` used consistently. `StimulusProbe.match` is the field the classifier reads (matches pilot_session.py).

**Ordering/contention:** Tasks 1→2 (pilot_session then executor+delete navigator), 3→4 (both stage6_pilot.py, sequential), 5 (reasoner stage1 + deletes), 6 (regression). Sequential as required.

**Guardrail check:** adaptive nav stays stuck-DOM-gated (Task 2 explicitly leaves the gate untouched). Reproducibility preserved (no eager runtime LLM added). Scientific core untouched.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-28-navigation-redesign.md`. Execute via **superpowers:subagent-driven-development** — fresh implementer subagent per task, spec-compliance reviewer between tasks, SKIP code-quality reviewer (per project preference). Sequential (no parallel implementers — shared files). Gate Task 6's live runs on Tasks 1–5 being green.

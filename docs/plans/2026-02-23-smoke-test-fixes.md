# Smoke Test Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all bugs discovered during live smoke testing of the 4 target tasks (ExpFactory stop signal, ExpFactory cued task switching, PsyToolkit stopsignal, PsyToolkit taskswitching_cued) so each runs to completion and produces valid summary statistics.

**Architecture:** Each task targets a specific bug in the executor, platform adapter, or summary module. Tasks are ordered so that unit tests come first, then integration fixes, then live smoke test verification. All changes are in existing files — no new files created.

**Tech Stack:** Python 3.12, pytest, playwright, numpy

---

### Task 1: Commit existing uncommitted smoke test fixes

The working tree has 3 modified files with fixes from live testing that haven't been committed yet. These are: task-switching dynamic key resolution, attention check handling (ordinal + "last" support), ExpFactory phase detection (attention check DOM query, context-destroyed catch), and PsyToolkit demo URL fallback.

**Files:**
- Modified: `src/experiment_bot/core/executor.py`
- Modified: `src/experiment_bot/platforms/expfactory.py`
- Modified: `src/experiment_bot/platforms/psytoolkit.py`

**Step 1: Run existing tests to confirm nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: All 42 tests PASS

**Step 2: Commit the existing changes**

```bash
git add src/experiment_bot/core/executor.py src/experiment_bot/platforms/expfactory.py src/experiment_bot/platforms/psytoolkit.py
git commit -m "fix: smoke test fixes for task switching, attention checks, and platform adapters"
```

---

### Task 2: Add tests for attention check parser

The `_parse_attention_check_key` method handles two attention check formats but has no unit tests. Add tests for both formats plus edge cases.

**Files:**
- Modify: `tests/test_executor.py`

**Step 1: Write the failing tests**

Add to `tests/test_executor.py`:

```python
def test_parse_attention_check_direct_key():
    """'Press the X key' format returns the letter."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._parse_attention_check_key("Press the q key") == "q"
    assert executor._parse_attention_check_key("Press the P key") == "p"


def test_parse_attention_check_ordinal():
    """'Press the key for the Nth letter' format returns correct letter."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._parse_attention_check_key(
        "Press the key for the third letter of the English alphabet. This screen will advance automatically in 25 seconds."
    ) == "c"
    assert executor._parse_attention_check_key(
        "Press the key for the twenty-sixth letter of the English alphabet."
    ) == "z"


def test_parse_attention_check_last():
    """'last letter' maps to z."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._parse_attention_check_key(
        "Press the key for the last letter of the English alphabet. This screen will advance automatically in 25 seconds."
    ) == "z"


def test_parse_attention_check_unknown():
    """Unrecognized format returns None."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._parse_attention_check_key("Some random text") is None
    assert executor._parse_attention_check_key("") is None
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_executor.py -v`
Expected: All tests PASS (the implementation already exists)

**Step 3: Commit**

```bash
git add tests/test_executor.py
git commit -m "test: add unit tests for attention check parser"
```

---

### Task 3: Add tests for task-switching dynamic key resolution

The `_resolve_key_mapping` method now handles both stop signal and task switching formats. Add tests for the task switching path.

**Files:**
- Modify: `tests/test_executor.py`

**Step 1: Write the tests**

Add a task-switching sample config and tests to `tests/test_executor.py`:

```python
TASK_SWITCHING_CONFIG = {
    "task": {"name": "Cued Task Switching", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "parity_even",
            "description": "Even number with parity cue",
            "detection": {"method": "js_eval", "selector": "window.currTask === 'parity' && window.currStim.number % 2 === 0"},
            "response": {"key": "dynamic", "condition": "parity_even"},
        },
        {
            "id": "magnitude_high",
            "description": "Number > 5 with magnitude cue",
            "detection": {"method": "js_eval", "selector": "window.currTask === 'magnitude' && window.currStim.number > 5"},
            "response": {"key": "dynamic", "condition": "magnitude_high"},
        },
    ],
    "response_distributions": {
        "task_switch": {"distribution": "ex_gaussian", "params": {"mu": 580, "sigma": 70, "tau": 100}},
    },
    "performance": {"go_accuracy": 0.88, "stop_accuracy": 0, "omission_rate": 0.03, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {
        "default_group_index": 1,
        "group_index_mappings": {
            "0_to_4": {"higher": ",", "lower": ".", "odd": ",", "even": "."},
            "5_to_9": {"higher": ",", "lower": ".", "odd": ".", "even": ","},
        },
    },
}


def test_resolve_key_mapping_task_switching():
    """Task switching config resolves group_index_mappings to condition keys."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._key_map["parity_even"] == "."
    assert executor._key_map["parity_odd"] == ","
    assert executor._key_map["magnitude_high"] == ","
    assert executor._key_map["magnitude_low"] == "."


def test_resolve_response_key_dynamic():
    """'dynamic' keys are resolved via the key map."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    match = StimulusMatch(stimulus_id="parity_even", response_key="dynamic", condition="parity_even")
    assert executor._resolve_response_key(match) == "."


def test_resolve_response_key_static():
    """Non-dynamic keys are returned as-is."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    match = StimulusMatch(stimulus_id="go_left", response_key="z", condition="go")
    assert executor._resolve_response_key(match) == "z"
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_executor.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_executor.py
git commit -m "test: add unit tests for task-switching dynamic key resolution"
```

---

### Task 4: Fix RT sampling fallback for task-switching conditions

The executor tries to sample from `"go_correct"` or `"go_error"`, but the cued task switching config defines distributions named `"task_repeat_cue_repeat"`, `"task_repeat_cue_switch"`, `"task_switch"`, and `"first_trial"`. The current fallback (`list(self._sampler._samplers.keys())[0]`) works but is fragile and doesn't produce switch-cost patterns. Fix the sampler to fall back to the first available distribution cleanly.

**Files:**
- Modify: `src/experiment_bot/core/executor.py:245-250`
- Modify: `src/experiment_bot/core/distributions.py`
- Modify: `tests/test_executor.py`

**Step 1: Write the failing test**

Add to `tests/test_executor.py`:

```python
def test_sampler_fallback_to_first_distribution():
    """When requested condition doesn't exist, sampler falls back to first available."""
    from experiment_bot.core.distributions import ResponseSampler
    from experiment_bot.core.config import DistributionConfig
    dists = {
        "task_switch": DistributionConfig(distribution="ex_gaussian", params={"mu": 580, "sigma": 70, "tau": 100}),
    }
    sampler = ResponseSampler(dists, seed=42)
    # "go_correct" doesn't exist, should fall back
    rt = sampler.sample_rt_with_fallback("go_correct")
    assert 150 < rt < 2000
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_executor.py::test_sampler_fallback_to_first_distribution -v`
Expected: FAIL with `AttributeError: 'ResponseSampler' object has no attribute 'sample_rt_with_fallback'`

**Step 3: Implement `sample_rt_with_fallback` in ResponseSampler**

In `src/experiment_bot/core/distributions.py`, add to `ResponseSampler`:

```python
def sample_rt_with_fallback(self, condition: str) -> float:
    """Sample RT for condition, falling back to first available distribution."""
    if condition in self._samplers:
        rt = self._samplers[condition].sample()
    elif self._samplers:
        rt = next(iter(self._samplers.values())).sample()
    else:
        rt = 500.0  # safe default
    return max(rt, self._floor_ms)
```

**Step 4: Update executor to use `sample_rt_with_fallback`**

In `src/experiment_bot/core/executor.py`, replace lines 246-250:

```python
# Before:
try:
    rt_ms = self._sampler.sample_rt(rt_condition)
except KeyError:
    rt_ms = self._sampler.sample_rt(list(self._sampler._samplers.keys())[0])

# After:
rt_ms = self._sampler.sample_rt_with_fallback(rt_condition)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/experiment_bot/core/distributions.py src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "fix: add clean RT sampler fallback for non-standard distribution keys"
```

---

### Task 5: Add test for ExpFactory context-destroyed completion detection

The `detect_task_phase` wrapper catches exceptions (from page navigation destroying the execution context) and returns `COMPLETE`. Add a test for this behavior.

**Files:**
- Modify: `tests/test_expfactory.py`

**Step 1: Write the test**

```python
@pytest.mark.asyncio
async def test_detect_task_phase_context_destroyed_returns_complete():
    """When page navigation destroys context, detect_task_phase returns COMPLETE."""
    from experiment_bot.core.config import TaskPhase
    platform = ExpFactoryPlatform()
    page = AsyncMock()
    page.query_selector = AsyncMock(side_effect=Exception("Execution context was destroyed"))
    result = await platform.detect_task_phase(page)
    assert result == TaskPhase.COMPLETE
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_expfactory.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_expfactory.py
git commit -m "test: add test for ExpFactory context-destroyed completion detection"
```

---

### Task 6: Add test for PsyToolkit demo URL fallback

The PsyToolkit adapter now falls back to the demo page HTML when the zip download returns 403. Test that `get_demo_url` returns the correct URL and that `get_task_url` uses the demo URL.

**Files:**
- Modify: `tests/test_psytoolkit.py`

**Step 1: Write the tests**

```python
def test_get_demo_url():
    platform = PsyToolkitPlatform()
    url = platform.get_demo_url("stopsignal")
    assert url == "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html"


def test_get_task_url_returns_demo_url():
    """get_task_url should return the demo URL, not the library URL."""
    platform = PsyToolkitPlatform()
    url = asyncio.run(platform.get_task_url("stopsignal"))
    assert url == "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html"
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_psytoolkit.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_psytoolkit.py
git commit -m "test: add tests for PsyToolkit demo URL and fallback"
```

---

### Task 7: Run ExpFactory task 9 (stop signal) smoke test

Live smoke test to verify the stop signal task runs to completion with valid race model statistics.

**Files:**
- No code changes expected (verification only)

**Step 1: Clear old output and run**

```bash
rm -rf output/expfactory/stop_signal_task_*
source .env && uv run experiment-bot expfactory --task 9 -v
```

Expected: Runs to completion (~10 min). Check logs for:
- Navigation phases complete without errors
- Trial loop enters and processes trials
- Feedback/attention screens handled
- "Run summary: N trials" logged

**Step 2: Verify summary statistics**

```bash
cat output/expfactory/stop_signal_task_*/*/summary_stats.json | python3 -m json.tool
```

Check:
- `total_trials` > 400
- `race_model_validation.pass` is `true` (stop_failure RT < go RT)
- `stop_signal.stop_accuracy` between 0.4 and 0.8
- `omission_rate` < 0.10

**Step 3: Commit any fixes if needed**

```bash
git commit -m "fix: adjustments from stop signal smoke test"
```

---

### Task 8: Run ExpFactory task 2 (cued task switching) smoke test

Live smoke test to verify the task switching task runs to completion.

**Files:**
- No code changes expected (verification only)

**Step 1: Clear old output and run**

```bash
rm -rf output/expfactory/cued_task_switching_*
source .env && uv run experiment-bot expfactory --task 2 -v
```

Expected: Runs to completion (~12 min). Check logs for:
- All attention checks handled with correct keys (letters, ordinals, "last")
- No "Could not parse attention check text" warnings
- Task completes (either COMPLETE detected or context-destroyed catch)
- "Run summary: N trials" logged

**Step 2: Verify summary statistics**

```bash
cat output/expfactory/cued_task_switching_*/*/summary_stats.json | python3 -m json.tool
```

Check:
- `total_trials` > 150 (3 blocks × 64 trials = 192 expected, minus omissions)
- `omission_rate` < 0.10
- `overall_rt.mean` between 400 and 800
- All 4 conditions present: `parity_even`, `parity_odd`, `magnitude_high`, `magnitude_low`

**Step 3: Commit any fixes if needed**

```bash
git commit -m "fix: adjustments from task switching smoke test"
```

---

### Task 9: Run PsyToolkit stopsignal smoke test

First PsyToolkit live test. This will generate a config via Claude API (no cached config exists), then run the experiment on the PsyToolkit demo page.

**Files:**
- Possibly modify: `src/experiment_bot/platforms/psytoolkit.py` (if phase detection needs tuning)
- Possibly modify: `src/experiment_bot/core/executor.py` (if PsyToolkit stimuli need different handling)

**Step 1: Run**

```bash
source .env && uv run experiment-bot psytoolkit --task stopsignal -v
```

Expected: Downloads demo page HTML as source, analyzes with Claude, generates config, then runs experiment.

**Step 2: If config generation succeeds, verify the cached config**

```bash
cat cache/psytoolkit/stopsignal/config.json | python3 -m json.tool
```

Check that stimuli, response_distributions, and navigation phases look reasonable.

**Step 3: If experiment runs, verify summary**

```bash
cat output/psytoolkit/*/*/summary_stats.json | python3 -m json.tool
```

**Step 4: Fix any issues and commit**

PsyToolkit experiments use canvas-based rendering. Common issues:
- `detect_task_phase` may not correctly identify phases (canvas text not in `body.textContent`)
- Stimulus detection selectors from Claude may not work with PsyToolkit's internal state
- Navigation may need PsyToolkit-specific handling ("Click to start" button, spacebar for instructions)

```bash
git commit -m "fix: PsyToolkit stopsignal smoke test fixes"
```

---

### Task 10: Run PsyToolkit taskswitching_cued smoke test

Second PsyToolkit live test.

**Files:**
- Possibly modify: same files as Task 9

**Step 1: Run**

```bash
source .env && uv run experiment-bot psytoolkit --task taskswitching_cued -v
```

**Step 2: Verify config and summary (same checks as Task 9)**

**Step 3: Fix any issues and commit**

```bash
git commit -m "fix: PsyToolkit taskswitching_cued smoke test fixes"
```

---

### Task 11: Final test suite run and commit

Ensure all unit tests still pass after all smoke test fixes.

**Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS

**Step 2: Final commit if any cleanup needed**

```bash
git commit -m "chore: final cleanup after smoke test verification"
```

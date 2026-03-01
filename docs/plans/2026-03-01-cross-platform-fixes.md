# Cross-Platform Fixes: Selector Fragility & Fixation Filtering

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two generalizable issues that affect jsPsych tasks across platforms: Claude generating tag-specific selectors that break on different experiments, and fixation crosses being treated as trial stimuli.

**Architecture:** Prompt-first approach — both issues are primarily caused by Claude generating suboptimal configs, so the prompt (`system.md`) gets the main fixes. The executor gets a small safety guard for fixation stimuli that slip through.

**Tech Stack:** Python 3.11, pytest, Playwright (async)

---

### Task 1: Add tag-agnostic selector guidance to system prompt

**Files:**
- Modify: `src/experiment_bot/prompts/system.md:16-22`

**Step 1: Add selector best practices paragraph**

In `system.md`, after line 22 (the `**IMPORTANT**: Identify ALL possible stimulus types...` paragraph), add:

```markdown

   **Selector best practices**: Do not assume the stimulus is wrapped in a specific HTML tag (`span`, `p`, `div`). Experiment authors use different tags in their stimulus HTML strings. Prefer tag-agnostic selectors:
   - Use `firstElementChild` to get the first child of a container (e.g., `document.querySelector('#jspsych-html-keyboard-response-stimulus')?.firstElementChild`)
   - Use `children[0]` as an alternative
   - Only target a specific tag (e.g., `querySelector('span')`) if the experiment source code explicitly defines that tag

```

**Step 2: Verify prompt loads correctly**

Run: `python3.11 -c "from pathlib import Path; p = Path('src/experiment_bot/prompts/system.md'); t = p.read_text(); assert 'firstElementChild' in t; assert 'Selector best practices' in t; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/experiment_bot/prompts/system.md
git commit -m "prompt: add tag-agnostic selector guidance to prevent span/p fragility"
```

---

### Task 2: Add fixation exclusion guidance to system prompt

**Files:**
- Modify: `src/experiment_bot/prompts/system.md:22-28` (after the new selector paragraph from Task 1)

**Step 1: Add fixation exclusion paragraph**

After the selector best practices paragraph added in Task 1, add:

```markdown

   **Do NOT include fixation crosses, inter-trial intervals, or blank screens as stimuli.** Only include stimuli that require a keyboard response from the participant. Fixation/ITI phases are handled by the executor's polling loop and `response_window_js` timing — they do not need stimulus entries.

```

**Step 2: Verify prompt loads correctly**

Run: `python3.11 -c "from pathlib import Path; p = Path('src/experiment_bot/prompts/system.md'); t = p.read_text(); assert 'fixation crosses' in t; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/experiment_bot/prompts/system.md
git commit -m "prompt: exclude fixation/ITI from stimuli array"
```

---

### Task 3: Add executor guard for non-trial stimulus matches

**Files:**
- Test: `tests/test_executor.py`
- Modify: `src/experiment_bot/core/executor.py:284-290`

**Step 1: Write the failing test**

Add to `tests/test_executor.py`:

```python
def test_non_trial_stimulus_does_not_reset_consecutive_misses():
    """Non-trial stimuli (fixation, no_response) should not reset consecutive_misses.

    If a fixation stimulus resets the miss counter, the executor can get stuck
    indefinitely polling fixation → reset → poll fixation → reset, never triggering
    advance behavior that would dismiss an instruction screen.
    """
    config_data = dict(SAMPLE_CONFIG)
    # Only "go" distributions — "no_response" has no distribution
    config_data["response_distributions"] = {
        "go": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)

    # A fixation match: null key, no_response condition, no matching distribution
    fixation_match = StimulusMatch(
        stimulus_id="fixation",
        response_key=None,
        condition="no_response",
    )
    assert executor._is_trial_stimulus(fixation_match) is False
```

**Step 2: Run the test to verify it passes**

Run: `cd /Users/loganbennett/Downloads/experiment_bot && uv run pytest tests/test_executor.py::test_non_trial_stimulus_does_not_reset_consecutive_misses -v`
Expected: PASS (this just validates the helper — the real behavior test is in the executor change)

**Step 3: Modify executor to guard consecutive_misses reset**

In `src/experiment_bot/core/executor.py`, change lines 284-290 from:

```python
            consecutive_misses = 0
            stuck_detector.heartbeat()

            # Skip non-trial stimuli
            if match.condition == "no_response":
                await asyncio.sleep(0.05)
                continue
```

to:

```python
            # Skip non-trial stimuli (fixation, ITI) without resetting miss counter.
            # Resetting here would prevent advance behavior from triggering when
            # the executor is stuck detecting fixation on an instruction screen.
            if not self._is_trial_stimulus(match) and match.response_key is None:
                await asyncio.sleep(0.05)
                continue

            consecutive_misses = 0
            stuck_detector.heartbeat()
```

This moves the `consecutive_misses = 0` and `stuck_detector.heartbeat()` to AFTER the non-trial guard, so fixation matches don't reset the counter. The guard also broadens from `condition == "no_response"` to any stimulus without a distribution and null key.

**Step 4: Run all executor tests**

Run: `cd /Users/loganbennett/Downloads/experiment_bot && uv run pytest tests/test_executor.py -v`
Expected: All tests PASS

**Step 5: Run full test suite**

Run: `cd /Users/loganbennett/Downloads/experiment_bot && uv run pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "fix: non-trial stimuli (fixation) no longer reset consecutive_misses counter"
```

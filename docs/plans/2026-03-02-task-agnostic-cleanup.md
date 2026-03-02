# Task-Agnostic Cleanup — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all remaining hardcoded task knowledge from the Python source so the bot reads as a generic experiment executor where Claude provides 100% of task-specific intelligence.

**Architecture:** Delete the hardcoded ordinal map and attention-check regex parser — replace with config-driven `response_js`. Derive interrupt log conditions from config instead of hardcoding `"inhibit_success"` / `"inhibit_failure"`. Rewrite the Claude system prompt and schema descriptions to lead with generic language. Clean CLI help strings.

**Tech Stack:** Python dataclasses, Playwright async, pytest

---

### Task 1: Remove hardcoded attention check parsing from executor.py

The executor currently embeds a 26-entry English ordinal lookup table (`_ORDINAL_MAP`) and regex patterns to parse attention check prompts. This is hardcoded task knowledge — Claude should provide a `response_js` expression that returns the correct key instead.

**Files:**
- Modify: `src/experiment_bot/core/executor.py`

**Changes:**

1. Delete `_ORDINAL_MAP` (lines 507-515)

2. Replace `_parse_attention_check_key()` with a minimal fallback that only handles the trivial "Press the X key" pattern (1 line of regex, not task knowledge — it's a universal instruction pattern):

```python
def _parse_attention_check_key(self, text: str) -> str | None:
    """Minimal fallback: extract single-letter key from 'Press the X key' patterns."""
    import re
    m = re.search(r'[Pp]ress (?:the )?(\w) key', text)
    return m.group(1).lower() if m else None
```

3. Update `_handle_attention_check()` to try `response_js` first (config-driven), then fall back to the minimal regex:

```python
async def _handle_attention_check(self, page: Page) -> None:
    """Handle attention check using config-driven response logic."""
    await asyncio.sleep(1.5)
    ac = self._config.runtime.attention_check
    try:
        # Prefer config-driven JS response (Claude provides the logic)
        if ac.response_js:
            key = await page.evaluate(ac.response_js)
            if key:
                logger.info(f"Attention check: pressing '{key}' (via response_js)")
                await page.keyboard.press(str(key))
                return

        # Fallback: read text and try minimal pattern match
        selector_js = ac.text_selector or "body"
        text = await page.evaluate(
            f"(() => {{ var el = document.querySelector('{selector_js}'); return el ? el.textContent : ''; }})()"
        )
        key = self._parse_attention_check_key(text)
        if key:
            logger.info(f"Attention check: pressing '{key}'")
            await page.keyboard.press(key)
        else:
            logger.warning(f"Could not parse attention check text: {text[:100]}")
            await page.keyboard.press("Enter")
    except Exception as e:
        logger.warning(f"Attention check handling failed: {e}")
        await page.keyboard.press("Enter")
```

---

### Task 2: Derive interrupt log conditions from config

Currently the executor hardcodes `"inhibit_success"` and `"inhibit_failure"` as condition values in trial logs. These should derive from the configured `detection_condition`, making logs self-documenting regardless of paradigm.

**Files:**
- Modify: `src/experiment_bot/core/executor.py`

**Changes:**

In `_execute_trial()`, replace the hardcoded condition strings:

```python
# Before:
"condition": "inhibit_success",
# After:
"condition": f"{interrupt_cfg.detection_condition}_withheld",

# Before:
"condition": "inhibit_failure",
# After:
"condition": f"{interrupt_cfg.detection_condition}_responded",
```

This means if Claude configures `detection_condition: "stop"`, logs will say `"stop_withheld"` / `"stop_responded"`. If it's `"nogo"`, logs say `"nogo_withheld"` / `"nogo_responded"`. No hardcoded paradigm terminology in the output.

---

### Task 3: Clean system.md — remove paradigm-specific guidance

The Claude system prompt currently teaches Claude about specific paradigms with specific parameter ranges. This should be rewritten to provide generic analysis guidance and let Claude's own training knowledge supply paradigm-specific parameters.

**Files:**
- Modify: `src/experiment_bot/prompts/system.md`

**Changes:**

1. **Lines 37-38** (RT distribution naming): Remove the task-switching-specific naming convention. Replace with:
```
RT distribution naming: Name distributions after their stimulus conditions.
Use `{condition}` for the primary distribution, optionally
`{condition}_correct` and `{condition}_error` if correct and error
responses have different RT profiles.
```
(This is already done from the previous refactor — verify it's clean.)

2. **Lines 39-41** (Literature-grounded ranges): Replace paradigm-specific ranges with generic guidance:
```
Literature-grounded parameters:
- Base your ex-Gaussian parameters (mu, sigma, tau) on published RT data
  for the specific task you identify. Typical healthy adult RTs fall in
  mu=350-600ms, sigma=40-100ms, tau=50-150ms, but vary by task demands.
```

3. **Lines 45-57** (Performance targets section): Replace paradigm-specific examples with generic ones:
```
4. **Performance targets**: Provide per-condition accuracy and omission rates.
   Key the `accuracy` and `omission_rate` objects by condition name from your
   stimulus definitions. Include accuracy for all conditions, including any
   that require response suppression. Base all values on published literature
   for the specific task you identify.

   Example:
   {"accuracy": {"condition_a": 0.95, "condition_b": 0.88},
    "omission_rate": {"condition_a": 0.01, "condition_b": 0.03},
    "practice_accuracy": 0.85}
```

4. **Line 22** (Stimulus ordering): Replace paradigm-specific instruction:
```
**IMPORTANT**: Identify ALL possible stimulus types. Missing a stimulus type
will cause the bot to freeze. Order stimulus rules by detection priority —
stimuli requiring response suppression should be detected BEFORE standard
response stimuli when both may be simultaneously present.
```

5. **Line 75** (trial_context_js): Update to remove paradigm reference:
```
- `trial_context_js`: A JS expression that returns trial context text
  (e.g., cue identity, block label, or other per-trial metadata for logging)
```

6. **Section 10 (Attention checks)**: Add guidance for Claude to provide `response_js`:
```
10. **Attention checks**: If the experiment has attention checks:
    - `detection_selector`: CSS/JS selector that detects when an attention check is displayed
    - `text_selector`: CSS selector to read the attention check prompt text
    - `response_js`: JavaScript expression that reads the attention check prompt and returns the correct key to press as a string. The bot evaluates this expression directly — provide complete logic for determining the response (e.g., parsing ordinal references, reading instructions). This is the primary response mechanism; without it, the bot falls back to simple "Press the X key" pattern matching.
```

---

### Task 4: Clean schema.json descriptions

**Files:**
- Modify: `src/experiment_bot/prompts/schema.json`

**Changes:**

1. Line 99 — runtime description: already updated in previous refactor, verify clean.

2. Line 122 — `rt_cap_fraction` description:
```json
"rt_cap_fraction": {"type": "number", "default": 0.9, "description": "Fraction of max_response_time to cap sampled RTs at"}
```

3. Lines 140-145 — `trial_interrupt` section descriptions:
```json
"trial_interrupt": {
  "type": "object",
  "description": "Trial-level interrupt behavior. When detection_condition matches a stimulus condition, the executor polls for that stimulus during the RT wait and probabilistically suppresses the response.",
  "properties": {
    "detection_condition": {"type": "string", "default": "", "description": "Stimulus condition name that triggers mid-trial detection. Empty string for tasks without trial interrupts."},
    "failure_rt_key": {"type": "string", "default": "", "description": "Distribution key for RTs when suppression fails and a response escapes"},
    "failure_rt_cap_fraction": {"type": "number", "default": 0.85, "description": "Fraction of max_response_time to cap failed-suppression RTs"},
    "inhibit_wait_ms": {"type": "integer", "default": 1500, "description": "Wait duration (ms) after successful response suppression"}
  }
}
```

4. Attention check section — add `response_js` description if missing:
```json
"response_js": {"type": "string", "description": "JS expression returning the correct key to press. This is the primary response mechanism — provide complete parsing logic here."}
```

---

### Task 5: Clean CLI help and docstrings

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Modify: `src/experiment_bot/core/scraper.py` (docstring only)

**Changes:**

1. CLI help strings:
```python
@click.option("--hint", default="", help="Hint about the task type for Claude's analysis")
@click.option("--accuracy", type=float, default=None, help="Override primary accuracy target (0-1)")
```

2. Scraper docstring — replace `"stop signal task"` example:
```python
hint: Optional user-provided hint about the task type.
```

---

### Task 6: Update tests

**Files:**
- Modify: `tests/test_executor.py`

**Changes:**

1. Update attention check tests to reflect simplified `_parse_attention_check_key`:
   - `test_parse_attention_check_direct_key` — keep (tests the remaining "Press the X key" pattern)
   - `test_parse_attention_check_ordinal` — delete (ordinal parsing removed)
   - `test_parse_attention_check_last` — delete (ordinal parsing removed)
   - `test_parse_attention_check_unknown` — keep

2. Add test for config-driven `response_js` attention check:
```python
@pytest.mark.asyncio
async def test_attention_check_uses_response_js():
    """When response_js is configured, it's used instead of text parsing."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "attention_check": {
            "response_js": "document.querySelector('#ac-key').textContent.trim()",
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="q")
    await executor._handle_attention_check(page)
    page.keyboard.press.assert_called_with("q")
```

3. Update interrupt condition log value tests — the `test_trial_interrupt_config_controls_inhibition` test already verifies the JS expression; add a test that verifies log condition values are config-derived:
```python
def test_interrupt_log_conditions_derive_from_config():
    """Interrupt log conditions use detection_condition, not hardcoded names."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    assert '"inhibit_success"' not in source
    assert '"inhibit_failure"' not in source
```

---

### Task 7: Run tests and verify

Run: `uv run pytest tests/ -v`
Expected: All tests pass.

Then run experiments to verify:
```bash
bash scripts/launch.sh --headless --count 1
```
Expected: 4/4 succeed. Check bot logs for the new config-derived condition names (e.g., `"stop_withheld"` / `"stop_responded"` instead of `"inhibit_success"` / `"inhibit_failure"`).

---

### Hardcoded Elements Reference

| Element | Current State | After This Plan |
|---|---|---|
| `_ORDINAL_MAP` (26-entry English lookup) | Hardcoded in executor.py | Deleted — Claude provides `response_js` |
| `_parse_attention_check_key()` ordinal regex | Hardcoded regex + ordinal map | Deleted — only minimal "Press X key" fallback remains |
| `"inhibit_success"` / `"inhibit_failure"` log values | Hardcoded strings | Derived from `detection_condition` config field |
| System prompt RT ranges | Paradigm-specific (SSRT, switch cost) | Generic guidance, Claude uses own knowledge |
| System prompt examples | Stop signal / Stroop specific | Generic condition names |
| Schema descriptions | "go RTs", "stop", "inhibition" | Paradigm-neutral language |
| CLI `--hint` help | `"stop signal task"` example | Generic description |
| CLI `--accuracy` help | "go accuracy" | "primary accuracy target" |

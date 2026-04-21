# Code Review Findings — 2026-04-21

Scope: `src/experiment_bot/core/`, `src/experiment_bot/prompts/`, and the pilot validation loop.

Standard: task-agnostic, platform-agnostic per the claim in `docs/how-it-works.md`.

## Severity legend
- **Critical** — breaks the agnosticism claim or produces wrong behavior on a novel task.
- **Significant** — hidden contract or default behavior Claude cannot override via config.
- **Minor** — code quality, narrow scope, or test coverage gap.
- **Nit** — style.

---

## `core/executor.py`

### Finding 1 — Hardcoded condition strings for navigation and attention checks
**Severity: Critical**

**Location:** `executor.py:318`, `executor.py:326`

**Before:**
```python
# Line 318
if match.condition == "navigation":
    ...

# Line 326
if match.condition in ("attention_check", "attention_check_response"):
    ...
```

These two checks compared `match.condition` against Python string literals. Any config that named its navigation stimulus something other than `"navigation"`, or its attention-check stimulus something other than `"attention_check"` / `"attention_check_response"`, would silently fall through to the trial-response path — either attempting `page.keyboard.press` with a garbage key (navigation) or running an attention-check stimulus through the RT sampling pipeline (attention check). Both produce wrong behavior with zero error signal.

**After:**
```python
nav_condition = self._config.runtime.navigation_stimulus_condition or "navigation"
if match.condition == nav_condition:
    ...

ac_conditions = set(self._config.runtime.attention_check.stimulus_conditions)
if match.condition in ac_conditions:
    ...
```

New config fields:
- `runtime.navigation_stimulus_condition` (string, default `""`): when empty, executor falls back to `"navigation"` for backward compatibility.
- `runtime.attention_check.stimulus_conditions` (list, default `["attention_check", "attention_check_response"]`): backward-compatible default means existing cached configs continue to work.

Both fields are documented in `schema.json` and `system.md`. The backward-compatible defaults mean the four existing cached configs (`expfactory_stop_signal`, `expfactory_stroop`, `stopit_stop_signal`, `cognitionrun_stroop`) do not need to be regenerated to maintain correct behavior — they will pick up the defaults.

The fix also corrected a subtle interaction: the early-exit guard for non-trial stimuli (`if not self._is_trial_stimulus(match) and match.response_key is None`) was evaluated before the navigation/attention-check checks. This meant that a navigation or attention-check stimulus with `response_key=None` would be silently skipped before reaching the condition checks. The fix moved the special-condition resolution before the early-exit guard.

---

### Finding 2 — `response_key_js` withhold sentinel not handled: crash on unknown key
**Severity: Critical**

**Location:** `executor._resolve_response_key()` (~line 65), `executor._execute_trial()` (~line 582)

**Reproduction (from Phase 0 smoke run of `stopit_stop_signal`, trial 86):**
```
playwright._impl._errors.Error: Keyboard.press: Unknown key: "none"
```

**Root cause:**  
`_resolve_response_key()` evaluated `page.evaluate(response_key_js)` and returned whatever the JS expression yielded, stringified. For the stopit stop-signal task, the JS expression correctly returns the string `"none"` on stop trials (where the correct response is to withhold). The executor then passed `"none"` directly to `page.keyboard.press()`, which is not a valid Playwright key name.

The executor silently assumed `response_key_js` always returns a pressable key. This is an undocumented constraint invisible to Claude and a crash that is impossible to debug from the config alone.

**Fix in `_resolve_response_key()`:**
```python
# Before — any truthy string was returned directly:
key = await page.evaluate(stim_cfg.response.response_key_js)
if key:
    key = str(key)
    self._seen_response_keys.add(key)
    return key

# After — withhold sentinels are intercepted:
key = await page.evaluate(stim_cfg.response.response_key_js)
if self._is_withhold_sentinel(key):
    return None
key = str(key)
self._seen_response_keys.add(key)
return key
```

`_is_withhold_sentinel()` treats `None`, `""`, and the case-insensitive strings `"none"` and `"null"` as withhold instructions.

**Fix in `_execute_trial()` — new withhold path for normal trials:**
```python
resolved_key = await self._resolve_response_key(match, page)

if resolved_key is None:
    # Config-authored withhold — distinct from random omission
    self._writer.log_trial({
        ...,
        "response_key": None,
        "omission": False,
        "withheld": True,
    })
    return  # No keyboard press

# Normal path
await page.keyboard.press(resolved_key)
```

The `withheld: true` flag in `bot_log.json` is semantically distinct from `omission: true` — `withheld` means the config instructed no keypress; `omission` means the bot randomly skipped a response to simulate human miss rate.

**System.md update:** Section 8 now documents that returning `null`, `""`, `"none"`, or `"null"` from `response_key_js` is the supported mechanism for config-authored response suppression.

---

### Finding 3 — Behavioral timing hardcoded in executor, not configurable
**Severity: Significant**

**Location:** `executor.py:321` (`asyncio.sleep(1.0)`), `executor.py:571` (`asyncio.sleep(1.5)`), `executor.py:607` (`asyncio.sleep(2.0)`), `_wait_for_trial_end` default `timeout_s=5.0`

Four timing values were hardcoded as Python literals with no path for Claude's config to override them:

| Value | Location | Purpose |
|-------|----------|---------|
| `1.0 s` | `_trial_loop` navigation branch | Pause before pressing navigation key |
| `1.5 s` | `_handle_attention_check` | Pause before handling attention check |
| `2.0 s` | `_wait_for_completion` | Settle time before data capture |
| `5.0 s` | `_wait_for_trial_end` default arg | Timeout waiting for response window to close |

Any task with tighter or looser timing requirements had no recourse.

**Fix:** All four values are now read from `runtime.timing`:

```python
# Before:
await asyncio.sleep(1.0)   # navigation
await asyncio.sleep(1.5)   # attention check
await asyncio.sleep(2.0)   # completion settle

# After:
await asyncio.sleep(self._config.runtime.timing.navigation_delay_ms / 1000.0)
await asyncio.sleep(self._config.runtime.timing.attention_check_delay_ms / 1000.0)
await asyncio.sleep(self._config.runtime.timing.completion_settle_ms / 1000.0)
```

New `TimingConfig` fields (with defaults matching the old hardcoded values for backward compatibility):

| Field | Default | Old literal |
|-------|---------|-------------|
| `navigation_delay_ms` | 1000 | `1.0 s` |
| `attention_check_delay_ms` | 1500 | `1.5 s` |
| `completion_settle_ms` | 2000 | `2.0 s` |
| `trial_end_timeout_s` | 5.0 | `5.0 s` |

All four fields are documented in `schema.json` and `system.md` section 5. The 0.05 s poll sleep in the non-trial-stimulus skip path was left as-is — this is a structural constant (busy-wait grain), not a behavioral parameter Claude should tune.

---

## What was NOT changed

- `("dynamic_mapping", "dynamic")` sentinel checks in `_resolve_response_key` — these are structural, not behavioral, and are explicitly documented as reserved sentinel values in the config schema.
- `asyncio.sleep(0.05)` in the non-trial-stimulus poll — structural busy-wait grain, not a behavioral knob.
- The four cached configs in `cache/` — they will be regenerated in Phase 3 with schema awareness of the new fields.

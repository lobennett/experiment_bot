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

---

### Post-review fixes (Task 4 code quality pass)
- Cached `_navigation_condition_name` / `_attention_check_conditions` in `__init__` per plan spec (removed per-loop recomputation).
- Strengthened `test_resolve_response_key_sentinel_no_keyboard_press` assertions (was a vacuously-passing `or`).
- Made `RuntimeConfig.to_dict` always emit `navigation_stimulus_condition` for round-trip stability (matching `AttentionCheckConfig.to_dict` policy).
- Added sentinel coverage for the global `task_specific.response_key_js` resolution path.

---

## `core/config.py` — Task 5: Agnosticism review of dataclass defaults

Scope: all non-zero, non-empty defaults in `config.py` dataclasses. Task 4's new timing fields (`navigation_delay_ms`, `attention_check_delay_ms`, `completion_settle_ms`, `trial_end_timeout_s`) are out of scope — they carry legacy hardcoded values forward and were intentionally given backward-compatible defaults.

### Structural — `poll_interval_ms`
Default: 20 ms
Claim check: Not mentioned in system.md. Claude does not set this.
Verdict: **Structural.** This is the executor's busy-wait polling cadence — a fixed mechanical constant analogous to a clock tick. It is not a behavioral parameter; no published RT norm specifies "poll every N ms." The value is task-invariant: faster polling increases CPU load without changing behavior (trials respond within one poll cycle of the threshold anyway). 20 ms is a reasonable engineering constant.

### Structural — `max_no_stimulus_polls`
Default: 500
Claim check: system.md says "canvas-based tasks may need more (~2000)" and Claude may override it.
Verdict: **Structural** with a documented override path. The default covers a ~10 s budget (500 × 20 ms) before the stuck-timeout fires. Claude is already instructed to raise this for canvas tasks. Changing the default would break non-canvas tasks that expect fewer polls. Acceptable.

### Structural — `stuck_timeout_s`
Default: 10.0 s
Claim check: Not mentioned in system.md. Claude does not set this.
Verdict: **Structural.** Safety timeout for the executor polling loop. Task-invariant: 10 s is a conservative upper bound for "stimulus appeared but was not detected." Not a behavioral parameter.

### Structural — `completion_wait_ms`
Default: 5000 ms
Claim check: system.md says "How long the experiment takes to save/upload data after the last trial." Claude is told to set it.
Verdict: **Acceptable default with rationale.** 5 s is a conservative wait that works for most experiments. The downside of a non-zero default is minimal — it adds at most 5 s of wait time, not a behavioral error. Claude is instructed to tune it. Not changed.

### Structural — `feedback_delay_ms`
Default: 2000 ms
Claim check: Not mentioned in system.md. Claude does not set this.
Verdict: **Structural.** Controls how long the executor waits on a feedback screen before advancing. This is a mechanical pacing parameter, not a stimulus timing constant tied to any task design. 2 s is conservatively long; task-specific behavior comes from the feedback screen's actual content, not this wait.

### Structural — `omission_wait_ms`
Default: 2000 ms
Claim check: Not mentioned in system.md. Claude does not set this.
Verdict: **Structural.** How long the executor waits when simulating an omission (missed response). Task designs vary, but this default is a safe upper bound. The executor relies on the experiment's own response deadline to end the trial; this is an executor-side safety wait, not a behavioral timing claim.

### Structural — `rt_floor_ms`
Default: 150.0 ms
Claim check: system.md section 5 ("RT floor") documents this explicitly as a physiological constant.
Verdict: **Structural.** The minimum deliberate keypress RT is ~150 ms across all tasks and paradigms (Luce 1986). This is a physiology constant, not a task-specific parameter.

### Structural — `rt_cap_fraction`
Default: 0.90
Claim check: Not mentioned in system.md. Claude does not set this.
Verdict: **Structural.** Executor-side cap that clips sampled RTs at 90% of the experiment's response window duration. This prevents the executor from timing out on every trial. Task-invariant: the fraction is set conservatively to avoid false timeouts.

### Require Claude to set — `advance_keys`
Default was: `[" "]`
New default: `[]`
Verdict: **Require Claude to set.** The assumption that Space advances screens is wrong for tasks that use Enter, button clicks, or other keys. If Claude doesn't populate this and the default is Space, the executor will spam Space on feedback screens that expect Enter or a button click — silently advancing past content or producing no action on click-only screens. All 4 cached configs already include this field explicitly, so backward compat is maintained.
Fix: default changed to `[]`; system.md section 6 updated to mark as required.

### Require Claude to set — `feedback_fallback_keys`
Default was: `["Enter"]`
New default: `[]`
Verdict: **Require Claude to set.** Same reasoning as `advance_keys`. The fallback key for feedback screens varies by task; Enter is not universal. All 4 cached configs include this field explicitly.
Fix: default changed to `[]`; system.md section 6 updated.

### Structural — `advance_interval_polls`
Default: 100
Claim check: Not mentioned in system.md. Claude does not set this.
Verdict: **Structural.** Polling cadence for the advance-screen loop (how many polls between advance-key attempts). A mechanical constant; task-invariant.

### Require Claude to set (when interrupt task) — `failure_rt_cap_fraction`
Default was: `0.85`
New default: `0.0`
Verdict: **Require Claude to set when `detection_condition` is non-empty.** A value of 0.85 is a stop-signal–specific assumption not appropriate for tasks with different interrupt designs. The stroop tasks (non-interrupt) had this value baked into their cached JSONs even though it's inert for them — that's noise. More critically: `expfactory_stop_signal` had detection_condition="stop" but no explicit `failure_rt_cap_fraction` in its JSON (relying on the Python default 0.85). After the change, the value 0.85 stored in that cached JSON continues to be loaded correctly.
**Backward compat:** All 4 cached JSONs embed an explicit value (0.85) for this field; the Python default is irrelevant for them. Safe.
**Config generation gap:** `expfactory_stop_signal`'s JSON shows 0.85 — this was the Python default embedded at config-gen time, not a value Claude reasoned about. Future config regenerations will require Claude to set it explicitly (system.md updated).
Fix: default changed to `0.0`; system.md section 9 updated to mark as required for interrupt tasks.

### Require Claude to set (when interrupt task) — `inhibit_wait_ms`
Default was: `1500`
New default: `0`
Verdict: **Require Claude to set when `detection_condition` is non-empty.** 1500 ms is a stop-signal–specific constant (roughly the post-signal wait in many SST implementations). Tasks with different interrupt designs need different values. `stopit_stop_signal` correctly set 1300 ms; `expfactory_stop_signal` relied on the Python default 1500 ms.
**Backward compat:** Same as `failure_rt_cap_fraction` — all cached JSONs embed an explicit numeric value (1300 or 1500) that will continue to be loaded. Python default is irrelevant. Safe.
**Config generation gap:** `expfactory_stop_signal` has 1500 in JSON from old Python default — marks a gap where Claude did not reason about the value. System.md now documents the requirement clearly.
Fix: default changed to `0`; system.md section 9 updated.

### Structural — `sigma_tau_range`
Default: `[1.0, 1.0]`
Claim check: system.md section 11 says "Set to `[1.0, 1.0]` to disable shape jitter."
Verdict: **Structural.** `[1.0, 1.0]` means "multiply by 1.0" — semantically equivalent to "off." This is a well-documented "disabled" sentinel value per system.md. The default correctly communicates the disabled state.

### Structural — `min_trials`
Default: `20`
Claim check: system.md section 12 instructs Claude to set `min_trials` based on the experiment's trial structure.
Verdict: **Structural / acceptable default.** 20 is a reasonable lower bound for a pilot session on any task. Claude is instructed to set it based on condition ratios. The default prevents a completely empty pilot but does not prescribe task-specific behavior.

### Structural — `max_blocks`
Default: `1`
Claim check: system.md section 12 says "typically 1."
Verdict: **Structural.** Running one block in the pilot is the universal default — see more blocks only for multi-block tasks that require it for validation. The default is task-invariant.

---

### Backward compat summary (Task 5)

All 4 cached configs (`cognitionrun_stroop`, `expfactory_stop_signal`, `expfactory_stroop`, `stopit_stop_signal`) embed explicit values for `advance_keys`, `feedback_fallback_keys`, `failure_rt_cap_fraction`, and `inhibit_wait_ms` in their JSON files. Changing the Python dataclass defaults has no effect on these configs at load time — `from_dict` reads the JSON value, not the field default. All 4 configs continue to load and operate correctly.

**Config generation gap identified:** `expfactory_stop_signal` has `failure_rt_cap_fraction=0.85` and `inhibit_wait_ms=1500` in its JSON — values identical to the old Python defaults, indicating Claude did not reason about these fields during generation. The system.md changes (marking both as **Required when `detection_condition` is set**) will force Claude to set them explicitly on future config regenerations.

### Tests added (Task 5)
- `test_advance_keys_empty_by_default`
- `test_feedback_fallback_keys_empty_by_default`
- `test_failure_rt_cap_fraction_zero_by_default`
- `test_inhibit_wait_ms_zero_by_default`

---

## `prompts/system.md` and `prompts/schema.json` — Task 6: Agnosticism review

Methodology: (1) `rg -n -i 'jspsych|psytoolkit|labjs|gorilla|cognition\.run'` across both files; (2) manual cross-check of every schema top-level property against system.md; (3) cross-check of config.py `TimingConfig` fields against schema.

---

### Significant — `firstElementChild` selector example is jsPsych-only

**Path:** `system.md` Section 1 (Selector best practices)

**Observation:** The `firstElementChild` best-practice note used `document.querySelector('#jspsych-html-keyboard-response-stimulus')?.firstElementChild` as its sole example. Claude patterns-matches on concrete examples; this biased it toward generating jsPsych container selectors even for lab.js, Gorilla, and custom HTML tasks. The section is general advice that applies to all platforms.

**Fix:** Added parallel examples for lab.js/Gorilla (`'.content-vertical-center'`) and custom HTML (`'#stimulus-container'`), framed as "inspect the source for the task's actual wrapper" to avoid over-prescribing selector names. The jsPsych example was retained as the first item.

---

### Significant — `response_window_js` schema description was a PsyToolkit tutorial

**Path:** `schema.json` → `runtime.timing.response_window_js`

**Observation:** The description devoted its entire content to PsyToolkit-specific implementation details (`psy_readkey.keys.includes(KEYCODE)`, JS keyCodes for 'b' and 'n'). The opening phrase "Required for PsyToolkit tasks where…" trained Claude to think this field is PsyToolkit-only and to skip it for jsPsych or custom-HTML tasks that also have response-window timing gaps.

**Fix:** Rewritten to lead with the platform-agnostic concept ("stimulus detection can fire BEFORE the response window opens"), then provide one example per platform type (PsyToolkit, jsPsych, custom HTML) in compact form. PsyToolkit example (`psy_readkey.keys.includes(KEYCODE)`) is retained — concrete examples improve Claude's pattern-matching — but now positioned as "one of three examples."

---

### Minor — `phase_detection.method` description implied a two-platform binary

**Path:** `schema.json` → `runtime.phase_detection.method`

**Observation:** Description read "dom_query for jsPsych/HTML tasks, js_eval for PsyToolkit/canvas tasks." This omitted lab.js and Gorilla, both of which use DOM-based detection and should use `dom_query`. The description also could mislead Claude into thinking `js_eval` is PsyToolkit's identifier rather than describing canvas tasks broadly.

**Fix:** Rewrote as "dom_query: works for jsPsych, lab.js, Gorilla, and most custom HTML tasks; js_eval: required for PsyToolkit and canvas-based tasks where DOM elements do not reflect phase transitions." Clarifies intent for each value rather than mapping to platform names.

---

### Minor — `max_no_stimulus_polls` and `completion_wait_ms` used jsPsych/PsyToolkit binary

**Paths:** `schema.json` → `runtime.timing.max_no_stimulus_polls`, `runtime.timing.completion_wait_ms`

**Observation:** Both descriptions gave jsPsych and PsyToolkit as the only two platform examples. This obscured the actual technical distinction (canvas-based vs. DOM-based rendering for polls; server-upload vs. local-only for completion wait) and omitted lab.js, Gorilla, and custom HTML from guidance.

**Fix:** Rewrote both descriptions in terms of the underlying technical distinction (canvas-based vs. DOM-based; server-upload vs. local-only) with platform examples subordinated to that framing.

---

### Significant — `trial_context_js` in system.md and executor but absent from schema

**Path:** `schema.json` → (absent) `runtime.timing.trial_context_js`

**Observation:** `trial_context_js` is documented in system.md Section 5 and is read by `executor.py` (line 380: `await page.evaluate(timing.trial_context_js)`) and stored in `config.py` `TimingConfig`. It was completely absent from `schema.json`, so Claude received no schema hint to populate it, and the field name did not appear in schema-driven documentation. This is a schema gap: the field exists in the contract between system.md and the executor but was invisible to schema-aware tooling.

**Fix:** Added `trial_context_js` to `schema.json` under `runtime.timing` with type `string`, default `""`, and a description matching the system.md definition. No system.md change needed — Section 5 already documented the field.

---

### Minor — `task_specific` in schema was an untyped open object without description

**Path:** `schema.json` → `task_specific`

**Observation:** `task_specific` was defined as `{"type": "object"}` with no `description` and no documented properties. System.md (Section 2) instructed Claude to place `key_map` and `trial_timing.max_response_time_ms` here, and the executor reads both at runtime. Additionally, `task_specific.response_key_js` is read by the executor as a global key-resolution fallback (`executor.py:123`). None of these were discoverable from the schema alone.

**Fix:** Added a `description` to `task_specific` summarizing its purpose and the two well-known executor-read sub-fields. Added explicit property schemas for `key_map` (object of string → string), `trial_timing.max_response_time_ms` (integer), and `response_key_js` (string) with descriptions. `additionalProperties` left implicit (open schema) — task-specific fields by definition vary per task.

---

### No issue — other framework mentions

The following rg hits were reviewed and found acceptable:

- `schema.json:11` (`task.platform` description): lists jsPsych, PsyToolkit, lab.js, Gorilla — balanced, all 4 platforms.
- `schema.json:222` (`pre_keypress_js`): "e.g., 'psy_expect_keyboard()' for PsyToolkit" — clearly labeled as PsyToolkit-specific.
- `schema.json:224` (`exit_pager_key`): "e.g., 'q' for PsyToolkit" — clearly labeled.
- `system.md:5` (task description): lists all 4 platforms — balanced.
- `system.md:169` (`stimulus_container_selector`): "#jspsych-content for jsPsych, `body` if unknown" — generic fallback provided.

---

### No issue — Sections 10, 11 (Temporal Effects, Between-Subject Jitter)

Both sections are purely behavioral. They describe mathematical mechanisms (AR(1), drift, noise parameters) with no platform-specific content. No framework names appear. Verified platform-invariant.

---

### No issue — Section 8 (Attention Checks) reads as optional

Section 8 opens with "If the experiment has attention checks:" — clearly conditional, not mandatory. A task without attention checks simply omits this section. No changes needed.

---

### Summary — Task 6

| Severity | Count | Fixed |
|----------|-------|-------|
| Significant | 3 | Yes |
| Minor | 3 | Yes |
| No issue | 5 | N/A |

All fixes are backward-compatible. The schema additions (`trial_context_js`, `task_specific` sub-properties) are additions only — no existing fields were removed or renamed. All 4 cached configs continue to load correctly. No executor or config.py changes — prompts/schema only.

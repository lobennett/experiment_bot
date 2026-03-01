# Fix PsyToolkit Cued Task Switching Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the PsyToolkit cued task switching bot so it completes trials and produces human-like data, matching the pattern already working for expfactory task switching.

**Architecture:** The fix is config-only for the primary deadlock, plus one small config restructure for switch-cost modeling. The executor code already supports everything needed (cue tracking, task-switching distributions, response window gating) -- the PsyToolkit config just needs to be aligned with what the executor expects. No executor code changes required.

**Tech Stack:** Python 3.11, Playwright (async), PsyToolkit JS runtime globals

---

## Background

### Root Cause

The PsyToolkit cued task switching bot completes **0 trials** in every session. Root cause is a deadlock between two gates in the executor's trial loop:

1. **`response_window_js`** checks `psy_readkey.expect_keyboard === true && psy_readkey.keys.includes(66)` -- this only becomes true during PsyToolkit's `readkey` step
2. **Stimulus detection** checks `task_color.step === 5` or `task_shape.step === 5` -- this is only true during the bitmap display step, which occurs BEFORE the readkey step

The executor checks response_window_js first; if it returns false, it `continue`s without checking stimulus detection. By the time `psy_readkey` activates (readkey step), `step` has advanced past 5. The two conditions are never simultaneously true.

### Why Other Tasks Work

- **Expfactory task switching**: Its `response_window_js` checks DOM state (`.lowerbox .fixation === null`) which overlaps with when stimuli are visible. No timing gap.
- **PsyToolkit stop signal**: Has NO `runtime` section at all, so `response_window_js` defaults to `""` (disabled). Stimulus detection alone gates trial execution.

### Secondary Issues

The config also has:
- `go_correct`/`go_error` distribution keys, which triggers the legacy (non-task-switching) path in `_resolve_rt_distribution_key` -- no switch cost modeling
- Conditions named `go_left`/`go_right` instead of task-aware names -- prevents task type extraction
- No `cue_selector_js` -- no cue-switch tracking
- No `key_map` in task_specific -- error trials fall back to pressing correct key
- No task-switching RT distributions (`task_repeat_cue_repeat`, `task_switch`, etc.)

---

## Task 1: Remove the response_window_js deadlock

**Files:**
- Modify: `cache/psytoolkit/taskswitching_cued/config.json:167-171`

**Why:** This is the critical fix. The PsyToolkit stop signal task works without `response_window_js` -- the stimulus detection selectors already encode the correct step check. Removing `response_window_js` eliminates the deadlock and lets trials execute.

**Step 1: Remove the response_window_js from the runtime section**

In `cache/psytoolkit/taskswitching_cued/config.json`, replace the entire `runtime` block:

```json
"runtime": {
    "timing": {
      "response_window_js": "(() => { try { return typeof psy_readkey !== 'undefined' && psy_readkey.expect_keyboard === true && Array.isArray(psy_readkey.keys) && psy_readkey.keys.includes(66); } catch(e) { return false; } })()"
    }
  }
```

With an empty runtime block (or remove it entirely):

```json
"runtime": {
    "timing": {}
  }
```

**Step 2: Run a single session to verify trials execute**

```bash
uv run experiment-bot psytoolkit --task taskswitching_cued 2>&1 | head -50
```

Expected: Trial log lines like `Trial 1: respond_left (go_left) cue=None` should appear. The session should complete with >0 trials and produce an `experiment_data.csv`.

**Step 3: Commit**

```bash
git add cache/psytoolkit/taskswitching_cued/config.json
git commit -m "fix: remove response_window_js deadlock from psytoolkit task switching"
```

---

## Task 2: Fix stimulus detection to use the readkey step

**Files:**
- Modify: `cache/psytoolkit/taskswitching_cued/config.json:16-44` (stimuli section)

**Why:** After Task 1 removes the response_window_js gate, `step === 5` might still be too early or too brief. In PsyToolkit, the bitmap draw step and readkey step are sequential. The stop signal config uses `step === 8` which is the readkey step for that task. We need to find the correct readkey step for the task switching experiment and use that, OR use a range that covers both the display and readkey steps.

**Step 1: Probe the PsyToolkit task switching JS globals to find the readkey step**

Run a manual non-headless session and use browser devtools, OR add a one-time debug evaluate. The key question: what is the value of `task_color.step` and `task_shape.step` when `psy_readkey.expect_keyboard === true`?

A practical approach: change the stimulus detection to check a step range instead of exact step, so it catches the readkey window:

In `cache/psytoolkit/taskswitching_cued/config.json`, replace the `respond_left` stimulus selector:

```json
"selector": "(() => { try { return (typeof task_color !== 'undefined' && task_color.step === 5 && typeof tablerow !== 'undefined' && t_colortasktable[tablerow].c3 === 1) || (typeof task_shape !== 'undefined' && task_shape.step === 5 && typeof tablerow !== 'undefined' && t_shapetasktable[tablerow].c3 === 1); } catch(e) { return false; } })()"
```

With a version that checks a step range (5-8 covers display through readkey):

```json
"selector": "(() => { try { var cs = typeof task_color !== 'undefined' ? task_color.step : -1; var ss = typeof task_shape !== 'undefined' ? task_shape.step : -1; if (cs >= 5 && cs <= 8 && typeof tablerow !== 'undefined' && t_colortasktable[tablerow].c3 === 1) return true; if (ss >= 5 && ss <= 8 && typeof tablerow !== 'undefined' && t_shapetasktable[tablerow].c3 === 1) return true; return false; } catch(e) { return false; } })()"
```

Do the same for `respond_right` (change `c3 === 1` to `c3 === 2`):

```json
"selector": "(() => { try { var cs = typeof task_color !== 'undefined' ? task_color.step : -1; var ss = typeof task_shape !== 'undefined' ? task_shape.step : -1; if (cs >= 5 && cs <= 8 && typeof tablerow !== 'undefined' && t_colortasktable[tablerow].c3 === 2) return true; if (ss >= 5 && ss <= 8 && typeof tablerow !== 'undefined' && t_shapetasktable[tablerow].c3 === 2) return true; return false; } catch(e) { return false; } })()"
```

**Step 2: Run a session and verify detection works**

```bash
uv run experiment-bot psytoolkit --task taskswitching_cued 2>&1 | grep "Trial"
```

Expected: Trial lines with `respond_left` and `respond_right` detected. If the step range is wrong (e.g., readkey is step 10), adjust the upper bound.

**Step 3: Commit**

```bash
git add cache/psytoolkit/taskswitching_cued/config.json
git commit -m "fix: widen step range for psytoolkit task switching stimulus detection"
```

---

## Task 3: Add task-aware conditions and switch-cost distributions

**Files:**
- Modify: `cache/psytoolkit/taskswitching_cued/config.json` (stimuli, response_distributions sections)

**Why:** Currently the config uses `go_left`/`go_right` conditions and `go_correct`/`go_error` distributions. This means the executor uses the legacy (flat) RT path -- no switch cost modeling. To get realistic task-switching RTs, we need:
1. Conditions that encode the task type (color vs shape) so `_resolve_rt_distribution_key` can detect switches
2. Task-switching distribution keys (`task_repeat_cue_repeat`, `task_repeat_cue_switch`, `task_switch`, `first_trial`)

**Step 1: Split stimuli into 4 conditions by task type**

Replace the 2 stimuli with 4 that distinguish color-task vs shape-task:

```json
"stimuli": [
    {
      "id": "color_left",
      "description": "Color task, left response (yellow) - press B",
      "detection": {
        "method": "js_eval",
        "selector": "(() => { try { var cs = typeof task_color !== 'undefined' ? task_color.step : -1; return cs >= 5 && cs <= 8 && typeof tablerow !== 'undefined' && t_colortasktable[tablerow].c3 === 1; } catch(e) { return false; } })()",
        "alt_method": "",
        "pattern": ""
      },
      "response": {
        "key": "b",
        "condition": "color_left"
      }
    },
    {
      "id": "color_right",
      "description": "Color task, right response (blue) - press N",
      "detection": {
        "method": "js_eval",
        "selector": "(() => { try { var cs = typeof task_color !== 'undefined' ? task_color.step : -1; return cs >= 5 && cs <= 8 && typeof tablerow !== 'undefined' && t_colortasktable[tablerow].c3 === 2; } catch(e) { return false; } })()",
        "alt_method": "",
        "pattern": ""
      },
      "response": {
        "key": "n",
        "condition": "color_right"
      }
    },
    {
      "id": "shape_left",
      "description": "Shape task, left response (circle) - press B",
      "detection": {
        "method": "js_eval",
        "selector": "(() => { try { var ss = typeof task_shape !== 'undefined' ? task_shape.step : -1; return ss >= 5 && ss <= 8 && typeof tablerow !== 'undefined' && t_shapetasktable[tablerow].c3 === 1; } catch(e) { return false; } })()",
        "alt_method": "",
        "pattern": ""
      },
      "response": {
        "key": "b",
        "condition": "shape_left"
      }
    },
    {
      "id": "shape_right",
      "description": "Shape task, right response (rectangle) - press N",
      "detection": {
        "method": "js_eval",
        "selector": "(() => { try { var ss = typeof task_shape !== 'undefined' ? task_shape.step : -1; return ss >= 5 && ss <= 8 && typeof tablerow !== 'undefined' && t_shapetasktable[tablerow].c3 === 2; } catch(e) { return false; } })()",
        "alt_method": "",
        "pattern": ""
      },
      "response": {
        "key": "n",
        "condition": "shape_right"
      }
    }
  ]
```

**Important:** With these conditions, `_resolve_rt_distribution_key` will extract:
- `"color_left"` → `task_type = "color"` (via `rsplit("_", 1)[0]`)
- `"shape_right"` → `task_type = "shape"`

This enables task-switch detection (color→shape or shape→color).

**Step 2: Replace RT distributions with task-switching keys**

Replace the `response_distributions` section:

```json
"response_distributions": {
    "task_repeat_cue_repeat": {
      "distribution": "ex_gaussian",
      "params": {
        "mu": 490,
        "sigma": 55,
        "tau": 85
      },
      "unit": "ms"
    },
    "task_repeat_cue_switch": {
      "distribution": "ex_gaussian",
      "params": {
        "mu": 510,
        "sigma": 55,
        "tau": 90
      },
      "unit": "ms"
    },
    "task_switch": {
      "distribution": "ex_gaussian",
      "params": {
        "mu": 525,
        "sigma": 60,
        "tau": 95
      },
      "unit": "ms"
    },
    "first_trial": {
      "distribution": "ex_gaussian",
      "params": {
        "mu": 525,
        "sigma": 65,
        "tau": 95
      },
      "unit": "ms"
    }
  }
```

These match the expfactory task switching distributions. They may need separate tuning later if PsyToolkit overhead differs, but they're a correct starting point.

**Step 3: Add key_map to task_specific for error trials**

Add a `key_map` entry to `task_specific`:

```json
"task_specific": {
    "paradigm": "cued_task_switching",
    "key_map": {
      "color_left": "b",
      "color_right": "n",
      "shape_left": "b",
      "shape_right": "n"
    },
    ...
}
```

This lets `_pick_wrong_key` find the alternative key for error trial generation.

**Step 4: Run tests to verify executor handles new conditions**

```bash
uv run pytest tests/test_executor.py -v -k "rt_distribution"
```

Expected: Existing tests pass (they use expfactory config). The psytoolkit config changes are config-only and don't affect existing test fixtures.

**Step 5: Commit**

```bash
git add cache/psytoolkit/taskswitching_cued/config.json
git commit -m "feat: add task-aware conditions and switch-cost distributions for psytoolkit task switching"
```

---

## Task 4: Add cue tracking via PsyToolkit JS globals

**Files:**
- Modify: `cache/psytoolkit/taskswitching_cued/config.json` (runtime.timing section)

**Why:** Without `cue_selector_js`, the executor can't distinguish cue-repeat from cue-switch within the same task. PsyToolkit's `current_task` global should contain the active task name (`"task_color"` or `"task_shape"`), which serves as the cue identity. Since there are only 2 tasks (no redundant cue words like expfactory's "Parity"/"Odd-Even"), cue switches always mean task switches for this paradigm. However, setting up the cue_selector_js correctly ensures the executor's cue tracking code path is exercised and future enhancements (if PsyToolkit adds redundant cues) would work.

**Step 1: Add cue_selector_js that reads current_task**

In the `runtime.timing` section of the config, add:

```json
"runtime": {
    "timing": {
      "cue_selector_js": "(() => { try { return typeof current_task !== 'undefined' ? current_task : ''; } catch(e) { return ''; } })()"
    }
  }
```

Note: `current_task` is set by PsyToolkit before each trial to the task object name (e.g., `"task_color"` or `"task_shape"`). If this global doesn't exist or has a different name, the fallback returns `''` which the executor treats as `None` (no cue tracking, graceful degradation).

**Step 2: Run a session and verify cue tracking appears in logs**

```bash
uv run experiment-bot psytoolkit --task taskswitching_cued 2>&1 | grep "cue="
```

Expected: Log lines showing `cue='task_color'` or `cue='task_shape'` (or `cue=None` if the global doesn't exist -- still functional, just without cue tracking).

**Step 3: Commit**

```bash
git add cache/psytoolkit/taskswitching_cued/config.json
git commit -m "feat: add cue tracking for psytoolkit task switching via current_task global"
```

---

## Task 5: Remove stop_accuracy from performance (not a stop signal task)

**Files:**
- Modify: `cache/psytoolkit/taskswitching_cued/config.json:66-71` (performance section)

**Why:** The config has `"stop_accuracy": 0.5` which is meaningless for a task-switching paradigm (there are no stop trials). While the executor ignores it for non-stop tasks, cleaning it up prevents confusion.

**Step 1: Update performance section**

```json
"performance": {
    "go_accuracy": 0.92,
    "stop_accuracy": 0,
    "omission_rate": 0.005,
    "practice_accuracy": 0.90
  }
```

Note: `stop_accuracy` is kept at 0 (not removed) because the `PerformanceConfig` dataclass requires it. Omission rate lowered from 0.03 to 0.005 to match real data benchmarks.

**Step 2: Commit**

```bash
git add cache/psytoolkit/taskswitching_cued/config.json
git commit -m "fix: clean up performance params for psytoolkit task switching"
```

---

## Task 6: End-to-end verification batch

**Files:** None (verification only)

**Step 1: Run a small batch of psytoolkit task switching sessions**

```bash
bash scripts/launch.sh --platform psytoolkit --task task_switching --count 3 --headless --stagger 5
```

**Step 2: Verify sessions completed**

```bash
for d in output/psytoolkit/cued_task_switching/2026-02-26_*; do
  echo "$(basename $d): $(wc -l < $d/experiment_data.csv 2>/dev/null || echo 'NO DATA')"
done
```

Expected: Each session should have 50-60 lines of data (50 test trials + header).

**Step 3: Run analysis and check metrics**

```bash
uv run scripts/check_data.py --save 2>&1 | grep -A 30 "psytoolkit/task_switching"
```

Expected:
- Overall accuracy: 85-95%
- RTs in 500-750ms range
- Positive switch cost
- Trial count: 50-60 per session

**Step 4: Verify other tasks still work**

```bash
bash scripts/launch.sh --platform expfactory --count 1 --headless --stagger 5
bash scripts/launch.sh --platform psytoolkit --task stop_signal --count 1 --headless --stagger 5
```

Check that expfactory task switching, expfactory stop signal, and psytoolkit stop signal all still produce valid data.

**Step 5: Final commit (if any iteration was needed)**

```bash
git add -A
git commit -m "chore: verify psytoolkit task switching fix across all task types"
```

---

## File Change Summary

| File | Changes |
|------|---------|
| `cache/psytoolkit/taskswitching_cued/config.json` | Remove response_window_js, widen step range, split stimuli into 4 task-aware conditions, add switch-cost distributions, add key_map, add cue_selector_js, clean up performance |

## Risk Assessment

- **Low risk to other tasks:** All changes are to the psytoolkit task switching config only. No executor code changes. Expfactory and psytoolkit stop signal configs are untouched.
- **Step range uncertainty:** The `step >= 5 && step <= 8` range is an educated guess based on the stop signal config using `step === 8`. If the task switching experiment uses different step numbering, Task 2's verification will catch it and the range can be adjusted.
- **`current_task` global uncertainty:** If PsyToolkit doesn't expose this global or names it differently, cue tracking gracefully degrades to `None` (all task-stay trials use `task_repeat_cue_repeat`). This is a nice-to-have, not a blocker.

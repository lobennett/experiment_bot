# Cross-Platform Test Results & Proposed Fixes

## Date: 2026-02-28

## Overview

Tested the bot on 4 new experiment URLs (2 Stroop, 2 Stop Signal) across 3 platforms.
Expfactory tasks work well. jsPsych standalone tasks (Cognition.run, STOP-IT) work with
minor config fixes. PsyToolkit tasks fail due to canvas-based rendering.

---

## Test Results

### Working Well

| Task | URL | Platform | Trials | Notes |
|------|-----|----------|--------|-------|
| Stroop (rDoC) | `deploy.expfactory.org/preview/10/` | Expfactory (jsPsych) | 130 | Congruent 536ms, Incongruent 657ms. Textbook Stroop effect. |
| Stop Signal (rDoC) | `deploy.expfactory.org/preview/9/` | Expfactory (jsPsych) | 117 | Go 616ms, Stop failures 575ms. Good go/stop ratio. |
| STOP-IT | `kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html` | Standalone jsPsych 6.0.5 | 147+ (still running) | Verbruggen & Logan canonical implementation. Detects go_left, go_right, stop_right, stop_left via `<img>` elements. Running through 288-trial protocol (32 practice + 4x64 experimental). |
| Cognition.run Stroop | `strooptest.cognition.run/` | jsPsych 7.3.1 on Cognition.run | 15 Stroop + 18 fixation | Completed 30-trial protocol. Needed one config fix (see below). |

### Failed (PsyToolkit — canvas rendering)

| Task | URL | Issue |
|------|-----|-------|
| PsyToolkit Stroop | `psytoolkit.org/.../experiment_stroop_en.html` | 44/56 trials detected, 42:2 congruent:incongruent skew. Canvas pixel sampling can't distinguish ink colors reliably. |
| PsyToolkit Stop Signal | `psytoolkit.org/.../experiment_stopsignal.html` | 54 trials detected, but 0 registered by experiment. Wrong key mapping (z// vs actual keys). Canvas arrow direction detection failed. |

---

## Config Fixes Applied Manually (cached configs)

### 1. Cognition.run Stroop — wrong element selector

**Cache**: `cache/cognitionrun_stroop/config.json`

**Problem**: Claude generated `#jspsych-html-keyboard-response-stimulus span` selectors, but
the experiment renders stimuli as `<p style="font-size:60px;color: yellow">red</p>`.

**Fix**: Replace all `span` with `p` in stimulus detection selectors and phase detection
expressions (12 occurrences).

**Root cause**: Claude assumed jsPsych wraps stimulus text in `<span>` elements. In this
experiment, the author used `<p>` tags in the stimulus HTML string:
```js
stimulus: '<p style="color: '+values.colour+'">'+values.text+'</p>'
```

### 2. PsyToolkit Stop Signal — wrong response_window_js

**Cache**: `cache/5a04b1c025500272/config.json`

**Problem**: `response_window_js` checked specific keycodes `psy_readkey.keys.includes(90)`,
but PsyToolkit uses different internal key codes.

**Fix**: Changed to generic `psy_readkey.keys.length > 1` (same pattern as working PsyToolkit
Stroop config).

### 3. PsyToolkit Stop Signal — completion threshold too low

**Problem**: `outputdata.length > 100` triggers after ~4 trials.

**Fix**: Changed to line-count based: `outputdata.split('\n').filter(...).length > 55`.

---

## Generalizable Code Changes Needed

These are patterns that recur across platforms and should be fixed in the bot's source code
or prompt/schema, not just in individual cached configs.

### Issue 1: Stimulus element selector fragility

**Symptom**: Claude generates selectors for a specific HTML element tag (`span`, `p`, `div`)
but the actual experiment uses a different tag.

**Affected files**: `src/experiment_bot/prompts/system.md`, `src/experiment_bot/prompts/schema.json`

**Proposed fix**: Update the system prompt to instruct Claude to use tag-agnostic selectors.
Instead of `querySelector('#jspsych-html-keyboard-response-stimulus span')`, prefer
`querySelector('#jspsych-html-keyboard-response-stimulus')?.firstElementChild` or
`querySelector('#jspsych-html-keyboard-response-stimulus *')` when the tag type is uncertain.
Add guidance: "Do not assume the stimulus is wrapped in a specific tag. Use `firstElementChild`
or `*` wildcard selectors unless the experiment source explicitly shows the tag."

### Issue 2: Fixation crosses detected as trials

**Symptom**: The fixation cross (`+`) matches as a stimulus and gets logged as a trial,
inflating trial counts and producing trials with no meaningful response.

**Affected files**: `src/experiment_bot/core/executor.py` (trial loop), possibly
`src/experiment_bot/core/stimulus.py`

**Proposed fix options**:
- **Option A (executor)**: Skip stimuli with `response.key == null` in the trial loop —
  don't log them as trials, don't sample RT. Just continue polling.
- **Option B (prompt)**: Instruct Claude not to include fixation/ITI as stimuli in the config.
  They aren't behaviorally meaningful — only include stimuli that require a response.
- **Option C (both)**: Prompt says don't include fixation, executor also guards against
  null-key stimuli reaching the trial execution path.

**Recommendation**: Option C. The prompt should exclude fixation, but the executor should
also be robust to it.

### Issue 3: PsyToolkit response_window_js uses specific keycodes

**Symptom**: Claude generates `psy_readkey.keys.includes(KEYCODE)` for PsyToolkit experiments,
but the internal keycodes may differ from standard JavaScript keycodes.

**Affected files**: `src/experiment_bot/prompts/system.md`

**Proposed fix**: Add PsyToolkit-specific guidance to the prompt:
"For PsyToolkit experiments, use `psy_readkey.keys.length > 1` as the response_window_js.
Do NOT check for specific keycodes — PsyToolkit's internal key representation may differ
from standard JavaScript keyCode values."

### Issue 4: PsyToolkit canvas pixel detection is unreliable

**Symptom**: Claude generates canvas pixel-sampling JS to detect stimuli by color/shape,
but the detection is imprecise — colors overlap, arrow directions can't be distinguished,
and condition classification is heavily skewed.

**Affected files**: `src/experiment_bot/prompts/system.md`

**Proposed fix**: This is fundamental to how PsyToolkit works (all rendering is on `<canvas>`).
Two approaches:
- **Short term**: Add PsyToolkit-specific guidance to read runtime JS globals
  (`t_{table}[tablerow]`, `psy_readkey.possiblekeys`) for trial state instead of canvas pixels.
  The `psychtoolkit_bot/` package already does this successfully.
- **Long term**: If the bot should support PsyToolkit generically, integrate a
  `state_reader`-style module that reads PsyToolkit JS globals for stimulus identity,
  bypassing canvas entirely.

### Issue 5: Navigation re-runs full sequence on phase re-detection

**Symptom**: After experiment ends, if an instruction/feedback phase is re-detected (common
in PsyToolkit), the navigator re-runs the full navigation sequence including clicking the
start button (which is now hidden), causing 10s timeouts per loop iteration.

**Affected files**: `src/experiment_bot/navigation/navigator.py`, possibly
`src/experiment_bot/core/executor.py`

**Proposed fix**: After the trial loop has started (i.e., at least one trial has been
executed), do not re-run the full navigation sequence. Instead, only press advance keys
when instructions/feedback is detected post-trial-loop. The navigator should have a
"post_trial" mode that only does simple key presses, not the full click/wait/focus sequence.

### Issue 6: Completion detection for PsyToolkit using outputdata.length

**Symptom**: Claude generates `outputdata.length > N` but outputdata grows per-trial at
~20-25 chars/line, making character-based thresholds unreliable.

**Affected files**: `src/experiment_bot/prompts/system.md`

**Proposed fix**: Add guidance: "For PsyToolkit completion detection, use line-count based
checks: `outputdata.split('\\n').filter(function(l){return l.trim().length>0}).length > N`
where N is approximately 80% of the expected total trial count. Do NOT use
`outputdata.length > N` as character counts are unreliable."

---

## launch.sh Registry (updated)

```bash
TASKS=(
    "https://deploy.expfactory.org/preview/9/|stop signal task|expfactory_stop_signal"
    "https://deploy.expfactory.org/preview/10/|stroop color-word task|expfactory_stroop"
    "https://deploy.expfactory.org/preview/2/|cued task switching|expfactory_task_switching"
    "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html|stop signal task|psytoolkit_stop_signal"
    "https://www.psytoolkit.org/experiment-library/experiment_stroop_en.html|stroop color-word task|psytoolkit_stroop"
    "https://www.psytoolkit.org/experiment-library/experiment_taskswitching_cued.html|cued task switching|psytoolkit_task_switching"
    "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html|stop signal task|stopit_stop_signal"
    "https://strooptest.cognition.run/|stroop color-word task|cognitionrun_stroop"
)
```

## Output Locations (check these for final results)

- STOP-IT log: `/tmp/run_stopit_stopsignal.log`
- STOP-IT data: `output/stop_signal_task/2026-02-28_15-53-*/` (look for most recent)
- Cognition.run Stroop data: `output/stroop_color-word_task/2026-02-28_15-57-33/`
- Expfactory Stroop data: `output/stroop_color-word_task_(rdoc)/2026-02-28_15-16-11/`
- Expfactory Stop Signal data: `output/stop_signal_task_(rdoc)/2026-02-28_15-16-44/`

## Cached Configs (with manual fixes applied)

- `cache/cognitionrun_stroop/config.json` — span→p fix applied
- `cache/stopit_stop_signal/config.json` — worked without manual fix
- `cache/5a04b1c025500272/config.json` — PsyToolkit stop signal, response_window_js + complete fix
- `cache/6be7d2a81d82da43/config.json` — PsyToolkit Stroop, instructions/feedback/complete fix

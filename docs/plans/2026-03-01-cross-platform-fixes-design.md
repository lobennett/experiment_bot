# Cross-Platform Fixes Design: Selector Fragility & Fixation Filtering

## Date: 2026-03-01

## Scope

Two generalizable issues from the 2026-02-28 cross-platform test results. Both affect
jsPsych tasks across multiple platforms (ExpFactory, Cognition.run, STOP-IT). PsyToolkit
issues (3-6 from the original plan) are deferred.

---

## Issue 1: Stimulus Element Selector Fragility

### Problem

Claude generates CSS selectors targeting specific HTML tags (`span`, `p`, `div`) inside
jsPsych stimulus containers. Different experiment authors use different tags in their
stimulus HTML strings. The cognition.run stroop required 12 manual `span→p` replacements.

### Fix: Prompt guidance in `system.md`

Add guidance after the detection methods list (around line 22) instructing Claude to use
tag-agnostic selectors:

- Prefer `firstElementChild` over specific tag selectors
- Use `querySelector('#container *')` wildcard when tag is uncertain
- Only use specific tags when the experiment source explicitly shows them

### Files changed

- `src/experiment_bot/prompts/system.md` — add selector guidance paragraph

---

## Issue 2: Fixation Crosses Detected as Trials

### Problem

Claude sometimes includes fixation crosses (`+`) and ITI periods as stimulus entries with
`response.key: null` and `condition: "no_response"`. While the executor skips keypresses
for these, they still count as stimulus matches that reset the `consecutive_misses` counter,
and they get logged/counted unnecessarily.

### Fix A: Prompt guidance in `system.md`

Add guidance instructing Claude not to include non-response stimuli (fixation, ITI, blank
screens) in the stimuli array. Only stimuli requiring a participant response should be listed.

### Fix B: Executor guard in `executor.py`

In the trial loop, when a stimulus is detected but is not a trial stimulus (no RT
distribution, null response key), do NOT reset `consecutive_misses`. This prevents
fixation matches from masking genuine "no stimulus" periods that should trigger advance
behavior.

### Files changed

- `src/experiment_bot/prompts/system.md` — add fixation exclusion guidance
- `src/experiment_bot/core/executor.py` — guard `consecutive_misses` reset for non-trial stimuli

---

## Implementation Plan

### Step 1: Update `system.md` with selector guidance

Add after the detection methods enumeration (line ~22):

```
**Selector best practices**: Do not assume the stimulus is wrapped in a specific HTML tag
(`span`, `p`, `div`). Authors use different tags in their stimulus HTML. Prefer tag-agnostic
selectors: use `firstElementChild` to get the first child element, or `querySelector('*')`
within a container, rather than `querySelector('span')` or `querySelector('p')`. Only target
a specific tag if the experiment source explicitly defines it.
```

### Step 2: Update `system.md` with fixation exclusion guidance

Add to the stimulus-response mappings section:

```
**Do NOT include fixation crosses, inter-trial intervals, or blank screens as stimuli.**
Only include stimuli that require a participant response. Fixation/ITI detection should be
handled through `response_window_js` or phase detection, not the stimuli array.
```

### Step 3: Add executor guard for non-trial stimulus matches

In `executor.py` `_trial_loop`, after the stimulus match is found and before
`consecutive_misses = 0`, check if the match is a trial stimulus. If it's a non-trial match
(no RT distribution, null key), skip resetting `consecutive_misses` and continue without
logging a trial.

### Step 4: Run tests

Verify existing tests pass. No new tests needed — these are prompt changes and a small
guard condition.

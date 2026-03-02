# How Experiment Bot Works

This document explains what happens under the hood when experiment-bot runs a web-based cognitive experiment, from invocation to data output.

## Overview

Experiment-bot is a general-purpose agent that completes web-based cognitive psychology experiments (Stroop, stop signal, task switching, etc.) by simulating realistic human behavior. It requires **no task-specific code** — a single Claude API call analyzes the experiment's source code and produces a JSON configuration that drives all behavior.

```
CLI invocation
  -> Cache check (hit? skip to executor)
  -> Scrape experiment HTML + linked JS/CSS
  -> Claude Opus analyzes source, returns TaskConfig JSON
  -> Cache config for reuse
  -> Apply between-subject jitter
  -> Playwright browser opens experiment
  -> Navigate instruction screens
  -> Poll-detect-respond trial loop
  -> Capture experiment data
  -> Save outputs
```

---

## 1. What the Bot Knows Before a Run

Before the trial loop starts, the bot has **zero hardcoded knowledge** about any specific experiment. Everything it knows comes from one of two sources:

1. **The Claude-generated config** (`TaskConfig`), produced from the experiment's own source code.
2. **The user-provided hint** (optional), a short phrase like `"stop signal task"` or `"stroop color-word task"`.

The **hint flag** (`--hint`) gives Claude context about the task's psychological paradigm. This helps Claude identify the correct stimulus-response mappings, select literature-based RT distributions, and recognize stop signal or task-switching structure — especially when the experiment's HTML/JS alone is ambiguous. The hint is not required, but improves config quality.

The **label flag** (`--label`) controls cache storage — configs are saved under `cache/{label}/config.json` so repeated runs of the same experiment skip the Claude API call.

---

## 2. Config Generation: The Claude API Call

When no cached config exists (or `--regenerate-config` is set), the bot:

1. **Scrapes the experiment page** — fetches the HTML and up to 30KB from each linked JS/CSS resource.
2. **Sends everything to Claude Opus** with a system prompt (`prompts/system.md`) and a JSON schema (`prompts/schema.json`).

Claude receives instructions to:

- Identify the cognitive task type and cite relevant literature.
- Find every possible stimulus in the DOM/JS and define how to detect it (CSS selector, JS expression, text pattern, or canvas state).
- Determine the correct keyboard response for each stimulus condition.
- Provide ex-Gaussian RT distribution parameters (mu, sigma, tau) grounded in published data.
- Set per-condition accuracy and omission rate targets from the literature.
- Map the full navigation sequence (clicks, keypresses, waits) from page load to the first trial.
- Write JavaScript expressions for phase detection (is the experiment showing instructions? feedback? is it complete?).
- Configure data capture (how to extract the experiment's recorded CSV/JSON after completion).

Claude returns a single JSON object conforming to the schema. This is parsed into a `TaskConfig` — the dataclass hierarchy that controls all bot behavior.

---

## 3. The TaskConfig Structure

A `TaskConfig` contains:

| Section | What It Controls |
|---|---|
| `task` | Metadata: task name, psychological constructs, literature citations, framework detected |
| `stimuli` | List of stimulus definitions — each with a detection method, CSS/JS selector, response key, and condition label |
| `response_distributions` | Ex-Gaussian RT parameters per condition (e.g., `congruent`, `incongruent`, `stop_failure`) |
| `performance` | Per-condition accuracy (e.g., go: 0.95, stop: 0.50) and omission rates |
| `navigation` | Ordered steps to navigate from page load to first trial (click buttons, press keys, wait) |
| `runtime.phase_detection` | JS expressions evaluated each poll cycle to determine experiment phase |
| `runtime.timing` | Poll interval, response window gating, RT floor, fatigue drift, autocorrelation |
| `runtime.trial_interrupt` | Trial-level interrupt/inhibition config (detection condition, failure RT, wait times) |
| `runtime.data_capture` | How to extract the experiment's recorded data after completion |
| `runtime.advance_behavior` | Keys/buttons to press to advance past instruction and feedback screens |
| `task_specific` | Arbitrary fields like `key_map` (mapping conditions to keyboard keys) |

---

## 4. Response Time Generation

Response times are sampled from the **ex-Gaussian distribution**, which is the standard model for human RT data in cognitive psychology. It combines:

- A **Gaussian component** (mu, sigma) — the bulk of the RT distribution
- An **Exponential tail** (tau) — the characteristic rightward skew of slow responses

**Sampling formula:** `RT = Normal(mu, sigma) + Exponential(1/tau)`

Typical parameters for a healthy adult on a go trial: mu = 400-500ms, sigma = 50-80ms, tau = 60-100ms.

### Temporal effects applied to raw samples

After sampling, three adjustments model realistic human behavior:

1. **AR(1) autocorrelation** (phi = 0.25): Each RT is pulled toward the previous trial's RT. This models the "sticky" timing humans exhibit — if you respond fast on one trial, you tend to respond fast on the next.

2. **Fatigue drift** (+0.15ms per trial): RTs gradually increase across the experiment, simulating fatigue and declining focus.

3. **RT floor** (150ms): No RT can fall below 150ms, which is the physiological lower bound for a keypress response.

### Between-subject jitter

Before each run, `jitter_distributions()` applies random offsets to simulate individual differences:

- A shared mu shift (SD ~ 40ms) affects all conditions equally, preserving task structure (e.g., Stroop effect size).
- Per-condition mu jitter (SD ~ 15ms) adds additional variance.
- Sigma and tau are scaled by a random multiplier (0.85-1.15x).
- Accuracy targets are jittered by ~1.5-3% depending on baseline.

This means two runs of the same experiment will produce different (but realistic) data, mirroring natural variability across human participants.

---

## 5. Accuracy and Error Simulation

On each trial, the bot makes three sequential decisions:

### Step 1: Should I omit this response?
A random draw against the per-condition omission rate (e.g., 2% for go trials). If omitting, the bot does nothing and waits for the trial to time out.

### Step 2: Should I respond correctly?
A random draw against the per-condition accuracy target (e.g., 95% for congruent Stroop, 88% for incongruent). These targets come from published literature via Claude's config.

### Step 3: What key do I press?
- **Correct response**: Press the key mapped to this stimulus condition.
- **Error response**: Press a randomly chosen wrong key from the available response keys.
- **Post-error slowing**: If the previous trial was an error, add 20-60ms to the current RT (a well-documented human phenomenon).

---

## 6. Trial Interrupt / Inhibition

When `runtime.trial_interrupt.detection_condition` is set (e.g., `"stop"` for a stop signal task), the bot implements a **trial-level interrupt** using the independent race model (Logan & Cowan, 1984):

1. When a go stimulus appears, the bot begins waiting for the sampled go RT.
2. **During that wait**, the bot polls the DOM for the interrupt stimulus (e.g., an audio cue element or a colored shape overlaid on the go stimulus).
3. If the interrupt stimulus appears:
   - A random draw determines whether inhibition succeeds (based on `performance.accuracy` for the interrupt condition, typically ~50%).
   - **Successful inhibition**: The bot withholds the response entirely and waits (`inhibit_wait_ms`).
   - **Failed inhibition**: The bot samples an RT from the `failure_rt_key` distribution (which is faster than go RTs, matching the race model prediction) and presses the go key after that delay.
4. If no interrupt stimulus appears during the go RT wait, the bot responds normally.

The interrupt check builds a JavaScript expression that combines all stimuli tagged with the detection condition (e.g., `document.querySelector('img[src*="stop_left"]') !== null || document.querySelector('img[src*="stop_right"]') !== null`) and evaluates it via `page.evaluate()`. This mechanism generalizes to any paradigm with trial-level response inhibition (stop signal, go/no-go, etc.).

---

## 7. The Trial Loop

The core execution is a continuous polling loop (`_trial_loop`) that runs until the experiment is complete:

```
while not complete:
    1. Detect current phase (JS expressions)
       - COMPLETE -> exit loop
       - ATTENTION_CHECK -> parse prompt, press correct key
       - FEEDBACK -> click continue button or press advance key
       - INSTRUCTIONS -> re-run navigation steps

    2. Check response window (if configured)
       - If closed (e.g., fixation cross showing): skip, keep polling
       - If open: proceed to stimulus detection

    3. Detect stimulus (StimulusLookup.identify)
       - Try each stimulus rule in order
       - First match wins (stop signals ordered before go stimuli)
       - No match: increment miss counter, press advance keys periodically

    4. Skip non-trial stimuli
       - Fixation crosses and ITI markers have no response key
       - These are detected but ignored without resetting the miss counter

    5. Execute trial
       - Sample RT, decide accuracy/omission
       - Handle stop signal if applicable
       - Press key (or withhold)
       - Log trial data

    6. Wait for trial end
       - Poll until response window closes
       - Prevents re-detecting the same stimulus
```

The poll interval is typically 20ms, meaning the bot checks for stimuli ~50 times per second.

---

## 8. Stimulus Detection

Each stimulus in the config has a detection method:

| Method | How It Works | Example |
|---|---|---|
| `dom_query` | CSS selector via `page.query_selector()` — returns true if element exists | `img[src*='circle']` |
| `js_eval` | JavaScript expression via `page.evaluate()` — returns truthy value | `document.querySelector('#stim')?.textContent === 'RED'` |
| `text_content` | CSS selector + string pattern match on `textContent` | selector: `#stimulus`, pattern: `"red"` |
| `canvas_state` | JavaScript expression (same as js_eval, used for canvas experiments) | `offscreenCanvas.getContext('2d').getImageData(...)` |

Stimulus rules are evaluated in config order. This ordering matters: **stop signals must be checked before go stimuli** to ensure the bot can detect a stop signal overlaid on a go stimulus.

---

## 9. Phase Detection

The bot evaluates JavaScript expressions each poll cycle to determine the experiment's current state. These expressions are written by Claude based on the experiment's source code.

Phases are checked in priority order:
1. **complete** — e.g., `document.querySelector('.jspsych-content')?.textContent.includes('finished')`
2. **loading** — start screen visible
3. **instructions** — instruction page displayed
4. **attention_check** — attention check prompt showing
5. **feedback** — between-block feedback screen
6. **practice** — practice block active
7. **test** (default fallback) — main experiment trials

If a JS expression throws (e.g., execution context destroyed because the page navigated), the bot interprets this as task completion.

---

## 10. Navigation

Before the trial loop starts, the bot follows a scripted navigation sequence to reach the first trial. Claude generates this from the experiment's source code.

Navigation phases support these action types:

| Action | What It Does |
|---|---|
| `click` | Click a button by CSS selector (with human-like reading delay of 3-8s) |
| `keypress` | Press a key (optionally running JS first, e.g., to re-enable keyboard listeners) |
| `wait` | Sleep for a fixed duration |
| `sequence` | Execute nested steps in order |
| `repeat` | Repeat nested steps up to 20 times (for multi-page instructions) |

---

## 11. Data Capture and Output

After the trial loop exits (phase = COMPLETE), the bot captures the experiment's own recorded data:

- **`js_expression`**: Evaluate a JS expression that returns the full dataset as a string (common in jsPsych: `jsPsych.data.get().csv()`)
- **`button_click`**: Click a "show data" button, then scrape the result element's text content

The captured data is saved alongside the bot's own trial logs:

```
output/{task_name}/{timestamp}/
  config.json          # The full TaskConfig used for this run
  bot_log.json         # Bot's trial-by-trial log (stimulus, condition, RT, key, accuracy, etc.)
  experiment_data.csv  # The experiment's own recorded data (captured from the page)
  run_metadata.json    # Run metadata (URL, trial count, headless flag)
```

The **bot_log.json** records what the bot decided and did. The **experiment_data.csv** records what the experiment framework measured. Comparing the two can reveal timing discrepancies between the bot's intended RT and the experiment's recorded RT.

---

## 12. How General Is the Source Code?

The bot contains **no task-specific or platform-specific code**. Every behavioral difference between running a Stroop task on ExpFactory vs. a stop signal task on STOP-IT comes from the Claude-generated config.

The source code is general across:

- **Task paradigms**: Simple go trials, stop signal, go/no-go, task switching — all handled by the same executor with config-driven branching.
- **Experiment platforms**: jsPsych, PsyToolkit, lab.js, Gorilla, custom HTML — the bot interacts with any DOM via configurable selectors and JS expressions.
- **Stimulus types**: Visual elements (images, text, colored shapes), canvas-rendered stimuli, and JS-state-based stimuli.
- **Response types**: Single keypresses with configurable key mappings.

To support a new experiment, the only requirement is that Claude can analyze its source code and produce a valid `TaskConfig`. No code changes are needed.

---

## Key Design Decisions

**Why ex-Gaussian?** It is the most widely used parametric model for human RT distributions in cognitive psychology. The exponential tail captures the characteristic rightward skew that simpler distributions (normal, uniform) cannot model.

**Why poll-based detection?** Web experiments render stimuli asynchronously. Polling at 20ms intervals (50Hz) reliably catches stimulus onset while remaining lightweight. Event-based approaches would require hooking into each framework's internal event system, breaking generality.

**Why Claude for config generation?** Experiment source code varies enormously — different frameworks, different DOM structures, different JS patterns. A single Claude API call replaces what would otherwise be hundreds of per-experiment parsers. The hint flag provides a lightweight way to guide analysis without writing custom code.

**Why cache configs?** The Claude API call takes 15-30 seconds and costs money. Once a config is generated and validated, it can be reused indefinitely for the same experiment URL.

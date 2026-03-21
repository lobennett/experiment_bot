# How Experiment Bot Works

Experiment-bot takes a URL, scrapes the experiment's HTML and JavaScript source, sends it to Claude which infers all behavioral parameters from the cognitive psychology literature, then executes the task via Playwright with humanlike timing and accuracy — requiring no task-specific code.

---

## 1. Overview

The bot is a zero-shot agent: it has never seen the experiment it is about to run, and it contains no hardcoded knowledge of any specific task, paradigm, or platform. A single Claude API call analyzes the experiment's source code and produces a `TaskConfig` JSON object that fully specifies all behavioral parameters. The executor reads that config and runs. Nothing more is added.

The key question this document answers: **how much of the humanlike behavior was engineered vs. emergent from the bot's own reasoning?** The answer is: the execution mechanics are engineered; the behavioral parameters are entirely Claude's.

---

## 2. Information Flow — What the Bot Knows and When

### At build time (Python code)

The Python codebase contains only execution mechanics:

- How to drive a Playwright browser (navigate, click, keypress, poll the DOM).
- How to sample from an ex-Gaussian distribution given mu, sigma, tau.
- How to apply temporal effects to a sequence of RT samples — *if* those effects are enabled and parameterized in the config.
- How to implement a race model for trial-level response inhibition — *if* a stop-signal condition is configured.

The code contains **no behavioral assumptions** and **no default parameter values** for any task. If `temporal_effects.autocorrelation.enabled` is false, AR(1) is not applied. If `between_subject_jitter.rt_mean_sd_ms` is 0, no jitter is applied. All defaults are off or zero.

### At config generation (Claude API call)

Claude receives the experiment's full HTML and linked JavaScript source, a structural JSON schema defining the `TaskConfig` format, and an optional short hint from the user (e.g., `"stop signal task"`).

Claude infers from the source code and its knowledge of the cognitive psychology literature:

- The task type, psychological constructs measured, and relevant reference literature.
- Every stimulus present in the experiment, with detection rules for each.
- The correct keyboard response for each stimulus condition.
- Ex-Gaussian RT distribution parameters (mu, sigma, tau) per condition, grounded in published norms.
- Per-condition accuracy and omission rate targets.
- Which temporal effects to enable and with what parameters — e.g., whether post-error slowing is documented for this task type, whether 1/f noise is appropriate.
- Between-subject jitter parameters reflecting natural individual differences.
- The full navigation sequence from page load to the first trial.
- JavaScript expressions for phase detection (instructions, feedback, task complete, etc.).
- How to extract the experiment's recorded data after completion.

Claude's reasoning for each behavioral decision is captured in `rationale` fields within the config. The config is the artifact — the reasoning is transparent and inspectable.

### At runtime

The executor reads the config and applies it mechanically. Between-subject jitter is applied once before the trial loop begins, producing the session's parameter set. No further reasoning occurs. The executor does not adapt, infer, or make decisions beyond those encoded in the config.

---

## 3. Config Generation Pipeline

```
CLI invocation
  -> Cache check (hit? skip to executor)
  -> Scrape experiment HTML + linked JS/CSS (up to 30KB per file)
  -> Claude Opus: structural prompt (schema) + behavioral prompt (literature knowledge)
  -> Parse response into TaskConfig
  -> Pilot validation (see below)
  -> Cache refined config under cache/{label}/config.json
  -> Apply between-subject jitter (deep copy — cached config is not mutated)
  -> Playwright browser opens experiment
  -> Navigate instruction screens (config-driven)
  -> Poll-detect-respond trial loop
  -> Capture experiment data
  -> Save outputs
```

**Scrape.** The bot fetches the experiment page HTML and follows `<script src>` and `<link href>` tags, downloading each linked resource up to a size limit. This provides Claude with the complete source.

**Claude.** The system prompt (`prompts/system.md`) instructs Claude to analyze the source as a cognitive psychology researcher, identify the task paradigm, and populate every field in the schema. The schema (`TaskConfig` structure) constrains the output format. The hint flag provides paradigm context when the source alone is ambiguous.

**Pilot validation.** After initial config generation, the bot runs a short pilot session against the live experiment. The pilot navigates instruction screens, polls for stimuli, and records which selectors matched, which conditions were observed, and captures DOM snapshots of the actual rendered HTML. If selectors fail or conditions are missing, the diagnostic report — including the real DOM structure — is sent back to Claude for targeted config refinement (max 2 iterations). This loop runs once per novel task; cached configs skip the pilot entirely.

**Cache.** The refined config is written to `cache/{label}/config.json`. Subsequent runs skip the API call and pilot entirely. Use `--regenerate-config` to force regeneration.

**Jitter.** `jitter_distributions()` applies random offsets drawn from Claude-specified distributions to simulate individual differences. A shared mu shift moves all conditions together (preserving effect sizes like the Stroop effect). Per-condition shifts, sigma/tau scaling, and accuracy jitter add additional variance.

**Execute.** The executor reads the jittered config and runs the trial loop.

---

## 4. TaskConfig Schema

`TaskConfig` is a dataclass hierarchy. All behavioral sections are populated by Claude; runtime is a mix of Claude-inferred and structurally required fields.

| Section | Contents |
|---|---|
| `task` | Name, psychological constructs, reference literature, platform detected |
| `stimuli` | Stimulus definitions — each with a detection method, selector/expression, response key, and condition label |
| `response_distributions` | Ex-Gaussian parameters (mu, sigma, tau) per condition, e.g., `congruent`, `incongruent`, `stop_signal` |
| `performance` | Per-condition accuracy and omission rate targets (0–1 fractions) |
| `navigation` | Ordered steps to reach the first trial (click, keypress, wait, sequence, repeat) |
| `temporal_effects` | Six named slots — **Claude-determined** whether to enable each and with what parameters |
| `between_subject_jitter` | Jitter parameters for between-session variability — **Claude-determined** |
| `runtime` | Phase detection JS, timing, advance behavior, trial interrupt, data capture, attention check |

The `temporal_effects` and `between_subject_jitter` sections are fully Claude-authored. The Python code implements the mechanics of each effect; Claude decides which effects are appropriate for the task and sets the parameter values.

---

## 5. Response Time Modeling

### Ex-Gaussian distribution

Response times are sampled from the **ex-Gaussian distribution**, the standard parametric model for human RT data in cognitive psychology (Luce, 1986; Whelan, 2008). It combines a Gaussian component (mu, sigma) representing the bulk of the distribution with an exponential tail (tau) capturing the characteristic rightward skew of slow responses.

**Sampling:** `RT = Normal(mu, sigma) + Exponential(tau)`

Claude sets mu, sigma, and tau for each condition by drawing on published RT norms for the task paradigm. Typical values for a healthy adult on a go trial: mu = 400–500 ms, sigma = 50–80 ms, tau = 60–100 ms.

### Temporal effects (Claude-determined)

After sampling a raw RT, the executor may apply sequential temporal adjustments. Claude decides which of the following six effects to enable and parameterizes each from the literature:

| Effect | What It Models |
|---|---|
| `autocorrelation` (AR(1), phi) | Trial-to-trial serial dependence — fast trials tend to be followed by fast trials |
| `fatigue_drift` (drift_per_trial_ms) | Gradual RT increase across the experiment as attention and effort decline |
| `post_error_slowing` (slowing_ms_min/max) | RT increase on the trial immediately following an error (Rabbitt, 1966) |
| `condition_repetition` (facilitation_ms, cost_ms) | Gratton effect — facilitation when the previous trial had the same condition, cost when it switched |
| `pink_noise` (sd_ms, hurst) | Long-range 1/f temporal correlations in RT sequences, present in human data at rest and under task |
| `post_interrupt_slowing` (slowing_ms_min/max) | RT increase following a successfully inhibited stop-signal trial |

All effects default to disabled (`enabled: false`, parameters at 0). Claude enables and parameterizes only the effects that are empirically documented for the task type in question. The `rationale` field in each effect records Claude's reasoning.

### RT floor

No sampled RT can fall below `rt_floor_ms` (default 150 ms), the physiological lower bound for a deliberate keypress response.

---

## 6. Trial Execution

### Stimulus detection

Each stimulus definition specifies one of four detection methods:

| Method | Mechanism |
|---|---|
| `dom_query` | CSS selector via `page.query_selector()` — true if element exists |
| `js_eval` | JavaScript expression via `page.evaluate()` — true if expression returns truthy |
| `text_content` | CSS selector + string pattern matched against `element.textContent` |
| `canvas_state` | JavaScript expression reading canvas pixel data or off-screen state |

Stimulus rules are evaluated in config order. Stop-signal stimuli must be ordered before go stimuli so that a stop signal overlaid on a go stimulus is detected correctly.

### Phase detection

Each poll cycle, the executor evaluates JavaScript expressions to determine the current experiment phase. Phases are checked in priority order: complete → loading → instructions → attention_check → feedback → practice → test (default). If a JS expression throws — typically because the execution context was destroyed by page navigation — the bot treats this as task completion.

### Accuracy and omission decisions

On each trial, the executor makes three sequential decisions:

1. **Omit?** Draw against the per-condition omission rate. If omitting, wait for the trial to time out.
2. **Correct?** Draw against the per-condition accuracy target. Sets whether the response key will be correct or a randomly selected wrong key.
3. **Post-error slowing?** If the previous trial was an error and `post_error_slowing` is enabled, add a random slowing offset (uniform between slowing_ms_min and slowing_ms_max) to the sampled RT.

### Trial interrupt (stop signal / race model)

When `runtime.trial_interrupt.detection_condition` is set, the executor implements the independent race model (Logan & Cowan, 1984):

1. A go stimulus appears. The executor begins waiting for the sampled go RT.
2. During that wait, it polls the DOM for the interrupt stimulus (e.g., a stop-signal overlay).
3. If the interrupt appears: draw against `performance.accuracy` for the interrupt condition. Successful inhibition — withhold the response and wait `inhibit_wait_ms`. Failed inhibition — sample from the `failure_rt_key` distribution (faster than go RTs, matching the race model prediction) and press the go key after that delay.
4. If no interrupt appears before the go RT, respond normally.

---

## 7. Data Output

All outputs are saved to `output/{task_name}/{timestamp}/`:

| File | Contents |
|---|---|
| `config.json` | The full `TaskConfig` used for this run (after jitter) |
| `bot_log.json` | Per-trial log: stimulus, condition, sampled RT, key pressed, accuracy, phase |
| `experiment_data.{csv\|tsv\|json}` | The experiment's own recorded data, extracted from the page after completion |
| `run_metadata.json` | Run metadata: URL, trial count, headless flag, timestamp |
| `error_*.png` | Screenshots captured on errors or unexpected phases |

`bot_log.json` records what the bot decided and did. `experiment_data.*` records what the experiment framework measured. Comparing the two reveals timing discrepancies between the bot's intended RT and the experiment's recorded RT.

---

## 8. Validation Approach

Bot performance is validated by comparing mean metrics against human reference data collected under identical conditions. Human data from RDoC acquisition is stored in `data/human/`.

Analysis is conducted in `scripts/analysis.ipynb`. Key metrics:

- **Mean RT** per condition — does the bot's central tendency match humans?
- **Accuracy** per condition — does the bot's error rate match published norms?
- **Effect sizes** — Stroop interference effect (incongruent minus congruent RT), SSRT (stop-signal reaction time estimated from the integration method).
- **Sequential effects** — post-error slowing magnitude, condition repetition (Gratton) effect.

The validation standard is mean-metric agreement, not distribution identity. The goal is that the bot's data, aggregated across trials, is statistically indistinguishable from a human participant's data on the same task.

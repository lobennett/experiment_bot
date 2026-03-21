# Design Spec: Experiment Bot Generalizability Cleanup

**Date:** 2026-03-20
**Status:** Approved
**Goal:** Restructure the experiment bot so that all behavioral parameters are inferred by Claude at config-generation time, eliminating hardcoded domain knowledge from the Python codebase. The bot should function as a zero-shot system: point it at a URL, and Claude determines how a human would behave on that task.

## Motivation

An expert reviewer in cognitive psychology should not be able to identify the bot's output as non-human based on crude mean metrics (mean RT, accuracy, effect sizes). The system must demonstrate that its behavioral realism is a product of Claude's reasoning about the cognitive task — not of hand-tuned code.

A secondary motivation: a nefarious actor could build a similar bot to fake behavioral data on online collection platforms. The simpler the pipeline (URL in, humanlike data out), the more convincing the threat model for motivating platform-level countermeasures.

## Philosophy

- **At build time (Python code):** Execution mechanics only. How to drive a browser, sample from distributions, apply temporal effects *if configured*. No behavioral assumptions. No default parameter values for behavioral quantities.
- **At config generation (Claude API call):** Claude receives experiment source code and a structural schema. It infers all behavioral parameters from its knowledge of the cognitive psychology literature. Reasoning is captured in `rationale` fields.
- **At runtime:** The executor reads the config and applies it. Between-subject jitter adds variability (see Section 1, "Between-subject jitter" for how jitter parameters are determined). No further reasoning occurs.

## Scope

**Target experiments:**
- ExpFactory stop signal (human reference data available)
- ExpFactory Stroop (human reference data available)
- STOP-IT stop signal (cross-platform demonstration)
- cognition.run Stroop (cross-platform demonstration)

**Comparison metrics (initial):**
- Stop signal: mean go RT, go accuracy, go omission rate, mean stop failure RT, stop accuracy, mean SSD, SSRT
- Stroop: congruent/incongruent RT, congruent/incongruent accuracy, congruent/incongruent omission rates, Stroop effect magnitude

---

## 1. Schema Restructuring: `temporal_effects` in TaskConfig

Add a `temporal_effects` block to the TaskConfig schema with six named effect slots. Claude populates these per-task based on the literature.

### Schema structure

```json
"temporal_effects": {
  "autocorrelation": {
    "enabled": true,
    "phi": 0.22,
    "rationale": "Typical lag-1 autocorrelation in speeded choice tasks (Gilden, 2001)"
  },
  "fatigue_drift": {
    "enabled": true,
    "drift_per_trial_ms": 0.12,
    "rationale": "Gradual slowing across block consistent with vigilance decrement literature"
  },
  "post_error_slowing": {
    "enabled": true,
    "slowing_ms_min": 20,
    "slowing_ms_max": 60,
    "rationale": "Rabbitt (1966); robust PES of 30-50ms in choice RT tasks"
  },
  "condition_repetition": {
    "enabled": true,
    "facilitation_ms": 8,
    "cost_ms": 10,
    "rationale": "Gratton et al. (1992); asymmetric repetition/alternation effects in Stroop"
  },
  "pink_noise": {
    "enabled": true,
    "sd_ms": 12,
    "hurst": 0.75,
    "rationale": "1/f noise in RT series (Gilden, 1997; Van Orden et al., 2003)"
  },
  "post_interrupt_slowing": {
    "enabled": true,
    "slowing_ms_min": 20,
    "slowing_ms_max": 40,
    "rationale": "Post-stop-signal slowing (Verbruggen & Logan, 2008)"
  }
}
```

### Design decisions

- Each effect: `enabled` flag + parameters + `rationale` string
- `rationale` makes Claude's reasoning auditable and citable for reviewers
- All effects are optional — if Claude omits an effect or sets `enabled: false`, the Python code skips it
- `post_error_slowing` and `post_interrupt_slowing` are separate effects (currently split across `distributions.py` and `executor.py`) — they unify under the same config-driven pattern
- Claude may choose different effects for different tasks (e.g., `post_interrupt_slowing` for stop signal but not Stroop)
- **Effect interaction rule:** `condition_repetition` and `post_interrupt_slowing` should not both apply to the same trial. If both are enabled, the executor skips the condition-repetition adjustment on trials where post-interrupt slowing was applied, avoiding double-counting. Claude should be aware that for inhibitory tasks, `post_interrupt_slowing` is the more specific effect and `condition_repetition` applies only to non-interrupted trial sequences.

### `temporal_effects` placement in TaskConfig

`temporal_effects` is a **top-level field on `TaskConfig`**, alongside `response_distributions` and `performance`. It is not nested under `runtime` because it represents behavioral parameters (Claude-determined), not execution mechanics.

```python
@dataclass
class TaskConfig:
    task: TaskMetadata
    stimuli: list[StimulusConfig]
    response_distributions: dict[str, DistributionConfig]
    performance: PerformanceConfig
    navigation: NavigationConfig
    task_specific: dict
    temporal_effects: TemporalEffectsConfig  # NEW — Claude-determined
    runtime: RuntimeConfig
```

### Between-subject jitter

`jitter_distributions()` applies between-subject variability to RT distributions and performance targets. The jitter *magnitudes* are also Claude-determined via a `between_subject_jitter` block in the config:

```json
"between_subject_jitter": {
  "rt_mean_sd_ms": 40,
  "rt_condition_sd_ms": 15,
  "sigma_tau_range": [0.85, 1.15],
  "accuracy_sd": 0.015,
  "omission_sd": 0.005,
  "rationale": "Between-subject SD of mean RT ~50-80ms (Whelan, 2008); accuracy variability from individual differences literature"
}
```

This block lives in `TaskConfig` alongside `temporal_effects`. If absent, no jitter is applied. The Python `jitter_distributions()` function reads these values instead of using hardcoded constants.

### PerformanceConfig fallback removal

Currently `PerformanceConfig.get_accuracy()` falls back to `0.90` and `get_omission_rate()` falls back to `0.02` when a condition is missing. These are behavioral assumptions. After restructuring:

- `get_accuracy()` falls back to the first available condition's value (preserving the "use any available data" pattern) but has **no hardcoded numeric fallback**. If the accuracy dict is empty, it raises a `ValueError`.
- `get_omission_rate()` same pattern — falls back to first available, raises if empty.
- `practice_accuracy` default is removed — Claude must specify it.

### New dataclass: `TemporalEffectsConfig`

Added to `config.py` with sub-dataclasses for each slot:

```python
@dataclass
class AutocorrelationConfig:
    enabled: bool = False
    phi: float = 0.0
    rationale: str = ""

@dataclass
class FatigueDriftConfig:
    enabled: bool = False
    drift_per_trial_ms: float = 0.0
    rationale: str = ""

@dataclass
class PostErrorSlowingConfig:
    enabled: bool = False
    slowing_ms_min: float = 0.0
    slowing_ms_max: float = 0.0
    rationale: str = ""

@dataclass
class ConditionRepetitionConfig:
    enabled: bool = False
    facilitation_ms: float = 0.0
    cost_ms: float = 0.0
    rationale: str = ""

@dataclass
class PinkNoiseConfig:
    enabled: bool = False
    sd_ms: float = 0.0
    hurst: float = 0.0
    rationale: str = ""

@dataclass
class PostInterruptSlowingConfig:
    enabled: bool = False
    slowing_ms_min: float = 0.0
    slowing_ms_max: float = 0.0
    rationale: str = ""

@dataclass
class TemporalEffectsConfig:
    autocorrelation: AutocorrelationConfig
    fatigue_drift: FatigueDriftConfig
    post_error_slowing: PostErrorSlowingConfig
    condition_repetition: ConditionRepetitionConfig
    pink_noise: PinkNoiseConfig
    post_interrupt_slowing: PostInterruptSlowingConfig
```

All defaults are `enabled: False` with zero-valued parameters — **no behavioral assumptions in Python**. When `enabled` is `true`, the implementation should validate that required parameters are non-zero (e.g., `hurst` must be in (0, 1] when pink noise is enabled) and raise a clear error if not.

---

## 2. Prompt Restructuring: Technical vs. Behavioral Split

### Section A — Technical Instructions (retained and clarified)

What stays in `prompts/system.md`:
- Detection methods: dom_query, js_eval, text_content, canvas_state — syntax and usage
- JS expression syntax for phase detection, response windows, trial context
- Navigation action types: click, keypress, wait, sequence, repeat
- Response key resolution: static key, response_key_js, key_map
- Data capture: js_expression, button_click methods
- JSON schema structure and field definitions
- How `temporal_effects` slots work mechanically (what each field means)

### Section B — Behavioral Instructions (minimal, open-ended)

New behavioral section:

> "You are analyzing a cognitive experiment. Based on the task source code and your knowledge of the cognitive psychology literature:
> 1. Identify the cognitive constructs being measured and the relevant literature
> 2. Determine appropriate response time distributions (ex-Gaussian: mu, sigma, tau) for each condition, informed by published findings for this paradigm
> 3. Set per-condition accuracy and omission rate targets consistent with the literature
> 4. Decide which temporal effects to enable and parameterize, with rationale citing relevant studies
> 5. If the task involves any form of response suppression or signal-based interruption, configure the trial_interrupt parameters based on the relevant theoretical framework, citing your reasoning
>
> Your behavioral parameters should reflect what a typical healthy adult participant would produce. Cite your reasoning in the rationale fields."

### What's removed

- Specific parameter values or ranges (no "accuracy should be 0.85-0.95")
- Hints about which effects to enable for which task types
- References to specific tasks or platforms in behavioral context

### `prompts/schema.json`

Updated to include the `temporal_effects` section with all six named slots and the `between_subject_jitter` block. The JSON schema structure mirrors the Python dataclasses exactly — each effect slot has `enabled` (boolean), its specific parameters (numbers), and `rationale` (string). Structural contract only — defines fields and types, not values.

---

## 3. Python Code Changes

### `config.py` — Migration from TimingConfig

- Remove `autocorrelation_phi` and `fatigue_drift_per_trial` from `TimingConfig` — these are now in `TemporalEffectsConfig`
- Remove hardcoded fallback values from `PerformanceConfig.get_accuracy()` (currently `0.90`) and `get_omission_rate()` (currently `0.02`)
- Remove `practice_accuracy` default — Claude must specify it
- Add `temporal_effects: TemporalEffectsConfig` field to `TaskConfig`
- Add `between_subject_jitter: BetweenSubjectJitterConfig` field to `TaskConfig`
- Old cached configs containing the removed `TimingConfig` fields will be regenerated (Section 6)

### `distributions.py` — ResponseSampler becomes config-driven

- `ResponseSampler.__init__` takes a `TemporalEffectsConfig` instead of individual `phi`, `drift_rate`, `pink_noise_sd`, `pink_hurst` params
- `_apply_temporal_effects()` checks each effect's `enabled` flag — skips disabled effects
- Pink noise buffer only allocated if `pink_noise.enabled`
- Named constants `_GRATTON_MS` and `_PINK_BUFFER_LEN` are removed — values come from config
- `jitter_distributions()` reads jitter magnitudes from the new `between_subject_jitter` config block instead of hardcoded constants

### `executor.py` — Post-error and post-interrupt slowing become config-driven

- `_execute_trial()` reads `temporal_effects.post_error_slowing` and `temporal_effects.post_interrupt_slowing` from config
- If an effect is disabled or absent, no slowing applied
- `_prev_trial_error` and `_prev_interrupt_detected` state tracking remains (needed to know *when* to apply) — magnitude comes from config
- `_interrupt_js` caching (from earlier simplify pass) retained

### What doesn't change

- `ExGaussianSampler` — pure ex-Gaussian sampling
- `StimulusLookup`, `phase_detection.py`, `navigator.py` — technical/structural
- `scraper.py`, `analyzer.py`, `cache.py` — pipeline mechanics
- `cli.py` — entry point

### Principle

Python code has **no default values for behavioral parameters**. If `temporal_effects` is absent from a config, no temporal effects are applied. Claude must explicitly opt in.

---

## 4. Scripts Consolidation and Human Data Comparison

### Directory restructure

```
scripts/
├── launch.sh               # Batch launcher (operational tool, stays)
├── analysis.ipynb           # Single consolidated notebook
└── __deprecated__/
    ├── check_data.py
    ├── check_data.ipynb
    └── verify_humanlike.py
data/
└── human/
    ├── stop_signal.csv      # RDoC human reference data (~2500 rows, ExpFactory format)
    └── stroop.csv           # RDoC human reference data (~2500 rows, ExpFactory format)
```

### Human data source

The human reference data comes from an RDoC behavioral battery acquisition (ExpFactory platform). Files are moved from the repo root (`stop_signal.csv`, `stroop.csv`) to `data/human/`. Each row is one session for one participant (`sub_id` column). The data includes QC exclusion columns that must be filtered.

**Stop signal columns:** `sub_id`, `go_accuracy`, `go_omission_rate`, `go_rt`, `mean_stop_failure_RT`, `stop_accuracy`, `mean_SSD`, plus exclusion flags.

**Stroop columns:** `sub_id`, `congruent_accuracy`, `congruent_omission_rate`, `congruent_rt`, `incongruent_accuracy`, `incongruent_omission_rate`, `incongruent_rt`, plus exclusion flags.

### `analysis.ipynb` sections

1. **Setup** — imports, paths, helper functions for loading bot output directories
2. **Load Human Data** — read from `data/human/`, filter all three exclusion columns (`Session-Level Exclusions`, `Task-Level Exclusions`, `Subject-Level Exclusions`) to "Include" only
3. **Load Bot Data** — scan `output/` for completed runs, load `bot_log.json` + `experiment_data.{csv|tsv}` + `config.json` per run
4. **Stop Signal Metrics** — human and bot side-by-side:
   - Mean go RT (test trials only for ExpFactory)
   - Go accuracy, go omission rate
   - Mean stop failure RT
   - Stop accuracy
   - Mean SSD, SSRT estimation
   - Comparison table + distribution plots
5. **Stroop Metrics** — human and bot side-by-side:
   - Congruent RT, incongruent RT
   - Congruent accuracy, incongruent accuracy
   - Congruent/incongruent omission rates
   - Stroop effect (incongruent RT - congruent RT)
   - Comparison table + distribution plots
6. **Cross-Platform Comparison** — same metrics for STOP-IT and cognition.run runs vs. ExpFactory human norms

### Task-specific filtering

ExpFactory data requires filtering to `test_trial` trial IDs. This is handled with explicit, commented filtering logic in the notebook — acceptable task-specific analysis code (not bespoke bot behavior). Each filtering step has a markdown cell explaining what and why.

---

## 5. Documentation: `docs/how-it-works.md`

Restructured as a living methods section. Updated whenever code changes.

### Sections

1. **Overview** — single-sentence description, zero-shot philosophy
2. **Information Flow — What the Bot Knows and When**
   - At build time (Python): mechanisms only, no behavioral defaults
   - At config generation (Claude): infers all behavioral parameters from literature
   - At runtime: executes config, applies jitter
3. **Config Generation Pipeline** — Scrape → Claude (prompt split explained) → Cache → Jitter → Execute
4. **TaskConfig Schema** — full schema reference including `temporal_effects`, documented with "Claude determines these values"
5. **Response Time Modeling** — ex-Gaussian as standard methodology (Luce 1986, Whelan 2008), temporal effects as optional Claude-specified layers
6. **Trial Execution** — stimulus detection, phase detection, accuracy/omission, interrupt handling
7. **Data Output** — what gets saved, where, format
8. **Validation Approach** — mean-metric comparison against human reference data

---

## 6. Cached Config Regeneration

- All four cached configs regenerated after schema/prompt changes
- Process: update schema → update prompt → delete old configs → run bot with `--regenerate` against each URL → review generated configs → commit
- New configs contain Claude's `rationale` fields as auditable artifacts
- All four URLs are confirmed stable and accessible

---

## 7. Testing Strategy

### What changes

- `test_distributions.py`: `ResponseSampler` tests pass `TemporalEffectsConfig` instead of individual params. New tests verify: all effects disabled → raw ex-Gaussian output; each effect enabled independently produces expected behavior.
- `test_executor.py`: post-error/post-interrupt slowing tests verify config-driven magnitudes, not hardcoded ranges.

### What doesn't change

- Test philosophy: unit tests for components, async mock tests for executor
- Test infrastructure: pytest + pytest-asyncio via `uv run`
- Tests for stimulus detection, phase detection, navigation, key resolution — unchanged (mechanical)

### No new test files

Existing `test_distributions.py` and `test_executor.py` updated to reflect config-driven API.

---

## Anti-Goals

- **No bespoke fitting:** No hardcoded behavioral constants in Python. No parameter values that assume a specific task.
- **No domain knowledge leakage:** The prompt tells Claude *how* to fill out the schema, not *what* to put in it.
- **No over-engineering:** Named effect slots, not a plugin system. Six effects, not an extensible registry.
- **No premature timeseries analysis:** Mean metrics only in the analysis notebook for now. Temporal effects exist in the bot for future validation but aren't analyzed yet.

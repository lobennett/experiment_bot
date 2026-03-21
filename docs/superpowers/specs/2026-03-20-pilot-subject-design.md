# Design Spec: Pilot Subject — Self-Correcting Config Validation

**Date:** 2026-03-20
**Status:** Draft
**Goal:** Add a pilot run phase to the config generation pipeline that validates stimulus selectors, phase detection, and navigation against the live experiment, then sends diagnostic results back to Claude for config refinement. Runs once per novel task, results cached.

## Motivation

Claude generates TaskConfig from static source code, but correct stimulus selectors require knowledge of the **rendered DOM** — not just the source HTML. The source defines stimuli as HTML strings (e.g., `<span style="color:red">GREEN</span>`), but selectors must match what those strings look like after the experiment framework renders them into the page. Claude sometimes guesses wrong, producing selectors like `.stroop-stim` that don't exist in the actual DOM.

This is not a problem that more domain knowledge can solve. It's an observability problem: Claude needs to see the actual rendered experiment to write reliable selectors.

## Philosophy

The pilot subject follows the same zero-shot philosophy as the rest of the bot. It does not introduce task-specific logic. It gives Claude **empirical evidence** — DOM snapshots, selector match results, trial logs — and asks it to correct its own config. The corrections are Claude's reasoning, not engineered fallbacks.

## Pipeline Change

### Current pipeline

```
Scrape source → Claude generates config → Cache → Jitter → Execute
```

### New pipeline

```
Scrape source → Claude generates config (with pilot spec) → Pilot run → Diagnose → Claude refines config → Cache → Jitter → Execute
```

The pilot-and-refine loop happens **only when generating a new config** (cache miss or `--regenerate-config`). Cached configs skip directly to jitter and execute.

---

## 1. Pilot Configuration in TaskConfig

Claude specifies pilot parameters as part of the initial config generation, in a new top-level `pilot` section:

```json
"pilot": {
  "min_trials": 30,
  "target_conditions": ["congruent", "incongruent"],
  "max_blocks": 1,
  "rationale": "Stroop has 2 conditions with 24 trials per block. One full block guarantees both conditions appear multiple times."
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `min_trials` | int | Minimum number of trials to attempt before stopping the pilot |
| `target_conditions` | list[str] | Condition labels the pilot should observe (from stimulus definitions) |
| `max_blocks` | int | Maximum number of experimental blocks to run (safety cap) |
| `rationale` | str | Claude's reasoning for these choices, based on the experiment's trial structure |

### Stopping criteria

The pilot stops when ANY of these are met:
1. `min_trials` reached AND all `target_conditions` have been observed at least once
2. `max_blocks` blocks completed (detected via block-level feedback/instruction screens)
3. Task completion detected (the experiment ended naturally)
4. A hard timeout of 5 minutes elapsed (safety valve)
5. Zero stimulus matches for 100+ consecutive polls (the config is fundamentally broken — stop early and report)

Claude determines `min_trials`, `target_conditions`, and `max_blocks` from the experiment source code. It can read block sizes, trial counts, condition ratios, and practice/test structure from the JS source.

### Schema addition

Add `pilot` to `schema.json` as a top-level property:

```json
"pilot": {
  "type": "object",
  "description": "Pilot run parameters. The executor runs a short pilot session to validate selectors and detection before the full run. Specify enough trials to observe all experimental conditions at least once.",
  "properties": {
    "min_trials": {"type": "integer", "minimum": 1, "description": "Minimum trials before pilot can stop"},
    "target_conditions": {"type": "array", "items": {"type": "string"}, "description": "Condition labels that should be observed during pilot"},
    "max_blocks": {"type": "integer", "minimum": 1, "description": "Maximum blocks to run"},
    "rationale": {"type": "string"}
  }
}
```

### Dataclass

```python
@dataclass
class PilotConfig:
    min_trials: int = 20
    target_conditions: list[str] = field(default_factory=list)
    max_blocks: int = 1
    rationale: str = ""
```

Default `min_trials=20` is a safe fallback if Claude omits the pilot section. But Claude should always populate it — the prompt instructs this.

---

## 2. Pilot Runner

The pilot runner is a **mode of the existing TaskExecutor**, not a separate system. It uses the same trial loop, stimulus detection, phase detection, and navigation code — but collects diagnostics and stops early.

### What the pilot collects

During the pilot run, the executor records:

1. **DOM snapshots** — at 3 key moments:
   - After navigation completes (first stimulus should be visible)
   - After the first successful stimulus match (to confirm what "working" looks like)
   - After 50 consecutive polls with no match (to capture what "broken" looks like)

   Each snapshot is the `outerHTML` of the experiment's stimulus container element (e.g., `#jspsych-content` or `document.body` if no container is identifiable). Kept small — just the relevant subtree, not the full page.

2. **Selector match results** — for each defined stimulus, how many times its selector returned truthy vs. falsy during the pilot. Structured as:

   ```json
   {
     "stroop_congruent_red": {"matches": 15, "polls": 200},
     "stroop_incongruent_red": {"matches": 0, "polls": 200}
   }
   ```

3. **Phase detection results** — which phase expressions fired and when:

   ```json
   {
     "complete": {"fired": false, "first_fire_trial": null},
     "test": {"fired": true, "first_fire_trial": 1},
     "feedback": {"fired": true, "first_fire_trial": 25}
   }
   ```

4. **Condition coverage** — which `target_conditions` were actually observed:

   ```json
   {"observed": ["congruent"], "missing": ["incongruent"]}
   ```

5. **Trial log** — the standard bot_log entries from the pilot trials (same format as production runs).

6. **Anomalies** — specific events worth reporting:
   - Consecutive polls with zero stimulus matches (count and DOM at time)
   - Navigation steps that timed out
   - Stimulus selectors that matched but response key resolution failed
   - Phase detection expressions that threw JS errors

### Pilot execution flow

1. Launch browser, navigate to experiment URL
2. Execute navigation phases (same as production)
3. Enter trial loop with diagnostics collection enabled
4. On each poll, record selector match/miss counts
5. Capture DOM snapshots at trigger points
6. Check stopping criteria after each trial
7. When stopped: close browser, compile diagnostic report

### What the pilot does NOT do

- It does not save to `output/`. Pilot data is ephemeral — used only for the refinement call.
- It does not apply between-subject jitter. The pilot runs with the base config.
- It does not need to produce humanlike behavior. Timing accuracy doesn't matter — the point is selector validation.

---

## 3. Diagnostic Report

The pilot results are compiled into a structured diagnostic report sent to Claude for refinement. The report is plain text (not JSON) for readability in the prompt:

```
## Pilot Run Diagnostic Report

### Summary
- Trials completed: 24
- Conditions observed: ["congruent"] (missing: ["incongruent"])
- Stimulus match rate: 12/24 trials had a match

### Selector Results
- stroop_congruent_red: 12 matches / 240 polls (5.0%)
- stroop_incongruent_red: 0 matches / 240 polls (0.0%)   ← NEVER MATCHED
- fixation: 0 matches / 240 polls (0.0%)   ← NEVER MATCHED

### DOM Snapshot (at first stimulus display)
<div id="jspsych-html-keyboard-response-stimulus">
  <p style="font-size:48px; color:rgb(255,0,0);">RED</p>
</div>

### DOM Snapshot (during no-match period)
<div id="jspsych-html-keyboard-response-stimulus">
  <p style="font-size:48px; color:rgb(0,128,0);">RED</p>
</div>

### Phase Detection
- complete: never fired
- test: fired on trial 1
- feedback: never fired

### Anomalies
- 120 consecutive polls with no stimulus match starting at trial 13
- Selector 'stroop_incongruent_red' uses class '.stroop-stim' which does not exist in DOM
```

This gives Claude everything it needs: the actual HTML structure, which selectors worked and which didn't, and specific failure modes.

---

## 4. Refinement Call

A second Claude API call sends:

1. The original config (JSON)
2. The diagnostic report (text)
3. A focused refinement prompt

### Refinement prompt

```
You previously generated a TaskConfig for this experiment. A pilot run tested your config against the live experiment. Below is the diagnostic report showing what worked and what didn't.

## Your Original Config
{config JSON}

## Pilot Diagnostic Report
{diagnostic report}

## Instructions

Fix the config based on the diagnostic evidence:

1. For selectors that NEVER MATCHED: rewrite them using the actual DOM structure shown in the snapshots. The DOM snapshots show exactly what the experiment renders — write selectors that match this HTML.
2. For missing conditions: examine the DOM snapshots to understand how different conditions are rendered and write detection rules that distinguish them.
3. For phase detection expressions that never fired: check against the DOM and fix.
4. Do NOT change behavioral parameters (RT distributions, accuracy, temporal effects, jitter). Only fix structural/detection issues.
5. Update the pilot section if your understanding of the trial structure has changed.

Return the complete corrected config JSON.
```

### Key constraint

The refinement prompt explicitly tells Claude: **do not change behavioral parameters.** The pilot is only for validating structural config (selectors, phase detection, navigation). RT distributions, accuracy, temporal effects, and jitter were determined in the initial analysis and should not be revised based on a 20-trial pilot.

### Iteration cap

If the first refinement doesn't resolve all issues (e.g., still has 0-match selectors), run a second pilot and refinement. Cap at **2 refinement iterations**. If selectors still fail after 2 corrections, cache the best config and log a warning. The user can inspect and manually fix, or provide a better hint.

---

## 5. Pipeline Integration

### In `cli.py`

The config generation block changes from:

```python
config = await analyzer.analyze(bundle)
cache.save(url, config, label)
```

To:

```python
config = await analyzer.analyze(bundle)

# Pilot validation loop (max 2 refinement iterations)
for attempt in range(3):  # initial + 2 refinements
    diagnostics = await pilot_runner.run(config, url, headless=True)
    if diagnostics.all_conditions_observed and diagnostics.match_rate > 0.5:
        break  # Config is working
    if attempt < 2:
        click.echo(f"Pilot found issues (attempt {attempt + 1}), refining config...")
        config = await analyzer.refine(config, diagnostics)
    else:
        click.echo("Warning: Config still has issues after 2 refinements. Caching best attempt.")

cache.save(url, config, label)
```

### New modules

| Module | Responsibility |
|--------|---------------|
| `core/pilot.py` | `PilotRunner` class — runs pilot, collects diagnostics, compiles report |
| `core/analyzer.py` | Add `refine()` method to `Analyzer` — sends diagnostic report to Claude |

### `PilotRunner` interface

```python
class PilotRunner:
    async def run(self, config: TaskConfig, url: str, headless: bool = True) -> PilotDiagnostics:
        """Execute pilot run and return diagnostics."""

@dataclass
class PilotDiagnostics:
    trials_completed: int
    conditions_observed: list[str]
    conditions_missing: list[str]
    selector_results: dict[str, dict]  # stimulus_id → {matches, polls}
    phase_results: dict[str, dict]     # phase → {fired, first_fire_trial}
    dom_snapshots: list[dict]          # [{trigger, html}]
    anomalies: list[str]
    trial_log: list[dict]

    @property
    def all_conditions_observed(self) -> bool:
        return len(self.conditions_missing) == 0

    @property
    def match_rate(self) -> float:
        total = sum(r['matches'] for r in self.selector_results.values())
        return total / max(self.trials_completed, 1)
```

### Cache behavior

- The **refined** config is what gets cached. The pilot diagnostics are not cached.
- On subsequent runs (cache hit), the pilot is skipped entirely.
- `--regenerate-config` deletes the cache and re-runs the full pipeline including pilot.

---

## 6. Prompt Changes

### Addition to behavioral instructions (Section B of system.md)

Add to the behavioral prompt:

> "Your parameters should reflect typical performance in **online behavioral experiments** (not laboratory settings). Online samples tend to have slower mean RTs (50-150ms slower than lab norms), higher RT variability, and slightly lower accuracy due to hardware latency, environmental distractions, and broader participant demographics. Calibrate your ex-Gaussian parameters and performance targets accordingly."

This addresses the RT calibration issue (bot was ~140ms too fast) without overfitting — it's a methodological consideration any researcher would apply.

### Addition to technical instructions (Section A of system.md)

Add a section describing the `pilot` config:

> "**12. Pilot Configuration**: Specify parameters for a validation pilot run. The executor runs a short pilot session before the full experiment to test your selectors and detection logic against the live DOM. Based on the experiment's trial structure (block sizes, condition ratios, practice/test phases), specify:
> - `min_trials`: Minimum trials needed to observe all conditions at least once
> - `target_conditions`: The condition labels you expect to see during the pilot
> - `max_blocks`: Maximum number of blocks to run (typically 1)
> - `rationale`: Why these values are appropriate for this experiment's structure"

---

## 7. What This Does NOT Change

- **ExGaussianSampler, ResponseSampler, temporal effects** — untouched. Behavioral modeling is not affected.
- **Production trial loop** — the executor's main `_trial_loop` is unchanged. The pilot reuses it with early stopping.
- **Output format** — pilot data is not saved to `output/`. Production runs produce the same output as before.
- **Cached configs** — once a config passes the pilot and is cached, it's used exactly as before.
- **Between-subject jitter** — applied after the pilot, during production runs only.

## 8. Anti-Goals

- **No task-specific fallback logic.** If selectors fail, Claude fixes them — the code doesn't guess.
- **No DOM-based heuristics.** The pilot collects data; Claude interprets it.
- **No changes to behavioral parameters during refinement.** The pilot validates structure only.
- **No mandatory pilot for cached configs.** The pilot runs once; the cache stores the result.

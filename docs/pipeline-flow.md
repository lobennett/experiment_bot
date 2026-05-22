# experiment_bot pipeline flow

Quick reference for what happens between `experiment-bot <url> --label X`
and the final `bot_log.json` write. Sections are added as SP12 walks
each module.

## Surviving scripts

| Script | Purpose |
|---|---|
| `scripts/launch.sh` | Production launcher; wraps `experiment-bot` with the standard env. |
| `scripts/audit_alignment.py` | Per-session bot-vs-platform pairing audit. Paradigm-aware via `--label`. |
| `scripts/analyze_sessions.py` | Per-paradigm aggregate analysis vs TaskCard + human norms. |

## Pipeline phases (filled in below as SP12 walks each module)

## 1. CLI entry: `cli.py`

The bot launches via `experiment-bot <url> --label X`. The CLI:
1. Loads the latest TaskCard for `<label>` via `taskcard.loader.load_latest`.
2. Samples session-level distributional parameters via
   `taskcard.sampling.sample_session_params(seed=...)`.
3. Constructs a `TaskExecutor`, awaits `executor.run(url)`.

Entry point: `src/experiment_bot/cli.py:main` (click command).

## 2. TaskExecutor: `core/executor.py`

The executor coordinates one bot session. Flow:

1. **Open page** via Playwright → CDP session.
2. **Construct KeypressDeliverer** (`_setup_keypress_deliverer`).
   CDP is default; falls back to page.keyboard.press if CDP
   unavailable (Firefox/WebKit).
3. **Navigate instructions** (`_navigator.execute_all`).
4. **Calibration pass** (`_run_calibration_pass`) — fires N keys with
   the four-step protocol; estimates offset; installs result on
   sampler when model is non-escalate.
5. **Trial loop** (`_trial_loop`) — polls for stimulus, samples RT,
   fires response via `_fire_response_key`, logs trial.
6. **Completion + finalize** (`_wait_for_completion`, finally-block) —
   captures data, writes bot_log.json + run_metadata.json.

Entry point: `src/experiment_bot/core/executor.py:TaskExecutor.run`.

## 3. TaskCard config: `core/config.py`

Dataclass tree representing the TaskCard JSON. Loaded via
`taskcard.loader.load_latest`. Roundtrip through `to_dict`/`from_dict`
preserves fidelity. Each runtime knob has a dataclass field with a
default; the Reasoner emits values for the ones it determines.

Entry point: `src/experiment_bot/core/config.py:TaskConfig.from_dict`.

## 4. Calibration: `src/experiment_bot/calibration/`

Optional pre-trial-loop pass that fires N keys to measure platform-side
recording offset. Result is installed on the sampler; subsequent RT
samples are adjusted to compensate. Four model outcomes:

| Model | Trigger | Action |
|---|---|---|
| `fixed_offset` | SD ≤ 30ms, unimodal | shift sampler RT by mean |
| `regression` | SD > 30ms, unimodal | invert linear fit |
| `escalate` | bimodal detected | no adjustment |
| `too_few_events` | < 5 paired events | no adjustment |

Surviving files (per Task 6 walk):
- `deliverer.py` — abstract `KeypressDeliverer` interface + MockDeliverer
- `cdp_deliverer.py` — Chrome DevTools Protocol implementation (canonical, only channel)
- `runner.py` — orchestrator: `run_calibration(deliverer, gate_dismisser)`
- `estimator.py` — fit per-event offsets to one of the 4 models above
- `playwright_gate_dismisser.py` — visible-button + keyboard-fallback gate

Entry point: `src/experiment_bot/core/executor.py:TaskExecutor._run_calibration_pass`.

## 5. Output writer: `output/writer.py`

Writes the per-session output dir at `<output_root>/<task_name>/<timestamp>/`.
Honors `EXPERIMENT_BOT_OUTPUT_DIR` env var (overrides the repo-relative
default — used by orchestration scripts).

Outputs per session:
- `bot_log.json` — per-trial log + per-trial delivery metadata
- `run_metadata.json` — session-level metadata (seed, params, delivery
  channel counts, calibration result summary)
- `config.json` — the TaskCard's effective config for this run
- `experiment_data.{csv,json}` — platform's own data export (saved by
  executor before finalize)
- `screenshots/` — startup + error screenshots
- (Phase 2 will add `run_trace.json` — see Phase 2 plan)

Entry point: `src/experiment_bot/output/writer.py:OutputWriter.create_run`.

## 6. RT sampler: `core/distributions.py`

Per-condition RT sampling with temporal-effects application:
1. Pulls the per-condition ex-Gaussian / lognormal / shifted-Wald
   distribution from the TaskCard's `response_distributions`.
2. Draws a raw RT.
3. Applies temporal effects in registry order (autocorrelation,
   fatigue_drift, condition_repetition [deprecated], pink_noise,
   practice_effect, vigilance_decrement, lag1_pair_modulation,
   post_event_slowing).
4. Applies calibration adjustment if a CalibrationResult is installed.

Entry point: `core/distributions.py:ResponseSampler.sample_rt`.

## 7. Stimulus detection + phase: `core/stimulus.py`, `core/phase_detection.py`

`StimulusLookup.identify(page)` polls the page DOM/state for any of
the configured stimuli. Each stimulus's `detection` block declares
method (`dom_query`, `js_eval`) and selector. The first match wins.

`detect_phase(page, config)` classifies the current page state into
TaskPhase.{INSTRUCTIONS, FEEDBACK, TEST, COMPLETE, etc.} via the
TaskCard's `phase_detection` JS predicates. The trial loop dispatches
on phase to know whether to fire a response, advance instructions,
or finalize.

Entry point: `core/stimulus.py:StimulusLookup.identify`.

## 10. LLM client abstraction: `llm/`

Two-implementation client pattern (Reasoner-only consumer; SessionAgent
removed in Task 4):
- `cli_client.py` — wraps the `claude` CLI binary
- `api_client.py` — wraps the Anthropic Python SDK

`factory.py:build_default_client(model=...)` picks based on env (API
key → SDK; else CLI on PATH). Used by:
- Reasoner pipeline stages (offline, before sessions)

Entry point: `llm/factory.py:build_default_client`.

## 11. TaskCard load + sample: `taskcard/`

- `loader.py` — `load_latest(taskcards_dir, label)` finds the most-recent
  TaskCard JSON for a label (by file mtime).
- `types.py` — `TaskCard` Pydantic / dataclass shape with
  `produced_by` provenance.
- `sampling.py` — `sample_session_params(taskcard_dict, seed)` draws
  between-subject jitter for the session.
- `hashing.py` — SHA256 over the TaskCard for `produced_by.taskcard_sha256`.

Entry point: `taskcard/loader.py:load_latest`.

## 11. TaskCard load + sample: `taskcard/`

- `loader.py` — `load_latest(taskcards_dir, label)` finds the most-recent
  TaskCard JSON for a label (by file mtime). `save_taskcard` writes a
  new card with SHA-prefixed filename.
- `types.py` — `TaskCard` dataclass + nested types (Citation, ProducedBy,
  ParameterValue with provenance, ReasoningStep, TaskMetadata).
- `sampling.py` — `sample_session_params(taskcard_dict, seed)` draws
  per-session distributional parameter values from `N(mean, between_subject_sd**2)`,
  clipped to `literature_range`.
- `hashing.py` — SHA256 over canonicalized TaskCard for `produced_by.taskcard_sha256`.

Entry point: `taskcard/loader.py:load_latest`.


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

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
3. Builds a SessionAgent via `_build_session_agent()` (returns None if
   no LLM credentials available; the executor degrades gracefully).
4. Constructs a `TaskExecutor`, awaits `executor.run(url)`.

Entry point: `src/experiment_bot/cli.py:main` (click command).

## 2. TaskExecutor: `core/executor.py`

The executor coordinates one bot session. Flow:

1. **Open page** via Playwright → CDP session.
2. **Construct KeypressDeliverer** (`_setup_keypress_deliverer`).
   CDP is default; falls back to page.keyboard.press if CDP
   unavailable (Firefox/WebKit).
3. **Navigate instructions** (`_navigator.execute_all`).
4. **Install keydown listener** (`_install_keydown_listener`) — SP7
   diagnostic; retention decision pending controller review.
5. **SessionAgent** (`_invoke_session_agent`) — runtime LLM key-mapping
   resolution; retention decision pending controller review.
6. **Calibration pass** (`_run_calibration_pass`) — fires N keys with
   the four-step protocol; estimates offset; installs result on
   sampler when model is non-escalate.
7. **Trial loop** (`_trial_loop`) — polls for stimulus, samples RT,
   fires response via `_fire_response_key`, logs trial.
8. **Completion + finalize** (`_wait_for_completion`, finally-block) —
   captures data, writes bot_log.json + run_metadata.json.

Entry point: `src/experiment_bot/core/executor.py:TaskExecutor.run`.

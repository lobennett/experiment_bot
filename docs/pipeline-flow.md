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

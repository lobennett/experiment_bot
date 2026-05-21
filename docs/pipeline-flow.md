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


# Sessions

One directory per run, named by its timestamp: 240 sessions across the
twelve battery tasks, twenty each.

| File | Contents |
|---|---|
| `experiment_data.csv` or `.json` | what the experiment's own software recorded — the only file analysis reads |
| `run_metadata.json` | the card hash, the program hash, and the seed |
| `bot_log.json` | the bot's own per-trial decisions, for debugging only |
| `config.json`, `run_trace.json` | the resolved settings and a navigation trace |

Analysis deliberately ignores `bot_log.json`. The bot is scored on what the
platform wrote down, exactly as a person would be.

To reproduce any session, read its `run_metadata.json` and pass the three
values back to `experiment-bot`.

# experiment-bot

Human-like behavior executor for web-based cognitive tasks.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- An `ANTHROPIC_API_KEY` environment variable (only needed for first run per task, to generate config)

## Setup

```bash
uv sync
uv run playwright install chromium
```

## Usage

Point the bot at any experiment URL. On first run it scrapes the page, sends it to Claude for analysis, and caches the resulting config. Subsequent runs use the cache.

```bash
# Any experiment URL
uv run experiment-bot "https://deploy.expfactory.org/preview/9/"

# With a hint to help Claude identify the task
uv run experiment-bot "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html" --hint "stop signal task"

# Cache under a custom label for easy reuse
uv run experiment-bot "https://example.com/my-experiment/" --label my_experiment --headless
```

### Options

| Flag | Description |
|------|-------------|
| `--hint TEXT` | Hint about the task (e.g., "stop signal task") |
| `--label TEXT` | Cache label (default: URL hash) |
| `--headless` | Run browser without visible window |
| `--regenerate-config` | Force re-analysis via Claude API (ignores cache) |
| `--rt-mean FLOAT` | Override mean reaction time in ms |
| `--accuracy FLOAT` | Override go-trial accuracy (0–1) |
| `-v, --verbose` | Enable debug logging |

### Batch Launching

```bash
# Run all registered tasks
./scripts/launch.sh --headless --count 2

# Filter by label
./scripts/launch.sh --label expfactory_stop_signal --count 5

# Single URL mode
./scripts/launch.sh --url "https://deploy.expfactory.org/preview/9/" --count 3 --headless
```

## Output

Each run saves to `output/<task_name>/<timestamp>/`:

| File | Contents |
|------|----------|
| `experiment_data.*` | Raw experiment data (format depends on task) |
| `bot_log.json` | Per-trial bot decision log |
| `config.json` | Task config used for the run |
| `screenshots/` | Screenshots captured during execution |

## Tests

```bash
uv run pytest
```

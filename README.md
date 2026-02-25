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

The bot has two platform subcommands: `expfactory` and `psytoolkit`. Each takes a `--task` ID.

### ExpFactory

```bash
# Stop Signal Task (task ID: 9)
uv run experiment-bot expfactory --task 9

# Cued Task Switching (task ID: 2)
uv run experiment-bot expfactory --task 2
```

### PsyToolkit

```bash
# Stop Signal Task
uv run experiment-bot psytoolkit --task stopsignal

# Cued Task Switching
uv run experiment-bot psytoolkit --task taskswitching_cued
```

### Options

| Flag | Description |
|------|-------------|
| `--headless` | Run browser without visible window |
| `--regenerate-config` | Force re-analysis via Claude API (ignores cache) |
| `--rt-mean FLOAT` | Override mean reaction time in ms |
| `--accuracy FLOAT` | Override go-trial accuracy (0–1) |
| `-v, --verbose` | Enable debug logging |

### Example

```bash
# Run stop signal task headlessly with faster responses
uv run experiment-bot expfactory --task 9 --headless --rt-mean 350
```

## Output

Each run saves to `output/<platform>/<task_name>/<timestamp>/`:

| File | Contents |
|------|----------|
| `experiment_data.tsv` | Raw experiment data (PsyToolkit) |
| `experiment_data.csv` | Raw jsPsych trial data (ExpFactory) |
| `bot_log.json` | Per-trial bot decision log |
| `config.json` | Task config used for the run |
| `screenshots/` | Screenshots captured during execution |

## Tests

```bash
uv run pytest
```

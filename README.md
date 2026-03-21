# experiment-bot

A zero-shot bot that completes web-based cognitive experiments with humanlike behavior. Given only a URL, it scrapes the experiment source, sends it to Claude which infers all behavioral parameters from the cognitive psychology literature, then executes the task via Playwright — no task-specific code required.

## Why This Exists

Online cognitive experiments are vulnerable to automated participants producing fake data. This bot demonstrates that a general-purpose agent can produce behavioral data that is difficult to distinguish from real human performance on standard cognitive tasks (Stroop, stop signal, etc.), motivating platform-level countermeasures.

The bot contains **no hardcoded domain knowledge**. All behavioral parameters — response time distributions, accuracy targets, temporal effects, error patterns — are inferred by Claude at config generation time based on the cognitive psychology literature. The Python code provides execution mechanics only.

For a detailed technical description, see [`docs/how-it-works.md`](docs/how-it-works.md).

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- An [Anthropic API key](https://console.anthropic.com/) (needed once per task to generate config)

### Setup

```bash
# Install dependencies
uv sync

# Install browser for Playwright
uv run playwright install chromium

# Set your API key
cp .env.example .env
# Edit .env and replace the placeholder with your actual key
```

### Run

```bash
# Point at any experiment URL
uv run experiment-bot "https://deploy.expfactory.org/preview/10/"

# With a hint to help Claude identify the task
uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --hint "stop signal task"

# Headless mode (no visible browser)
uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --headless

# Cache under a label for easy reuse
uv run experiment-bot "https://example.com/experiment/" --label my_experiment --headless
```

On first run for a given URL, the bot scrapes the page, sends it to Claude for analysis, and caches the resulting config in `cache/`. Subsequent runs use the cache and do not call the API.

## How It Works

The bot follows a simple pipeline:

```
URL → Scrape HTML/JS → Claude API → TaskConfig JSON → Execute via Playwright → Save Data
```

1. **Scrape**: Fetches the experiment page and its linked JavaScript/CSS resources.
2. **Analyze**: Sends the source to Claude with a structural schema. Claude identifies the task, infers behavioral parameters from the literature, and returns a TaskConfig JSON.
3. **Cache**: The config is saved to `cache/{label}/config.json` for reuse.
4. **Jitter**: Between-subject variability is applied (magnitudes determined by Claude).
5. **Execute**: Playwright drives the browser — navigating instructions, detecting stimuli, sampling response times, pressing keys, and capturing output data.

All behavioral decisions (how fast to respond, how accurate to be, which temporal effects to include) are made by Claude during step 2. The executor applies them mechanically.

For the full technical description including the config schema, response time modeling, and trial execution loop, see **[`docs/how-it-works.md`](docs/how-it-works.md)**.

## CLI Options

| Flag | Description |
|------|-------------|
| `--hint TEXT` | Hint about the task type (e.g., `"stop signal task"`) |
| `--label TEXT` | Cache label (default: URL hash) |
| `--headless` | Run browser without a visible window |
| `--regenerate-config` | Force re-analysis via Claude API (ignores cache) |
| `--rt-mean FLOAT` | Override mean reaction time (mu) in ms |
| `--accuracy FLOAT` | Override primary accuracy target (0-1) |
| `-v, --verbose` | Enable debug logging |

## Batch Runs

For collecting multiple sessions of bot data:

```bash
# Run all 4 registered tasks, 5 instances each
bash scripts/launch.sh --headless --count 5

# Sequential batch (one at a time, safer for long runs)
bash scripts/batch_run.sh

# Filter to a specific task
bash scripts/launch.sh --label expfactory_stroop --count 10 --headless
```

`launch.sh` runs instances in parallel with stagger delays. `batch_run.sh` runs them sequentially (slower but more reliable for large batches).

## Output

Each run saves to `output/{task_name}/{timestamp}/`:

| File | Contents |
|------|----------|
| `bot_log.json` | Per-trial decision log (stimulus, condition, RT, accuracy, etc.) |
| `experiment_data.{csv,tsv,json}` | Raw experiment data captured from the platform |
| `config.json` | The TaskConfig used for this run |
| `run_metadata.json` | Run metadata (task name, URL, trial count, headless flag) |

## Comparing Bot vs. Human Data

Human reference data from an RDoC behavioral battery is in `data/human/`. The analysis notebook computes mean metrics and compares bot output to human distributions:

```bash
uv run jupyter lab scripts/analysis.ipynb
```

Key comparison metrics:
- **Stop signal**: mean go RT, go accuracy, stop accuracy, SSRT
- **Stroop**: congruent/incongruent RT, accuracy, Stroop effect magnitude

## Project Structure

```
experiment-bot/
├── src/experiment_bot/
│   ├── cli.py                  # Entry point
│   ├── core/
│   │   ├── config.py           # TaskConfig data model (all dataclasses)
│   │   ├── distributions.py    # Ex-Gaussian RT sampling, temporal effects
│   │   ├── executor.py         # Playwright task execution engine
│   │   ├── stimulus.py         # Stimulus detection rules
│   │   ├── phase_detection.py  # Experiment phase detection
│   │   ├── analyzer.py         # Claude API integration
│   │   ├── scraper.py          # Experiment source scraping
│   │   └── cache.py            # Config caching
│   ├── navigation/             # Instruction screen navigation
│   ├── output/                 # Data capture and output writing
│   └── prompts/
│       ├── system.md           # Claude system prompt (technical + behavioral)
│       └── schema.json         # TaskConfig JSON schema
├── cache/                      # Cached TaskConfigs per experiment
├── data/human/                 # Human reference data (RDoC)
├── scripts/
│   ├── analysis.ipynb          # Bot vs. human comparison notebook
│   ├── launch.sh               # Parallel batch launcher
│   └── batch_run.sh            # Sequential batch launcher
├── tests/                      # pytest test suite
├── docs/
│   └── how-it-works.md         # Full technical documentation
└── output/                     # Bot run outputs (gitignored)
```

## Validated Experiments

The bot has been tested against these platforms and tasks:

| Label | Task | Platform |
|-------|------|----------|
| `expfactory_stop_signal` | Stop Signal | [ExpFactory](https://deploy.expfactory.org/preview/9/) |
| `expfactory_stroop` | Stroop | [ExpFactory](https://deploy.expfactory.org/preview/10/) |
| `stopit_stop_signal` | Stop Signal | [STOP-IT](https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html) |
| `cognitionrun_stroop` | Stroop | [Cognition.run](https://strooptest.cognition.run/) |

## Tests

```bash
uv run python -m pytest tests/ -v
```

## Further Reading

- **[`docs/how-it-works.md`](docs/how-it-works.md)** — Full technical documentation: information flow, config schema, response time modeling, trial execution, and validation approach.

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
# Point at any experiment URL — Claude infers the task from the source code
uv run experiment-bot "https://deploy.expfactory.org/preview/10/"

# Headless mode (no visible browser)
uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --headless

# Cache under a label for easy reuse
uv run experiment-bot "https://example.com/experiment/" --label my_experiment --headless

# Optional: provide a hint if the source code alone is ambiguous
uv run experiment-bot "https://example.com/experiment/" --hint "task switching" --headless
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
| `--hint TEXT` | Optional hint about the task type (not recommended — Claude should infer from source) |
| `--label TEXT` | Cache label (default: URL hash) |
| `--headless` | Run browser without a visible window |
| `--regenerate-config` | Force re-analysis via Claude API (ignores cache) |
| `--rt-mean FLOAT` | Override mean reaction time (mu) in ms |
| `--accuracy FLOAT` | Override primary accuracy target (0-1) |
| `-v, --verbose` | Enable debug logging |

## Batch Runs

For collecting multiple sessions of bot data:

```bash
# Sequential batch: 5 instances of each task, one at a time (recommended)
bash scripts/batch_run.sh --count 5 --headless

# Sequential with config regeneration on the first run of each task
bash scripts/batch_run.sh --count 5 --headless --regenerate

# Parallel batch: 5 instances each, launched simultaneously with stagger delays
bash scripts/launch.sh --headless --count 5

# Filter to a specific task
bash scripts/launch.sh --label expfactory_stroop --count 10 --headless
```

`batch_run.sh` runs instances sequentially (one at a time) — recommended for clean timing data. `launch.sh` runs instances in parallel, which is faster but may inflate RTs under CPU contention.

## Output

Each run saves to `output/{task_name}/{timestamp}/`:

| File | Contents |
|------|----------|
| `bot_log.json` | Per-trial decision log (stimulus, condition, RT, accuracy, etc.) |
| `experiment_data.{csv,tsv,json}` | Raw experiment data captured from the platform |
| `config.json` | The TaskConfig used for this run |
| `run_metadata.json` | Run metadata (task name, URL, trial count, headless flag) |

## Running the Bot

### First run (generates config via Claude API)

The first time the bot encounters a new experiment URL, it scrapes the source, calls Claude to generate a TaskConfig, runs a pilot validation, refines the config if needed, and caches it. This requires an API key and takes a few minutes.

```bash
# Generate config + run the task
uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless

# Force regeneration (e.g., after updating the prompt or schema)
uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --regenerate-config --headless
```

Use `--regenerate-config` whenever you have changed `prompts/system.md`, `prompts/schema.json`, or the config dataclasses — otherwise the bot reuses the old cached config.

### Subsequent runs (uses cached config)

Once a config is cached, subsequent runs skip the API call entirely. No API key is needed.

```bash
# Uses cached config — fast, no API call
uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless
```

### When to regenerate

Regenerate configs when:
- You've updated `src/experiment_bot/prompts/system.md` or `schema.json`
- You've changed config dataclasses in `config.py`
- You want Claude to re-infer behavioral parameters (e.g., after prompt improvements)
- The experiment source code has changed

You do NOT need to regenerate when:
- Running additional sessions with the same config
- Between-subject jitter is applied fresh on every run automatically

## Analyzing Data

### Running the analysis notebook

The primary analysis tool is `scripts/analysis.ipynb`. It loads the raw experiment data (not the bot's decision log), compares metrics to human reference data, and exports per-run CSVs.

```bash
# Open in Jupyter Lab
uv run jupyter lab scripts/analysis.ipynb
```

The notebook processes each platform in order:
1. **RDoC Stop Signal** (ExpFactory) — 180 test trials, go/stop split
2. **RDoC Stroop** (ExpFactory) — 120 test trials, congruent/incongruent
3. **STOP-IT Stop Signal** — 288 trials, signal-based filtering
4. **Cognition.run Stroop** — 15 trials, dynamic condition mapping

For each platform, the notebook:
1. Loads the cached config and displays Claude's expected parameters (RT distributions, accuracy targets, temporal effects)
2. Loads the experiment's raw output data (`experiment_data.{csv,json}`)
3. Computes metrics using the experiment's own correctness scoring
4. Compares each metric to the human reference distribution (mean ± 1 SD)

### Output CSVs

The notebook exports per-run metrics to `data/bot/` in the same format as the human reference data:
- `data/bot/stop_signal.csv` — one row per bot session, same columns as `data/human/stop_signal.csv`
- `data/bot/stroop.csv` — one row per bot session, same columns as `data/human/stroop.csv`

Each row includes a generated subject ID (e.g., `bot_amber_falcon`), timestamp, platform, and all task metrics.

### Human reference data

Human data from an RDoC behavioral battery is in `data/human/`:
- `stop_signal.csv` — ~2500 sessions with go RT, go accuracy, stop accuracy, SSD metrics
- `stroop.csv` — ~2500 sessions with congruent/incongruent RT and accuracy

Both files include exclusion columns. The notebook filters to rows where all three exclusion columns equal "Include".

### Key comparison metrics

| Task | Metrics (in column order) |
|------|---------|
| **Stop signal** | `go_accuracy`, `go_omission_rate`, `go_rt`, `go_rt_all_responses`, `mean_stop_failure_RT`, `stop_accuracy`, `max_SSD`, `mean_SSD`, `min_SSD`, `final_SSD` |
| **Stroop** | `congruent_accuracy`, `congruent_omission_rate`, `congruent_rt`, `incongruent_accuracy`, `incongruent_omission_rate`, `incongruent_rt` |

### Quick command-line check

```bash
# Count completed bot runs
find output -name "experiment_data.*" | wc -l

# Check cached configs
ls cache/*/config.json
```

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

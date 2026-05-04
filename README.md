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
- Claude Max subscription (used by `experiment-bot-reason` via the `claude` CLI) **or** an [Anthropic API key](https://console.anthropic.com/) set as `ANTHROPIC_API_KEY` (fallback)

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
# Step 1: generate TaskCard (once per experiment, uses Claude)
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# Step 2: run a session (no API key required)
uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop --headless

# With a hint (not recommended — Claude should infer from source)
uv run experiment-bot-reason "https://example.com/experiment/" --label my_experiment --hint "task switching"
uv run experiment-bot "https://example.com/experiment/" --label my_experiment --headless
```

Run `experiment-bot-reason` once per experiment to generate the TaskCard, then use `experiment-bot` for all sessions. The TaskCard is stored in `taskcards/{label}/` and does not require the API again.

## How It Works

The bot follows a two-phase pipeline:

**Phase 1 — Reason** (`experiment-bot-reason`, run once per experiment):
```
URL → Scrape HTML/JS → 5-stage Reasoner → TaskCard JSON → taskcards/{label}/
```
1. **Scrape**: Fetches the experiment page and its linked JavaScript/CSS resources.
2. **Reason**: The 5-stage Reasoner runs structural inference, behavioral parameter estimation, literature citation, DOI verification, and sensitivity tagging — producing a peer-reviewable TaskCard.
3. **Store**: The TaskCard is written to `taskcards/{label}/{hash}.json` (content-addressed, immutable).

**Phase 2 — Execute** (`experiment-bot`, run per session):
```
TaskCard → Sample session params → Playwright session → Save Data
```
4. **Load**: The executor loads the latest TaskCard for the label.
5. **Jitter**: Per-session distributional parameters are sampled (deterministic given `--seed`).
6. **Execute**: Playwright drives the browser — navigating instructions, detecting stimuli, sampling response times, pressing keys, and capturing output data.

All behavioral decisions (how fast to respond, how accurate to be, which temporal effects to include) are determined by the Reasoner in Phase 1. The executor applies them mechanically.

For the full technical description including the config schema, response time modeling, and trial execution loop, see **[`docs/how-it-works.md`](docs/how-it-works.md)**.

## CLI Options

| Flag | Description |
|------|-------------|
| `--hint TEXT` | Optional hint about the task type (not recommended — Claude should infer from source) |
| `--label TEXT` | TaskCard label (default: URL hash) |
| `--headless` | Run browser without a visible window |
| `--rt-mean FLOAT` | Override mean reaction time (mu) in ms |
| `--accuracy FLOAT` | Override primary accuracy target (0-1) |
| `-v, --verbose` | Enable debug logging |

## Batch Runs

For collecting multiple sessions of bot data:

```bash
# Sequential batch: 5 instances of each task, one at a time (recommended)
bash scripts/batch_run.sh --count 5 --headless

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

For detailed descriptions of each file and what generated it, see **[`examples/README.md`](examples/README.md)**. The `examples/` directory contains representative output from one run of each validated task.

## Workflow: two-step (reason then execute)

experiment-bot is split into two commands:

1. `experiment-bot-reason <url> --label <label>` — reads the experiment source,
   runs the 5-stage Reasoner (structural inference → behavioral parameters →
   literature citations → DOI verification → sensitivity tagging), and writes
   a peer-reviewable TaskCard to `taskcards/{label}/{hash}.json`. Uses your
   Claude Max subscription via the `claude` CLI by default; falls back to the
   Anthropic API with `ANTHROPIC_API_KEY` if `claude` is not on PATH. Run once
   per experiment; the TaskCard is content-addressed and immutable.

2. `experiment-bot <url> --label <label> --headless` — loads the latest
   TaskCard for the given label, samples per-session distributional parameters
   (deterministic given a `--seed`), and runs a Playwright session.

```bash
# Step 1: generate TaskCard (once per experiment)
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal

# Step 2: run sessions (no API key required)
uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless
```

See `docs/superpowers/specs/2026-04-23-taskcard-reasoner-design.md` for the
TaskCard schema and reasoning pipeline.

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

# Check generated TaskCards
ls taskcards/*/
```

## Project Structure

```
experiment-bot/
├── src/experiment_bot/
│   ├── cli.py                  # experiment-bot entry point
│   ├── reasoner_cli.py         # experiment-bot-reason entry point
│   ├── core/
│   │   ├── config.py           # TaskConfig data model (all dataclasses)
│   │   ├── distributions.py    # Ex-Gaussian RT sampling, temporal effects
│   │   ├── executor.py         # Playwright task execution engine
│   │   ├── stimulus.py         # Stimulus detection rules
│   │   └── phase_detection.py  # Experiment phase detection
│   ├── taskcard/               # TaskCard schema and I/O
│   ├── reasoner/               # 5-stage reasoning pipeline
│   ├── llm/                    # Claude CLI + API client shim
│   ├── navigation/             # Instruction screen navigation
│   ├── output/                 # Data capture and output writing
│   └── scraper.py              # Experiment source scraping
├── taskcards/                  # Content-addressed TaskCards per experiment
├── data/human/                 # Human reference data (RDoC)
├── examples/                   # Sample output from one run per task (see examples/README.md)
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

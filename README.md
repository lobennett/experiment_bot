# experiment-bot

A zero-shot bot that completes web-based cognitive experiments with humanlike behavior. Given only a URL, it scrapes the experiment source, sends it to Claude which infers all behavioral parameters from the cognitive psychology literature, then executes the task via Playwright — no task-specific code required.

## Why This Exists

Online cognitive experiments are vulnerable to automated participants producing fake data. This bot demonstrates that a general-purpose agent can produce behavioral data that is difficult to distinguish from real human performance on standard cognitive tasks (Stroop, stop signal, etc.), motivating platform-level countermeasures.

The bot contains **no hardcoded domain knowledge**. All behavioral parameters — response time distributions, accuracy targets, temporal effects, error patterns — are inferred by the Reasoner (from the cognitive-psychology literature) into a TaskCard. The Python code provides execution mechanics only.

For the full start-to-finish walkthrough, see [How It Works](#how-it-works) below.

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

The system is three layers run in order: the **Reasoner** thinks (offline,
once per experiment), the **Executor** acts (per session), and the **Oracle**
scores (after sessions). The Reasoner makes every behavioral decision; the
Executor applies them mechanically; the Oracle judges them against published
norms.

```
URL ──[experiment-bot-reason]──► TaskCard ──[experiment-bot]──► output/  ──[experiment-bot-validate]──► report
       (Reasoner: Stages 1–6)     (JSON)      (Executor: Playwright)        (Oracle: norms scoring)
```

### 1. Reasoner — `experiment-bot-reason` (offline, once per experiment)

The Reasoner scrapes the experiment's HTML and linked JS/CSS, then runs a
six-stage pipeline that infers every behavioral parameter from the
cognitive-psychology literature and emits a TaskCard. It has never seen the
experiment before and contains no hardcoded knowledge of any task, paradigm,
or platform.

| Stage | Role |
|---|---|
| 1. structural | Parse page source → stimuli (with detection rules), navigation steps, runtime knobs |
| 2. behavioral | Add `response_distributions` (ex-Gaussian mu/sigma/tau per condition), per-condition accuracy/omission targets, and which generic temporal-effect mechanisms to enable |
| 3. citations | Attach literature citations + rationale to numeric parameters |
| 4. DOI-verify | Check each citation's DOI against OpenAlex (existence, year, author, title) |
| 5. sensitivity | Tag each parameter's sensitivity |
| 6. pilot | Optional live-DOM pilot against the real URL; a sequential walker advances one screen at a time and refines navigation/selectors until the run reaches trials |

Each numeric parameter records its provenance (literature range, citation,
rationale) so the TaskCard is peer-reviewable. The TaskCard is written to
`taskcards/{label}/{sha}.json` — content-addressed and immutable.

### 2. TaskCard — the versioned JSON contract

The TaskCard is the only artifact passed from reasoning to execution. It is a
dataclass tree (`core/config.py`, `taskcard/types.py`) with these sections:

| Section | Contents |
|---|---|
| `stimuli` | Per-stimulus detection rule (`dom_query`, `js_eval`), response key, condition label |
| `navigation` | Ordered steps from page load to the first trial (`click`, `keypress`, `wait`, `sequence`, `repeat`) |
| `response_distributions` | Per-condition RT distribution parameters (ex-Gaussian mu/sigma/tau) plus a between-subject SD |
| `temporal_effects` | Generic mechanism configs — the Reasoner enables only those documented for the paradigm; all default to off |
| citations | Each numeric parameter carries its DOI-verified citation (or an explicit no-citation rationale) and reasoning chain |

The Executor loads the **newest-by-mtime** card from `taskcards/{label}/` via
`taskcard.loader.load_latest`. No reasoning happens after this point.

### 3. Executor — `experiment-bot` (per session)

`experiment-bot <url> --label <label>` loads the latest TaskCard, samples one
session's distributional parameters via `sample_session_params(seed=...)`
(drawn from `N(mean, between_subject_sd²)`, clipped to the literature range —
deterministic given `--seed`), then drives the live URL through a single
Playwright session (`PilotSession`):

1. **Navigate** the TaskCard's instruction phases to reach the first trial.
   If a between-block instruction screen the fixed nav can't advance survives
   two re-runs, **adaptive nav** asks the LLM to propose one more nav phase
   (budgeted; disabled with `--no-llm-client`).
2. **Trial loop** — each cycle: detect the current stimulus (first matching
   detection rule wins; stop-signal stimuli are ordered before go stimuli),
   sample a response time, decide whether to omit and whether to be correct,
   and fire the keypress (via Chrome DevTools Protocol, falling back to
   Playwright's keyboard).
3. **Finalize** — capture the platform's own data export, then write the
   session directory.

**RT modeling.** Response times are drawn from the per-condition distribution
in the TaskCard (ex-Gaussian: `Normal(mu, sigma) + Exponential(tau)`, the
standard model for human RT), floored at a physiological minimum. After
sampling, the executor applies whichever generic temporal-effect mechanisms
the Reasoner enabled — autocorrelation, fatigue/linear drift, lag-1 pair
modulation, post-event slowing, practice effect, vigilance decrement, pink
(1/f) noise. These are named in **mechanism** vocabulary, not paradigm
vocabulary (per G2 below): a conflict task's congruency-sequence effect is
configured as `lag1_pair_modulation`, not "CSE". When a stimulus carries an
interrupt condition (stop-signal), the executor runs the independent race
model — polling for the interrupt during the go-RT wait and either inhibiting
or firing from the faster failure-RT distribution.

Each run writes `output/{task_name}/{timestamp}/`:

| File | Contents |
|---|---|
| `experiment_data.{csv,json}` | The platform's own recorded data (the authoritative source for validation) |
| `bot_log.json` | Per-trial decision log (stimulus, condition, sampled RT, key pressed, accuracy) + delivery metadata |
| `run_metadata.json` | Session metadata (seed, sampled params, delivery-channel counts, adaptive-nav summary) |
| `config.json` | The TaskCard's effective config for this run |

### 4. Oracle — `experiment-bot-validate` (after sessions)

`experiment-bot-validate --label <label> --paradigm-class <class>` reads the
platform export through a per-paradigm adapter (`validation/platform_adapters.py`),
computes per-metric values (mean RT, accuracy, effect sizes, SSRT, etc.), and
gates each against the published ranges in `norms/<class>.json` (e.g.
`conflict`, `interrupt`, `working_memory`), writing a pass/fail report. It
reads the platform's export — never the bot's own log.

### Design principles

- **G1 — Generalizability.** The library bakes in no paradigm-specific
  knowledge. Pointing the bot at a novel paradigm's URL (n-back, Flanker,
  etc.) should work without code changes; held-out paradigms verify this
  empirically.
- **G2 — Generic mechanisms.** The bot's library is a small set of generic
  mechanisms; the Reasoner translates the literature into mechanism
  *configurations*. The bot's code never names a paradigm-specific phenomenon.
- **G4 — Anti-circularity.** The Reasoner cites primary studies; the Oracle
  gates on independent meta-analytic norms committed *before* the sessions
  that reference them — two different evidence tiers, so validation can't be
  tuned to its own answer.

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
| `config.json` | The TaskCard's effective config used for this run |
| `run_metadata.json` | Run metadata (task name, URL, trial count, headless flag) |

For detailed descriptions of each file and what generated it, see **[`examples/README.md`](examples/README.md)**. The `examples/` directory contains representative output from one run of each validated task.

## Analyzing Data

Two tested CLIs score sessions from the platform's own data export
(`experiment_data.{csv,json}` — never the bot's self-log; see goal G4):

```bash
# Oracle: point-estimate gates vs pre-registered meta-analytic norms
uv run experiment-bot-validate --paradigm-class conflict --label stroop_rdoc

# Human-reference comparison: bot cohort mean z-positioned within the human
# RDoC distribution (the paper's analysis)
uv run experiment-bot-compare --label stroop_rdoc \
  --human-csv data/human/stroop_rdoc.csv \
  --map data/human/comparison_maps/stroop_rdoc.json
```

Current numbers live in **[`docs/validation-results.md`](docs/validation-results.md)**
(single living results doc). Per-metric walkthroughs that recompute every
oracle metric from first principles against real session data are in
**[`notebooks/`](notebooks/README.md)** (marimo; assertions verify
hand-rolled == library == oracle).

### Human reference data

Session-level RDoC battery summaries are committed at
`data/human/{stroop,stop_signal}_rdoc.csv` (~2,510 rows each; the Include
exclusion filter yields the paper's reference Ns 2,478 / 2,412). Trial-level
Eisenberg data is fetched separately — see
**[`data/human/README.md`](data/human/README.md)** for download + sha256.
Comparison metric mappings (which human column ↔ which bot computation) are
data files under `data/human/comparison_maps/`.

> `scripts/analysis.ipynb` is the legacy exploratory notebook this analysis
> was ported from; it predates the current pipeline and is kept for
> reference only — use `experiment-bot-compare` for citable numbers.

## Reproduce the Paper's Numbers

```bash
scripts/reproduce.sh 5    # sessions per paradigm (4 parallel streams)
```

runs sessions for all four implementations, stages STOP-IT under its adapter
label, then runs the oracle validation and the human-reference comparison.
TaskCards are committed (content-addressed under `taskcards/`); sessions are
reproducible per-card via `experiment-bot --taskcard-sha256 <hash> --seed
<session_seed>` using the values recorded in each session's
`run_metadata.json`. Expfactory preview URLs are ephemeral deployments — if
one 404s, redeploy and update the URL (as-run commands are recorded in
`docs/validation-results.md`).

## Project Structure

```
experiment-bot/
├── src/experiment_bot/
│   ├── cli.py                  # experiment-bot entry point (Executor)
│   ├── core/
│   │   ├── config.py           # TaskCard config dataclass tree
│   │   ├── distributions.py    # Ex-Gaussian RT sampling + temporal-effects application
│   │   ├── executor.py         # Playwright task execution engine
│   │   ├── pilot_session.py    # Single-session Playwright wrapper (PilotSession)
│   │   ├── stimulus.py         # Stimulus detection rules
│   │   ├── phase_detection.py  # Experiment phase detection
│   │   └── scraper.py          # Experiment source scraping
│   ├── reasoner/               # 6-stage reasoning pipeline + experiment-bot-reason CLI
│   ├── taskcard/               # TaskCard schema, loader, session sampling
│   ├── effects/                # Generic temporal-effect mechanisms + validation metrics
│   ├── calibration/            # Optional platform-recording offset calibration
│   ├── validation/             # Oracle: experiment-bot-validate + per-paradigm adapters
│   ├── llm/                    # Claude CLI + API client shim (Reasoner consumer)
│   ├── navigation/             # Instruction-screen navigation
│   └── output/                 # Data capture and output writing
├── taskcards/                  # Content-addressed TaskCards per experiment
├── norms/                      # Pre-committed meta-analytic norms per paradigm class
├── data/human/                 # Human reference data (RDoC)
├── examples/                   # Sample output from one run per task (see examples/README.md)
├── scripts/
│   ├── analysis.ipynb          # Bot vs. human comparison notebook
│   ├── launch.sh               # Parallel batch launcher
│   └── batch_run.sh            # Sequential batch launcher
├── tests/                      # pytest test suite
├── docs/                       # Scope, validation results, reviewer charter, citation history
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

- **[`docs/scope-of-validity.md`](docs/scope-of-validity.md)** — what the framework claims and does not claim.
- **[`docs/validation-results.md`](docs/validation-results.md)** — current validation results.
- **[`docs/reviewer-1-charter.md`](docs/reviewer-1-charter.md)** — adversarial review instructions.
- **[`docs/stage3-citation-history.md`](docs/stage3-citation-history.md)** — citation provenance and integrity history.

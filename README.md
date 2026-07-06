# experiment-bot

A zero-shot bot that completes web-based cognitive experiments with humanlike behavior. Given only a URL, it scrapes the experiment source and asks Claude to (a) extract the structural facts a browser harness needs (navigation, stimulus detection, keys) into a TaskCard, and (b) author a generative *participant program* — a small Python program that decides every response (key, RT) trial by trial. The harness executes the task via Playwright with the program as the behavioral layer — no task-specific code required.

## Why This Exists

Online cognitive experiments are vulnerable to automated participants producing fake data. This bot demonstrates that a general-purpose agent can produce behavioral data that is difficult to distinguish from real human performance on standard cognitive tasks (Stroop, stop signal, etc.), motivating platform-level countermeasures.

The bot contains **no hardcoded domain knowledge and no behavioral scaffolding**. All behavior — RT structure, accuracy, errors, sequential effects, stop-signal race dynamics — comes from the LLM-generated participant program (one per task implementation, gated only by a mechanical simulation check). The Python code provides execution mechanics only.

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
# Step 1: generate the structural TaskCard (once per experiment, uses Claude)
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# Step 2: generate the participant program (once per experiment, uses Claude)
uv run experiment-bot-naive-gen "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# Step 3: run a session (no API key required; seed = participant)
uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop \
  --behavior-program expfactory_stroop/<hash-prefix> --seed 735001 --headless
```

Run `experiment-bot-reason` and `experiment-bot-naive-gen` once per experiment, then use `experiment-bot` for all sessions. The TaskCard is stored in `taskcards/{label}/`, the program under `naive_programs/{label}/` (content-hashed) — neither requires the API again.

## How It Works

The system is three layers run in order: the **structural Reasoner** maps the
page (offline, once per experiment), the **program generator** writes the
computational participant (offline, once per experiment), and the **Executor**
runs sessions. Analysis compares the recorded data per-subject against the
human reference.

```
URL ──[experiment-bot-reason]──► TaskCard ─┐
       (Stage 1 structural → Stage 6 pilot) │
URL ──[experiment-bot-naive-gen]──► program ┴─[experiment-bot]──► output/ ──[experiment-bot-per-subject]──► report
       (participant program + sim gate)        (Executor: Playwright)          (vs. human reference data)
```

### 1. Reasoner — `experiment-bot-reason` (offline, once per experiment)

The Reasoner scrapes the experiment's HTML and linked JS/CSS, then runs a
structural pipeline and emits a TaskCard. It has never seen the experiment
before and contains no hardcoded knowledge of any task, paradigm, or platform.

| Stage | Role |
|---|---|
| 1. structural | Parse page source → stimuli (with detection rules), navigation steps, runtime knobs |
| 6. pilot | Optional live-DOM pilot against the real URL; a sequential walker advances one screen at a time and refines navigation/selectors until the run reaches trials |

The TaskCard carries **no behavioral parameters** — behavior lives in the
generated participant program. The TaskCard is written to
`taskcards/{label}/{sha}.json` — content-addressed and immutable.

### 2. TaskCard — the versioned JSON contract

The TaskCard is the only artifact passed from reasoning to execution. It is a
dataclass tree (`core/config.py`, `taskcard/types.py`) with these sections:

| Section | Contents |
|---|---|
| `stimuli` | Per-stimulus detection rule (`dom_query`, `js_eval`), response key, condition label |
| `navigation` | Ordered steps from page load to the first trial (`click`, `keypress`, `wait`, `sequence`, `repeat`) |
| `runtime` | Phase detection, timing knobs, advance behavior, trial-interrupt detection, data capture |
| `task_specific` | `key_map` (condition → key) and trial timing facts |

The Executor loads the **newest-by-mtime** card from `taskcards/{label}/` via
`taskcard.loader.load_latest`. No reasoning happens after this point.

### 3. Executor — `experiment-bot` (per session)

`experiment-bot <url> --label <label> --behavior-program <program>` loads the
latest TaskCard, instantiates the program's participant for this `--seed`
(`make_participant(seed)` — each seed is a distinct simulated subject), then
drives the live URL through a single Playwright session (`PilotSession`):

1. **Navigate** the TaskCard's instruction phases to reach the first trial.
   If a between-block instruction screen the fixed nav can't advance survives
   two re-runs, **adaptive nav** asks the LLM to propose one more nav phase
   (budgeted; disabled with `--no-llm-client`).
2. **Trial loop** — each cycle: detect the current stimulus (first matching
   detection rule wins; stop-signal stimuli are ordered before go stimuli),
   pass the trial context (condition, correct key, keys seen so far, trial
   index, previous-trial outcome) to the program's `respond(ctx)`, and fire
   whatever (key, RT) it returns (via Chrome DevTools Protocol, falling back
   to Playwright's keyboard). Returning `key=None` withholds/omits.
3. **Finalize** — capture the platform's own data export, then write the
   session directory.

**Behavior modeling.** The harness never imposes distributions, effects, or
race structure — the program is the participant. On stop trials the executor
polls for the interrupt during the program's intended RT and, on detection,
hands the program the signal delay via `on_interrupt(ctx, ssd_ms, intended)`;
the program itself decides the stop/go race. Programs are stdlib+numpy only,
deterministic per seed, and pass a mechanical simulation gate
(`experiment-bot-naive-sim`: no crashes over ~1,000 synthetic trials, seed
determinism, import whitelist) before first use — never behavioral iteration
(see `docs/preregistration-naive.md`).

Each run writes `output/{task_name}/{timestamp}/`:

| File | Contents |
|---|---|
| `experiment_data.{csv,json}` | The platform's own recorded data (the authoritative source for validation) |
| `bot_log.json` | Per-trial decision log (stimulus, condition, sampled RT, key pressed, accuracy) + delivery metadata |
| `run_metadata.json` | Session metadata (seed, program sha256 + path, delivery-channel counts, adaptive-nav summary) |
| `config.json` | The TaskCard's effective config for this run |

### 4. Analysis — `experiment-bot-per-subject` (after sessions)

`experiment-bot-per-subject` computes per-subject measures (RT location and
dispersion, accuracy, omissions, sequential structure, SSRT) from the
platform's own data export and compares the bot cohort against trial-level
human reference data (Eisenberg et al. 2019) with identical estimators for
both cohorts. It reads the platform's export — never the bot's own log.

### Design principles

- **G1 — Generalizability.** The library bakes in no paradigm-specific
  knowledge. Pointing the bot at a novel paradigm's URL (n-back, Flanker,
  etc.) should work without code changes; held-out paradigms verify this
  empirically.
- **G2 — No behavioral scaffolding.** The harness's code contains no
  distributions, no effect vocabulary, no race structure. The generation
  prompt names no phenomena and carries no numeric priors (enforced by
  invariant tests); everything behavioral is authored by the model inside
  the participant program.
- **G4 — No behavioral iteration.** The first program per task to pass the
  mechanical simulation gate is the program (pre-registered;
  `docs/preregistration-naive.md`). Programs are content-hashed and archived
  with their generation transcripts under `naive_programs/`.

## CLI Options

| Flag | Description |
|------|-------------|
| `--label TEXT` | TaskCard label (folder under `taskcards/`) |
| `--behavior-program TEXT` | Required: program path or `<label>/<hash-prefix>` under `naive_programs/` |
| `--seed INT` | Selects the program's participant (default: random) |
| `--headless` | Run browser without a visible window |
| `--taskcard-sha256 TEXT` | Hermetic replay: load the exact card a past session recorded |
| `--no-llm-client` | Disable adaptive nav (deterministic / no-LLM runs) |
| `--no-calibration` | Skip the startup keypress-latency calibration pass |
| `-v, --verbose` | Enable debug logging |

## Batch Runs

For collecting multiple sessions of bot data:

```bash
# N seeded sessions per paradigm (generate once, then collect; idempotent by seed)
bash scripts/naive_run.sh 30
```

`scripts/naive_run.sh` pins one program per task (content hash recorded),
assigns explicit seeds, and runs the four dev paradigms as parallel streams
(sequential within a stream).

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

`experiment-bot-per-subject` scores sessions from the platform's own data
export (`experiment_data.{csv,json}` — never the bot's self-log):

```bash
# Per-subject measures + comparison against the human reference
uv run experiment-bot-per-subject --help
```

Current numbers live in **[`docs/validation-results.md`](docs/validation-results.md)**
(single living results doc); naive-arm outputs land under
`analysis_out_naive/`.

### Human reference data

Session-level RDoC battery summaries are committed at
`data/human/{stroop,stop_signal}_rdoc.csv` (~2,510 rows each; the Include
exclusion filter yields the paper's reference Ns 2,478 / 2,412). Trial-level
Eisenberg data is fetched separately — see
**[`data/human/README.md`](data/human/README.md)** for download + sha256.
Comparison metric mappings (which human column ↔ which bot computation) are
data files under `data/human/comparison_maps/`.

## Reproduce the Paper's Numbers

```bash
scripts/naive_run.sh 30    # seeded sessions per paradigm (4 parallel streams)
```

collects the naive-arm dataset for all four implementations. TaskCards and
programs are committed (content-addressed under `taskcards/` and
`naive_programs/`); sessions are reproducible via `experiment-bot
--taskcard-sha256 <hash> --behavior-program <label>/<hash> --seed
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
│   │   ├── executor.py         # Playwright task execution engine (program-driven trials)
│   │   ├── pilot_session.py    # Single-session Playwright wrapper (PilotSession)
│   │   ├── stimulus.py         # Stimulus detection rules
│   │   ├── phase_detection.py  # Experiment phase detection
│   │   └── scraper.py          # Experiment source scraping
│   ├── behavior/               # Naive arm: program generation (naive-gen), sim gate, provider
│   ├── reasoner/               # Structural pipeline (Stage 1 + Stage 6 pilot) + reason CLI
│   ├── taskcard/               # TaskCard schema, loader, content hashing
│   ├── analysis/               # experiment-bot-per-subject (vs. human reference)
│   ├── calibration/            # Optional platform-recording offset calibration
│   ├── llm/                    # Claude CLI + API client shim
│   ├── navigation/             # Instruction-screen navigation
│   └── output/                 # Data capture and output writing
├── taskcards/                  # Content-addressed structural TaskCards per experiment
├── naive_programs/             # Content-hashed participant programs + generation transcripts
├── data/human/                 # Human reference data (RDoC / Eisenberg)
├── examples/                   # Sample output from one run per task (see examples/README.md)
├── scripts/
│   └── naive_run.sh            # Seeded naive-arm collection (4 parallel streams)
├── tests/                      # pytest test suite
├── docs/                       # Scope, validation results, pre-registration, paper drafts
└── output_naive/               # Naive-arm session outputs
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

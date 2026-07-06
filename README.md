# experiment-bot

A zero-shot bot that completes web-based cognitive experiments with humanlike
behavior. Given only a URL, it scrapes the experiment source and asks Claude
to (a) extract the structural facts a browser harness needs (navigation,
stimulus detection, keys) into a TaskCard, and (b) author a generative
*participant program* — a small Python program that decides every response
(key, RT) trial by trial. The harness executes the task via Playwright with
the program as the behavioral layer — no task-specific code required.

The bot contains **no hardcoded domain knowledge and no behavioral
scaffolding**. All behavior — RT structure, accuracy, errors, sequential
effects, stop-trial dynamics — comes from the LLM-generated participant
program (one per task implementation, gated only by a mechanical simulation
check, never behavioral iteration). The Python code provides execution
mechanics only.

## Why This Exists

Online cognitive experiments are vulnerable to automated participants
producing fake data. This bot demonstrates that a general-purpose agent can
produce behavioral data that is difficult to distinguish from real human
performance on standard cognitive tasks (Stroop, stop signal, etc.),
motivating platform-level countermeasures. The experimental design and
pre-registration live in `docs/preregistration-naive.md` and
`docs/paper-draft-v2-naive-participant.md`.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Claude Max subscription (used by the reasoning/generation CLIs via the
  `claude` CLI) **or** an [Anthropic API key](https://console.anthropic.com/)
  set as `ANTHROPIC_API_KEY` (fallback)

### Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env   # add your API key if not using the claude CLI
```

### Run

```bash
# Step 1: reason a structural TaskCard from the URL (once per experiment, uses Claude)
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# Step 2: generate the participant program (once per experiment, uses Claude;
# runs the mechanical simulation gate automatically and archives the transcript)
uv run experiment-bot-naive-gen "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# Step 3: run sessions (no API key required; each seed is a distinct participant)
uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop \
  --behavior-program expfactory_stroop/<hash-prefix> --seed 735001 --headless

# Step 4: per-subject analysis vs. the human reference (after fetching the
# Eisenberg CSVs — see data/human/README.md)
uv run experiment-bot-per-subject --label stroop_rdoc --output-dir output \
  --human-stroop data/human/stroop_eisenberg.csv --out-dir analysis_out
```

Steps 1–2 run once per experiment; the TaskCard lands in `taskcards/{label}/`
(content-addressed, immutable) and the program under `naive_programs/{label}/`
(content-hashed, with its simulation-gate report and full generation
transcript). Neither requires the API again.

## The Five CLIs

| CLI | What it does |
|---|---|
| `experiment-bot-reason` | Scrape URL → structural TaskCard (Stage 1 structural parse; Stage 6 live-DOM pilot with a sequential refinement walker; `--skip-pilot` to disable) |
| `experiment-bot-naive-gen` | One neutral prompt (page source + mechanical facts + protocol contract) → participant program; runs the gate; archives program + transcript, content-hashed |
| `experiment-bot-naive-sim` | Standalone mechanical simulation gate for a program file (no crashes over ~1,000 synthetic trials, seed determinism, distinct seeds differ, import whitelist) |
| `experiment-bot` | Execute one session: load TaskCard + program, drive the live URL via Playwright; requires `--behavior-program` |
| `experiment-bot-per-subject` | Per-subject metric CSVs + bot-vs-human comparison report from the platform's own data export |

Run any of them with `--help` for the full option list.

## How It Works

```
URL ──[experiment-bot-reason]──► TaskCard ─┐
       (Stage 1 structural → Stage 6 pilot) │
URL ──[experiment-bot-naive-gen]──► program ┴─[experiment-bot]──► output/ ──[experiment-bot-per-subject]──► report
       (participant program + sim gate)        (Executor: Playwright)          (vs. human reference data)
```

### 1. Structural Reasoner — `experiment-bot-reason` (offline, once per experiment)

Scrapes the experiment's HTML and linked JS/CSS, then runs the structural
pipeline and emits a TaskCard. It has never seen the experiment before and
contains no hardcoded knowledge of any task, paradigm, or platform.

| Stage | Role |
|---|---|
| 1. structural | Parse page source → stimuli (with detection rules), navigation steps, runtime knobs |
| 6. pilot | Live-DOM pilot against the real URL; a sequential walker advances one screen at a time and refines navigation/selectors until the run reaches trials |

The TaskCard carries **no behavioral parameters** — behavior lives entirely
in the generated participant program. Cards are written to
`taskcards/{label}/{sha}.json`, content-addressed and immutable. The Executor
loads the newest-by-mtime card by default, or an exact card via
`--taskcard-sha256`.

### 2. Program generator — `experiment-bot-naive-gen` (offline, once per experiment)

A single prompt contains: the scraped page source, the mechanical facts the
harness must share (condition labels, key map, whether a mid-trial interrupt
exists), and the protocol contract below. The prompt names no phenomena, no
distribution families, and no numeric behavioral priors — enforced by
invariant tests (`tests/test_naive_prompt_invariants.py`) that scan the
template and every injected constant against a banned-terms list.

**Provider contract** (`src/experiment_bot/behavior/provider.py`):

```python
make_participant(seed)                    # same seed => identical behavior
participant.respond(ctx)                  # per trial -> (key_or_None, rt_ms)
participant.on_interrupt(ctx, ssd_ms, intended)  # interrupt tasks only ->
                                          # None (withhold) or (key, rt_ms)
```

`ctx` carries condition, correct key, keys seen so far, trial index, and the
previous trial's outcome. Programs are stdlib+numpy only, deterministic per
seed, with no file/network/clock access; return values are validated at the
boundary (no silent coercion).

**No behavioral iteration (pre-registered).** The first program per task to
pass the mechanical gate is the program; regeneration only on gate failure
(max 2 retries, all attempts archived). See `docs/preregistration-naive.md`.

### 3. Executor — `experiment-bot` (per session)

Loads the TaskCard, instantiates the program's participant for this `--seed`,
then drives the live URL through a single Playwright session:

1. **Navigate** the TaskCard's instruction phases to reach the first trial.
   If a between-block instruction screen the fixed nav can't advance survives
   two re-runs, **adaptive nav** asks the LLM to propose one more nav phase
   (budgeted; disabled with `--no-llm-client`).
2. **Trial loop** — each cycle: detect the current stimulus (first matching
   detection rule wins; interrupt stimuli are checked before go stimuli),
   pass the trial context to the program's `respond(ctx)`, and fire whatever
   (key, RT) it returns via Chrome DevTools Protocol (falling back to
   Playwright's keyboard). Returning `key=None` withholds. On interrupt
   trials the executor polls during the program's intended RT and, on
   detection, hands the program the signal delay via `on_interrupt` — the
   program itself decides the outcome.
3. **Finalize** — capture the platform's own data export and write the
   session directory.

The harness never imposes distributions, effects, or race structure — the
program is the participant.

Each run writes `output/{task_name}/{timestamp}/`:

| File | Contents |
|---|---|
| `experiment_data.{csv,json}` | The platform's own recorded data (the authoritative source for analysis) |
| `bot_log.json` | Per-trial decision log (stimulus, condition, intended RT, key pressed) + delivery metadata |
| `run_metadata.json` | Session metadata (seed, program sha256 + path, taskcard sha256, delivery-channel counts, adaptive-nav summary) |
| `config.json` | The TaskCard's effective config for this run |
| `run_trace.json` | Structured per-stage trace |

### 4. Analysis — `experiment-bot-per-subject` (after sessions)

Computes per-subject measures (RT location and dispersion, accuracy,
omissions, sequential structure, SSRT) from the platform's own data export —
never the bot's self-log — and compares the bot cohort against trial-level
human reference data (Eisenberg et al. 2019) with identical estimators for
both cohorts. Outputs per-subject CSVs (`*_bot.csv`, `*_human.csv`) and a
Markdown comparison report; the naive-arm results for the paper live under
`analysis_out_naive/`.

### Human reference data

Trial-level Eisenberg data is fetched separately (too large for git) — see
**[`data/human/README.md`](data/human/README.md)** for download + sha256
verification.

## Batch Runs

```bash
# N seeded sessions per paradigm (generate once, then collect; idempotent by seed)
bash scripts/naive_run.sh 30
```

`scripts/naive_run.sh` pins one program per task (content hash recorded),
pins the structural TaskCard by content hash, assigns explicit seeds, and
runs the four dev paradigms as parallel streams (sequential within a stream).
Sessions land under `output_naive/`.

## Provenance and Reproducibility

Every session is hermetically pinned by three values recorded in its
`run_metadata.json`:

- **TaskCard content hash** — replay the exact card with
  `--taskcard-sha256 <hash>` (full or unambiguous prefix).
- **Program content hash** — `--behavior-program <label>/<hash-prefix>`;
  programs, gate reports, and generation transcripts are committed under
  `naive_programs/`.
- **Seed** — `--seed <session_seed>`; the participant is deterministic per
  seed.

TaskCards and programs are committed, so any past session reproduces with:

```bash
uv run experiment-bot <url> --label <label> \
  --taskcard-sha256 <hash> --behavior-program <label>/<hash> --seed <seed>
```

Expfactory preview URLs are ephemeral deployments — if one 404s, redeploy and
substitute the new URL (structure, not behavior, so the pinned card still
applies).

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
│   ├── behavior/               # Program generation (naive-gen), sim gate, provider contract
│   ├── reasoner/               # Structural pipeline (Stage 1 + Stage 6 pilot) + reason CLI
│   ├── taskcard/               # TaskCard schema, loader, content hashing
│   ├── analysis/               # experiment-bot-per-subject (vs. human reference)
│   ├── calibration/            # Optional platform-recording offset calibration
│   ├── llm/                    # Claude CLI + API client shim
│   ├── navigation/             # Instruction-screen navigation
│   └── output/                 # Data capture and output writing
├── taskcards/                  # Content-addressed structural TaskCards per experiment
├── naive_programs/             # Content-hashed participant programs + gate reports + transcripts
├── data/human/                 # Human reference data (Eisenberg; fetched, see its README)
├── scripts/
│   ├── naive_run.sh            # Seeded collection (4 parallel streams)
│   └── check_doc_links.py      # CI: dead intra-repo doc references
├── analysis_out_naive/         # Committed per-subject CSVs + comparison reports
├── output_naive/               # Committed session outputs (the paper's dataset)
├── tests/                      # pytest test suite
└── docs/                       # Pre-registration + paper draft
```

## Validated Experiments

| Label | Task | Platform |
|-------|------|----------|
| `expfactory_stop_signal` | Stop Signal | [ExpFactory](https://deploy.expfactory.org/preview/9/) |
| `expfactory_stroop` | Stroop | [ExpFactory](https://deploy.expfactory.org/preview/10/) |
| `stopit_stop_signal` | Stop Signal | [STOP-IT](https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html) |
| `cognitionrun_stroop` | Stroop | [Cognition.run](https://strooptest.cognition.run/) |

## Tests

```bash
uv run pytest -q
```

## Further Reading

- **[`docs/preregistration-naive.md`](docs/preregistration-naive.md)** — the frozen pre-registration (committed before any generation call).
- **[`docs/paper-draft-v2-naive-participant.md`](docs/paper-draft-v2-naive-participant.md)** — paper draft. The comparison-arm (expert pipeline) code and dataset live on the `main` branch.

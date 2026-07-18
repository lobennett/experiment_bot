# experiment-bot

A zero-shot bot that completes web-based cognitive experiments with
humanlike behavior. Given only a URL, it scrapes the experiment source and
asks Claude to (a) extract the structural facts a browser harness needs
(navigation, stimulus detection, keys) into a TaskCard, and (b) author a
generative *participant program* — a small Python program that decides
every response (key, RT) trial by trial. The harness executes the task via
Playwright with the program as the behavioral layer — no task-specific
code anywhere.

The codebase contains **no hardcoded domain knowledge and no behavioral
scaffolding**. All behavior — RT structure, accuracy, errors, sequential
effects, stop-trial dynamics — comes from the LLM-generated participant
program, produced by one neutral prompt, gated only by a mechanical
simulation check, and never iterated on behavioral grounds. Those
integrity rules are enforced by tested invariants, not convention.

**Read [`docs/how-it-works.md`](docs/how-it-works.md)** — the full
narrative, from the research question through every stage to the evidence.

## Why this exists

Online cognitive experiments are vulnerable to automated participants
producing fake data. This bot demonstrates that a general-purpose agent
can produce behavioral data that is difficult to distinguish from real
human performance on standard cognitive tasks, motivating platform-level
countermeasures — and, in the other direction, measures what task
understanding a model brings to bare source code (the structure its
participants implement unprompted).

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), and either
a Claude subscription (via the `claude` CLI) or `ANTHROPIC_API_KEY` for
the two reasoning/generation steps.

```bash
uv sync
uv run playwright install chromium
cp .env.example .env   # add your API key if not using the claude CLI

# 1. Structural TaskCard from the URL (uses Claude; once per experiment)
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# 2. Participant program (uses Claude; once per experiment; mechanical gate runs automatically)
uv run experiment-bot-naive-gen "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop

# 3. Seeded sessions (no API needed; each seed = one synthetic participant)
uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop \
  --behavior-program expfactory_stroop/<hash-prefix> --seed 735001 --headless

# 4. Per-subject analysis vs the human reference (see data/human/README.md)
uv run experiment-bot-per-subject --label stroop_rdoc --output-dir output \
  --human-stroop data/human/stroop_eisenberg.csv --out-dir analysis_out
```

Batch collection: `bash scripts/naive_run.sh <N>` — generate once, gate,
then N seeded sessions per configured task, idempotent by seed.

## The five CLIs

| CLI | What it does |
|---|---|
| `experiment-bot-reason` | Scrape URL → structural TaskCard (structural parse + live-DOM pilot with a refinement walker) |
| `experiment-bot-naive-gen` | One neutral prompt → participant program; runs the gate; archives program + full transcript, content-hashed |
| `experiment-bot-naive-sim` | Standalone mechanical gate for a program file (~1,000 synthetic trials: crash/legality/determinism checks only) |
| `experiment-bot` | Execute one hermetic session: TaskCard + program + seed against the live URL |
| `experiment-bot-per-subject` | Per-subject metric CSVs + bot-vs-human comparison from the platform's own data export |

```
URL ──[reason]──► TaskCard ─┐
URL ──[naive-gen]──► program ┴─[experiment-bot]──► session data ──[per-subject]──► comparison vs humans
```

## Evidence of performance

Full narrative and numbers: [`docs/how-it-works.md`](docs/how-it-works.md) §8.

| Body of evidence | Scope | Headline |
|---|---|---|
| Pre-specified comparison ([paper draft](docs/paper-draft-v2-naive-participant.md)) | Stroop + stop-signal, 2 implementations each, N=30 | 22/28 measures within 1 human SD; per-subject SSRT indistinguishable from humans (KS p ≈ 0.3) where the expert-parameterized arm fails architecturally (KS p ≈ 10⁻⁴⁶) |
| Held-out probe | Eriksen flanker, never seen, frozen pipeline | First-shot program; flanker effect +58 ± 23 ms (literature ≈ 40–70), positive in all 5 sessions |
| Exploratory battery, v2 ([results](docs/rdoc-battery-results.md)) | All 12 RDoC Experiment Factory tasks, N=5, two rounds | v2: **102/150 (68%)** within 1 human SD (v1: 84/149, 56%); spatial task-switching 16/16, n-back 13/14, stop-signal 12/12; attention checks answered on 11/12 tasks; misses documented honestly, no behavioral iteration (v1 archived at the `battery-v1` tag) |

The raw evidence is in-repo: sessions (`output_naive/`), programs with
generation transcripts and gate reports (`naive_programs/`), structural
cards (`taskcards/`), metric matrices (`data/bot/rdoc/` vs
`data/human/rdoc/`), and per-subject comparisons (`analysis_out_naive/`).

## Provenance and reproducibility

Every session's `run_metadata.json` records the triple that pins it:
TaskCard content hash, program content hash, seed. Cards and programs are
committed content-addressed, so any past session reproduces with:

```bash
uv run experiment-bot <url> --label <label> \
  --taskcard-sha256 <hash> --behavior-program <label>/<hash> --seed <seed>
```

Expfactory preview URLs are ephemeral — if one 404s, redeploy and
substitute the new URL (the pinned card captures structure, not the
deployment).

## Project structure

```
experiment-bot/
├── src/experiment_bot/
│   ├── core/                   # Executor (Playwright engine), TaskCard config, stimulus/phase detection, scraper
│   ├── behavior/               # Program generation, mechanical gate, participant-program protocol
│   ├── reasoner/               # Structural pipeline (parse + live pilot) + reason CLI
│   ├── taskcard/               # TaskCard schema, loader, content hashing
│   ├── analysis/               # Per-subject measures + human comparison
│   ├── calibration/            # Timing-calibrated CDP input delivery
│   ├── navigation/             # Instruction-screen navigation
│   └── output/                 # Data capture and output writing
├── taskcards/                  # Content-addressed structural TaskCards
├── naive_programs/             # Content-hashed programs + gate reports + transcripts
├── output_naive/               # Committed session outputs (the datasets)
├── analysis_out_naive/         # Per-subject CSVs + comparison reports
├── data/
│   ├── human/                  # Human reference data (Eisenberg; fetched — see its README)
│   │   └── rdoc/               # RDoC battery human matrices (gitignored) + committed placeholders
│   ├── bot/rdoc/               # Bot metric matrices at human-schema parity (see its README)
│   └── rdoc_task_urls.tsv      # RDoC battery label → URL registry
├── scripts/                    # naive_run.sh (collection), check_doc_links.py (CI)
├── tests/                      # 750-test suite, incl. the prompt-neutrality invariants
└── docs/                       # how-it-works, prereg (frozen) + provenance, paper draft, battery results
```

## Tests

```bash
uv run pytest -q
```

The suite is part of the package's evidence: the prompt-neutrality
invariant tests are the experiment's integrity guarantee, and the
protocol/executor/gate tests pin the participant-program contract.

## Further reading

- **[`docs/how-it-works.md`](docs/how-it-works.md)** — the whole system, start to finish: question, integrity design, every stage, evidence, limitations.
- **[`docs/rdoc-battery-results.md`](docs/rdoc-battery-results.md)** — the exploratory 12-task battery results.
- **[`docs/paper-draft-v2-naive-participant.md`](docs/paper-draft-v2-naive-participant.md)** — paper draft. The expert-arm comparison pipeline and dataset are archived at the `expert-arm-final` git tag.

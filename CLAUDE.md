# CLAUDE.md — Project Goals and Guardrails

Standing guidance for any Claude session working on `experiment-bot`.
Read this before making non-trivial changes.

## What this is

The **naive-participant system**: given only a web experiment's URL, a
frontier LLM authors a *generative participant program* — a small Python
program that decides every response (key, RT) trial by trial — and a
timing-faithful Playwright harness executes it against the live page.
No behavioral scaffolding exists anywhere in the codebase: no
distribution families, no effect vocabulary, no race structure, no
numeric priors. Everything behavioral is written by the model inside
the program.

The comparison-arm (expert pipeline: Reasoner stages 2–5, effects
registry, oracle/norms validation) and its dataset are archived at the
`expert-arm-final` git tag. This tree contains the naive system only.

## Components

- **Structural Reasoner** (`src/experiment_bot/reasoner/`,
  `experiment-bot-reason`) — Stage 1 parses page source into a
  *structural* TaskCard (stimulus detection, navigation, keys, runtime
  knobs — no behavioral parameters); Stage 6 pilots it against the live
  URL with a sequential refinement walker. Cards are content-addressed
  under `taskcards/{label}/{sha}.json`.
- **Behavior package** (`src/experiment_bot/behavior/`) —
  `experiment-bot-naive-gen` renders one neutral prompt (page source +
  mechanical facts + the protocol contract) and archives the generated
  program, content-hashed with its full transcript, under
  `naive_programs/{label}/`. `experiment-bot-naive-sim` is the purely
  mechanical gate (no crashes over ~1,000 synthetic trials, seed
  determinism, distinct seeds differ, import whitelist). Prompt
  neutrality is enforced by invariant tests
  (`tests/test_naive_prompt_invariants.py`) scanning the template and
  every injected constant against a banned-terms list.
- **Executor** (`src/experiment_bot/core/`, `experiment-bot`) —
  REQUIRES `--behavior-program`. The program IS the behavioral layer:
  the harness calls `make_participant(seed)` once, then `respond(ctx)`
  per trial, and on interrupt-capable tasks polls during the intended
  RT and hands the program `on_interrupt(ctx, ssd_ms, intended)`.
  Programs return plain `(key, rt_ms)` tuples (stdlib+numpy only,
  deterministic per seed, no I/O/clock; see `behavior/provider.py`).
- **Analysis** (`src/experiment_bot/analysis/`,
  `experiment-bot-per-subject`) — per-subject measures from the
  platform's own data export (never the bot's self-log), compared
  against trial-level human reference data (Eisenberg et al. 2019)
  with identical estimators for both cohorts.

## Operational rules

- **No behavioral iteration (pre-specified).** The first program per
  task to pass the mechanical gate is the program. Regeneration only on
  gate failure (max 2 retries, all attempts archived). Never regenerate,
  edit, or select programs based on how their behavior looks.
- **Prompt neutrality.** The generation prompt and every value injected
  into it must name no phenomena, no distribution families, and no
  numeric behavioral priors. The invariant tests are the experiment's
  integrity guarantee — never weaken them to make a change pass.
- **Design freeze, not preregistration.** The dev-4 design/analysis plan
  was frozen in a document committed before any generation call (git
  `d75cd69`; removed from HEAD because its name overclaimed — no external
  registry holds it). Never call anything in this project "pre-registered";
  never rewrite history that carries the ordering evidence.
- **Hermetic provenance.** Sessions pin the structural card by content
  hash (`--taskcard-sha256`), the program by content hash
  (`--behavior-program <label>/<hash>`), and the participant by
  `--seed`. All three are recorded in each session's
  `run_metadata.json`; `scripts/naive_run.sh` pins them explicitly.
- **Generalizability (G1).** No paradigm-specific knowledge in library
  code. Structural facts (condition labels, key maps, interrupt
  presence) flow from the TaskCard/CLI into generic mechanics — never
  hardcode them.
- **Authoritative data.** Analysis reads the platform's export
  (`experiment_data.{csv,json}`), not `bot_log.json`.

## Style

- Inline TDD for small changes; subagent-driven development for larger
  plans. Keep the suite green (`uv run pytest -q`).
- Aggressive simplification bar: "necessary for current production
  runs," not "exists and works." Delete over refactor.
- Commit incrementally; tight, focused messages; end commits with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Avoid narration in user-facing replies; state results, propose next
  steps.

## Documents

- `docs/how-it-works.md` — the whole system, start to finish (question,
  integrity design, stages, evidence, limitations). Read this first.
- `docs/paper-draft-v2-naive-participant.md` — the paper draft for the
  two-arm experiment (this branch holds the naive arm).
- `docs/rdoc-battery-results.md` — the exploratory 12-task RDoC battery
  (collection + gate record, behavioral comparison vs the lab's human
  matrices). Registry: `data/rdoc_task_urls.tsv`; matrices:
  `data/bot/rdoc/` vs `data/human/rdoc/` (gitignored + placeholders).
- `README.md` — front door: quickstart, the five CLIs, evidence summary.
- `data/human/README.md` — human reference data download + integrity.

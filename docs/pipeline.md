# How the pipeline works, start to finish

One document, the whole system: from a task URL to a scored dataset. Every
step names the command that runs it and the artifact it produces.

```
URL ──▶ 1. structural reasoning ──▶ TaskCard (structure only)
              │
              ▼
        2. program generation ──▶ participant program (+ transcript)
              │
              ▼
        3. mechanical gate ──▶ gate report (pass required)
              │
              ▼
        4. seeded sessions ──▶ platform-native data (+ provenance)
              │
              ▼
        5. per-subject analysis ──▶ CSVs + comparison vs human reference
```

## 1. Structural reasoning — `experiment-bot-reason <url> --label <L>`

An LLM reads the experiment's scraped page source and produces a
**structural TaskCard**: how to *detect* each stimulus (CSS selector or JS
expression, with a condition label per stimulus), how to *navigate* the
instruction flow (ordered phases: clicks, keypresses, form fills/selects,
waits), which *keys*
the task accepts, runtime timing knobs (response-window checks, keypress
dwell, data-capture expressions), and whether the task has a mid-trial
interrupt signal. A short live pilot (~20 trials) then validates the
selectors against the real page, refining them one step at a time when they
fail. The card contains **no behavioral content** — no distributions, no
effect parameters — and is committed content-addressed at
`taskcards/<label>/<sha256>.json`. Sessions later pin it with
`--taskcard-sha256`.

## 2. Program generation — `experiment-bot-naive-gen <url> --label <L> --taskcard-sha256 <sha>`

A single prompt to the generation model contains exactly four things: the
task's page source, the mechanical facts the harness will share at runtime
(condition labels, key map, interrupt presence — pulled from the pinned
structural card), the participant-program protocol (below), and the
instruction to write a Python program whose recorded data would be
indistinguishable from a typical healthy adult's, with each seed a distinct
participant.

The prompt is **neutral by construction**: no distribution families, no
phenomenon names, no numeric behavioral priors. Invariant tests
(`tests/test_naive_prompt_invariants.py`) scan the template and every
injected constant against a banned-terms list; weakening them invalidates
the experiment's integrity guarantee.

The model's reply is archived under its content hash at
`naive_programs/<label>/<sha>.py` together with `<sha>.transcript.json`
(model, full prompt, raw response) — every attempt, including failed ones.

**The protocol** (`src/experiment_bot/behavior/provider.py`): a program
defines `make_participant(seed)` returning an object with
`respond(ctx) -> (key, rt_ms)` — called once per trial with the condition,
the correct key, the keys observed so far, the trial index, the previous
trial's outcome, the trial's visible context text (`ctx.stimulus_text`,
when the task exposes one), and, for tasks answered by clicking an
on-screen option, the options' labels (`ctx.response_elements`; the program
may then return `("click", index, rt_ms)` instead of a keypress) — and, for
interrupt tasks, `on_interrupt(ctx, ssd_ms, intended)` returning `None`
(withhold) or a commission response. Programs are stdlib+numpy only,
deterministic per seed, no I/O/network/clock. Every return value is
validated at the boundary; nothing is silently coerced.

## 3. Mechanical gate — `experiment-bot-naive-sim <program> ...`

Before any live session, the program runs against ~1,000 synthetic trials
built from the card's condition stream (including interrupts on the card's
interrupt condition). Checks are **purely mechanical**: no crashes; RTs
finite and in (0, 60 s]; keys legal; same seed → identical trace; different
seeds → distinct traces; imports within the whitelist. The report is
archived as `<sha>.simgate.json`. The gate never judges whether behavior
looks human — by pre-registered rule, the **first program to pass the gate
is the program** (regeneration only on mechanical failure, max 2 retries,
all attempts archived).

## 4. Seeded sessions — `experiment-bot <url> --label <L> --taskcard-sha256 <sha> --behavior-program <label>/<hash> --seed <N> --headless --no-calibration`

The executor opens the page in Playwright and, using only the structural
card: navigates the instruction flow (with a bounded LLM fallback for
unfamiliar screens), then polls the DOM for stimuli. Per trial it resolves
the correct key, builds the trial context, asks the program for `(key,
rt_ms)`, waits exactly that long, and delivers the keypress through a
timing-calibrated CDP channel (a `("click", index, rt_ms)` response is
delivered instead as a click on the chosen option's selector). On interrupt-capable tasks it polls for the
signal during the intended RT and, if the signal appears, hands the
program the stop/go decision (`ssd_ms` is the bot's detection latency for
the signal; the platform's own recorded delay is authoritative for
analysis). The trial outcome is fed back so the next trial's context
carries real history.

Everything needed to reproduce the session is recorded in
`run_metadata.json`: the structural-card hash, the program hash, and the
seed. `scripts/naive_run.sh` runs the full collection (generate → gate →
N seeded sessions per paradigm, idempotent by seed — re-running collects
only missing seeds) into `output_naive/`.

## 5. Analysis — `experiment-bot-per-subject --label all --output-dir output_naive --human-stop ... --human-stroop ... --out-dir <dir>`

Analysis reads the **platform's own data export**
(`experiment_data.{csv,json}`), never the bot's self-log. Each session
becomes one row of per-subject measures (correct-trial mean RTs,
accuracies, omissions, task effects, mean-method SSRT, lag-1 RT
autocorrelation, post-error slowing), computed by the same estimators
applied to the trial-level human reference data (Eisenberg et al. 2019;
`data/human/`). The comparison report positions the program cohort inside
the human between-subject distribution (z, within-1-SD) and carries the
pre-registered exploratory distribution-level checks (SD ratio, two-sample
KS).

## What is deliberately NOT here

The behavioral machinery lives in the generated program, not the codebase:
there is no distribution sampler, no effect registry, no accuracy targets,
no norms/oracle gating. The expert-parameterized comparison pipeline and
its dataset live on the `main` branch. The experiment's design and analysis
plan are frozen in `docs/preregistration-naive.md`; the write-up is
`docs/paper-draft-v2-naive-participant.md`.

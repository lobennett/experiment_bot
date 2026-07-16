# How experiment-bot works, start to finish

This is the one document to read to understand the system: what question it
answers, how it is built so the answer can be trusted, what happens at each
stage from a URL to a scored dataset, and what the evidence shows. It
explains the science first and names commands and files only where you need
them to follow along or reproduce something.

## 1. The question

Can a language model, given nothing but a web experiment's source code,
author a *computational participant* — a small program that decides every
response, key and reaction time, trial by trial — whose recorded data is
hard to distinguish from a real human participant's?

The question matters in two directions. For online data quality: if a
general-purpose agent can produce convincing data on standard cognitive
tasks, platforms need countermeasures, and the demonstration should be
public and reproducible. For cognitive science: whatever structure the
model writes into its participants *unprompted* — race models for stopping,
conflict adaptation, fatigue drift — is a measure of what task
understanding a model brings to bare source code.

The hard part of the question is the word *nothing*. It is easy to make a
bot match human data if you tell it what human data looks like. The entire
design below exists to make sure nobody — not the codebase, not the prompt,
not the experimenter — tells it.

## 2. The integrity design

Four rules make the result mean something. Each is enforced by machinery,
not by good intentions.

**Prompt neutrality.** The prompt that asks the model to write a
participant program contains no phenomenon names, no distribution families,
and no numeric behavioral priors — it names the task's mechanical facts
(condition labels, key map, whether a mid-trial interrupt exists) and asks
for data indistinguishable from a typical healthy adult's, each seed a
distinct person. Enforcement: invariant tests
(`tests/test_naive_prompt_invariants.py`, `tests/test_system_prompt_invariants.py`)
scan the prompt templates and every constant injected into them against a
banned-terms list (mechanism names, distributions, phenomena, `N ms`/`N %`
patterns). If a change would leak behavioral knowledge into the prompt, the
suite fails. Weakening these tests invalidates the experiment.

**No behavioral iteration.** The first program to pass the mechanical gate
(§5) *is* the program. No regenerating because the data looks wrong, no
editing, no selecting among candidates by behavior. Regeneration is allowed
only when the gate fails mechanically (max 2 retries), and every attempt —
including failures — is archived with its full model transcript. This rule
is what makes the result a one-shot measurement rather than an optimized
artifact.

**Design freeze — and what it is not.** The confirmatory experiment's
design, measures, and decision rules were fixed in a design document
committed to this repository *before the first generation call* (the
document's last edit, commit `d75cd69`, 2026-07-03 08:17 PDT, predates the
earliest archived generation transcript, 09:00 PDT). To be explicit about
the strength of that evidence: this is an **internal design freeze whose
ordering rests on git history**, not a preregistration — no external
registry (OSF, AsPredicted) holds an independent timestamp, and the word
"preregistration" is deliberately not used for it anywhere in this
package. The frozen document itself was removed from the tree for exactly
that reason (its original filename overclaimed); read it from history with
`git show d75cd69:docs/preregistration-naive.md`.

**Hermetic provenance.** Every session records three hashes/values that
pin it completely: the structural TaskCard's content hash, the participant
program's content hash, and the seed. Cards and programs are stored
content-addressed, so a recorded session can always be traced to the exact
bytes that produced it.

A fifth principle governs the code itself: **the library knows no tasks**.
There is no Stroop code, no stop-signal code, no grid code anywhere in the
harness. Every task-varying fact flows from the TaskCard into generic
mechanics. That is what lets the same pipeline run on a task it has never
seen — which is the claim under test.

## 3. Stage 1 — structural reasoning (URL → TaskCard)

`experiment-bot-reason <url> --label <L>`

Before anything can behave, something must *operate the page*. An LLM reads
the experiment's scraped page source (HTML plus linked JS/CSS) and produces
a **structural TaskCard**: how to detect each stimulus on screen (a
selector or JS expression, with a condition label), how to navigate the
instruction flow (ordered phases of clicks, keypresses, form fills, waits),
which keys the task accepts, where the correct answer for the current
trial can be read from the page's own state, how to capture the platform's
recorded data, and whether the task has a mid-trial interrupt signal. For
tasks answered by clicking on-screen options, the card lists those
elements; for tasks that test reproduction of a sequence (spatial span and
kin), the card exposes a JS expression that yields the trial's target
order.

The card is *structural only* — it contains no distributions, no effect
sizes, nothing behavioral. It answers "what is on the page and how do you
drive it," never "what should a participant do."

Because a parse of source code can be wrong about a live page, the card is
validated in two steps: a short live pilot (~20 trials) refines selectors
and navigation one step at a time against the real page, and a **replay
gate** then proves, in a fresh browser shaped exactly like the executor,
that the finalized navigation actually reaches trial rendering — feeding
failures back into refinement for a bounded number of rounds. Validated
cards land content-addressed at `taskcards/<label>/<sha>.json`.

## 4. Stage 2 — program authorship (the one generative act)

`experiment-bot-naive-gen <url> --label <L> --taskcard-sha256 <sha>`

One prompt to the model contains exactly four things: the page source, the
mechanical facts the harness will share at runtime (read from the pinned
card), the participant-program protocol, and the instruction to write a
Python program whose recorded data would be indistinguishable from a
typical healthy adult's, with each seed a distinct participant. Nothing
else — see §2 on how that "nothing else" is enforced.

**What a participant program is.** A program defines
`make_participant(seed)` returning an object with:

- `respond(ctx) → (key, rt_ms)` — called once per trial. The context
  carries the condition label, the correct key, the keys seen so far, the
  trial index, the previous trial's outcome, and the trial's visible text
  when the task exposes one. For click-answered tasks the context lists the
  options and the program may return `("click", index, rt_ms)`. For
  serial-reproduction trials the context carries the target order
  (`ctx.correct_sequence`) and the program may return a *list* of actions,
  each with its own inter-action time.
- `on_interrupt(ctx, ssd_ms, intended)` — interrupt tasks only. When a
  stop-type signal appears during the program's intended response time, the
  harness hands the program the signal delay and its own intended response;
  the program decides the outcome (withhold or respond). The race between
  going and stopping is therefore the program's to implement — or to fail
  to implement.

Two design points carry the science. First, the bot **does not perceive
stimuli**. It is told the trial's condition and correct answer, the same
way a psychophysicist knows the answer key; everything human about the
data — errors, RT structure, drifting attention, individual differences —
must be *generated*, drawn against that key from whatever internal model
the program implements. Second, programs are sandboxed to stdlib+numpy,
deterministic per seed, with no I/O, network, or clock — so a seed is a
reproducible synthetic participant, and a program can never look anything
up at runtime.

Every generation attempt is archived under its content hash at
`naive_programs/<label>/<sha>.py` with `<sha>.transcript.json` (model, full
prompt, raw response) and `<sha>.simgate.json` (gate report).

## 5. Stage 3 — the mechanical gate

`experiment-bot-naive-sim <program> ...`

Before any live session, the program runs ~1,000 synthetic trials built
from the card's condition stream (including interrupt trials and fuzzed
edge cases). The gate checks only that the program is *executable and
lawful*: no crashes; RTs finite and within (0, 60 s]; keys legal; same
seed → identical trace; different seeds → distinct traces; imports within
the whitelist. It never judges whether behavior looks human — that would
reintroduce behavioral selection through the back door. Its one job is to
make "the first passing program is the program" a safe rule to follow.

## 6. Stage 4 — execution (seeded sessions on the live page)

`experiment-bot <url> --label <L> --taskcard-sha256 <sha> --behavior-program <label>/<hash> --seed <N> --headless`

The executor opens the page in Playwright and, using only the structural
card: navigates the instruction flow (paced like a person — advances
spaced ≥2 s, because real tasks have anti-skim guards; a bounded LLM
fallback handles unfamiliar screens), then polls the DOM for stimuli. Per
trial it resolves the correct answer from the page's own state, builds the
context, asks the program for its response, waits exactly the program's
`rt_ms`, and delivers the response through a timing-calibrated channel
(CDP-level keypresses; clicks on the chosen option's selector; ordered
multi-action delivery for sequences). On interrupt-capable tasks it polls
for the signal during the intended RT and, on detection, hands the program
the stop/go decision. The trial's outcome is fed back so the next trial's
context carries real history — and when an outcome is unscoreable (e.g. a
keyboard-delivered reproduction), the program is told "unknown," never a
fabricated value.

What counts as a trial is structural, not behavioral: a stimulus is a
trial if it has a response channel and plays no structural role
(navigation, attention check, interrupt condition). Timing faithfulness is
the point of all of this — the platform's own recorded timestamps, not the
bot's intentions, are what analysis will read.

Each session writes the platform's native export
(`experiment_data.{csv,json}`), a per-trial decision log for debugging
(`bot_log.json` — never used for analysis), and `run_metadata.json` with
the provenance triple (§2). `scripts/naive_run.sh` runs full collections —
generate once, gate, then N seeded sessions per task, idempotent by seed.

## 7. Stage 5 — analysis (identical estimators, platform data only)

`experiment-bot-per-subject ...`

Analysis reads the platform's export, never the bot's self-log — the bot
is scored on what the platform recorded, exactly as a human would be. Each
session becomes one row of per-subject measures (condition-wise RTs,
accuracies, omissions, task effects, mean-method SSRT, lag-1 RT
autocorrelation, post-error slowing), computed by the *same estimator
code* applied to trial-level human reference data (Eisenberg et al. 2019,
N=522 workers; `data/human/`). Comparison places the bot cohort inside the
human between-subject distribution (z-scores, within-1-SD counts) plus
distribution-level checks (SD ratio, two-sample KS).

For the 12-task RDoC battery the comparison goes one step further: the
bot's exports were run through the *lab's own preprocessing pipeline* —
the same code that produced the human matrices — yielding
`data/bot/rdoc/<task>.csv` at exact column parity with
`data/human/rdoc/<task>.csv`. Parity by construction, not reimplementation.

## 8. The evidence

Three bodies of evidence, in increasing order of generalization distance.
Full numbers: `docs/paper-draft-v2-naive-participant.md` (dev-4
experiment) and `docs/rdoc-battery-results.md` (battery).

**Pre-specified comparison (dev-4).** Two paradigms × two independent
implementations (Stroop and stop-signal; Experiment Factory, STOP-IT,
Cognition.run), N=30 seeded sessions each, scored against the Eisenberg
human reference; an expert-parameterized pipeline (tuned distributions +
effect modules; archived at the `expert-arm-final` tag) ran as comparison
arm on the identical harness. Naive arm: **22 of 28 pre-specified
measures within 1 human SD** (expert: 23/28) — but the *kinds* of miss
differ diagnostically. The naive misses are calibration constants (RT
location runs slow; post-error slowing overshoots). The expert arm's miss
is architectural: its inhibition is a configured probability, so the
platform's SSD staircase cannot converge (SSRT collapses; KS p ≈ 10⁻⁴⁶
against human SSRT distributions), while the naive programs implemented an
actual race — unprompted — and are statistically indistinguishable from
humans on per-subject SSRT (274±46 / 278±40 ms vs human 303±76; KS
p ≈ 0.3). Zero program crashes and zero protocol violations across all 120
naive sessions.

**Held-out probe (flanker).** After the dev-4 collection, the
frozen pipeline was pointed at a fifth, never-seen implementation. One
structural card, one generation (first gate pass), five sessions:
flanker effect +58 ± 23 ms (literature ≈ 40–70 ms), positive in every
session, correct accuracy ordering. Every failure met on the way was a
harness bug, fixed generally; the behavioral layer was never touched.

**Exploratory 12-task RDoC battery.** All 12 RDoC Experiment Factory
tasks at N=5 (registry: `data/rdoc_task_urls.tsv`), including two
grid-recall span tasks that required the sequence-response capability (§4;
multi-action trials against a card-exposed target order — generic, no grid
geometry in library code). 11 of 12 programs passed the gate first-attempt.
Against the lab's human matrices: **84/149 metrics within 1 human SD**,
with an informative gradient — inhibition strongest (stop-signal 12/12),
attention/switching mid-range with the known slow-RT calibration shift
(internal effect structure intact everywhere), working memory weakest
(spans' recall real but degraded). Two framework findings reported
honestly rather than patched: attention checks go unanswered on the 10
newly generated cards (a Stage-1 classification variance — 1.0 accuracy on
the two dev cards where they are answered), and no number was ever fed
back into regeneration.

**What the programs contained** (archival observation — never a selection
criterion): hierarchical individual differences, autocorrelated attentional
states, practice and fatigue dynamics, deadline-emergent omissions;
congruency-sequence modulation in the Stroop programs; the independent
horse race of Logan & Cowan (1984) in the stop-signal programs.

## 9. Limitations and boundaries

- **Matching output distributions is not mechanism equivalence.** These
  are simulations of data, not of minds.
- **RT location drifts slow** without literature anchoring — the price of
  the no-priors rule, deliberately left unfixed under the no-iteration
  rule.
- **One program per task**: generation variance is unmeasured.
- The 12-task battery is exploratory (N=5, outside the frozen dev-4 plan),
  and its human comparison uses session-level matrices rather than
  trial-level data.
- The Stage-1 target-reconstruction guidance for span-type tasks was
  refined against this battery's two span implementations; its generality
  beyond them is untested.
- Online platform capture contributes occasional recording stalls,
  arm-independent of the behavioral layer.
- Platform knowledge in the harness is limited to declared, overridable
  jsPsych defaults (data-capture expressions, an instructions-pager
  fallback); no URLs or task names exist in library code.

## 10. Running it on a new task

```bash
uv sync && uv run playwright install chromium

# 1. Structural card (uses Claude; once per experiment)
uv run experiment-bot-reason "<url>" --label my_task

# 2. Participant program (uses Claude; once per experiment; gate runs automatically)
uv run experiment-bot-naive-gen "<url>" --label my_task \
  --taskcard-sha256 <sha printed by step 1>

# 3. Seeded sessions (no API needed; each seed = one synthetic participant)
uv run experiment-bot "<url>" --label my_task \
  --taskcard-sha256 <card-sha> --behavior-program my_task/<program-hash> \
  --seed 1001 --headless --no-calibration

# 4. Per-subject analysis vs a human reference
uv run experiment-bot-per-subject --help
```

Worked artifacts to study alongside a run: any
`taskcards/<label>/<sha>.json` (what a structural card looks like), any
`naive_programs/<label>/<sha>.py` with its `.transcript.json` (what the
model was asked and what it wrote), and any
`output_naive/<task>/<timestamp>/` session directory (what a hermetic
session records).

# How it works

Give this system the web address of a cognitive experiment. It comes back
with recorded behavioral data that looks, on most measures, like data from
a real person — and nobody ever told it what human data looks like.

## The question

Can a language model, reading nothing but an experiment's source code,
write a small program that plays a participant convincingly? The program
decides every response: which key, and how many milliseconds later.

The answer matters twice over. Online experiments can be flooded with fake
participants, so anyone running one should know how good a fake can get.
And whatever human-like structure the model builds into its programs
*without being asked* tells us something about how much it understands a
task from code alone.

The hard word in the question is *nothing*. Making a bot match human data
is easy if you tell it what human data looks like. Everything below exists
to make sure nobody tells it — not the code, not the prompt, not the person
running it.

## Four rules, enforced by machines

**The prompt says nothing about behavior.** It names the task's mechanical
facts: the condition labels, which keys the task accepts, whether a stop
signal can interrupt a trial. It never names an effect, a distribution, or
a number. Tests scan the prompt and every value injected into it against a
list of banned terms, so a change that leaks behavioral knowledge fails the
suite. Weaken those tests and the experiment means nothing.

**The first program that works is the program.** A generated program has to
survive a mechanical check (below). The first one that passes is kept. We
never regenerate it because the data looks wrong, never edit its responses,
and never run several and keep the most human-looking one. Regeneration is
allowed only when the check fails mechanically, at most twice, and every
attempt is archived with the full model transcript.

**The design was frozen before the first generation.** The measures and
decision rules were committed before any program was generated — commit
`d75cd69`, timestamped an hour before the earliest archived transcript.
This is a freeze that rests on git history, not a preregistration. No
outside registry holds a timestamp, and the word "preregistration" is never
used for it. Read the frozen document with
`git show d75cd69:docs/preregistration-naive.md`.

**Every session can be traced to the exact bytes that made it.** Each one
records three things: the hash of the structural description, the hash of
the program, and the seed. Both artifacts are stored by content hash, so
any past session replays exactly.

One more rule governs the code: **the library knows no tasks.** There is no
Stroop code, no stop-signal code, no grid code. Every fact that varies by
task flows in from the structural description. That is why the same
pipeline runs on a task it has never seen — which is the whole claim.

## Stage 1: read the page

```
experiment-bot-reason <url> --label <name>
```

Something has to drive the page before anything can behave. A model reads
the scraped source — HTML plus the linked JavaScript — and writes a
**structural description** of the task: how to spot each stimulus on
screen, how to click through the instructions, which keys the task accepts,
where on the page the current trial's correct answer can be read, and
whether a stop signal can interrupt. For tasks answered by clicking, it
lists the clickable options. For tasks that ask you to reproduce a
sequence, it gives an expression that yields the target order.

The description holds no behavior. It answers "what is on this page and how
do I operate it," never "what should a participant do."

A parse of source code can be wrong about a live page, so the description
gets tested twice: a pilot of about twenty trials fixes selectors and
navigation against the real page one step at a time, and then a replay
check proves, in a browser shaped exactly like the one that will run the
session, that the navigation really does reach the first trial. Failures
feed back into refinement. What survives lands at
`taskcards/<name>/<hash>.json`.

## Stage 2: write the participant

```
experiment-bot-naive-gen <url> --label <name> --taskcard-sha256 <hash>
```

This is the only creative step. One prompt carries four things: the page
source, the mechanical facts the harness will share at runtime, the
protocol the program must follow, and the instruction to write a Python
program whose recorded data would be indistinguishable from a typical
healthy adult's, with each seed a different person. Nothing else.

A program defines `make_participant(seed)`, which returns an object with
two methods:

- **`respond(ctx)`** returns `(key, rt_ms)` once per trial. The context
  carries the condition, the correct key, the keys seen so far, the trial
  number, how the last trial went, the trial's visible text, and anything
  the task displayed since the previous trial — a between-block score
  message, for instance. The harness never interprets that text. It only
  makes sure the participant can see what a person at the keyboard would
  see. On click tasks the program may answer with an option index; on
  reproduction tasks it may return a list of actions, each with its own
  delay.
- **`on_interrupt(ctx, ssd_ms, intended)`** runs only on tasks with a stop
  signal. When the signal appears during the program's intended reaction
  time, the harness hands over the delay and the response the program had
  planned. The program decides whether it manages to stop. The race between
  going and stopping is the program's to implement — or to fail to
  implement.

Two details carry the science. First, **the bot cannot see stimuli.** It is
told the condition and the correct answer, the way an experimenter knows
the answer key. Everything human about the data — errors, the shape of the
reaction-time distribution, attention drifting, one participant differing
from the next — has to be generated. Second, programs run on the standard
library and numpy only, with no file access, no network, and no clock, and
they are deterministic given a seed. A seed is therefore a reproducible
synthetic person, and a program can never look anything up.

Every attempt is archived at `naive_programs/<name>/<hash>.py` beside its
transcript and its check report.

## Stage 3: check that the program is lawful

```
experiment-bot-naive-sim <program>
```

Before any live session, the program runs about a thousand simulated
trials. The check asks only whether the program is executable and legal: it
must not crash, its reaction times must be finite and under a minute, its
keys must be pressable, the same seed must reproduce the same trace,
different seeds must differ, and its imports must be on the safe list.

It never asks whether the behavior looks human. That would sneak
behavioral selection in through the back door. Its one job is to make "keep
the first program that passes" a safe rule.

## Stage 4: run the session

```
experiment-bot <url> --label <name> --taskcard-sha256 <hash> \
  --behavior-program <name>/<hash> --seed <n>
```

The executor opens the page in a real browser and, using only the
structural description, clicks through the instructions at a human pace —
advances spaced at least two seconds apart, because real tasks guard
against skimming. Then it watches the page for stimuli.

For each trial it reads the correct answer out of the page's own state,
builds the context, asks the program what to do, waits exactly the
program's reaction time, and delivers the response through a
timing-calibrated channel. On stop-signal tasks it watches for the signal
during that wait and hands the program the decision when it appears. The
outcome feeds forward, so the next trial's context carries real history —
and when an outcome cannot be scored, the program is told "unknown" rather
than a made-up value.

What counts as a trial is structural, never behavioral: a stimulus is a
trial when it has a response channel and plays no other role. Timing
fidelity is the point of all of it, because the numbers that matter are the
ones the experiment's own software writes down.

Each session saves the platform's native export, a decision log for
debugging that analysis never touches, and the provenance triple.

## Stage 5: score bot and humans the same way

```
experiment-bot-per-subject ...
```

Analysis reads what the experiment recorded, never the bot's own log. The
bot is scored on the platform's data exactly as a person would be.

Each session becomes one row of per-subject measures — reaction times and
accuracies by condition, omissions, task effects, stop-signal reaction
time, trial-to-trial correlation, slowing after errors — computed by the
*same code* that scores the human reference data. Then the bot cohort is
placed inside the spread of human individuals, with distribution-level
checks alongside.

For the twelve-task battery the comparison goes further: the bot's exports
ran through the lab's own preprocessing pipeline, the same code that made
the human matrices. The columns match by construction, not by
reimplementation.

## Running it on a new task

```bash
uv sync && uv run playwright install chromium

# 1. Structural description (uses Claude; once per experiment)
uv run experiment-bot-reason "<url>" --label my_task

# 2. Participant program (uses Claude; once per experiment)
uv run experiment-bot-naive-gen "<url>" --label my_task \
  --taskcard-sha256 <hash from step 1>

# 3. Sessions (no API needed; each seed is one synthetic participant)
uv run experiment-bot "<url>" --label my_task \
  --taskcard-sha256 <card-hash> --behavior-program my_task/<program-hash> \
  --seed 1001 --headless

# 4. Compare against a human reference
uv run experiment-bot-per-subject --help
```

Three artifacts are worth opening while you follow along: any
`taskcards/<name>/<hash>.json` to see what a structural description looks
like, any `naive_programs/<name>/<hash>.py` with its transcript to see what
the model was asked and what it wrote, and any session directory under
`output_naive/` to see what one run records.

## What this cannot tell you

- **Matching data is not matching minds.** These programs simulate
  behavior, not cognition.
- **Reaction times run slow.** Without literature to anchor absolute
  speed, the programs land late on several tasks. The no-iteration rule
  means we left it that way.
- **One program per task.** Generation variance is unmeasured, and every
  number comes from one model family. "A frontier model can do this" is
  really "this model did it once per task."
- **The battery uses a coarser human reference** than the two-task
  comparison — session-level matrices rather than trial-level data — and
  its headline is sensitive to how those rows are handled. See
  [results.md](results.md).
- **Detection evidence covers one product and one batch.** The
  human-discrimination pilot used two raters, one of them the author.
- **Reproduction under time pressure is a real boundary.** The two span
  tasks fail for a reason the design chose to accept.

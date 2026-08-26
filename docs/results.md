# Results

Three things were measured: how close the bot's behavior sits to human
behavior, whether a commercial bot-detector catches it, and where it breaks
down. This document covers all three and is honest about which numbers are
solid and which are not.

## The strongest result: the bot builds a race model nobody asked for

Start with the finding that does not depend on any bot framing.

Stopping a started action is a race. A "go" process runs toward the
response; when a stop signal appears, a "stop" process runs against it. If
the stop process wins, no response. Experiments measure this by moving the
signal earlier or later until the participant fails to stop about half the
time, then working backwards to the stopping latency (SSRT).

The generated programs implemented that race — a per-trial stopping latency
competing against the go process — with no prompting. Because the race is
closed-loop, the experiment's own adaptive staircase converged, and
per-subject SSRT came out indistinguishable from human SSRT (KS p ≈ 0.3).

A comparison pipeline built the expert way — hand-tuned distributions,
explicit effect modules, far more human knowledge poured in — **cannot do
this**. Its inhibition is a fixed probability that ignores the signal
delay, so the staircase never settles, and SSRT collapses (KS p ≈ 10⁻⁴⁶).
No parameter setting repairs it.

That is a claim about what kind of thing can represent a task. A generative
program can express closed-loop dynamics; a parameter template cannot. The
model supplied the right dynamics on its own.

The programs also contain, unprompted: differences between individuals
drawn from a hierarchy, attention that drifts and autocorrelates across
trials, practice and fatigue, and slowing after conflict.

_(These numbers come from the earlier two-paradigm comparison and were not
recomputed in the most recent documentation pass.)_

## The twelve-task battery

All twelve RDoC Experiment Factory tasks, twenty sessions each, 240
sessions total. Every program passed the mechanical check on its first
attempt.

**99 of 149 measures fall within one human standard deviation (66%).**
Drop the two span tasks and it is 95 of 121 (79%). Ten of twelve tasks
reach 60% or better.

| Task | Within 1 SD |
|---|---|
| flanker | 8/8 |
| spatial task-switching | 14/16 |
| n-back | 13/14 |
| stop-signal | 11/12 |
| spatial cueing | 10/14 |
| AX-CPT | 10/15 |
| visual search | 10/14 |
| cued task-switching | 9/13 |
| go/no-go | 5/7 |
| Stroop | 5/8 |
| simple span | 2/12 |
| operation span | 2/16 |
| **Total** | **99/149 (66%)** |

Attention checks are answered, and answered correctly, on eleven of twelve
tasks. On operation span the bot answers them with the task's grid keys
instead of the letter the check wants — a known defect on the battery's
most tangled trial flow.

### Two cautions about that number

**It moves depending on how you count the humans.** The human reference
holds about five sessions per person, plus rows that are not people at all.

| How the human rows are handled | Total |
|---|---|
| Everything, including `Max`/`Mean`/`Min`/`SD` rows | 100/149 (67%) |
| **All sessions, non-person rows dropped** (reported above) | **99/149 (66%)** |
| One session per person (a true between-person spread) | 97/149 (65%) |

An earlier version of this document reported the first number. That was
wrong in kind: `Max` and `Min` are not participants, and counting them
inflates the human spread, which makes the test easier to pass. The last
row is the strictest and arguably the most correct. Two percentage points
separate them, so nothing here turns on the choice.

**Per-task fractions do not survive a change in sample size.** An earlier
round with five sessions per task reported stop-signal 12/12 and spatial
task-switching 16/16. Neither holds at twenty sessions against a strict
between-person reference (6/12 and 9/16). More sessions tighten the bot's
average against a fixed human spread, and borderline measures fall out.

**So trust the total and the ordering of tasks. Do not treat any single
task's fraction as a finding.**

### Where the reaction times still drift

Absolute speed runs slow on Stroop, spatial cueing, cued task-switching,
and the harder visual-search condition. The internal structure of the
effects stays intact — the pattern is right, the offset is wrong. This is
the price of refusing to give the model any numbers, and the no-iteration
rule means it stays.

One channel went entirely unused: the harness passes along any message the
task displays between trials, and not one of the twelve programs read it.
Nothing here shows the bot adapting within a session.

## Can a detector catch it?

All 240 sessions carried Roundtable's Proof-of-Human tracker, which returns
a risk score from 0 (accept) to 100 (reject).

Getting the browser right is what matters. Running headless scored 100 out
of 100 — flagged as a bot browser with a software renderer. Switching to
real Chrome with a GPU renderer and no automation flag dropped it to about
50, and every environment flag cleared. Humanizing how long keys are held
down changed nothing.

On those 240 clean-environment sessions:

| Risk score | Meaning | Sessions |
|---|---|---|
| 0 | accept | 33 (14%) |
| 30 | low | 1 |
| 50 | manual review | 201 (84%) |
| 80 | high | 4 (2%) |
| 100 | reject | 1 (<1%) |

**One session in 240 was rejected outright.** Fourteen percent were
accepted. The rest were handed to a human to decide.

The rule-based behavioral detectors found almost nothing: teleporting mouse
fired 5 times in 240, center clicks once, and every other behavioral flag
zero times. What remains is a single opaque machine-learning score.

Operation span — the most complex task, with a math sub-task interleaved
with grid recall — passed **20 out of 20**, with no mouse events at all.
That kills the obvious theory that adding a fake mouse trail is the missing
piece.

**Scope:** this is one commercial product on one batch of sessions. It says
nothing about detection in general, and chasing an opaque score further
would be evasion research rather than the question this project asks.

### Can a person catch it?

A small pilot: five tasks, forty records each (twenty bot, twenty human),
identity stripped and shuffled, labeled by two cognitive scientists.

A domain expert blind to how the bot works scored at chance on the four
usable tasks — 51%. The system's own author, who knows its calibration
signatures, reached 79%. The fifth task, AX-CPT, was excluded: its giveaway
is a harness bug (the bot presses an advance key on a between-trials
screen), not behavior.

Two raters, one of them not independent. This motivates a real study; it is
not an estimate.

## Where it breaks: the two span tasks

The spans are the floor of the battery (2/16 and 2/12), and the reason is
specific and instructive.

A span trial asks you to reproduce a sequence of grid cells. You navigate a
cursor with arrow keys and select with the spacebar. So a trial is not one
timed keypress — it is a burst of them under a deadline.

The bot moves through the grid at roughly 1,500 ms per step. People take
about 290 ms. Nothing in the design tells the model how fast a hand moves,
and telling it would be exactly the behavioral prior the whole project
forbids. So the bot runs out of time and its recall gets cut off partway
through. Low recall is a *consequence* of slow navigation, not a separate
memory failure: the bot delivers about as many selections as a person but
finishes with roughly 900 ms left on the clock instead of 3,000.

Operation span fails a second way. It interleaves a symmetry judgment about
an 8×8 pattern, and the bot answers "symmetric" every time — 100% correct
on symmetric trials, 0% on asymmetric ones. It cannot see the pattern. The
structural description points at a plausible-looking page variable that
does not hold the per-trial answer, and the real answer sits in a
task-internal field no card references. Re-deriving the description from
scratch did not find it either.

None of this is fixable within the rules. Timing needs a number. Recall
needs a prescribed policy. The symmetry judgment needs either working
perception or a hand-wired answer lookup, which would be task-specific code
in a pipeline whose whole claim is that it has none.

**So the boundary is clear: the approach generalizes to tasks where a trial
is a single timed keypress against an answer the page already exposes. It
does not generalize to building a multi-step response under time
pressure.** That is a limit worth reporting rather than engineering away.

## Where the evidence lives

Everything above is reproducible from the repository: sessions in
`output_naive/`, programs with their transcripts and check reports in
`naive_programs/`, structural descriptions in `taskcards/`, the metric
matrices in `data/bot/rdoc/` beside `data/human/rdoc/`, and per-subject
comparisons in `analysis_out_naive/`.

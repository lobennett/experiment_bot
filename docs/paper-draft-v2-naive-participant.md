# A Language Model Writes Validated Computational Participants from Task Source Code Alone

_Matured draft, 2026-07-06 — supersedes the two-arm draft of 2026-07-05.
Incorporates the standalone naive pipeline (this branch), the held-out
flanker probe, and the harness hardening it forced. Provenance: the
expert-pipeline comparison arm (code and dataset) lives on the `main`
branch; this branch contains the complete naive system. Pre-registration:
`docs/preregistration-naive.md` (committed before any generation call)._

## Abstract (working)

We test whether a frontier language model, given only a web experiment's
source code, can author a *generative computational participant* — a small
program deciding every response, trial by trial — whose platform-recorded
data matches human reference data. With no behavioral scaffolding (no
distribution families, no named effects, no numeric priors; enforced by
tested prompt invariants), one generation attempt per task, and no
behavioral iteration, the model's programs matched a 522-worker human
reference on 22 of 28 pre-registered measures across four task
implementations, and were statistically indistinguishable from humans on
per-subject stop-signal reaction time distributions (KS p ≈ 0.3) — a
property the expert-parameterized comparison pipeline fails
architecturally (z ≈ −3, KS p ≈ 10⁻⁴⁶). A held-out probe on a fifth,
never-before-seen task (Eriksen flanker) produced a first-shot,
gate-passing program and five sessions of literature-typical behavior
(flanker effect +58 ± 23 ms), while every failure encountered en route
hardened the browser harness — never the behavior.

## Methods

### The pipeline

The system is a thin, task-agnostic harness around a single generative
act. Four stages, each producing a content-addressed artifact:

**1. Structural reasoning.** An LLM parses the experiment's scraped page
source into a *structural* TaskCard: stimulus-detection expressions with
condition labels, navigation phases, key mappings, phase-detection
predicates, and data-capture configuration — no behavioral content of any
kind. A live pilot (~20 trials) validates the card against the real page,
refining selectors and navigation one step at a time, and a **replay
gate** then proves the finalized navigation reaches trial rendering in a
fresh browser shaped exactly like the executor — including the executor's
human-paced advance behavior (key presses and button clicks spaced ≥2 s,
which real anti-skim instruction guards require) — feeding any gate
failure back into the refinement walker for a bounded number of extra
rounds.

**2. Program generation.** One prompt to Claude Fable 5 contains the page
source, the mechanical facts the harness will share at runtime (condition
labels, key map, interrupt presence — read from the pinned structural
card), a ten-line protocol contract, and the instruction to write a
Python program whose recorded data would be indistinguishable from a
typical healthy adult's, each seed a distinct participant. The prompt is
neutral by construction: invariant tests scan the template and every
injected constant against a banned-terms list (mechanism names,
distribution families, phenomenon names, numeric behavioral priors).
Programs are stdlib+numpy, deterministic per seed, no I/O or clock.

**3. Mechanical gate.** Before any live session the program runs ~1,000
synthetic trials: no crashes, RTs finite and bounded, keys legal, same
seed → identical trace, different seeds → distinct traces, imports
whitelisted. The gate never evaluates whether behavior looks human. By
pre-registered rule the **first gate-passing program is the program**;
regeneration is permitted only on mechanical failure (max 2 retries, all
attempts archived with full transcripts).

**4. Execution and analysis.** The executor navigates with the structural
card, detects stimuli, and delegates every response to the program:
`respond(ctx) → (key, rt_ms)` per trial (context: condition, correct key,
keys observed so far, trial index, previous-trial outcome), and on
interrupt-capable tasks hands the program the stop/go race
(`on_interrupt(ctx, ssd_ms, intended)`). Keypresses are delivered through
a timing-calibrated channel; a stimulus is treated as a trial iff it has
a response channel and plays no structural role (navigation,
attention-check, or interrupt condition). Sessions are hermetic: card
hash + program hash + seed recorded per session. Analysis reads the
platform's own export, computing per-subject measures with estimators
applied identically to trial-level human reference data (Eisenberg et
al., 2019; N=522 workers).

### Datasets

**Pre-registered comparison (dev-4):** two paradigms × two independent
implementations (stop-signal: Experiment Factory RDoC, STOP-IT/jsPsych;
Stroop: Experiment Factory RDoC, Cognition.run), N=30 seeded sessions
each. Comparison arm: an expert-parameterized pipeline (LLM-tuned
ex-Gaussian distributions, Bernoulli accuracy targets, additive effect
modules) re-collected on the identical harness (N=30 × 4; assets on
`main`). Arms are scored against the human reference, never against each
other. Confirmatory measure: cohort mean within 1 human SD; exploratory:
between-subject SD ratio and two-sample KS.

**Held-out probe (flanker):** after the pre-registered collection was
complete and the naive system frozen, we pointed the pipeline at a fifth
implementation it had never encountered (Experiment Factory RDoC Eriksen
flanker). The full pipeline ran as designed: structural card generated
and gate-validated, one program generation (first gate pass, no
iteration), five seeded sessions. No trial-level human flanker reference
exists in this repository, so the probe is evaluated mechanically and
descriptively against the published literature, outside the
pre-registered battery.

## Results

### Pre-registered comparison

**Data quality.** A platform data-capture stall class (single trials
recorded at multi-second values) affected STOP-IT sessions in both arms
(naive 2/30, expert 3/30) — arm-independent, excluded and flagged. Zero
program crashes and zero protocol violations across all 120 naive
sessions.

**Confirmatory: 22 of 28 measures within 1 human SD** (expert arm:
23/28). Accuracy, omission, and stop-accuracy measures were within range
on all four implementations. On Experiment Factory Stroop the naive arm
was within range on **all seven** measures, including the Stroop effect
and lag-1 autocorrelation — both chronic expert-arm misses. The naive
misses are uniform in kind: reaction-time location runs slow on two
implementations (go RT 675 vs 585±85 ms, z = +1.06; Cognition.run
congruent 817 vs 673±102, z = +1.42) and post-error slowing overshoots
on the stop tasks (+74 vs +8±25 ms, z = +2.69) — calibration constants,
not structure.

**Stopping is human-indistinguishable — the headline.** Because the
programs implement an actual race (per-trial SSRT draws against the go
process, with trigger failures), the platforms' SSD staircases converged
and SSRT emerged correctly on both implementations: 274±46 and 278±40 ms
vs the human 303±76 (z = −0.37, −0.31), with two-sample KS unable to
distinguish bot from human per-subject SSRT distributions (p ≈ 0.3).
The expert arm — whose inhibition is a configured probability
independent of SSD — cannot converge the staircase: mean SSD inflates to
~500 ms and SSRT collapses (71/99 ms; z = −3.04, −2.67; KS p ≈ 10⁻⁴⁶).
Signal-respond trials were faster than go trials in every naive session,
as the race model requires. No parameter setting of the expert
vocabulary repairs this; it is an architectural property.

**Sequential structure and dispersion.** Lag-1 autocorrelation fell
within the human range on three of four implementations (expert:
overshoots to z = +4.27 on STOP-IT); between-subject dispersion, drawn
from each program's own trait hierarchy, reached SD ratios of 0.5–0.9 of
human on RT measures.

**What the programs contained** (archival description — programs were
never selected or edited on behavioral grounds): all four implemented
hierarchical individual differences, latent autocorrelated attentional
states, practice and fatigue dynamics, and deadline-emergent omissions;
both Stroop programs implemented interference with congruency-sequence
modulation and fast word-capture errors; both stop-signal programs
implemented the independent horse race of Logan and Cowan (1984),
unprompted.

### Held-out probe: flanker

The probe is the generalization test the pipeline claims to support:
URL in, data out, no task-specific code.

**Outcome.** Structural card produced (two walker refinements plus
replay-gate feedback rounds); program generated in one attempt and
passed the gate first-shot; 5/5 sessions completed with full platform
exports (120 test trials each). Descriptively, behavior is
literature-typical: flanker effect **+58 ± 23 ms** (letter-flanker
literature range ≈ 40–70 ms), positive in every session (range
30–91 ms — five visibly distinct participants); congruent/incongruent
RTs 573±71 / 632±73 ms; accuracy ordering correct (0.963 vs 0.923);
omissions 1.5%. The generated program again contained per-seed trait
hierarchies, Gratton-style conflict adaptation, and post-error slowing,
unprompted.

**The probe as an audit.** Reaching this outcome surfaced six framework
defects, every one fixed generally, with regression tests and zero
flanker-specific code: stray LLM-emitted behavioral fields crashing the
structural pipeline; replay-gate failures not feeding back into
refinement; the replay under-modeling the executor's advance behavior
(button clicks); unpaced instruction advancing tripping the task's
anti-skim guard — in the replay and in the executor; and a residue of
the deleted expert vocabulary (trial-ness inferred from
response-distribution keys) that silently produced zero-trial sessions
on any newly generated card. The division of labor held exactly as
designed: every failure was repaired in the harness; the behavioral
layer was never touched.

## Discussion

Three claims. **First**, behavioral scaffolding is not necessary: with
the entire expert vocabulary deleted from the codebase, a one-shot,
un-iterated program from a language model matches a human reference at
parity on coarse measures and surpasses the expert pipeline on
structure — race dynamics, serial dependence, dispersion. **Second**,
the failure profiles are complementary and diagnostic: the expert arm's
misses are architectural (a template that cannot express closed-loop
stopping), the naive arm's are calibration constants (absolute speed,
one effect magnitude) — the easiest kind of error to fix and, under our
no-iteration rule, the kind we deliberately left in place. **Third**,
generalization is cheap: the marginal cost of a new task was one
structural card, one generation, and five sessions — plus a set of
harness bugs whose repair benefits every task.

Limitations: the human reference covers two of the three paradigms
(flanker is evaluated descriptively); RT calibration drifts slow without
literature anchoring; single program per task (generation variance
unmeasured); online platform capture contributes a stall artifact
independent of the behavioral layer; and matching output distributions
is not mechanism equivalence — these are simulations of data, not of
minds. The natural synthesis is a hybrid: literature-calibrated
parameters embedded in model-authored generative programs, preserving
the naive arm's structure and the expert arm's calibration, with the
four dev-task programs plus the flanker program as the design corpus.

## References

Eisenberg, I. W., Bissett, P. G., Enkavi, A. Z., et al. (2019).
Uncovering the structure of self-regulation through data-driven ontology
discovery. *Nature Communications, 10*, 2319.

Eriksen, B. A., & Eriksen, C. W. (1974). Effects of noise letters upon
the identification of a target letter in a nonsearch task. *Perception &
Psychophysics, 16*, 143–149.

Lakens, D. (2017). Equivalence tests: A practical primer. *Social
Psychological and Personality Science, 8*(4), 355–362.

Logan, G. D., & Cowan, W. B. (1984). On the ability to inhibit thought
and action. *Psychological Review, 91*, 295–327.

Sochat, V. V., et al. (2016). The Experiment Factory: Standardizing
behavioral experiments. *Frontiers in Psychology, 7*, 610.

Stroop, J. R. (1935). Studies of interference in serial verbal
reactions. *Journal of Experimental Psychology, 18*, 643–662.

Verbruggen, F., et al. (2019). A consensus guide to capturing the
ability to inhibit actions and impulsive behaviors in the stop-signal
task. *eLife, 8*, e46323.

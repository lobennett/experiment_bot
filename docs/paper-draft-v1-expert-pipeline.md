# Draft A (Version 1): Agentic AI Can Generalize to Multiple Speeded Tasks with Human-Like Behavior

_Draft 2026-07-05, for co-author review. Supersedes the frozen-dataset draft
(`paper-methods-draft.md`): the bot dataset here is the **expert-v2**
re-collection (N=30/implementation) under the executor that applies the
TaskCards' declared between-subject variance — the frozen dataset's cohorts
were near-replicates because that variance was silently dropped. Companion
draft: `paper-draft-v2-naive-participant.md`._

## Methods

**Overview.** An agentic system takes a single experimental URL and produces
sessions of platform-native behavioral data intended to approximate a human
participant. A Reasoner (Claude Opus 4.8) reads the experiment's source and
emits a versioned, content-addressed TaskCard; an Executor drives the live
experiment (Playwright) and executes responses; analysis scores the resulting
cohorts against trial-level human reference data. The system simulates rather
than solves: on each trial it samples a reaction time from a configured
distribution and draws a response against configured accuracy targets.

**Reasoner.** Six staged LLM calls: structural analysis (stimulus-detection
selectors, navigation, key mappings), behavioral parameterization,
literature-grounded citation with programmatic DOI verification,
parameter-sensitivity tagging, and a live ~20-trial pilot validating the
selectors with a targeted refinement loop. The experimenter constrains the
behavioral vocabulary at two points: a closed menu of reaction-time
distribution families (ex-Gaussian, lognormal, shifted Wald; all four
implementations selected the ex-Gaussian) and a fixed set of eight generic
temporal mechanisms (autocorrelation, fatigue drift, condition repetition,
1/f noise, lag-1 pair modulation, post-event slowing, practice effect,
vigilance decrement) that the Reasoner selects and parameterizes per task.
The card also declares between-subject variance: a shared per-session speed
shift, multiplicative σ/τ scaling, and accuracy/omission perturbations.

**Executor.** For each session (explicit recorded seed, TaskCard pinned by
content hash) the executor draws the session's participant-level parameters
from the card's declared between-subject variance, then runs the trial loop:
detect stimulus, draw omission and correctness, sample the condition's RT,
apply enabled temporal mechanisms additively, wait, and deliver the keypress
through a timing-calibrated channel. On stop trials, inhibition is drawn
against a configured stop-accuracy target when the stop signal is detected.

**Tasks, platforms, dataset.** Two cognitive-control paradigms × two
independent implementations each: stop-signal (Experiment Factory RDoC;
STOP-IT/jsPsych) and Stroop (Experiment Factory RDoC; Cognition.run). N=30
sessions per implementation, hermetic (pinned card hash + recorded seed,
regenerable from `scripts/frozen_run.sh`), startup calibration disabled
(platform-inert; corrupted trial-1 RT on no-idle platforms).

**Human reference and measures.** Eisenberg et al. (2019) trial-level data,
test-phase, one metric row per worker (N=522), identical estimators for bot
and human: correct-trial mean RTs, accuracies, omissions, Stroop effect,
mean-method SSRT (reported descriptively), lag-1 RT autocorrelation, and
post-error slowing. Confirmatory analysis: cohort mean positioned in the
human between-subject distribution (z, within-1-SD). Pre-registered
exploratory analysis: between-subject SD ratio and two-sample KS test.

## Results

**Data quality.** Three STOP-IT sessions contained platform data-capture
stalls (single trials recorded at >2 s up to 66 s) and are excluded and
flagged; the stall class also appears at a similar rate in the companion
naive arm, indicating a platform/capture artifact independent of the
behavioral layer.

**Confirmatory: 23 of 28 measures within 1 human SD.** Reaction-time
location and accuracy were within 1 SD on all four implementations (go RT
575/581 ms vs 585±85; Stroop congruent/incongruent 631/691 and 652/717 ms vs
673±102/795±123), as were stop accuracies (both 0.5) and post-error slowing
on three of four implementations.

**Between-subject dispersion improved but remains under-human.** Applying
the cards' declared variance raised RT dispersion from 0.11–0.21× human (the
frozen dataset) to 0.29–0.97×. The KS test still rejects bot–human
distributional equivalence on 15 of 28 measures; matching the human mean
remains easier than matching the human spread.

**A structural stopping artifact, exposed by the dispersion fix.** SSRT was
far below the human range on both stop-signal implementations (71±22 and
99±27 ms vs 303±76; z = −3.04 and −2.67; KS p ≈ 10⁻⁴⁶) because mean SSD
ballooned to 504/482 ms vs the human 282 ms. The mechanism is architectural:
the bot's inhibition is a Bernoulli draw against a configured target and does
not depend on SSD, so the platform's staircase receives no corrective
feedback; with per-session accuracy jitter, the SSD random-walks toward its
rails. The frozen (variance-free) dataset masked this. The failure is not a
parameter mis-estimate — no setting of the current vocabulary produces
SSD-dependent stopping.

**Sequential structure remains the other systematic gap.** Lag-1
autocorrelation overshoots on STOP-IT (0.19±0.08 vs −0.00±0.04, z = +4.27)
and Experiment Factory Stroop (0.27±0.12 vs 0.07±0.13, z = +1.55); the
Stroop interference effect remains undersized on Experiment Factory
(60±39 ms vs 123±61, z = −1.04).

**Interpretation.** The expert-parameterized architecture reproduces
human-range means and accuracy across tasks and platforms — the
generalization the design targeted — but its remaining failures are
structural (closed-loop stopping, emergent serial dependence), not
calibrational, motivating the model-authored generative-participant
approach evaluated in the companion draft.

## References

(As in `paper-methods-draft.md`: Eisenberg 2019; Lakens 2017; Logan & Cowan
1984; Matzke & Wagenmakers 2009; Sochat 2016; Stroop 1935; Verbruggen 2019.)

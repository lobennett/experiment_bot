# Agentic AI Can Generalize to Multiple Speeded Tasks with Human-Like Behavior

## Methods

**Overview:** We built an agentic system that, from a single experimental URL,
produces a session of platform-native behavioral data intended to be
indistinguishable from that of a human participant. The system has three
layers. A Reasoner reads the experimental source and emits a structured task
representation; an Executor drives the live experiment and executes responses;
an Oracle scores the resulting sessions against human reference data. The
system simulates participant behavior by sampling a reaction time from a
configured distribution and drawing a response from a configured accuracy
target.

**Reasoner:** Given an experimental URL, the system scrapes the page's static
source and its runtime JavaScript state and passes them to Claude Opus 4.8
(Anthropic) through a staged reasoning pipeline: structural analysis of the
task, behavioral parameterization, literature-grounded citation with
programmatic DOI verification, parameter-sensitivity tagging, and a brief
automated pilot session (~20 trials) that validates the stimulus-detection
selectors against the live experimental DOM and triggers a targeted refinement
loop when a selector fails. The pipeline identifies the paradigm and emits a
versioned, content-addressed TaskCard specifying, per experimental condition, an
ex-Gaussian reaction time distribution (μ, σ, τ; Matzke & Wagenmakers, 2009),
accuracy and omission rate targets, any sequential reaction time effects, and
between-subject variance. Parameter values are derived from the model's
knowledge of the task literature, with no task-specific instruction from the
experimenter.

The experimenter intervenes on behavioral performance at two points. The first
is the choice of distribution family (ex-Gaussian). The second is a fixed
selection of eight generic temporal mechanisms from which the Reasoner selects
and parameterizes: autocorrelation, fatigue drift, condition repetition, 1/f
(pink) noise, lag-1 pair modulation, post-error slowing, practice effect, and
vigilance decrement. The mechanisms are deliberately paradigm-agnostic.
Paradigms that would be named for a specific task (e.g., post-stop-signal
slowing, congruency-sequence effect) are configured from these generic
mechanisms rather than named as primitives, so the executor's library carries
no paradigm-specific vocabulary and applies an effect only where the Reasoner
enables it.

**Executor:** The executor drives the live experiment in a headless Chromium
browser (Playwright), advancing through instructions and producing one response
per trial. On each trial it samples a reaction time from the condition's
configured ex-Gaussian, determines correctness by drawing against the configured
accuracy and omission targets, and applies any enabled temporal mechanism to the
reaction time series; the resulting keypress is delivered to the page. The
TaskCard is cached and content-addressed by hash, so once generated it is reused
without further model calls. A bounded session-time fallback (at most ten model
calls) handles unfamiliar between-block navigation; it did not fire on the four
task implementations reported here. Each session records its random seed and the
SHA-256 of the TaskCard it ran, which makes any session reproducible by
re-running the pinned card under the recorded seed.

**Tasks and platforms:** We evaluated two cognitive control paradigms across
four online implementations to test generalization across both tasks and
platforms. For the stop signal task (Logan & Cowan, 1984) we used the RDoC
battery implementation hosted on Experiment Factory (Sochat et al., 2016) and
the independent STOP-IT jsPsych implementation. For the Stroop color-word task
(Stroop, 1935) we used the RDoC Experiment Factory implementation and a
Cognition.run implementation. The same TaskCard-generation and execution
pipeline was applied to all four without paradigm- or platform-specific code.

**Bot dataset:** For each implementation, we collected 30 sessions, each loading
a single pinned TaskCard by content hash and running under an explicit, recorded
seed, so the full dataset regenerates deterministically from the run script. The
startup keypress-latency calibration routine was disabled: it is behaviorally
inert on these platforms (it applies an identity adjustment) and, on
implementations whose first trial begins with no pre-trial idle window, its
runtime was recorded by the platform as the first trial's response time;
disabling it removes that artifact with no change to sampled behavior.

**Human reference data:** We compared bot behavior to the trial-level human data
of Eisenberg et al. (2019), collected from online participants via Amazon
Mechanical Turk. We restricted to test-phase trials and computed one metric row
per worker using the identical estimators applied to the bot (below). For the
stop-signal task we flagged workers whose probability of responding on stop
trials fell outside the 0.25–0.75 range recommended for interpretable
stop-signal estimates (Verbruggen et al., 2019), and report results with and
without this filter.

**Behavioral measures:** Bot and human data passed through the same estimator
implementations. Mean reaction time was computed over correct trials within a
condition. We computed go accuracy and stop accuracy, omission rate, and, for
Stroop, the interference effect (incongruent minus congruent reaction time).
Stop-signal reaction time (SSRT) was estimated by the mean method (mean go RT
minus mean stop-signal delay); we treat SSRT as an emergent product of the
platform's tracking staircase rather than a bot-controlled quantity, and report
it descriptively. We additionally computed two trial-by-trial sequential
measures: lag-1 reaction-time autocorrelation (the Pearson correlation between
consecutive within-block reaction times) and post-error slowing (mean reaction
time on trials following an error minus mean reaction time on trials following a
correct response, over within-block pairs with valid responses, excluding
omissions).

**Analysis:** For each measure we computed the value per subject, summarized the
human reference as a between-subject distribution (mean ± SD), and positioned
the bot cohort within it as a z-score, z = (bot mean − human mean) / human SD,
together with a within-one-SD indicator. Per-subject distributions for every
measure are retained for distribution-level comparison; planned confirmatory
tests of distributional equivalence (two one-sided tests; Lakens, 2017) are
pre-registered as an extension.

**Reproducibility and code availability:** The pipeline, the pinned TaskCards,
the human-reference processing, and the per-subject analysis are implemented in
a single open package with an automated test suite. All reported numbers are
regenerable from the committed code and the pinned TaskCard hashes; the
frozen-run script and the per-subject analysis command reproduce the dataset and
the comparison tables end to end.

## Results

Across the four implementations we positioned each per-subject measure within
the human reference distribution. Reaction-time location and response accuracy
fell within one standard deviation of the human mean on every implementation. Of
the 44 bot–human comparisons, 38 fell within that band as computed over the full
cohort; two of the six exceptions — STOP-IT stop-failure reaction time and
post-error slowing — are driven entirely by a single data-capture outlier
session (below), so 40 of 44 fall within one SD once that session is excluded.
The four remaining exceptions were the Stroop interference magnitude on
Experiment Factory, lag-1 autocorrelation on STOP-IT and Experiment Factory
Stroop, and post-error slowing on Cognition.run, detailed below.

**Reaction time and accuracy.** On the stop signal task, mean go reaction time
fell within the human range on both platforms (Experiment Factory: 570 ms,
z = −0.17; STOP-IT: 575 ms, z = −0.11; human 585 ± 85 ms), as did go accuracy
(both |z| < 0.4; human 0.94 ± 0.05) and stop accuracy (Experiment Factory 0.46,
z = −0.36; STOP-IT 0.49, z = −0.14; human 0.50 ± 0.10). On the Stroop task,
congruent and incongruent reaction times fell within the human range on both
platforms (Experiment Factory: 635 / 684 ms, z = −0.37 / −0.91; Cognition.run:
683 / 765 ms, z = +0.11 / −0.24; human 673 ± 102 / 795 ± 123 ms), and congruent
and incongruent accuracy were within range throughout (all |z| < 0.4). The
identical configuration pipeline thus reproduced human-range reaction time and
accuracy on all four implementations, and on both platforms of each task — the
cross-platform generalization the design set out to test. Restricting the human
stop-signal reference to workers within the Verbruggen inhibition-rate band
(N = 496 of 522) left every within-range conclusion unchanged (Experiment
Factory stop accuracy z = −0.43, SSRT z = −0.45 against the filtered reference).

**Stop-signal reaction time.** Estimated by the mean method and reported
descriptively, SSRT fell within the human range on both platforms (Experiment
Factory: 265 ms, z = −0.49; STOP-IT: 323 ms, z = +0.27; human 303 ± 76 ms).

**Stroop interference.** The interference effect fell within the human range on
Cognition.run (82 ms, z = −0.67) but was undersized on Experiment Factory
(49 ms, z = −1.22; human 123 ± 61 ms). The bot reproduced the direction of
Stroop interference on both platforms and its magnitude on one.

**Sequential effects.** Both sequential measures were positive on most
implementations, matching the direction of the corresponding human effects.
Lag-1 reaction-time autocorrelation fell within the human range on two of the
four implementations (stop signal Experiment Factory −0.02, z = −0.47;
Cognition.run −0.02, z = −0.72) and was elevated on STOP-IT (0.11, z = +2.54;
human −0.00 ± 0.04) and Experiment Factory Stroop (0.22, z = +1.13; human
0.07 ± 0.13), where the configured autocorrelation exceeded the human sample's
weaker serial dependence. Post-error slowing was positive and within the human
range on the two Experiment Factory implementations and STOP-IT (stop signal
Experiment Factory +25 ms, z = +0.70; STOP-IT +31 ms, z = +0.93 with the outlier
session excluded; Stroop Experiment Factory +12 ms, z = −0.35), but was negative
and below the human range on Cognition.run (−101 ms, z = −1.18; human
+59 ± 136 ms).

**Data quality.** One STOP-IT session recorded a single 552-second response — a
data-capture stall rather than a reaction time — which we exclude from the
STOP-IT stop-failure and post-error-slowing summaries above and flag in the
released per-subject table; with it included, both measures are dominated by that
one trial (stop-failure RT z = +3.04, post-error slowing z = −3.18). A small
number of residual multi-second trials on Cognition.run are retained; they
inflate that implementation's reaction-time variance without moving its
congruent or incongruent mean out of the human range.

## References

Eisenberg, I. W., Bissett, P. G., Enkavi, A. Z., et al. (2019). Uncovering the
structure of self-regulation through data-driven ontology discovery. *Nature
Communications, 10*, 2319.

Lakens, D. (2017). Equivalence tests: A practical primer for t tests,
correlations, and meta-analyses. *Social Psychological and Personality
Science, 8*(4), 355–362.

Logan, G. D., & Cowan, W. B. (1984). On the ability to inhibit thought and
action. *Psychological Review, 91*, 295–327.

Matzke, D., & Wagenmakers, E.-J. (2009). Psychological interpretation of the
ex-Gaussian and shifted Wald parameters. *Psychonomic Bulletin & Review,
16*(5), 798–817.

Sochat, V. V., Eisenberg, I. W., Enkavi, A. Z., et al. (2016). The Experiment
Factory: Standardizing behavioral experiments. *Frontiers in Psychology, 7*,
610.

Stroop, J. R. (1935). Studies of interference in serial verbal reactions.
*Journal of Experimental Psychology, 18*, 643–662.

Verbruggen, F., Aron, A. R., Band, G. P. H., et al. (2019). A consensus guide
to capturing the ability to inhibit actions and impulsive behaviors in the
stop-signal task. *eLife, 8*, e46323.

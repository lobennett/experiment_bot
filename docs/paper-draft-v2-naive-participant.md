# Draft B (Version 2): A Language Model Writes Validated Computational Participants from Task Source Code Alone

_Draft 2026-07-05, for co-author review. Companion:
`paper-draft-v1-expert-pipeline.md`. Pre-registration:
`docs/preregistration-naive.md` (committed before any generation call)._

## Methods

**Claim under test.** Given only a web experiment's source code, and no
behavioral scaffolding of any kind, can a frontier language model author a
generative computational participant whose platform-recorded data matches
human reference data?

**Generation protocol.** For each of four task implementations (stop-signal:
Experiment Factory RDoC and STOP-IT/jsPsych; Stroop: Experiment Factory RDoC
and Cognition.run), a single prompt to Claude Fable 5 contained: the scraped
page source, the mechanical facts a browser harness needs to share (condition
labels, key map, whether a mid-trial interrupt exists), a ten-line protocol
contract (`make_participant(seed)`; `respond(ctx) → (key, rt_ms)`;
`on_interrupt(ctx, ssd_ms, intended)` for interrupt tasks), and the
instruction to write a Python program whose recorded data would be
indistinguishable from a typical healthy adult's, with each seed a distinct
participant. The prompt contains no distribution families, no effect or
phenomenon names, and no numeric behavioral priors — enforced by invariant
tests that scan the template and every injected constant against the
codebase's mechanism registry and a banned-terms list. Programs are
restricted to stdlib+numpy, determinism per seed, and no I/O or clock access.

**No behavioral iteration (pre-registered).** The first program per task to
pass a purely mechanical simulation gate (no crashes over ~1,000 synthetic
trials; same seed → identical output; different seeds → distinct output;
import whitelist) is the program; regeneration was permitted only on gate
failure (max 2 retries, all attempts archived). In the event, all four
programs passed the gate on the first attempt and were used as generated.
Programs are content-hashed and archived with their full generation
transcripts.

**Execution.** Programs run inside the same execution harness as the
comparison arm: identical navigation, stimulus detection, millisecond-
calibrated keypress delivery, platform data capture, and per-session
provenance (program hash + seed). On each trial the harness passes the
program its context (condition, correct key, keys observed so far, trial
index, previous-trial outcome) and delivers whatever (key, RT) the program
returns; on stop trials the program itself decides the stop/go race when the
signal is detected. The harness never imposes distributions, effects, or
race structure.

**What the programs contained (archival description, not selection).**
Unprompted, all four programs implemented: hierarchical individual
differences (every trait — RT parameters, effect magnitudes, error/lapse
rates — drawn per seed from population distributions); latent autocorrelated
attentional states; practice and fatigue dynamics; and deadline-emergent
omissions. Both Stroop programs implemented interference with
congruency-sequence modulation and fast word-capture errors. Both
stop-signal programs implemented an independent horse race (per-trial SSRT
draws racing the go process, with occasional trigger failures) — the
canonical race architecture of Logan & Cowan (1984).

**Dataset and analysis.** N=30 sessions per implementation, explicit seeds,
one pinned program per task. Comparison arm: the expert-parameterized
pipeline (companion draft), re-collected under the identical executor
(N=30 × 4). Human reference: Eisenberg et al. (2019) trial-level data
(N=522 workers), identical estimators for all three cohorts. Confirmatory:
cohort mean within 1 human SD. Pre-registered exploratory: SD ratio,
two-sample KS, and the naive-vs-expert contrast (arms are compared to the
human reference, never gated against each other).

## Results

**Data quality.** Two of 120 naive sessions (both STOP-IT) contained
platform data-capture stalls (excluded and flagged); the same stall class
appears in the expert arm (3/120), independent of the behavioral layer.
There were zero program crashes and zero protocol violations across 120
sessions.

**Confirmatory: 22 of 28 measures within 1 human SD** (expert arm: 23/28).
Accuracy, omission, and stop-accuracy measures were within range everywhere.
Reaction-time location was within range on five of eight RT measures; the
misses are uniformly in the slow direction (e.g., Experiment Factory
stop-signal go RT 675 vs 585±85 ms, z = +1.06; Cognition.run congruent RT
817 vs 673±102, z = +1.42) — a calibration offset, with dispersion and shape
preserved (SD ratios 0.5–0.9).

**Stopping behavior is human-indistinguishable — the headline result.**
Because the programs actually race stopping against going, the platforms'
SSD staircases converged and SSRT emerged correctly on both implementations:
274±46 and 278±40 ms vs the human 303±76 (z = −0.37 and −0.31), with the
two-sample KS test unable to distinguish the bot and human per-subject SSRT
distributions (p ≈ 0.3). The expert arm, whose inhibition is drawn against a
configured probability independent of SSD, fails the same test
catastrophically (SSRT 71/99 ms, z ≈ −3, KS p ≈ 10⁻⁴⁶). Stop-failure RTs
were faster than go RTs in every naive session, as the race model requires.

**Sequential structure lands where the expert arm misses.** Lag-1
autocorrelation was within the human range on three of four implementations
(the expert arm overshoots to z = +4.27 on STOP-IT); on Experiment Factory
Stroop the naive arm was within range on all seven measures, including the
Stroop effect and lag-1 — both chronic expert-arm misses. Post-error slowing
overshoots on the stop tasks (74±37 vs 8±25 ms, z = +2.69 on Experiment
Factory) — the naive arm's largest miss.

**Interpretation.** With no behavioral scaffolding, one generation attempt,
and no iteration, a language model produced computational participants at
parity with a literature-calibrated expert pipeline on coarse measures and
superior on structure: race dynamics, serial dependence, and
between-subject dispersion. The failure profiles are complementary — the
expert arm's misses are architectural, the naive arm's are calibration
constants — which argues for a hybrid in which literature-anchored
parameters are placed inside model-authored generative programs.

## References

Eisenberg et al. (2019); Logan & Cowan (1984); Verbruggen et al. (2019);
Stroop (1935); Matzke & Wagenmakers (2009); Lakens (2017); Sochat et al.
(2016). (Full citations as in `paper-methods-draft.md`.)

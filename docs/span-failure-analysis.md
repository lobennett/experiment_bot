# Why the span tasks fail: the naive approach's principled ceiling

_Analysis of operation_span and simple_span, the two weakest tasks in the
RDoC battery (N=20 stealth round). operation_span scored 2/16 metrics within
1 human SD; simple_span scored 2/12. Every other task scored 5/8 or better._

This document explains where the spans miss, why, and why re-reasoning the
cards did not help. The short version: the spans are where the naive,
no-behavioral-scaffolding approach hits a principled limit, not a fixable
bug.

## Background: what makes the spans different

The spatial spans are serial-reproduction tasks. A sequence of grid cells is
shown, and the participant reproduces it by navigating a cursor with arrow
keys and selecting cells with the spacebar. operation_span additionally
interleaves a processing sub-task: on each step the participant judges
whether an 8x8 grid pattern is symmetric before the next cell appears.

Unlike the choice tasks (Stroop, flanker, go/no-go), where the harness hands
the program the trial's correct key and the program generates a plausible
response around it, the spans require two things the naive approach cannot
supply: a calibrated motor and memory model for reproduction, and a
perceptual judgment for the symmetry sub-task.

## Where the misses are (N=20 vs ~2,510 human sessions)

The misses cluster into three causes.

### 1. Grid-navigation timing runs far too slow (the dominant miss)

| metric | bot | human | z |
|---|---|---|---|
| operation_span `mean_4x4_grid_movement_time` | 1540 ms | 288 ms | +16.8 |
| simple_span `first_4x4_grid_response_time` | 3622 ms | 1258 ms | +7.7 |
| simple_span `mean_4x4_grid_response_time` | 2090 ms | 1000 ms | +5.3 |
| operation_span `first_4x4_grid_movement_time` | 1777 ms | 523 ms | +4.9 |

The program chooses the inter-keypress time gaps that make up a reproduction.
A human moves a cursor cell-to-cell at motor speed, roughly 290 ms. The
generated program writes gaps around 1500 ms. It has no realistic
motor-timing anchor, and the only way to give it one is a numeric behavioral
prior (for example, "grid moves take about 300 ms"). Injecting that is
exactly the behavioral scaffolding the project forbids, and it is enforced
against by the prompt-neutrality invariant tests. This miss is therefore
intrinsic to the naive approach on reproduction tasks.

### 2. Recall is incomplete and inaccurate, worse on larger grids

| metric | bot | human | z |
|---|---|---|---|
| operation_span `4x4_grid_omission_rate` | 0.42 | 0.01 | +6.5 |
| operation_span `8x8_grid_omission_rate` | 0.47 | 0.03 | +3.0 |
| simple_span `mean_number_of_responses` | 3.11 | 3.97 | -5.0 |
| accuracy_irrespective_of_order (op / simple) | 0.44 / 0.71 | 0.85 / 0.95 | -2.9 |
| accuracy_respective_of_order (op / simple) | 0.43 / 0.62 | 0.76 / 0.92 | -2.3 to -1.6 |

The program knows the target sequence length (it is the length of the
exposed target), but its memory and noise model drops responses, omits whole
recall trials, and recalls fewer cells in the wrong order. This is a
weakness of the model's generated memory policy. It cannot be improved
without either a better-written program (already using Claude Opus 4.8) or a
prescribed recall policy, which is hand-holding, and the no-behavioral-
iteration rule forbids re-rolling programs until the recall happens to look
better.

### 3. operation_span's symmetry judgment collapses to a constant response

| metric | bot | human | z |
|---|---|---|---|
| `8x8_grid_symmetric_accuracy` | 1.00 | 0.89 | +1.0 |
| `8x8_grid_asymmetric_accuracy` | 0.00 | 0.93 | -9.0 |

100% correct on symmetric trials and 0% on asymmetric trials is the
signature of a bot that always answers "symmetric." It cannot perceive the
grid pattern, so it defaults to one response. This is the single largest
accuracy miss in the battery, and it is why operation_span (2/16) scores
below simple_span (2/12), which has no processing sub-task.

## Why re-reasoning the card did not fix the symmetry judgment

The symmetry judgment was the one miss that looked structurally fixable. For
choice trials the harness resolves the correct answer from page state via a
`response_key_js` expression the TaskCard supplies, and the program then
generates a response around it. If the symmetry sub-task had the same hookup,
the bot could respond correctly under its own accuracy model instead of
defaulting.

We re-reasoned the operation_span card from scratch to test this. The result
was decisive and negative. Both the old card and the freshly re-reasoned card
resolve the symmetry answer from `window.correctResponse`, a plausible-looking
global that does not hold the per-trial answer. The true answer lives in a
task-internal field (`correct_spatial_judgement_key`, arrowleft for
asymmetric and arrowright for symmetric), which neither card references.
Stage 1 reliably lands on the generic global and cannot discover the internal
field without task-specific knowledge.

Pointing the card at `correct_spatial_judgement_key` by hand would fix the
number, but it would be a paradigm-specific edit to a structural artifact,
which violates the generalizability principle (no paradigm-specific knowledge
in the pipeline) and would defeat the held-out testing design. We did not do
it.

## Conclusion

None of the three span misses is fixable without hand-holding:

- Timing needs a numeric motor prior, which neutrality forbids.
- Recall completeness needs a prescribed policy or a better program, and the
  no-iteration rule blocks selecting programs on behavior.
- The symmetry judgment needs either stimulus perception (the bot has none)
  or a hand-wired answer hookup (a paradigm-specific shim).

The spans mark the boundary of what the naive approach can do. It generalizes
cleanly to choice and inhibition tasks, where the correct answer is exposed
and the program only has to generate plausible response dynamics around it. It
does not extend to serial reproduction, which requires calibrated motor and
memory models, or to embedded perceptual sub-tasks, which require perceiving
the stimulus. This is a clean and honest limit, and it is reported as one
rather than engineered away.

## Note: a gate robustness fix found during this analysis

While regenerating a span program, Claude produced a syntactically invalid
Python file. The mechanical gate crashed on it (`ast.parse` in
`scan_imports` raised unguarded) instead of recording a gate failure. That is
now fixed: an unparseable program raises `ProgramSyntaxError`, which
`run_gate` records as a named failure so the standard retry path engages.
Regression test added (`tests/test_simgate.py`).

# SP2-E3 validation findings — bot-behavior backlog

The SP2-E3 validation dig (commits `4aef5f4` through `c326762`) fixed the
*infrastructure* layer of the validation oracle: PES lag-1 contract,
ex-Gaussian fitter bounds, platform-adapter format-agnosticism, and
schema-validator coverage of `performance.accuracy` /
`task_specific.key_map`. With those fixes in place, the metric formulas
themselves are correct.

Several bot-*behavior* gaps remain that the validator now correctly
surfaces. They are not metric bugs — they are real divergences between
configured behavior and observed behavior. Each is reproducible from
the smoke-batch v2 reports under `validation/smoke_2x4_v2/`.

## Open items

### 1. Sampler-side RT inflation (~80ms above configured)

**Observed**: `expfactory_stop_signal` smoke v2 — bot_log shows go-trial
sampled-mean RT 612ms vs configured ex-Gaussian mean (mu+tau) 530ms.
Playwright clock then adds ~12ms overhead, yielding observed actual
mean ~624ms.

**Suspected cause**: `between_subject_jitter.rt_mean_sd_ms = 80` draws
a per-session shared mu shift from `Normal(0, 80)` at session start.
Two-session average should be ~`Normal(0, 56)` — observed +82ms is
~1.5σ, plausible-but-high.

**Why we can't confirm**: `run_metadata.json` doesn't record
`session_params` (the actual jitter draws or the seed). The sampler
applies a draw but the value is lost.

**Suggested fix**:
- Persist `session_params` (seed + every per-session sampled value) to
  `run_metadata.json`. Lets the user reproduce a run exactly and
  diagnose distributions across N sessions.
- Once recorded, verify whether the inflation is jitter-only (drawn
  shift averaged across many sessions tends to 0) or a deterministic
  bias (autocorrelation amplifying any starting deviation).

### 2. Bot go-trial accuracy underperforms configured target

**Observed**: `expfactory_stop_signal` smoke v2 — bot logs 86/120 = 71.7%
correct go trials. TaskCard configures `performance.accuracy.go = 0.95`.

**Suspected cause**: The executor's `_should_respond_correctly` /
`_should_omit` interaction may not reach the 95% target when the bot's
slow RTs cause more deadline misses, or the random seed produces a
left-tail outlier session.

**Suggested fix**:
- Instrument the executor to log `intended_correct` alongside
  `intended_error` so the gap between target accuracy and realized
  accuracy is auditable per session.
- Sanity-check on synthetic tasks (no DOM, no real RTs) that
  `_should_respond_correctly(condition)` produces the configured rate
  in expectation.

### 3. lag1_pair_modulation labels don't match runtime conditions in
   expfactory_stop_signal

**Observed**: TaskCard's `lag1_pair_modulation.modulation_table` has
entries with `prev: "stop_success"` / `prev: "stop_failure"`. The
executor's runtime trial-condition vocabulary for interrupt trials is
`<detection_condition>_withheld` / `<detection_condition>_responded`
(e.g. `stop_withheld`, `stop_responded`). The mechanism is enabled in
the schema and validator, but the labels never match → 0 modulation at
runtime.

**Suggested fix**:
- Document the runtime condition-suffix conventions in
  `prompts/system.md` so the Reasoner emits compatible labels.
- Or: extend Stage 2 validator to cross-check
  `lag1_pair_modulation.modulation_table[].prev/curr` against the
  union of `response_distributions.keys()` plus the documented
  interrupt suffixes.

### 4. `decay_weights` documented but not implemented

**Observed**: `apply_post_event_slowing` docstring (in
`effects/handlers.py`) describes a `decay_weights` per-trigger field
for multi-trial decay. The handler doesn't actually use it — only
`state.prev_error` (a single bool) feeds the trigger check.

**Suggested fix** (one of):
- Implement decay_weights: handler reads `state.recent_*` and weights
  per-position contributions (requires the executor to populate a
  multi-trial state field).
- Or: remove the doc claim and the schema's `decay_weights` field. If
  the literature for the dev paradigms doesn't require multi-trial
  decay, single-trial PES is sufficient and the doc claim is
  aspirational.

### 5. `run_metadata.json` is sparse

**Observed**: only records `task_name`, `task_url`, `total_trials`,
`headless`. Missing fields useful for debugging session-to-session
behavior:
- Session seed (for reproducibility)
- Sampled `session_params` (per-session jitter draws,
  per-condition mu/sigma/tau after jitter)
- TaskCard hash used for the run (so we know which TaskCard produced
  which session even after regeneration)

**Suggested fix**: extend the executor's
`OutputWriter.save_run_metadata` to capture these. Backwards
compatible — analysis code can ignore unknown fields.

### 6. `cognitionrun_stroop` produces ~15 trials per session

**Observed**: smoke-v2 cognitionrun_stroop sessions log 15 trials each.
Other paradigms produce 100-300 trials per session.

**Suspected cause**: Either the cognition.run task is short by design
(only 1 short block) or the bot exits prematurely. Worth confirming
which.

**Suggested fix**: instrument the executor to log a clear "task
complete reason" (URL signaled completion / max trials reached / phase
detection said complete / timeout). Without this, sparse-data
diagnoses are hand-wavy.

## What's NOT in this backlog

These were investigated and ruled out:
- SSRT formula (mathematically correct given inputs).
- PES lag-1 contrast (fixed in `5a9df96`).
- ex-Gaussian fitter (fixed in `c326762`).
- Platform-adapter format mismatch (fixed in `4aef5f4`).
- Stroop bot RT distribution near-symmetric (skew ≈ 0): a
  consequence of mixing congruent + incongruent trials in the fit;
  per-condition skews are properly right-tailed. Either fit per
  condition or accept that mixed-condition fits will have lower skew.

## Status

Validation oracle infrastructure is sound. These items are bot-side
behavior or instrumentation gaps to address in a follow-up sub-project
(SP3 or similar). They do not block further use of the validator nor
the four dev-paradigm TaskCards in their current state.

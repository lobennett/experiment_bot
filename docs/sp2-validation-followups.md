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

### 1. Sampler-side RT inflation — **RESOLVED, FALSE ALARM**

**Original observation**: `expfactory_stop_signal` smoke v2 — bot_log
showed go-trial sampled-mean 612ms vs configured (mu+tau) 530ms.

**Resolution** (SP2.5-B): the sampler is correct. Reproducing in
isolation, 50 seeds × 200 trials averages to 525ms (delta 5ms within
noise). Single-session deviations are expected per-session jitter:
`between_subject_sd[mu]=50, tau=30` yields combined per-session SD ≈
58ms, so single sessions can plausibly land 80ms+ from population
mean. Comparing one session against the *population* mean rather than
that session's own jittered draw is what made it look like inflation.

The `between_subject_jitter.rt_mean_sd_ms` field in TaskCards is
separately dead code — `jitter_distributions()` is defined in
`distributions.py` but never called. Per-session draws use
`response_distributions[*].between_subject_sd` via
`sample_session_params()` in `taskcard/sampling.py`. That field could
be removed, or `jitter_distributions` could be wired in if a
*shared-shift* layer is desired on top of the per-condition draws.

**SP2.5-A unblocks future analysis**: `run_metadata.json` now records
`session_seed` and `session_params`, so subsequent dig-ins can compare
observed-session RT against the *session's own* sampled mu+tau, not
the population mean.

### 2. Bot go-trial accuracy underperforms — runtime-layer issue, NOT decision logic

**Observed (smoke v2)**: `expfactory_stop_signal` — platform records
93/120 = 77.5% correct go trials. TaskCard configures
`performance.accuracy.go = 0.95`.

**SP2.5-C drill-in resolves the cause**:
- Bot logs 107 go trials with only 3 `intended_error=True` (97.2%
  intended-correct, matches the 95% config).
- Platform records 120 go trials. 13 of them are absent from the bot
  log entirely — the bot never detected the stimulus.
- Of the 27 platform-side incorrect go trials: 2 wrong-key responses,
  25 omissions. The bot intended only 0–3 of those.

**Root cause**: runtime-layer mismatch between bot polling/keypress
and platform trial cycle. The bot's RNG-based decision logic
(`_should_respond_correctly` / `_should_omit`) is fine. The gap is
either:
- Stimulus-detection polling too slow → trials cycle past the bot
  unobserved → platform records as omission.
- Keypress arrives after the platform's per-trial response window →
  registered as no-response.

**Suggested investigation**:
- Add per-trial latency stats to `bot_log` (poll-to-detection time,
  detection-to-keypress time).
- Compare detection-poll interval vs typical jsPsych trial cycle on
  expfactory_stop_signal.
- Consider a `lookahead` mechanism: detect ALL upcoming stimuli rather
  than only react to one at a time.

This is bot-runtime engineering, separate from the bot's
behavioral-fidelity layer. Reasonable as standalone work; doesn't
block validation of the four current dev paradigms.

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

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

### 2. Bot go-trial accuracy underperforms — **RESOLVED in commit `<navigator-fix>`**

**Original observation (smoke v2)**: `expfactory_stop_signal` —
platform recorded 93/120 = 77.5% correct go trials, vs configured 95%.

**Root cause**: `InstructionNavigator._do_click` had a 10-second
timeout AND swallowed `PlaywrightError` with a warning instead of
re-raising. The `instruction_pages` repeat phase therefore kept
iterating after the Next button disappeared — 17 click timeouts ×
10 seconds = ~170 seconds wasted at the start of each session, during
which the platform was already running test trials the bot never
saw. The bot would catch up at trial ~35 of 180, miss everything
before that, and validation reported the missed trials as
omission/incorrect.

**Fix**: reduced `_do_click` timeout to 1500ms and made it re-raise
on timeout so the surrounding repeat loop breaks. Verified end-to-end
in smoke v3:
- expfactory_stop_signal: go acc 94.2%/96.7% (target 95%) ✓
- expfactory_stroop: 95.0%/95.8% ✓
- stopit_stop_signal: 95.3%/93.8% (target 97%) ✓
- stop-inhibit rates: 46.7%/48.4%/50.0% (target 50%) ✓

The bot's behavioral logic was correct all along; a navigator
hygiene bug was masquerading as a behavioral-fidelity gap.

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

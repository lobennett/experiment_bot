# Scope of Validity

**Version:** v1 (2026-05-06)
**Maintenance rule:** any change to a claim, metric, threshold, or held-out
paradigm must be reflected in this doc as part of the same commit.

This document states what the experiment-bot framework claims, how those
claims are tested, and what the framework is not designed to do. It is the
authoritative description of the framework's intended use; anything not in
this document is not a claim the framework makes.

---

## 1. What the framework is

`experiment-bot` is a system that:

1. Reads the source code of a web-based behavioral task and a body of
   primary literature on the relevant paradigm class (the **Reasoner**).
2. Produces a **TaskCard** — a versioned JSON artifact containing
   stimulus identification rules, navigation steps, and behavioral
   parameters (RT distribution shape, sequential-effect magnitudes,
   between-subject variability), each with citations and rationale.
3. Executes the task in a real browser via Playwright (the **Executor**),
   producing trial-level logs.
4. Scores those logs against canonical published norms drawn from
   meta-analyses and review articles (the **Oracle**), reporting
   per-metric pass/fail and a per-pillar summary.

The intended use is to verify, before deploying a task to human
participants, that the platform-rendered version of the task produces
behavior consistent with what the published literature reports for that
paradigm class.

## 2. Claims the framework makes

For a paradigm class with sufficient meta-analytic literature, the bot's
session output should:

- **C1.** Produce trial-level RT samples whose distributional summary
  parameters fall within the meta-analytic range published for the class
  (e.g. ex-Gaussian mu/sigma/tau within ranges from review articles).
- **C2.** Produce trial-to-trial sequential dependencies (post-error
  slowing, condition repetition, lag-1 autocorrelation, congruency-sequence
  effect when applicable) whose magnitudes fall within published ranges.
- **C3.** Produce between-subject variability across N independent sessions
  whose population SDs fall within published ranges, when those ranges
  exist.
- **C4.** Produce paradigm-specific signature metrics (e.g. SSRT for
  interrupt paradigms, n-back accuracy for working-memory paradigms,
  CSE magnitude for conflict paradigms) within published ranges.

The decision rule for each metric is *point-estimate-within-range*: a
metric whose published range exists and whose bot value falls inside it
**passes**; whose bot value falls outside **fails**; whose published
range is null (because no meta-analysis reports it) is **descriptive-only**
and does not gate.

Overall pass requires ALL gating metrics to pass and at least one
metric to be a gate (not all-descriptive).

## 3. Claims the framework does NOT make

The framework does not claim to model:

- **Semantic content** of stimuli. It does not understand what
  "RED" means versus "BLUE"; it identifies condition labels and
  emits responses, not interpretations.
- **Strategic individual differences.** Each session draws from one
  shared set of distributions plus between-subject jitter; it does not
  model speed-accuracy tradeoff strategies, attention deployment
  preferences, or motivational state.
- **Fatigue from non-task sources** (e.g. time-of-day, sleep, prior
  task exposure). The fatigue_drift handler models within-session
  monotone drift only.
- **Learning curves beyond practice.** The bot does not improve across
  trials within a session; it represents post-practice asymptotic
  performance.
- **Distributional similarity beyond point-estimate-within-range.** A
  bot session whose ex-Gaussian fit gives mu within range is judged
  to pass on mu, regardless of whether the full RT distribution is
  shape-similar to a hypothetical human distribution. KS-test or
  Wasserstein-distance comparisons against human distributions are
  not part of the validation protocol in this version.
- **Eye movements, gaze, mouse trajectories, or any non-keyboard
  output.** The bot operates via keyboard responses only.
- **Attention checks as adversarial probes.** The bot detects and
  responds to attention checks as configured per paradigm; it does
  not attempt to evade them or model the participant's experience of
  them.
- **Cross-paradigm transfer.** The bot's behavior on paradigm A is
  not informed by simulated experience on paradigm B; each session is
  generated from the active TaskCard alone.

## 4. Anti-circularity protocol

The framework uses two evidence tiers, kept structurally separate:

- **Bot-side (Reasoner) evidence:** primary studies and direct empirical
  reports on the paradigm. The Reasoner cites these to set parameter
  values. Stored in `taskcards/<label>/<hash>.json` under each
  parameter's `citations` array.
- **Oracle-side (norms) evidence:** meta-analyses, consensus review
  articles, and method-papers that aggregate primary studies. The
  norms-extractor cites these to define gating ranges. Stored in
  `norms/<paradigm_class>.json`.

The norms-extractor prompt forbids citing primary studies (as opposed to
meta-analyses) as the basis for a gating range. Where no meta-analysis
exists for a metric, the norms file marks the metric's range as null
with a textual `no_canonical_range_reason`; the metric becomes
descriptive-only rather than being filled in from primary studies. This
is enforced in `src/experiment_bot/reasoner/prompts/norms_extractor.md`.

**Temporal protocol.** The norms file for a paradigm class is committed
to the repository before any session-output directory for that paradigm.
This is verifiable from `git log`:
- `norms/<class>.json` commit timestamp must precede
- the earliest `output/<label>/<session_dir>/` directory containing
  bot output for any task whose `paradigm_classes` includes `<class>`.

The norms file for a class is not edited based on bot run results. Any
change to a norms file requires a new extraction run with new citations,
documented in commit history. This is a process discipline, not a
framework enforcement; reviewers should verify by inspecting commit
history.

## 5. Pre-registered metrics and thresholds

Per paradigm class, the gating-metric set is defined by the norms file
in `norms/<class>.json`. The metric registry is declarative
(`src/experiment_bot/validation/oracle.py::METRIC_REGISTRY`) and
data-driven from the norms file: adding a metric to a class is one entry
in the registry plus a norms-file declaration; the oracle iterates
whatever the norms file declares.

For the paradigm classes currently extracted:

- **conflict** (`norms/conflict.json`): rt_distribution (mu/sigma/tau),
  post_error_slowing, cse_magnitude. Between-subject SD and
  lag1_autocorr are descriptive-only (no meta-analytic ranges).
- **interrupt** (`norms/interrupt.json`): rt_distribution (mu/sigma/tau),
  post_error_slowing, ssrt. Between-subject SD and lag1_autocorr are
  descriptive-only.
- **working_memory** (`norms/working_memory.json`): n_back_accuracy_2back,
  capacity_k. RT shape, between-subject SD, sequential effects, and
  paradigm-signature metrics (set-size slope, d′, proactive interference)
  are descriptive-only — meta-analytic literature for working-memory
  RT/effects is dominated by primary studies, no consensus review aggregates.

The decision rule is stated in §2: point-estimate-within-range, non-null
ranges gate, null ranges are descriptive. This is a coarse gate. Stronger
distributional tests (KS, Wasserstein, two-sample Anderson-Darling)
against human session distributions are not part of v1.

## 6. Generalization protocol

The framework is iterated against four **development paradigms**:

- expfactory_stop_signal (interrupt)
- expfactory_stroop (conflict)
- stopit_stop_signal (interrupt)
- cognitionrun_stroop (conflict)

It is tested against **held-out paradigms** the development loop never
touches. The first held-out paradigm is:

- expfactory_n_back at https://deploy.expfactory.org/preview/5/
  (working_memory)

The held-out test is documented in `docs/heldout-nback-test.md`.
Result: 5 of 6 generalization checks passed (paradigm-class taxonomy,
norms extraction, validator-retry, stimulus selector emission, runtime
infrastructure). One failed: navigation-phase identification — the
Reasoner emitted no navigation phases for the n-back URL, the bot
could not click past a fullscreen-prompt screen, and 0 trials were
captured. The hard-fail-on-zero-trials guard
(`src/experiment_bot/core/executor.py`) raised loudly rather than
producing silent empty output.

The generalization claim is therefore qualified: the framework's
**scientific machinery** generalizes to novel paradigm classes; the
**Reasoner's static-source-only navigation identification** does not
yet reliably generalize to all entry-screen patterns. This is a known
limitation (§7).

Adding additional held-out paradigms is recommended future work. Each
should be a paradigm class with:
- A web-deployable implementation
- A meta-analysis or review article suitable for norms extraction
- No dev-loop iteration on that paradigm's prompts or normalization

Candidates: Flanker (conflict subclass), Simon (conflict subclass with
spatial mapping), Sternberg (working_memory subclass), random-dot motion
(perceptual_decision class), task-switching paradigms.

## 7. Known limitations

These are the architectural boundaries of the v1 framework. Each is a
non-claim; reviewers should weigh them as such.

- **L1. Navigation identification is static-source-only.** The Reasoner
  reads JS source files but does not verify the resulting TaskCard
  against the live page DOM. When the entry flow involves browser-API
  gestures (fullscreen prompts) or buttons whose presence depends on
  runtime state, the Reasoner may emit empty `navigation.phases`. The
  hard-fail-on-zero-trials guard catches the symptom; the fix
  (Reasoner-side pilot validation) is deferred to a later sub-project.

- **L2. Multi-trial decay defaults to 1-trial.** The
  `PostErrorSlowingConfig.decay_weights` field supports multi-trial
  decay profiles when populated, but the four dev paradigms and the
  held-out n-back paradigm did not invoke this. If a literature for a
  paradigm calls for multi-trial PES decay (e.g. Notebaert 2009),
  the Reasoner will need to populate `decay_weights` explicitly.

- **L3. Effect taxonomy is extensible but Python-only.** New effects
  can be registered programmatically via `register_effect()` but cannot
  yet be declared from a TaskCard. Adding a new universal mechanism
  requires both a handler function (Python code) and a registry entry.

- **L4. Distribution dispatch supports ex_gaussian / lognormal /
  shifted_wald, all three selectable and honored end-to-end.** The
  Reasoner picks the family per condition based on what the literature
  reports; `ParameterValue.distribution` carries the choice into
  `_taskcard_to_config` → `DistributionConfig` → `_build_sampler`
  (core/distributions.py). Stage 2 validation checks that the param
  keys match the declared family and fails loudly on mismatch.
  Adding a new family requires a new sampler class plus a dispatch
  entry in `_build_sampler`.

- **L5. Validation is point-estimate-within-range, not distributional
  similarity.** A bot session whose mu falls within the published range
  but whose RT histogram has the wrong shape will pass mu's gate. This
  is intentional (the meta-analytic literature reports point ranges,
  not full distributions), but it is a weaker test than KS/Wasserstein
  against a human reference distribution would be.

- **L6. Pilot integration is shipped and passes for all four dev
  paradigms.** The Reasoner's Stage 6 runs `PilotRunner` against the
  live URL after Stage 5, captures diagnostics (selector match rates,
  condition coverage, DOM snapshots, phase firings), and refines
  structural fields on failure with up to `pilot_max_retries`
  refinements (CLI default 2). Each refinement attempt's structural
  diff is persisted to `taskcards/<label>/pilot_refinement_<N>.diff`
  alongside `pilot.md`. The Stage 6 reasoning step in the TaskCard
  records `attempt_<N>` evidence for each pilot run.

  Empirical result on the four dev paradigms (current TaskCards):
  - expfactory_stop_signal (`7efedfd1.json`): pilot passed first
    attempt — 99 trials, both conditions (go, stop) observed.
  - expfactory_stroop (`6829e941.json`): pilot passed first attempt —
    46 trials, both conditions observed.
  - stopit_stop_signal (`9de8a663.json`): pilot passed first attempt —
    16 trials, all three conditions (go_left, go_right, stop_signal)
    observed (stop_signal first appeared at trial 16).
  - cognitionrun_stroop (`39b7fb4e.json`): pilot passed first attempt —
    8 trials, both conditions observed.

  Two pilot-side gaps surfaced during integration and were closed:
  pilot's `max_blocks` is now advisory rather than a hard stop (it
  was breaking out at first FEEDBACK on paradigms with trial-by-trial
  feedback), and pilot's keypress logic now filters the
  withhold-response sentinels the executor already filtered (it was
  crashing trying to press `"withhold"` literally on stop-signal
  trials).

  The held-out n-back paradigm has not been re-piloted under these
  fixes; the held-out result remains as documented in
  `docs/heldout-nback-test.md` and is the next empirical generalization
  test once additional held-out paradigms are added (§6).

- **L7. The dev paradigm sample is small and not stratified.** The
  four dev paradigms cover two paradigm classes (conflict, interrupt).
  Generalization to other classes is supported by architectural design
  (open paradigm-class taxonomy, data-driven oracle) but verified
  empirically only by the n-back held-out test (working_memory class).

- **L8. (CLOSED.)** The validation oracle now reads platform-native
  data via per-paradigm adapters under
  `src/experiment_bot/validation/platform_adapters.py`. Each adapter
  filters `experiment_data.{csv,json}` to actual test trials and emits
  canonical trial dicts (condition, rt, correct, omission). The CLI
  dispatches by label; `bot_log.json` remains a fallback when no
  adapter is registered. The four dev-paradigm adapters are in place;
  novel paradigms need a corresponding adapter or fall back to bot_log
  with a warning. Long-term, adapter config should move from Python
  code into the TaskCard's `runtime.data_capture` block so the
  Reasoner can declare the field-mapping per task — that's deferred
  follow-up work.

- **L9. (SP11 Phase 3 — calibration variance ceiling.)** Each session
  starts with a calibration pass: the bot fires a known sequence of
  keys via the platform's keyboard channel, reads back the platform's
  recorded responses, and computes a per-platform offset model. At
  trial time the executor adjusts sampled RTs by inverting the model
  so the platform's recorded RT lands near the sampler's target.
  Three model forms (per `src/experiment_bot/calibration/estimator.py`):
  - **fixed_offset** when filtered calibration SD ≤ 30 ms absolute:
    subtract a single mean. Phase 7 reports `(mean, sd)` per session
    in the descriptive table.
  - **regression** when SD > 30 ms: fit a linear `platform_rt =
    slope * bot_intended + intercept` over the calibration trials;
    trial-time adjustment inverts it. This is the SD-ceiling
    fallback for platforms whose recording timing varies enough
    that a single mean leaves a residual that re-inflates the
    recorded distribution's sigma.
  - **escalate** when the offset distribution is bimodal (two
    cluster means separated by >50 ms AND smaller cluster has ≥20%
    of mass AND separation/within-cluster-SD ≥ 3.0). Indicates the
    platform is using two distinct recording paths; a fitted model
    captures neither. Project owner decides remediation per SP11
    spec §11.
  - **too_few_events** when fewer than 5 correctly-recorded events
    survive the filter. Calibration not estimable; same disposition
    as escalate.

  The calibration offset is computed ONLY on correctly-recorded
  events (platform recorded the bot's intended key AND recorded
  something at all). Per SP7 layer-d, the platform records a
  different key on ~56% of trials in some conditions; if those
  events were included, the offset estimate would be polluted by
  mis-recording-induced timing.

  Platform RT resolution is the underlying limit on calibration
  precision. jsPsych uses `performance.now()` (sub-ms). Cognition.run
  is jsPsych 7.3.1 under the hood (probed in Phase 3.1), so its
  resolution is the same. Future platforms with coarser RT timers
  will have a higher calibration variance ceiling — document per
  platform when adding driver support.

- **L10. (SP11 Phase 3 — calibration pass implementation channels.)**
  The calibration runner takes a `KeypressDeliverer` abstraction
  rather than calling Playwright APIs directly. Phase 4 will provide
  two concrete deliverers: a primary `CDPDeliverer` using Chrome
  DevTools `Input.dispatchKeyEvent`, and a fallback
  `PlaywrightKeyboardDeliverer` using `page.keyboard.press`. The
  per-session bot_log records `delivery.channel` per keypress so the
  audit script and Phase 8 writeup can break down fidelity by
  channel. Non-Chromium browsers (Firefox / WebKit) accept the
  fallback's lower fidelity per SP11 scope (Chromium is the
  validation target).

- **L11. (SP11 Phase 4b — four-step per-trial protocol.)** The CDP
  and keyboard deliverers fire each key under a five-step pacing
  protocol validated in the Phase 4a spike (100% fidelity at
  ≥85% gate): (1) detect — read the current trial marker;
  (2) dwell — `default_dwell_ms` (200ms default) so the press lands
  inside the response window, not on trial-start microsecond zero;
  (3) verify — confirm the marker hasn't advanced during dwell, else
  skip; (4) focus + fire (Input.dispatchKeyEvent or
  page.keyboard.press); (5) wait-for-advance — poll the marker until
  it increments. Dwell is paradigm-configurable per fire
  (`dwell_ms=` argument). Paradigms with short response windows
  (e.g., stop-signal stop trials at 250ms) may need a tighter dwell;
  paradigms expecting longer human RTs (stop-signal go ~600ms) may
  set a longer one. The protocol is implemented uniformly across
  CDP and keyboard deliverers — only step 4's fire mechanism
  differs.

- **L12. (SP11 Phase 4b — trial-marker pairing.)** Bot fires pair to
  platform records by trial-marker equality, not sequential index.
  The Phase 4a spike surfaced an off-by-one between detect-time and
  fire-time when index-pairing was used; switching to
  `jsPsych.getProgress().current_trial_global` as the marker (probed
  at detect time and matched against the platform's `trial_index`
  field) eliminated the off-by-one (26%→100% fidelity on the same
  spike runs). The deliverer accepts paradigm-platform-aware
  `trial_marker_js` and `records_js` overrides for non-jsPsych
  platforms; the bot library contains no jsPsych-specific selectors
  beyond defaults, per G1. Audit script consumes the trial marker
  via `bot_log.session.method == 'sp11_input_layer'`; legacy sp10
  driver runs use RT-based pairing via the same audit script
  (`bot_log.session.method == 'sp10_driver'`). See
  `docs/sp11-complete.md` (Phase 6 summary).

- **L13. (SP11 Phase 5a — executor delivery + paradigm-configurable
  dwell.)** The executor's response-press path routes through a
  configured `KeypressDeliverer` (`runtime.delivery_channel`:
  `"cdp"` default, `"keyboard"` fallback, `"none"` legacy). The
  per-paradigm dwell is read from `runtime.timing.cdp_dwell_ms`
  (default 200 ms). The Reasoner pins paradigm-specific dwells in
  the TaskCard when the paradigm's response window demands it
  (stop-signal STOP trials' ~250 ms SSD typically motivates ~100 ms
  dwell so go-trial fires remain inside the response window).
  Per-trial `bot_log` records the `delivery.channel`,
  `trial_marker_at_fire`, and `skipped` / `skip_reason` for the
  Phase 6 audit script. Calibration auto-invocation is NOT enabled
  by default in Phase 5a; the infrastructure is present
  (`TaskExecutor._run_calibration_pass`), and Phase 5b's regenerated
  TaskCards + Phase 7's measurement runs will set the policy.

- **L14. (SP11 Phase 5a — calibration-adjusted RT sampling.)** The
  sampler accepts an installed `CalibrationResult` via
  `set_calibration_result(result)`. Subsequent `sample_rt` and
  `sample_rt_with_fallback` calls apply the model's `.adjust()`
  inversion AFTER temporal effects are applied. For `escalate` or
  `too_few_events` results, the adjustment is a no-op (Phase 7's
  scope-of-validity disclosure reports the un-calibrated z-score).
  The adjustment is re-floored at `runtime.timing.rt_floor_ms`
  (default 150 ms) so an aggressive offset cannot push the bot's
  fire time below physiological-floor cutoffs.

- **L15. (SP11 Phase 5b — drop-from-scope policy.)** Paradigms that
  fail the pilot-time alignment check after 3 total attempts (1
  initial + 2 retries) during Phase 5b regeneration are marked
  `task_specific.sp11_supported = False` in the TaskCard and listed
  in `docs/sp11-unsupported.md`. The CLI guard at
  `experiment_bot.cli._run_task` refuses to launch sessions for
  unsupported paradigms; the Phase 7 measurement sweep skips them.
  These paradigms drop out of the SP11 cross-deployment claim — the
  abstract's per-paradigm count tracks `task_specific.sp11_supported
  == True` only. Failure mode is loud and structural, not silent:
  the CLI exits non-zero with a pointer to this scope-of-validity
  entry. The 3-attempt retry budget is a single configuration
  (`max_retries=2`) tuned to absorb transient browser-state flakes
  while still catching real DOM-shape or platform-API breakages
  early. Re-enabling a dropped paradigm requires (a) editing the
  TaskCard manually to remove the flag, or (b) re-running Phase 5b
  regeneration end-to-end against a new source revision; ad-hoc
  unsticking is forbidden.

- **L16. (SP11 Phase 7 — pre-cal vs post-cal experimental arms.)**
  Phase 7 runs each paradigm twice with a single experimental
  manipulation: the second arm enables calibration application to
  the sampler (`runtime.calibration_apply_to_sampler = True`); the
  first arm leaves it disabled (`= False`). Both arms still run the
  calibration pass and record the offset descriptively, so the
  pre-cal arm yields a comparable offset measurement without
  applying it to sampled RTs. This single manipulation isolates the
  calibration adjustment's effect — without changing distribution
  parameters, effect magnitudes, sampler logic, or any other
  variable. The CLI flag `--no-calibration` toggles the pre-cal arm
  for the same TaskCard. Phase 8's writeup compares the two arms on
  the §6 hard gates (H1/H2 fidelity) and §6.2 absolute-RT z-scores;
  a Calibration × Paradigm interaction is the metric of interest.
  Phase 5b/5c characterized pipeline-output variance via a Stroop
  variance study (3 additional regens), establishing 15–37% intrinsic
  pipeline variance on ex-Gaussian parameters; see `docs/sp11-complete.md`
  (Phase 5b/5c summary) for the empirical anchor reading SP8 → SP11
  parameter changes as variance vs. systematic drift.

- **L17. (SP11 Phase 5c — §6.2 targets reinterpreted as |z| against
  human reference, not deltas from sp9c.)** Re-reading the spec
  reveals that §6.2's targets are absolute |z|-score values
  measured against the human reference distribution
  (`data/human/archive_rdoc/` for the Stroop/stop-signal arms;
  literature-typical bands for cognition.run and stopit). The
  sp9c-baseline column in §6.2 is descriptive context — it shows
  where the pre-SP11 pipeline landed — not a delta the SP11
  measurement must subtract from. This matters because Phase 5b's
  TaskCard regeneration produced parameter shifts > 10% relative
  to SP8 on five Stroop fields (mu, sigma, tau across congruent /
  incongruent); if §6.2 had been a delta-from-sp9c spec, those
  shifts would have moved the goalposts and made the pre-/post-cal
  comparison incoherent. As an absolute-|z| spec, §6.2 is intact:
  the pre-cal arm of Phase 7 establishes the new TaskCards'
  per-condition |z| starting point, and the post-cal arm measures
  calibration's *within-Phase-7* effect on that |z|. The §6.2
  "improve by ≥ 1.0" wording becomes a within-Phase-7 contrast
  (post-cal |z| ≤ pre-cal |z| − 1.0), not a contrast against the
  sp9c historical record. This reinterpretation:
  - Does NOT loosen the gate. The absolute-|z| target was always
    the operational measurement; only the descriptive framing
    shifted.
  - Is committed BEFORE Phase 7 data exists, preserving
    pre-registration discipline. The reframing is a clarification
    of what was always the meaningful comparison, not a retarget.
  - Pre-loads Phase 8's writeup with the right framing: report
    pre-cal |z| as the starting point, post-cal |z| as the
    calibrated state, the |z| reduction as the calibration effect.
    Sp9c numbers stay in the table as historical context, not as
    a contrast.

- **L18. (SP11 Phase 6 — audit-script generalization.)**
  `scripts/audit_alignment.py` now takes a `--label` argument that
  dispatches a per-paradigm test-row predicate from
  `experiment_bot.validation.platform_adapters.TEST_ROW_PREDICATES`.
  Pairing method is auto-selected from per-trial
  `delivery.trial_marker_at_fire` presence: present →
  `trial_counter` (SP11 input-layer); absent → `rt_match` (SP10
  driver legacy). An explicit `--pairing` flag overrides for
  forensic re-pairing. Channel breakdown (`cdp_dispatchKeyEvent`
  vs `keyboard_press_fallback` vs `page_keyboard_press`) appears
  in the audit output for the Phase 8 §7 channel-fidelity table.
  Loud failure on unregistered labels (raises with a pointer to
  `TEST_ROW_PREDICATES`) preserves the no-silent-fall-through
  discipline. Empirical anchor: the Phase 5a pilot session
  (122 CDP fires) audits at **100% pressed_eq_recorded on 118 paired
  trials** under trial-counter pairing — same data that gave 0%
  pairing under the SP10-era index-based audit, so the
  generalization captures the SP11 input-layer fidelity claim
  cleanly.

## 8. Operational rules

These rules govern day-to-day work on the framework. They are process,
not enforcement.

- **R1.** Norms files for a paradigm class are committed before any
  session-output directory referencing that class. Verifiable in
  `git log`.
- **R2.** Norms files are not edited based on session results.
  Refinements require a new extraction run with new citations and
  updated DOI verification timestamps.
- **R3.** Validation thresholds (the published ranges in norms files)
  do not change based on whether the bot passes or fails. If a range
  appears wrong on inspection, the path forward is a new norms
  extraction or an explicit, documented disagreement with the
  meta-analytic source — not a quiet edit.
- **R4.** Held-out paradigms are not iterated against. If a held-out
  paradigm fails, the failure is documented (per
  `docs/heldout-nback-test.md`); the path forward is either a
  framework-level fix (architectural change with no paradigm-specific
  prompts or selectors) or formal acknowledgment of the limitation in
  this document. Iteration on the held-out paradigm's prompts or
  TaskCard converts it into a dev paradigm; this conversion must be
  documented.
- **R5.** Effect handlers may not encode paradigm-specific magnitudes
  (e.g. "PES is 30 ms"). Magnitudes come from TaskCard parameters,
  which come from Reasoner inference, which cites primary studies.
  Handlers encode mechanisms, not values.
- **R6.** The Stage 1 system prompt may not contain numerical priors
  drawn from cognitive-control literature (e.g. "0.85 is typical for
  stop-signal tasks"). Such priors are removed where found; the
  prompt describes derivation rules ("consult source code for the
  task's response window; derive cap from primary-source literature")
  rather than asserting values.

## 9. Verifiability

A reviewer can audit the framework's claims by:

1. Reading `norms/<class>.json` files. Each metric carries citations
   with DOIs; DOIs are verified against OpenAlex during Stage 4 of
   the Reasoner (see `src/experiment_bot/reasoner/stage4_doi_verify.py`)
   and timestamped in the file.
2. Reading `taskcards/<label>/<hash>.json` files. Each parameter carries
   citations + literature_range + between_subject_sd, plus a
   `reasoning_chain` of the Reasoner stages with confidence ratings.
3. Reading the source code of the four dev paradigms and the
   held-out paradigm at the URLs documented in `scripts/batch_run.sh`
   and §6 above.
4. Running `experiment-bot-validate --paradigm-class <class>
   --label <label>` against a session-output directory and inspecting
   the per-pillar / per-metric pass/fail report against the norms file
   the oracle used.
5. Checking commit history for compliance with §4 (temporal protocol)
   and §8 (operational rules).

The framework is built so this audit produces a verdict, not a debate.
If a metric is in the gating set, its source is a meta-analysis; its
DOI is verified; the bot's value is mechanically computed; the gate is
arithmetic. The defensibility comes from the paper trail, not from
trust in the implementation.

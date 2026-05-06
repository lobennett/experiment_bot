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

- **L4. Distribution dispatch is fixed to ex_gaussian / lognormal /
  shifted_wald.** Adding a new distribution family requires a new
  sampler class plus a dispatch entry. Most published speeded-decision
  literature uses ex-Gaussian or shifted-Wald, but the dispatch is not
  open-ended.

- **L5. Validation is point-estimate-within-range, not distributional
  similarity.** A bot session whose mu falls within the published range
  but whose RT histogram has the wrong shape will pass mu's gate. This
  is intentional (the meta-analytic literature reports point ranges,
  not full distributions), but it is a weaker test than KS/Wasserstein
  against a human reference distribution would be.

- **L6. The bot does not run a pre-flight pilot.** The
  `PilotDiagnostics` system in `src/experiment_bot/core/pilot.py`
  exists but is not wired into the Reasoner or the Executor's
  pre-deployment path. Each session runs the full task immediately,
  with the hard-fail-on-zero-trials guard catching the worst silent
  failures but not earlier.

- **L7. The dev paradigm sample is small and not stratified.** The
  four dev paradigms cover two paradigm classes (conflict, interrupt).
  Generalization to other classes is supported by architectural design
  (open paradigm-class taxonomy, data-driven oracle) but verified
  empirically only by the n-back held-out test (working_memory class).

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

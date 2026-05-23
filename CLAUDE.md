# CLAUDE.md — Project Goals and Guardrails

This document is the standing guidance for any Claude session working on
`experiment-bot`. Read this before making non-trivial changes.

## What this project is

A general-purpose Task Turing Bot that completes web-based cognitive
experiments with human-like behavior. Three layers:

1. **Reasoner** — reads source code + literature, emits a versioned
   `TaskCard` (JSON) with stimulus/response rules, navigation, behavioral
   parameters, and citations.
2. **Executor** — drives the live URL via Playwright using the TaskCard,
   sampling RTs and producing platform-native data + a bot log.
3. **Oracle** — scores the resulting sessions against canonical
   meta-analytic norms.

The user's role is cognitive-control researcher, with a current dataset
share-out goal for four development paradigms (two Stroop, two
stop-signal).

## Core Goals (in priority order)

### G1. Generalizability beyond the dev paradigms

The bot's code must NOT bake in paradigm-specific knowledge.
"Generalizable" means: pointing the bot at a novel paradigm's URL
(e.g., n-back, Flanker, random-dot motion, Wisconsin Card Sorting)
should work *without code changes* to the bot's library.

The four development paradigms are a testbed for iteration, not the
universe. Held-out paradigms (n-back so far) verify generalization
empirically. Reviewers must be able to see that the framework is not
overfit to the four dev paradigms.

### G2. The Reasoner does the thinking; the bot does the mechanics

The bot's library is a small set of *generic mechanisms*
(autocorrelation, linear drift, lag-1 pair modulation, post-event
slowing, etc.). The Reasoner translates the literature for each task
into mechanism *configurations* in the TaskCard. The bot's code does
not name CSE, post-error slowing, post-inhibition slowing, or any
paradigm-specific phenomenon.

The user wants Claude to infer effects, magnitudes, and temporal
patterns from the literature scrape — not pre-load knowledge into the
bot's vocabulary. "Even if Claude said this paradigm has CSE, the bot
shouldn't have CSE in its vocabulary; it should configure a generic
2-back mechanism."

### G3. No effects on tasks that don't have them

Temporal effects, cues, and other modulations must NOT appear for
tasks where the literature doesn't document them. The Reasoner enables
mechanisms only when supported by the literature for the *specific*
paradigm class. A mechanism left disabled in the TaskCard contributes
nothing at runtime.

### G4. Scientific defensibility — reviewer-facing

The framework must withstand reviewer scrutiny on:

- **Anti-circularity**: the bot's parameter-setting Reasoner cites
  primary studies; the validation oracle gates on meta-analytic norms.
  These are different evidence tiers.
- **Pre-registration**: norms files committed *before* sessions
  reference them. Validation thresholds don't move based on results.
- **Verifiability**: every TaskCard parameter has a citation +
  rationale + reasoning chain. Pilot validation against live DOM is
  recorded in `pilot.md` alongside the TaskCard.
- **Authoritative data sources**: the oracle reads the platform's own
  data export (`experiment_data.{csv,json}`), not the bot's polling
  log (`bot_log.json`). Adapters per paradigm in
  `validation/platform_adapters.py`.
- **Hard-fail on broken state**: zero-trial sessions raise a clear
  error. Pilot failures are logged.

### G5. Iteration discipline

- Don't add features beyond what the immediate task requires.
- Don't introduce abstractions for hypothetical future requirements.
- Don't remove paradigm-named code by adding paradigm-named
  alternatives. Generic mechanisms only.
- When making a change, audit for backward implications across all
  stages of the pipeline (Reasoner Stages 1–6, Executor, Oracle,
  TaskCard schema, norms files, prompts, tests). Fix all of them in
  the same pass; don't leave half-migrated state.

## Specific guardrails for code changes

### When adding to the effect library

A new mechanism is justified only if at least two paradigms with
distinct paradigm-class memberships would use it. If only one paradigm
needs it, it's a configuration of an existing mechanism.

Mechanisms must:
- Be named in mechanism vocabulary (`lag1_pair_modulation`,
  `post_event_slowing`, `linear_drift`), not paradigm vocabulary
  (`congruency_sequence`, `post_error_slowing`).
- Be applicable in principle to any speeded-decision task.
- Read all paradigm-specific data (condition labels, magnitudes,
  thresholds) from the cfg argument — never hardcode.
- Have a default that contributes zero when the cfg is empty/disabled.

### When editing prompts

Stage 1 / Stage 2 / Stage 3 / Stage 5 / norms-extractor prompts must
not name paradigm-specific values. If a number or label appears in
the prompt, it must be either:
- A bot-mechanic value (e.g., `[" "]` for jsPsych's space-advance),
  or
- A clearly bracketed placeholder (`<low>`, `<sd_value>`).

Numerical priors from cognitive-control literature ("0.85 is typical
for stop-signal tasks") are forbidden in prompts. The Reasoner
derives values from the literature scrape, not from prompt anchors.

### When editing the validation oracle

The oracle's `METRIC_REGISTRY` is data-driven from the norms file. New
metrics are registered in the dispatch with a compute function. The
metric NAME in the norms file may use paradigm-conventional language
(e.g., `cse_magnitude` for conflict tasks) — that's a metric *name*,
not bot-library vocabulary. The compute function is a thin wrapper
around the generic `lag1_pair_contrast` (or similar generic).

### When updating tests

Negative assertions are valuable: tests that explicitly check
paradigm-named items are *absent* from the bot's library help prevent
regression. Example:
```python
assert "congruency_sequence" not in EFFECT_REGISTRY
assert "post_error_slowing" not in EFFECT_REGISTRY
```

## Sub-project history

- **SP1**: Replace v1 cache config with versioned TaskCard format
  produced by 5-stage Reasoner. ✓ Complete.
- **SP1.5**: Stage 1 validator gate + reasoning-chain accumulation.
  ✓ Complete.
- **SP2**: Behavioral fidelity — effect-type registry, generic-
  mechanism refactor, norms extractor, validation oracle (incl. SSRT),
  Stage 2 jsonschema gate with self-correcting refinement, Stage 6
  pilot-refinement persistence, executor lag-1 PES contract, and
  format-agnostic platform adapters. ✓ Complete; bot-behavior gaps
  surfaced in SP2-E3 (sampler RT inflation, accuracy underperformance,
  decay_weights aspirational, sparse run_metadata) tracked in
  `docs/sp2-validation-followups.md` for SP3 work.
- **SP2.5**: Post-SP2 hardening — navigator click-timeout fast-fail
  (took bot go-trial accuracy from 77.5% to 95% on dev paradigms),
  run-metadata instrumentation (session_seed, session_params,
  taskcard_sha256). Tag `sp2.5-complete` at `577f685`. ✓ Complete.
- **SP3**: Held-out generalization test (Flanker + n-back). Both
  held-out paradigms failed at Stage 2 schema validation; no TaskCards
  produced, no sessions run. Generalizability claim (G1) empirically
  falsified for both paradigms tested. Failure modes documented in
  `docs/sp3-heldout-results.md`; SP4 backlog with prioritized
  generalizable improvements in `docs/sp4-stage2-robustness.md`. Tag
  `sp3-complete` on the report-landing commit. ✓ Complete (the
  deliverable is the report and SP4 backlog, not a passing test).
- **SP4a**: Stage 2 robustness Tier 1 — refinement-loop slot
  preservation, schema-derived prompt examples with invariant test,
  performance.* envelope contradiction resolved. Internal CI gate:
  PASS (4 documented failure modes have fixture-based test coverage,
  +24 new tests, suite at 492). External evidence: held-out re-run
  closed all four Tier 1 failure modes in both Flanker and n-back at
  Stage 2; new failure modes surfaced downstream (Stage 3 in Flanker,
  Stage 6 pilot in n-back) per `docs/sp4a-results.md`. Tag
  `sp4a-complete`. ✓ Complete.
- **SP4b**: parse-retry class fix — single shared `parse_with_retry`
  helper applied to Stages 1, 3, 5, 6 (pilot refinement) and the
  norms_extractor; Stage 2 unchanged. Internal CI: 501 passed (was
  492); +9 tests covering helper, per-stage integration, and Stage 1
  parse/validation-retry independence. External: Flanker held-out
  re-run produces a TaskCard for the first time under any framework
  version (parse_with_retry did not fire — SP4a's Stage 3 failure was
  likely transient LLM noise). Tag `sp4b-complete`. ✓ Complete.
- **SP4** (continuing backlog): residual gaps in
  `docs/sp4b-results.md`. Tier 2/3 items at
  `docs/sp4-stage2-robustness.md` (canonicalization layer, two-pass
  Stage 2 split, schema-as-canonical autogeneration) and the
  `_extract_json` ownership cleanup. Each its own brainstorm/spec/
  plan cycle when prioritized.
- **SP5**: Held-out behavioral measurement — completed the SP3-original
  deliverable. 5 sessions × Flanker + 5 sessions × n-back, with
  paradigm adapters (`read_expfactory_flanker`, `read_expfactory_n_back`
  with N/A warmup-trial filter), validated against `norms/conflict.json`
  and `norms/working_memory.json`. **Flanker rt_distribution falls
  fully within published conflict-class meta-analytic ranges** on a
  paradigm never tuned against — strongest empirical generalization
  evidence yet. n-back metrics literature-typical. One real fidelity
  gap: Flanker post_error_slowing -7.23ms (facilitation) vs expected
  +10-50ms (n-back's PES correct at +16.30ms in same framework, so
  paradigm-specific). Tag `sp5-complete`. ✓ Complete.
- **SP6**: Executor trial-end fallback. SP5's "Flanker PES sign-flip"
  finding root-caused to a deeper bug: `runtime.timing.response_window_js`
  was None for Flanker / n-back / stroop, causing the executor's
  polling loop to re-detect the same stimulus and double-fire trial
  handlers (2-3× over-firing). Single-file fix in core/executor.py:
  `_wait_for_trial_end` accepts a `fallback_js` kwarg; new
  `_stimulus_detection_js` helper builds the fallback from the matched
  stimulus's detection config with per-stim.id caching; post-trial
  call site passes the fallback. Internal: 517 passed (was 505); +12
  tests. External: Flanker over-firing 2.05× → 1.02× aggregate; PES
  −7.23ms → +35.43ms (squarely in configured 25-55ms range). Tag
  `sp6-complete`. ✓ Complete.
- **SP7**: Keypress diagnostic (investigation-only). Added
  paradigm-agnostic page-level keydown listener (capture phase) at
  session start, per-trial drain, and two new bot_log fields
  (`resolved_key_pre_error`, `page_received_keys`). Generic
  `scripts/keypress_audit.py` uses `PLATFORM_ADAPTERS` dispatch.
  Internal: 524 passed (was 517); +7 tests. External: 4-way audit
  across 5 Flanker sessions (600 trials) named two compounding
  layers — (a) bot's `response_key_js` extraction ~50% match to
  platform_expected (essentially random in 2-key paradigm); (d)
  page_received vs platform_recorded only 44% (platform reads from a
  non-keydown source). Aggregate accuracy still ~93% by coincidence
  of 2-key choice + valid-key filter. See `docs/sp7-results.md`. Tag
  `sp7-complete`. ✓ Complete.
- **SP8**: Stage 1 multi-source `response_key_js` prompt. Per the
  user's redirection during SP8 brainstorm (the original SP7 Option B
  was rejected as paradigm-overfitting), the scope shifted to a
  Stage 1 prompt edit: append a `## Multi-source response_key_js
  extraction` section to `src/experiment_bot/prompts/system.md`
  instructing Stage 1 to emit a fallback chain (runtime variable
  first, DOM-derived computation second, static keymap third).
  Internal: 530 passed (was 524); +6 invariant tests. External:
  regenerated 4/6 paradigm TaskCards (Flanker failed on Stage 4
  openalex.py list/string crash; cognitionrun_stroop failed on
  Stage 6 pilot exhausted). All 4 successful TaskCards follow
  Pattern B with window.correctResponse check FIRST. Per-trial
  alignment: **n-back 49.8% → 72.1%** (clear win, page exposes
  window.correctResponse); stroop/stop_signal_expfactory/stop-it
  stayed at chance (DOM-derived fallback still unreliable for
  paradigms without window.correctResponse). See
  `docs/sp8-results.md`. Tag `sp8-complete`. ✓ Complete.
- **SP9a**: Session-time runtime LLM for key-mapping resolution. New
  `src/experiment_bot/agent/` package — `SessionAgent.resolve_key_mapping`
  runs once per session after navigation completes, probes the live page
  (DOM + window globals + screenshot), and asks `claude-haiku-4-5` to
  produce a `KeyMappingDirective`. Executor caches the directive's
  mapping into `_runtime_key_mapping`; `_resolve_response_key` checks it
  before the existing static / per-stim JS / global JS fallback chain.
  Per-trial cost: synchronous dict lookup. Internal: 563 passed (was
  530); +33 tests across LLM-Protocol multimodal, agent module,
  RuntimeConfig flag, executor integration, cli.py wiring, plus
  defensive layers (dynamic-sentinel fall-through, English-word key
  normalization). **External: behavioral hypothesis NOT supported.**
  n-back smoke 68.1% (vs SP8 72.1%, within variance), stroop x3 32.2%
  (vs SP8 28.9%, no improvement — "one key per condition" abstraction
  is structurally inadequate when correct key depends on stim_color),
  stop_signal x1 59.4% (SessionAgent's directive used stimulus IDs vs
  executor's condition labels; runtime branch silently never fired).
  Infrastructure is reusable for future SP candidates; the negative
  empirical result honestly informs scope. See `docs/sp9a-results.md`.
  Tag `sp9a-complete`. ✓ Complete.
- **SP9b**: Stage 4 `openalex.verify_doi` defensive fix. 1-line
  normalization: `expected_authors` may be `str` or `list`; list →
  space-joined string before `.split()`. Unblocks expfactory_flanker
  regeneration (SP8 Stage 4 crash). Plus +1 test (564 passed total).
  Tag `sp9b-complete`. ✓ Complete.
- **SP9** (continuing backlog): the SP9a empirical run surfaced two
  pre-existing higher-leverage issues than SessionAgent itself:
  (1) **Platform-recording gap (SP7 layer d)** — user-observed during
  SP9a runs: jsPsych keyboard-response-plugin doesn't read from raw
  document keydown events, so platform CSV `response` column drops
  from ~93% (bot→page) to ~48% (page→platform). Affects ALL paradigms.
  Next SP candidate (will be SP9c). (2) **TaskCard `task_specific.key_map`
  schema variation** — stop-signal uses stimulus IDs, stroop/n-back
  use condition labels. Executor's `_resolve_response_key` assumes one
  shape; runtime branch silently fails when shape doesn't match.
  (3) Also outstanding from SP8: Stage 6 pilot timing fragility.
  (4) Also outstanding: commit SP8-regenerated TaskCards to sp8
  branch (done in b06122e, but not on a new tag — sp8-complete still
  references the docs commit).
- **SP12**: Codebase simplification + antagonistic audit + runtime
  visibility + post-cleanup re-measurement. Top-down walk-and-prune
  from CLI entry through every module exercised in a production run.
  Removed: 14 one-shot SP-era scripts, 14 SP11 phase deliverable docs
  (consolidated to sp11-complete.md), SessionAgent path entirely
  (SP9a hypothesis empirically not supported), SP7 keypress diagnostic
  (zero production readers), 2 unused CLI flags, drop_from_scope/
  keyboard_deliverer/focus calibration modules, eisenberg validation
  module, v1-legacy TaskCard wrappers. Net src/experiment_bot/ shrink:
  -1,068 LOC across 21 commits (from SP12 baseline `2436289`; 26
  commits from the design-spec commit `19b809b`). Added:
  docs/pipeline-flow.md (13-section walkthrough), [sp12] stdout
  narration (5 lines/session), run_trace.json (structured per-stage
  trace), and docs/sp12-hardcoded-findings.md (paradigm-specific
  assumptions surfaced during the walk). Post-cleanup re-measurement
  on 4 SP11 paradigms × 5 sessions shows 3/4 paradigms behaviorally
  stable vs Phase 7 N=5 baseline; one notable shift on
  expfactory_stop_signal SSRT (178→353 ms, within baseline's wide SD)
  attributable to diagnostic-noise reduction. Tag `sp12-complete`.
  ✓ Complete.
- **SP13**: Iterative pilot refinement. Stage 6's one-shot refiner replaced
  with a sequential walker that advances one DOM state per attempt.
  `PilotDiagnostics.dom_fingerprint` enables stuck-detection (2 consecutive
  identical fingerprints → early `PilotValidationError`). `REFINEMENT_PROMPT`
  rewritten to "propose the smallest next advance"; prior-attempt diffs are
  forwarded so the LLM doesn't undo earlier progress. Budget bumped 3 → 12
  total attempts. Mid-SP13 fix: `PilotRunner.run` captures the page DOM on
  Playwright crashes so stuck-detection fires regardless of failure mode
  (was a real gap surfaced by the dev-4 regression run). Internal CI: 683
  passed (was 676); +7 tests across fingerprint, prompt invariants,
  prior_diffs rendering, stuck-detection, budget override. External:
  held-out paradigm `stop_signal_with_integrated_memory` STUCK-DOM FAIL at
  attempt 2 (stuck-detection correctly aborted; LLM proposed a navigation
  phase in nested-action JSON shape rather than the navigator's flat shape
  — surfaces "REFINEMENT_PROMPT lacks navigation-phase schema knowledge" as
  the next gap, motivating SP14). Dev-4 paradigms pass Stage 6 with the
  same refinement counts as pre-SP13 (3 on attempt 1, stopit_stop_signal
  needed 1 refinement same as before — backward-compatible). See
  `docs/sp13-spec.md` and `docs/sp13-results.md`. Tag `sp13-complete`.
  ✓ Complete.
- **Reviewer-1 charter**: `docs/reviewer-1-charter.md` (added in SP8)
  documents adversarial review instructions for a fresh Claude session
  to interrogate the abstract's central claim. Update on every
  SP-complete tag.
- **SP-HPC** (deferred): Sherlock/SLURM batch deployment for unattended
  overnight runs.

## Documents to read before starting

- `docs/scope-of-validity.md` — what the framework claims and does not
  claim. The reviewer-facing spec.
- `docs/generalization-audit.md` — original audit, all 13 findings
  resolved.
- `docs/effect-library-audit.md` — the audit that motivated the
  generic-mechanism refactor.
- `docs/cse-sign-flip-diagnostic.md` — diagnostic that surfaced the
  dead-code-CSE issue.
- `docs/clean-run-2026-05-06.md` — provenance for the current
  shareable dataset.
- `docs/heldout-nback-test.md` — held-out generalization test result.

## Operational rules

- Never modify norms files after sessions reference them. Re-extract
  with new citations to make a new norms-file version.
- Never tune effect magnitudes after seeing validation results.
  Magnitudes come from the Reasoner's literature scrape; if validation
  fails, the fix is at the Reasoner level (better citations, better
  prompt), not at the magnitude level.
- The held-out paradigm's prompts/configs are NEVER iterated against.
  If a held-out paradigm fails, document the limitation; do not change
  prompt text to make it pass.
- Validation against published ranges is point-estimate-within-range.
  Don't introduce alternative gating without an explicit scope-of-
  validity update.

## Style preferences

- Inline TDD when changes are small. Subagent-driven development for
  larger plans (see `superpowers:subagent-driven-development`).
- Commit incrementally with a co-author trailer for Claude.
- Tight, focused commit messages — describe what changed and why,
  reference docs/audit findings where relevant.
- Don't write multi-paragraph docstrings or planning docs unless
  explicitly asked.
- Avoid "we did X, then Y, then Z" narration in user-facing replies.
  State results, propose next steps.

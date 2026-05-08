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
- **SP3** (planned): Additional held-out paradigms (Flanker,
  Sternberg, etc.) to strengthen generalization claim. Not started.
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

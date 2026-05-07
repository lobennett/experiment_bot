# Level 1 Refactor — Inspection Report

**Date:** 2026-05-06
**Scope:** Audit the generic-mechanism refactor (commit `4257fae`) for
residual paradigm-named vocabulary. Goal: catch incomplete migration
*before* downstream consequences (running new pipelines, producing
new TaskCards) bake in the wrong names.

## Summary

The refactor's runtime path is clean (the registered effects in
`EFFECT_REGISTRY` are generic; the sampler/executor invokes the
generic handlers; `normalize.py` migrates old TaskCards). But there
are **eight residual paradigm-named items** elsewhere in the
pipeline that need cleanup or explicit reasoning:

1. **Stage 1 prompt (`prompts/system.md`)** — Section 10 still
   instructs the LLM to emit `post_error_slowing` and
   `post_interrupt_slowing`. Fresh regen will produce
   paradigm-named TaskCards that then need `normalize.py` to
   migrate. (Severity: high — drives all new generation.)

2. **Stage 1 schema (`prompts/schema.json`)** — same problem; lists
   `post_error_slowing` and `post_interrupt_slowing` as schema fields.

3. **Stage 5 prompt (`reasoner/prompts/stage5_sensitivity.md`)** —
   example uses paradigm-specific labels (`congruent`).

4. **Stage 3 prompt (`reasoner/prompts/stage3_citations.md`)** —
   minor; placeholder example references conflict-style condition
   names.

5. **`norms_extractor.md` prompt** — mentions `cse_magnitude` and
   `post_error_slowing` as example metrics. Some paradigm naming in
   norms files is acceptable (literature uses CSE convention) but
   "post_error_slowing" should be reconsidered.

6. **Dead handlers in `effects/handlers.py`** — `apply_cse`,
   `apply_post_error_slowing`, `apply_post_interrupt_slowing`,
   `compute_pes_delta` no longer called from the registry. Kept as
   "deprecated shims" but only `apply_cse` is referenced (by tests).

7. **Dead config dataclasses in `core/config.py`** —
   `PostErrorSlowingConfig`, `PostInterruptSlowingConfig` no longer
   wired to the registry's `config_class` slot. Pure dead code.

8. **Stale string literals**:
   - `core/distributions.py:147` — `_EXECUTOR_APPLIED_EFFECTS = frozenset({"post_error_slowing", "post_interrupt_slowing"})`. These names no longer exist in the registry. The set's purpose (skip executor-applied effects in the sampler loop) is also now unnecessary — `post_event_slowing` is the only executor-applied effect, and it IS registered, so the sampler's iteration would call it twice (once via the registry, once via the executor). Need to fix.
   - `effects/registry.py:121-123` — `register_effect` docstring lists old built-in names.

## Detailed findings

### F1. Stage 1 prompt Section 10 still uses paradigm vocabulary

**Location:** `src/experiment_bot/prompts/system.md:186–210`

The prompt instructs the LLM to populate
`temporal_effects.post_error_slowing` and
`temporal_effects.post_interrupt_slowing` (in those exact key names).
Even though `normalize.py` migrates these into
`post_event_slowing`, the *source* of LLM output is still
paradigm-vocabulary. Every fresh regen produces paradigm-named
TaskCards.

**Why it matters:** the user's stated goal is that the bot's
vocabulary doesn't include paradigm-specific names. If the Stage 1
prompt names them, then Stage 1 IS the bot's vocabulary as far as the
LLM is concerned. The fact that we migrate downstream is a workaround,
not a fix.

**Fix:** rewrite Section 10 to describe the generic mechanisms
(`lag1_pair_modulation`, `post_event_slowing`, etc.) with examples of
configurations that map to specific paradigms. The `condition_repetition`
description is a borderline case — the mechanism is universal, but
its description mentions "the trial following an interrupt" (paradigm-
shaped). Also generalize.

### F2. Stage 1 schema (schema.json) lists paradigm-named effects

**Location:** `src/experiment_bot/prompts/schema.json:137, 164`

If the LLM is instructed to emit JSON conforming to schema.json, and
schema.json names `post_error_slowing` and `post_interrupt_slowing`,
the LLM is being told to use paradigm vocabulary even before reading
the prompt text.

**Fix:** replace these schema entries with the generic mechanisms.
Then the prompt (Section 10) and schema agree.

### F3. Stage 5 prompt example uses paradigm-specific labels

**Location:** `src/experiment_bot/reasoner/prompts/stage5_sensitivity.md:9–10`

The example sensitivity-rating output shows
`response_distributions/congruent/mu`. This is conflict-paradigm-
specific. A working-memory paradigm wouldn't have a "congruent"
condition.

**Fix:** replace with bracketed placeholder
(`response_distributions/<condition_label>/mu`).

### F4. Stage 3 prompt minor example issue

**Location:** `src/experiment_bot/reasoner/stage3_citations.py:13` (a
docstring example). Lower priority — not user-visible.

### F5. norms_extractor.md mentions paradigm metric names

**Location:** `src/experiment_bot/reasoner/prompts/norms_extractor.md:55,
62`

Lists `cse_magnitude` and `ssrt` as example metrics. These are
literature-conventional metric names — paradigm-named in their data,
not in the bot's vocabulary. This is acceptable IF we want the norms
files to use literature-conventional names, which is the current
choice. But `post_error_slowing` listed alongside is more of a
paradigm-specific framing (one trigger of the generic mechanism).

**Fix:** keep paradigm-conventional metric names where literature uses
them (cse_magnitude, ssrt), but reframe the prompt as "metric names
follow the literature for THIS paradigm class — these are
descriptive labels, not bot mechanisms."

### F6. Dead handler functions

**Location:** `src/experiment_bot/effects/handlers.py`

- `apply_post_error_slowing` (lines 78–93) — no longer in the
  registry. Originally the registry's PES handler.
- `apply_post_interrupt_slowing` (lines 148–172) — same.
- `apply_cse` (lines 282 onwards) — kept as a deprecated shim. Used
  by some tests still; could be removed once test fixtures are
  updated.
- `compute_pes_delta` (lines 94–146) — formerly called from the
  executor's inline PES code. Now unused.

**Fix:** delete `apply_post_error_slowing`,
`apply_post_interrupt_slowing`, `compute_pes_delta`. The post-event
slowing functionality is in `apply_post_event_slowing`. Keep
`apply_cse` only if some tests are still using it (audit those tests).

### F7. Dead config dataclasses

**Location:** `src/experiment_bot/core/config.py:135, 189`

- `PostErrorSlowingConfig` — formerly the typed config for the
  registry's `post_error_slowing` entry. No longer wired
  (`EFFECT_REGISTRY["post_event_slowing"].config_class` is `None`).
- `PostInterruptSlowingConfig` — same.

These dataclasses still exist and are imported by some tests. Removing
them would cascade. Audit imports first.

**Fix:** remove the dataclasses. Update any importing tests (or test
fixtures) to use SimpleNamespace-shaped configs instead.

### F8. Stale executor-applied-effects set in distributions.py

**Location:** `src/experiment_bot/core/distributions.py:147`

```python
_EXECUTOR_APPLIED_EFFECTS = frozenset({"post_error_slowing", "post_interrupt_slowing"})
```

This is BROKEN now. The names in this set don't appear in the
registry anymore. The set's purpose was to prevent the sampler from
running PES / post_interrupt while the executor also runs them.

After the refactor:
- The registry has `post_event_slowing`, not the old names.
- The executor invokes `apply_post_event_slowing` directly.
- The sampler iterates registered effects and would invoke
  `post_event_slowing` too — meaning it gets applied twice per
  trial (once in sampler, once in executor).

This is a real runtime bug. The `recent_errors` and
`prev_interrupt_detected` fields on `SamplerState` are False inside
the sampler (the sampler doesn't track them), so the handler returns
0 there. So the double-invocation produces 0 + correct delta from the
executor side. Still, sloppy.

**Fix:** update the set to `frozenset({"post_event_slowing"})` so
the sampler skips it cleanly. Or, more cleanly, drop the set
entirely — the post_event_slowing handler returns 0 when the relevant
state flags are False anyway, which is the case in the sampler's
state-construction path. Both work; explicit skip is clearer.

### F9. `register_effect` docstring lists old built-ins

**Location:** `src/experiment_bot/effects/registry.py:121–123`

The docstring says "beyond the seven built-in entries (autocorrelation,
fatigue_drift, post_error_slowing, condition_repetition, pink_noise,
post_interrupt_slowing, congruency_sequence)". These are the OLD
built-ins. After the refactor, the built-ins are: autocorrelation,
fatigue_drift, condition_repetition, pink_noise,
lag1_pair_modulation, post_event_slowing.

**Fix:** update docstring.

## Recommended cleanup order

These are mechanical, low-risk changes once the user authorizes:

1. **F8 (highest priority)**: fix `_EXECUTOR_APPLIED_EFFECTS` —
   real runtime issue, prevents double-invocation.
2. **F1, F2**: update Stage 1 prompt + schema to generic mechanisms.
   This affects all future TaskCard generation.
3. **F6, F7**: delete dead handler functions and config dataclasses.
   Test surface for cascading imports needs review.
4. **F3, F4, F9**: minor doc/example cleanups.
5. **F5**: norms-extractor prompt — discuss whether to keep
   literature-conventional metric names (current state) or push
   harder on generic naming.

After cleanup, run the full test suite. Then re-validate the four
dev paradigms — the existing TaskCards continue to work via
`normalize.py` migration; freshly-regenerated ones would emit the new
mechanism names directly.

## What the refactor got right

For the record:

- **`EFFECT_REGISTRY` is generic.** No paradigm-named entries.
- **Sampler iteration is generic.** No paradigm-class filtering.
- **`apply_lag1_pair_modulation` and `apply_post_event_slowing` are
  generic.** They read tables/triggers from cfg.
- **`normalize.py` migration shim works.** Old TaskCards translate
  to new shape without regen.
- **Validation oracle's metric names are data-driven from norms files.**
  Paradigm-conventional names in *data* (norms files), not in the
  bot's library.
- **Tests have negative assertions** (paradigm-named items are absent
  from registry) that prevent regression.

The cleanup items above are residue, not architectural problems.

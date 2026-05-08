# SP3 Flanker Reasoner failure (provisional log)

This is a holding note. Final write-up lands in `docs/sp3-heldout-results.md` (Task 13).

**Date:** 2026-05-08 (run started 2026-05-07 22:41 PT)
**Branch:** `sp3/heldout-validation` @ commit `54ee29a` (post-Task-0)
**Command:**
```
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/3/" \
  --label expfactory_flanker --pilot-max-retries 3 -v
```

**Outcome:** Stage 2 schema validation failed after 3 refinement attempts. Pipeline raised `Stage2SchemaError`; no TaskCard produced.

## Stage 2 failure trail

Three attempts, each with different errors:

**Attempt 1:**
- `temporal_effects.lag1_pair_modulation.value.modulation_table.3`: extra props `accuracy_delta`, `rt_delta_ms`
- `temporal_effects.post_event_slowing.value.triggers.0`: extra props `duration_trials`, `slowing_ms`
- `performance.accuracy.incongruent`: `None is not of type 'number'`

**Attempt 2:**
- `performance.accuracy.incongruent`: `None is not of type 'number'` (regression: lag1/PES errors temporarily fixed but accuracy still null)

**Attempt 3 (final, surfaced):**
- `temporal_effects.lag1_pair_modulation.value.modulation_table.3`: extra props `curr_condition`, `prev_condition`, `rt_offset_ms` (new shape — LLM regressed)
- `temporal_effects.post_event_slowing.value.triggers.0`: `'error' is not of type 'object'` (LLM emitted bare string instead of structured trigger)
- `performance.accuracy.incongruent`: `None is not of type 'number'` (persistent across all 3 attempts)

## Reading

The LLM cannot stably produce schema-conformant Stage 2 output for Flanker, even with the post-audit prompt and schema documentation. Specific gaps:

1. **Field-name vocabulary mismatch.** LLM uses paradigm-natural names (`prev_condition`, `curr_condition`, `rt_offset_ms`, `accuracy_delta`, `slowing_ms`) for `lag1_pair_modulation.modulation_table[]` and `post_event_slowing.triggers[]`. The schema expects different (shorter) field names (`prev`, `curr`, ...).

2. **Trigger shape ambiguity.** `post_event_slowing.triggers` schema requires objects, but the LLM emitted a bare string `"error"` on attempt 3. Either the schema's trigger-object shape isn't documented clearly enough in the Stage 2 prompt, or the LLM's understanding of "trigger" defaults to a label rather than a structured spec.

3. **Persistent null in accuracy.** `performance.accuracy.incongruent` was `null` across all 3 attempts. The LLM repeatedly omitted a value. Stage 2 prompt may be ambiguous about whether per-condition accuracy is required, or the LLM may be overusing null when the literature provides a range rather than a point estimate.

This is **not** a bug to fix in SP3. Per the SP3 spec held-out policy, gaps surfaced by the held-out paradigm are findings to be triaged into a future SP4 sub-project. Tweaking the Stage 2 prompt or schema to make Flanker pass would defeat the purpose of the held-out test.

## Implication for SP3 deliverable

- Flanker operational pass: ✗ (Reasoner cannot produce a TaskCard)
- Flanker behavioral pass: N/A (no TaskCard, no sessions, no metrics)
- SP3 still proceeds with n-back to produce one held-out data point.

## SP4 backlog candidate

A Stage 2 prompt audit / schema-documentation pass focused on lag1 and PES sub-schemas, with Flanker as a regression test for the fix.

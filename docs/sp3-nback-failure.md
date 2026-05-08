# SP3 n-back Reasoner failure (provisional log)

This is a holding note. Final write-up lands in `docs/sp3-heldout-results.md` (Task 13).

**Date:** 2026-05-08 (run started 00:25 PT, ended 00:39 PT; 14 min)
**Branch:** `sp3/heldout-validation` @ commit `858222f` (post-Flanker-fail-log)
**Command:**
```
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/5/" \
  --label expfactory_n_back --pilot-max-retries 3 -v
```

**Outcome:** Stage 2 schema validation failed after 3 refinement attempts. Pipeline raised `Stage2SchemaError`; no TaskCard produced.

## Stage 2 failure trail

**Attempt 1:**
- `temporal_effects.post_event_slowing.value.triggers.0`: `'error' is not of type 'object'` (LLM emitted bare string)
- `performance.accuracy.mismatch`: `{'target': 0.93, 'rationale': '...'}` is not of type `'number'` (LLM emitted Stage-2-style `{value, rationale}` envelope where a bare number was expected)
- `task_specific.key_map.rationale`: too long (LLM included a multi-sentence rationale string in a key-map field that expects a literal Playwright key)

**Attempt 2:**
- `temporal_effects.post_event_slowing.value.triggers.0`: extra prop `slowing_ms` (LLM regressed to a different invalid shape)
- `performance.accuracy.mismatch`: still `{target, rationale}` envelope
- `task_specific.key_map.rationale`: still too long

**Attempt 3 (final, surfaced):**
- `performance.accuracy.mismatch`: still `{target, rationale}` envelope (persistent across 3 attempts)
- `task_specific.key_map.rationale`: still too long (persistent across 3 attempts)
- (post_event_slowing trigger shape resolved by attempt 3)

## Reading

n-back's failure overlaps significantly with Flanker's:

1. **Same root cause for `post_event_slowing.triggers[]`:** schema requires objects, LLM emitted bare strings or missing fields. Convergence on a valid shape didn't happen.

2. **Same root cause for `performance.accuracy.<condition>`:** schema requires bare numbers; LLM emitted some non-number variant (Flanker: `null`; n-back: `{target, rationale}` envelope leaking from Stage-2 wrapping convention).

3. **n-back-specific gap — rationale-leakage:** the LLM put a long rationale prose field at `task_specific.key_map.rationale`. Schema's `key_map.<key>` is a string with `maxLength`. The LLM is over-applying the "rationale everywhere" pattern from the Stage-2 prompt template.

Per the SP3 spec held-out policy this is a finding, not a fix to make in SP3. The repeated failure across two independently-held-out paradigms suggests Stage 2 is the framework's brittle interface, not an LLM noise issue.

## Implication for SP3 deliverable

- n-back operational pass: ✗ (Reasoner cannot produce a TaskCard)
- n-back behavioral pass: N/A
- Both held-out paradigms (Flanker + n-back) fail at the same pipeline stage with overlapping failure modes. Strong empirical signal that the dev-paradigm iteration loop tuned the framework's tolerance toward shapes the dev paradigms happen to land on, but the LLM does not reliably produce schema-conformant Stage 2 output for paradigms it wasn't tuned against.

# SP4a — Stage 2 robustness (Tier 1 fixes from SP4 backlog)

## Origin

SP3 (`docs/sp3-heldout-results.md`) ran the experiment-bot framework against two held-out paradigms (Flanker, n-back) and observed both fail at the same pipeline stage — Stage 2 schema validation — with overlapping error signatures. The SP4 backlog (`docs/sp4-stage2-robustness.md`) documents 10 proposed improvements grouped into four tiers. SP4a is the first sub-project: bundle the three Tier 1 items into one focused implementation.

## Goal

Close the four Stage 2 failure modes that SP3 surfaced, via three coordinated changes concentrated in Stage 2 of the Reasoner. Re-run SP3 against the same held-out paradigms and report the result descriptively as evidence about the framework's generalization curve.

## Success criterion

Two-tier success:

**Internal (CI-checkable, gates SP4a completion):** each of the four Tier 1 failure modes has unit-test coverage on captured fixtures proving the fix works. Specifically:

1. `temporal_effects.post_event_slowing.value.triggers[]` shape errors — fixed via prompt-side schema example (1.2).
2. `temporal_effects.lag1_pair_modulation.value.modulation_table[]` field-name vocabulary mismatch — fixed via prompt-side schema example (1.2).
3. `performance.accuracy.<condition>` envelope contradiction — fixed via schema accepting `{value, rationale}` envelopes (1.3).
4. `task_specific.key_map.rationale` rationale-leakage — fixed via prompt-side anti-example (part of 1.2).

Plus refinement-loop cross-attempt regression — fixed via slot-locked refinement (1.1).

**External (descriptive, scientific contribution):** SP3 is re-run on Flanker and n-back. The outcome is reported in `docs/sp4a-results.md`:

- per-paradigm Reasoner attempt count (refinement convergence vs. divergence)
- whether each paradigm produced a TaskCard
- residual failure modes if any
- comparison vs. SP3's outcome

Held-out outcome is the scientific evidence that builds toward the project's generalization claim. It does **not** gate SP4a completion. If the re-run reveals new failure modes, those become the next SP's input — SP4a does not expand to chase them.

This framing protects the held-out testing pattern itself: gating SP4a on held-out pass would create pressure to tune until it does, defeating the held-out method's purpose.

## Architecture

Five touch-points, each in one file or file pair.

### `src/experiment_bot/prompts/schema.json` (1.3)

`performance.accuracy`, `performance.omission_rate`, and `performance.practice_accuracy` accept either a bare number or a `{value: number, rationale: string}` envelope, via `oneOf`:

```jsonc
"accuracy": {
  "type": "object",
  "additionalProperties": {
    "oneOf": [
      {"type": "number", "minimum": 0, "maximum": 1},
      {
        "type": "object",
        "properties": {
          "value": {"type": "number", "minimum": 0, "maximum": 1},
          "rationale": {"type": "string"}
        },
        "required": ["value"]
      }
    ]
  }
}
```

Existing TaskCards (bare numbers) keep validating; new TaskCards can ship either shape. No migration tooling needed.

### `src/experiment_bot/reasoner/validate.py` (1.3)

Extend the envelope-unwrap helper so the validator dereferences `{value: number}` envelopes before the inner type check. Currently `_value_only` only handles `{value: dict}`. Add the `{value: number}` case explicitly, or generalize.

### Executor / TaskCard loader (1.3)

Wherever `performance.accuracy[<cond>]` (and siblings) are read at runtime — likely in `src/experiment_bot/core/executor.py` or a related config loader — unwrap the envelope at load time. Single helper, called once at TaskCard load, not per-trial.

### `src/experiment_bot/reasoner/prompts/stage2_behavioral.md` (1.2)

Add a `## Concrete shape examples` section with fenced JSON blocks. Each block tagged with a fence-class the invariant test recognizes:

- Good shapes: `\`\`\`json schema-example: <path>` (e.g., `temporal_effects.post_event_slowing.triggers[]`).
- Anti-examples: `\`\`\`json schema-anti-example: <path>`.

Coverage:

- `lag1_pair_modulation.modulation_table[]` items — good (with `prev`, `curr`, `delta_ms`); bad (with `prev_condition`, `curr_condition`, `rt_offset_ms`).
- `post_event_slowing.triggers[]` items — good (with `event`, `slowing_ms_min`, `slowing_ms_max`); bad (bare string `"error"`; bad shape with `slowing_ms` only).
- `performance.accuracy.<condition>` — both bare-number and envelope shapes shown as good.
- `task_specific.key_map` — good (flat condition→key map); anti-example with `rationale` key (the n-back failure mode); explicit text "do NOT include rationale fields in `key_map`."

Examples are hand-written and committed to the prompt file. The invariant test (Section 5) defends against drift.

### `src/experiment_bot/reasoner/stage2_behavioral.py` (1.1)

Refactor the refinement loop. New helpers:

- `_extract_failing_slots(errors: list[tuple[str, str]]) -> list[str]`: walks `Stage2SchemaError.errors` paths and produces slot keys at the granularity errors actually surface. Slot-extraction rule by path prefix:
  - `temporal_effects.<mech>.value.<inner>` → slot = `temporal_effects.<mech>`
  - `performance.<sub>.<cond>` → slot = `performance.<sub>` (where `<sub>` ∈ `accuracy`, `omission_rate`, `practice_accuracy`)
  - `task_specific.<key>.<inner>` → slot = `task_specific.<key>`
  - `between_subject_jitter.value.<inner>` → slot = `between_subject_jitter`
  - `response_distributions.<cond>.<inner>` → slot = `response_distributions.<cond>`
  Multiple errors at the same slot are deduplicated. Slot order is deterministic (sorted) so refinement prompts are stable.
- `_render_slot_refinement_prompt(partial: dict, failing_slots: list[str], errors: list[tuple]) -> str`: builds the slot-specific re-prompt. Sections: previously-validated context (locked, "do NOT modify"), failing-slot list, per-slot guidance pulled from the schema example blocks rendered in the prompt addendum.

The loop becomes:

1. Initial generation → parse → schema validate.
2. On validation failure: extract failing slots; render slot-specific refinement prompt; LLM call; merge response slots back into `partial`; re-validate.
3. Repeat up to `STAGE2_MAX_REFINEMENTS` (3, unchanged).
4. On budget exhaustion: surface `Stage2SchemaError` with attempt history.

The JSON-parse-error refinement path stays as-is; that's a separate failure mode SP4a does not modify.

## Data flow

```
Stage 2 input: Stage 1 partial + literature
    │
    ▼
LLM call (initial generation)
    │
    ▼
JSON parse → if fails, refine for parse error (existing behavior, unchanged)
    │
    ▼
schema validate ──pass──▶ exit loop, return partial
    │ fail
    ▼
extract failing slots from Stage2SchemaError.errors
    │
    ▼
render slot-specific refinement prompt:
  - "Previously-validated context (do NOT modify):" + JSON of validated slots
  - "Failing slots to fix:" + list
  - "Per-slot guidance:" + schema example for each failing slot's path
    │
    ▼
LLM call (refinement)
    │
    ▼
merge response into partial: for each failing slot, partial[<slot>] = response[<slot>]
    │
    ▼
re-validate (loop, budget = STAGE2_MAX_REFINEMENTS = 3)
    │
    ▼
budget exhausted: surface Stage2SchemaError with attempt history
```

## Test strategy

Four test files, each with one focused responsibility:

### `tests/test_stage2_envelope.py`

- Schema accepts both bare-number and envelope shapes for `performance.accuracy`, `omission_rate`, `practice_accuracy`.
- Validator's unwrap helper returns the inner number from both shapes.
- Executor/loader's unwrap returns identical results for both shapes (round-trip equivalence).

### `tests/test_prompt_schema_consistency.py`

The Q4 invariant test. Extracts every fenced block tagged `json schema-example: <path>` and `json schema-anti-example: <path>` from `stage2_behavioral.md`. For each:

- Look up the schema sub-tree at `<path>` (resolve `[]` array-item suffix as the `items` schema).
- `schema-example` blocks: must validate.
- `schema-anti-example` blocks: must fail validation.

If either invariant breaks, fail with a clear `prompt and schema disagree at <path>` message.

### `tests/test_stage2_refinement_locks.py`

- Captured fixtures: `tests/fixtures/stage2/sp3_flanker_attempt3.json`, `tests/fixtures/stage2/sp3_nback_attempt3.json` (extracted from `.reasoner-logs/sp3_*_regen.log` final attempts).
- `validate_stage2_schema` raises `Stage2SchemaError` with paths matching what SP3 actually saw (regression lock on diagnosis quality).
- `_extract_failing_slots` returns the expected slot list for each fixture's error set.
- Given a synthesized "previously-validated partial" + the fixture's failing slots, the merge logic preserves validated slots and replaces only failing ones.
- End-to-end: simulating a refinement attempt where the LLM's slot-only response fixes the failing slots, the merged partial passes validation.

### `tests/test_stage2_behavioral.py` (extend existing or add)

Higher-level test for the full refinement loop using a stub `LLMClient`:

- Initial passes, no refinement.
- One slot fails first attempt, fixes on second.
- Regression scenario: a slot fixed once is "regressed" by the LLM on a hypothetical follow-up — verifies the lock-in behavior prevents regression by *not* asking the LLM about that slot again.

### Held-out re-run (manual, descriptive)

Not a unit test. Re-run the SP3 protocol (the regen commands in Tasks 2 and 7 of the SP3 plan) on a fresh worktree off `sp4a-complete`. Capture the Reasoner logs and write `docs/sp4a-results.md` with the per-paradigm outcome.

## Deliverables

- Worktree `.worktrees/sp4a` on branch `sp4a/stage2-robustness`, branched off tag `sp3-complete` (with this spec and the SP4 backlog cherry-picked).
- Code changes in: `src/experiment_bot/prompts/schema.json`, `src/experiment_bot/reasoner/validate.py`, `src/experiment_bot/reasoner/stage2_behavioral.py`, `src/experiment_bot/reasoner/prompts/stage2_behavioral.md`, plus the executor/TaskCard-loader file that reads `performance.accuracy[<cond>]` (the implementing engineer locates the exact file via grep — likely `src/experiment_bot/core/executor.py` or a config-loading helper it imports from).
- Tests added per the test strategy: `tests/test_stage2_envelope.py`, `tests/test_prompt_schema_consistency.py`, `tests/test_stage2_refinement_locks.py`, plus extensions to `tests/test_stage2_behavioral.py`.
- Captured fixtures: `tests/fixtures/stage2/sp3_flanker_attempt3.json`, `tests/fixtures/stage2/sp3_nback_attempt3.json`.
- `docs/sp4a-results.md` — descriptive report of the SP3 re-run.
- Tag `sp4a-complete` on the report-landing commit. Push branch + tag to origin.
- `CLAUDE.md` sub-project history updated with SP4a completion.

## Out of scope

- Tier 2 items (#2.1 canonicalization layer, #2.2 constructive feedback, #2.3 held-out fixtures as standing CI). Each is a follow-on SP after SP4a's results land.
- Tier 3 items (#3.1 two-pass Stage 2 split, #3.2 schema-as-canonical autogeneration). Architectural refactors; their own brainstorm/spec cycles.
- Tier 4 #4.2 (divergence-aware retry budget). Defensive complement to SP4a but not required.
- Adding new held-out paradigms beyond Flanker + n-back. The SP3 re-run uses the same URLs to keep the comparison fair.
- Tuning the Tier 1 fixes if SP3 re-run reveals a fifth failure mode. That becomes the next SP's input.
- Refinement-loop performance/cost optimization. Slot-only prompts naturally reduce token usage but optimizing further is not a goal.
- TaskCard migration tooling. Schema's `oneOf` keeps both shapes valid.

## Sub-project boundary check

This spec is appropriately scoped to a single implementation plan:

- One concrete deliverable (the four Tier 1 fixes shipped + an SP3 re-run report).
- One bounded set of code changes (the five touch-points listed above).
- One pre-defined success criterion split into internal-CI gate and external descriptive evidence.
- A clear hand-off rule for findings (new failure modes → next SP, not SP4a's responsibility).

If the held-out re-run surfaces a fifth Tier-1-like failure mode, the resulting SP4b would be its own brainstorm/spec/plan cycle.

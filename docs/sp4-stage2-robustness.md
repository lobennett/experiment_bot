# SP4 backlog — Stage 2 LLM↔schema interface robustness

**Driver:** SP3 held-out test results — see `docs/sp3-heldout-results.md`. Both held-out paradigms (Flanker, n-back) failed at Stage 2 schema validation with overlapping error signatures. The dev paradigms converge; the held-out paradigms do not. The gap lies in a specific, named layer of the pipeline.

**Goal of SP4:** make Stage 2 the *least brittle* point in the LLM-driven pipeline rather than the most brittle. The improvements below are framed in terms of best-practice software interface patterns (Postel's law, single source of truth, defensive boundaries, regression-suite-driven evolution). They are deliberately generalizable — none of them name Flanker, n-back, or any specific paradigm. Each is a property of the interface, not a paradigm-specific fix.

## What's actually broken (recap, grounded)

| Failure mode | Where in code | What the LLM does | What the schema requires |
|---|---|---|---|
| post_event_slowing trigger shape | `src/experiment_bot/prompts/schema.json:184-206` | Emits bare string `"error"`, or `{slowing_ms: <num>}` | `{event: "error"|"interrupt", slowing_ms_min, slowing_ms_max}` |
| lag1_pair_modulation field-name mismatch | `schema.json:155-183` | Emits `prev_condition`, `curr_condition`, `rt_offset_ms` | `prev`, `curr`, `delta_ms` (or min/max pair) |
| performance.accuracy envelope leak | `schema.json:62-66` + prompt L24-26 | Emits `{value, rationale}` envelope (or `null`) | Bare `number ∈ [0,1]` |
| key_map.rationale leak | `schema.json:99-103` | Puts long rationale string at `key_map.rationale` | `key_map` is a flat condition-label → key-string map; values are 24-char keys |
| Cross-attempt regression | `src/experiment_bot/reasoner/stage2_behavioral.py:74-136` | Re-rolls *entire* Stage 2 output each attempt | (intent: refine only the broken fields) |

Two of these (post_event_slowing trigger shape; performance.accuracy envelope leak) hit *both* held-out paradigms. The pattern is: the prompt and the schema disagree about envelope conventions, and the prompt is missing concrete examples that would let the LLM see what shape the schema actually wants.

## Improvement proposals, prioritized

The proposals are grouped by impact-cost ratio. Within each tier, they're independent and can be tackled in any order; nothing has hidden dependencies on a later item.

### Tier 1 — High-impact, low-cost (do first)

#### 1.1. Refinement loop preserves validated slots

**Files:** `src/experiment_bot/reasoner/stage2_behavioral.py:74-136`, `src/experiment_bot/reasoner/validate.py:47-170`.

**Best-practice pattern:** *fix-forward iteration over partial state*. When part of a generated artifact passes validation, that part is now ground truth; subsequent iterations should not regenerate it.

**Concrete change:** track which top-level Stage 2 keys (and second-level enum-like keys: each `temporal_effects.<mech>`, each `performance.<sub>`, each `task_specific.<sub>`) passed schema validation on the previous attempt. On refinement, prompt the LLM with:
- The previously-passing slots as a "locked-in" reference.
- Only the failing slots as the slots to regenerate.
Merge the LLM's regenerated slots back into the partial; re-validate the whole thing.

This requires `validate_stage2_schema` to return *which top-level fields failed* rather than a flat error list. The current `Stage2SchemaError.errors` is `list[tuple[str, str]]` — the path string already contains the slot. A trivial parse plus a "slot manifest" data structure (set of passing slots vs. set of failing slots) closes the gap.

**Why this matters:** in both Flanker and n-back, refinement attempts regressed previously-correct slots. The fix raises convergence probability without raising the LLM's reasoning load.

#### 1.2. Prompt renders schema sub-object examples inline (auto-generated)

**Files:** `src/experiment_bot/reasoner/prompts/stage2_behavioral.md`, new `src/experiment_bot/reasoner/prompts/_render.py`.

**Best-practice pattern:** *single source of truth*. Schema is canonical; prompt content describing schema shape is *generated from the schema*, not hand-maintained alongside it.

**Concrete change:** add a render step that walks `schema.json` and, for each shape the LLM has historically gotten wrong (currently: trigger items, modulation_table items, key_map values, performance.* sub-fields), produces a literal example in the prompt. For example:

```markdown
## Concrete shape examples (read carefully — schema rejects variants)

post_event_slowing.triggers — each item must look like:
  {"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}
NOT:
  "error"
  {"slowing_ms": 50}
  {"event": "error"}

lag1_pair_modulation.modulation_table — each item must look like:
  {"prev": "<label>", "curr": "<label>", "delta_ms": -25}
  OR {"prev": "<label>", "curr": "<label>", "delta_ms_min": -40, "delta_ms_max": -10}
NOT:
  {"prev_condition": "...", "curr_condition": "...", "rt_offset_ms": ...}
  {"prev": "...", "curr": "...", "accuracy_delta": ...}
```

Render these from `schema.json`'s `properties.<path>` plus a small hand-curated `_anti_examples` table of observed LLM mis-shapes. The anti-examples table is the only paradigm-touching artifact; everything else is schema-derived.

**Why this matters:** the LLM does not stably infer field-name vocabulary or trigger object shape from abstract description. It does stably copy shape from concrete examples. This change addresses three of the four observed failure modes (1.1, 1.3, 1.4 in the recap table).

#### 1.3. Resolve the `performance.*` envelope contradiction

**Files:** `src/experiment_bot/reasoner/prompts/stage2_behavioral.md:24-26`, `src/experiment_bot/prompts/schema.json:58-74`.

**Best-practice pattern:** *internal consistency between contracts*. Two artifacts describing the same thing must agree.

**The contradiction:** prompt says "for each numeric parameter, also include a `rationale` string." Schema says `performance.accuracy.<condition>` is a bare number. The LLM follows the prompt. The schema rejects.

**Two clean choices:**
- (a) Make `performance.*` consistent with `temporal_effects.*` — accept `{value, rationale}` envelopes, unwrap in the executor's loader (`_value_only` already does this in `validate.py`). One-line schema change; small loader change.
- (b) Make the prompt explicit about the `performance.*` exception — "all numeric parameters are wrapped in `{value, rationale}` EXCEPT `performance.accuracy`, `performance.omission_rate`, and `performance.practice_accuracy`, which are bare numbers."

(a) is cleaner (no exceptions) and aligns with how `temporal_effects.*` already works. (b) is smaller-blast-radius and ships in a single prompt edit.

Recommend (a) for consistency. Either resolves the bug.

**Why this matters:** this single contradiction caused persistent failure across all 3 attempts in both held-out paradigms. It's not an LLM weakness; it's an interface defect.

### Tier 2 — Medium-impact, medium-cost

#### 2.1. Field-name canonicalization layer (Postel's law)

**Files:** new `src/experiment_bot/reasoner/canonicalize.py`, called from `stage2_behavioral.py` immediately before `validate_stage2_schema`.

**Best-practice pattern:** *be liberal in what you accept; be strict in what you produce*. A small, named, audited set of LLM-natural-name → canonical-name mappings.

**Concrete change:** add a `canonicalize_stage2_partial(partial: dict) -> dict` that walks the partial and rewrites known synonyms:

| LLM emitted | Canonical (per schema) |
|---|---|
| `prev_condition`, `previous_condition`, `previous` | `prev` |
| `curr_condition`, `current_condition`, `current` | `curr` |
| `rt_offset_ms`, `delta_rt_ms`, `rt_delta_ms` | `delta_ms` |

Strictly scoped — every entry has a comment justifying the mapping with a real LLM observation. Not a general fuzzy-matching fallback (that would mask real errors).

**Why this matters:** even with examples in the prompt, an LLM may emit field-name variants. The canonicalization layer absorbs that without the schema becoming permissive.

#### 2.2. Constructive validation feedback

**Files:** `src/experiment_bot/reasoner/validate.py:21-26` (Stage2SchemaError), `stage2_behavioral.py:122-133` (refinement prompt).

**Best-practice pattern:** *error messages that suggest the fix*, not just describe the failure.

**Concrete change:** `Stage2SchemaError` accepts an optional `schema_excerpt: dict` per error (the JSONSchema sub-tree at the failing path). When an error fires, render the schema excerpt as a "what was expected" block in the error message:

```
- temporal_effects.post_event_slowing.value.triggers.0:
    'error' is not of type 'object'
    Expected shape: {event: "error"|"interrupt", slowing_ms_min: number, slowing_ms_max: number}
    Example: {"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}
```

The rendered example reuses the same code path as #1.2's prompt-example renderer. Single source of truth for "what does this schema sub-object look like correctly."

**Why this matters:** the LLM has to derive the correct shape from the validation error. Constructive feedback shortens that loop and reduces the chance of regression on retry.

#### 2.3. Held-out Reasoner regression suite

**Files:** new `tests/test_stage2_heldout_regression.py`, fixtures under `tests/fixtures/stage2/`.

**Best-practice pattern:** *capture-and-replay regression tests* for components that depend on external systems.

**Concrete change:** record current Flanker and n-back Stage 2 raw LLM outputs (the malformed ones) as fixtures. Add tests that:
- Run the malformed fixtures through `validate_stage2_schema` and assert the error messages name the failing slots we expect (locks in the validator's diagnosis quality).
- Run the malformed fixtures through `canonicalize_stage2_partial` (#2.1) and assert the post-canonicalization candidates pass schema validation OR fail with the residual minimal error set.
- After improvements ship, also assert that *fixed* (well-formed) variants of the fixtures pass validation cleanly.

This makes the held-out paradigms part of CI without requiring live Reasoner runs each time. The fixtures are committed; the LLM is not in the loop for regression testing.

**Why this matters:** the dev-paradigm test suite passed 468/468 at `sp2.5-complete` and yet the framework's generalizability was empirically falsified. The dev paradigms cannot detect generalizability regressions. Held-out fixtures can.

### Tier 3 — Higher-impact, higher-cost (architectural)

#### 3.1. Two-pass Stage 2 (literature interpretation → schema mapping)

**Files:** `src/experiment_bot/reasoner/stage2_behavioral.py` (large rewrite), new `prompts/stage2a_literature.md`, `prompts/stage2b_schema.md`.

**Best-practice pattern:** *separation of concerns*. Each LLM pass has one job.

**Concrete change:** split Stage 2 into:
- **2a (literature pass):** the LLM produces a free-form, lightly-structured interpretation of the literature for the paradigm class (per-condition RT means/SDs, documented temporal effects, magnitudes, etc.). Output is a structured intermediate format with rationales — but not yet schema-conformant.
- **2b (schema-mapping pass):** a separate, smaller LLM call takes the 2a output plus the schema and emits schema-conformant JSON. This pass has a tightly bounded job: shape transformation, no scientific judgment.

The 2b pass is amenable to fine-tuning, deterministic-template-with-LLM-fill-ins, or even non-LLM rule-based mapping for the well-understood transforms. The 2a pass remains the LLM's most-judgment-heavy responsibility but no longer has to also worry about exact field names.

**Why this matters:** asking one LLM call to do "translate the literature into JSON with this exact shape" is asking it to do two cognitively distinct things at once. Splitting the passes addresses the persistent failure mode where the LLM gets the science right and the shape wrong.

**Cost:** non-trivial refactor of `stage2_behavioral.py`. New prompts to design and test. Approximately +1 LLM call per Stage 2 run (cost), but each call is shorter and less likely to fail.

#### 3.2. Schema as canonical: prompt and validator both generated/loaded from one source

**Files:** `src/experiment_bot/prompts/schema.json` (canonical), generated `prompts/_schema_examples.md`, generated `validate_stage2_schema_from_schema.py`.

**Best-practice pattern:** *single source of truth* for cross-component contracts.

**Concrete change:** treat `schema.json` as the only canonical source. Auto-generate:
- The example blocks for the Stage 2 prompt (#1.2's renderer).
- A reference Python validator (`validate_stage2_schema` is currently hand-written and partly out of step with the schema — e.g., it hand-codes the `_value_only` envelope unwrap).
- Documentation reference (`docs/scope-of-validity.md`-style schema appendix).

This is the long-form structural fix that obviates many tier-1 and tier-2 items by removing the drift surfaces.

**Cost:** larger refactor; touches multiple components; should be sequenced after tier 1+2 land.

### Tier 4 — Defensive (do alongside tier 1)

#### 4.1. Prompt-schema invariant test

**Files:** new `tests/test_prompt_schema_consistency.py`.

**Best-practice pattern:** *contracts can lie; invariants don't*. Add a test that asserts the contracts are consistent.

**Concrete change:** add a test that:
- Parses the Stage 2 prompt's claims about envelope conventions (e.g., grep for "rationale" claims).
- Cross-checks against `schema.json`'s shape for the corresponding fields.
- Fails with a clear message if the prompt asserts an envelope that the schema doesn't accept.

This catches the *type* of contradiction we observed (envelope mismatch) at CI time, before it becomes a production bug.

**Why this matters:** the `performance.accuracy` contradiction has been latent in the codebase since SP2. Without an invariant test it can re-appear after any prompt edit.

#### 4.2. Stage 2 max_refinements is a knob, but the right number is "until convergence within a budget"

**Files:** `stage2_behavioral.py:21`.

**Best-practice pattern:** *bounded retry with exit on diverging signal*.

**Concrete change:** rather than a fixed `STAGE2_MAX_REFINEMENTS = 3`, track whether the *failing-slot set* shrank between attempts. If it didn't (or if it grew, as observed in both runs), abort early with a "no convergence" error rather than burning the remaining budget. Saves wall time on hopeless runs and surfaces the divergence pattern as a distinct failure mode.

This is small and complementary to #1.1 (which addresses the regression directly).

## Cross-cutting observation: dev-paradigm tests can't detect this class of bug

The 468-test green suite at `sp2.5-complete` reflects the *internal* behavior of the framework being correct (effect handlers, oracle metrics, executor mechanics). It does not reflect the *interface between LLM-generated content and the schema*, because the LLM is not exercised in unit tests.

The held-out test was the only mechanism that could surface this gap. Held-out tests are not a one-off SP3 deliverable; they should be standing CI infrastructure (#2.3 above). Concretely:

- After tier 1 lands, re-run SP3 (Flanker + n-back) and capture the resulting Stage 2 outputs. If they pass and produce reasonable TaskCards, commit them as fixtures.
- Add a third held-out paradigm (Sternberg, Wisconsin Card Sorting, random-dot motion) periodically as additional generalization signal.
- Treat the held-out fixtures as the framework's true generalizability metric, alongside the dev-paradigm test suite.

## Suggested SP4 sub-project shape

If we want to reach a "second SP3 attempt" pass:

1. **SP4a (1-2 days):** Tier 1 items in order — 1.3 (smallest), 1.2 (largest impact), 1.1 (best for regression). Ship and re-run SP3 against each held-out paradigm.
2. **SP4b (1-2 days):** Tier 2 items if SP4a doesn't fully close the gap — 2.1 likely sufficient, 2.2 for diagnostic quality, 2.3 for CI.
3. **SP4c (later, deferred):** Tier 3 items as a separate sub-project with its own brainstorm/spec. Don't bundle with SP4a/b.

The sub-project boundary check from the SP3 spec applies: each of SP4a, SP4b, SP4c is one bounded set of changes with one pre-defined success criterion (the next SP3 attempt operationally passes).

## Status

This document is the SP4 backlog. Selecting and scoping SP4 is a separate brainstorm/spec cycle.

# SP3 — Held-out generalization test results (Flanker + n-back)

**Date:** 2026-05-08
**Spec:** `docs/superpowers/specs/2026-05-08-sp3-flanker-nback-heldout-design.md`
**Plan:** `docs/superpowers/plans/2026-05-08-sp3-flanker-nback-heldout.md`
**Branch:** `sp3/heldout-validation` (off `sp2.5-complete` = `577f685`)

## Goal

Empirical evidence that the experiment-bot framework generalizes to two paradigms whose iteration loop never touched: Flanker (conflict class, within-class held-out) and n-back (working_memory class, cross-class held-out). Per the SP3 spec, the held-out paradigms' prompts/schemas/TaskCards are not iterated against.

## Headline result

**Both held-out paradigms failed at the same pipeline stage** (Stage 2: behavioral parameters). Neither produced a TaskCard. No sessions ran. Behavioral validation could not be exercised.

| Paradigm | TaskCard produced? | 5 sessions completed? | Validator ran? | Operational pass |
|---|---|---|---|---|
| Flanker | ✗ (Stage 2 schema validation failed after 3 refinements) | N/A | N/A | ✗ |
| n-back | ✗ (Stage 2 schema validation failed after 3 refinements) | N/A | N/A | ✗ |

Provisional logs: `docs/sp3-flanker-failure.md`, `docs/sp3-nback-failure.md`.

## What this means

The strict reading per the SP3 spec interpretation table:

> **Either paradigm operationally fails:** framework is overfit to the dev paradigms in the relevant dimension. Catalog gap, defer fix.

Both held-out paradigms failed at Stage 2 with overlapping error signatures, on the very first run of each, with no fix attempted. This is the strongest possible held-out signal: the dev-paradigm iteration loop tuned the framework — specifically, the LLM-schema interface in Stage 2 — to shapes the four dev paradigms happen to land on, and the LLM does not stably produce schema-conformant output for paradigms outside that set.

The framework's prior generalizability claim (G1 in `CLAUDE.md`: "pointing the bot at a novel paradigm's URL should work without code changes") does not hold empirically across the two held-out paradigms tested here.

## Failure analysis

Both Reasoner runs reached Stage 2 (the behavioral-parameters stage), produced output, hit `Stage2SchemaError` after 3 refinement attempts, and aborted. No Stage 6 pilot ever ran because Stage 2 didn't produce a candidate TaskCard.

The errors clustered into four shapes, with substantial overlap across paradigms:

### Shape A — `temporal_effects.post_event_slowing.triggers[]` shape errors

Both paradigms hit this. Schema (`src/experiment_bot/prompts/schema.json:184-206`) requires each trigger to be `{event: "error"|"interrupt", slowing_ms_min: number, slowing_ms_max: number}`. The LLM emitted instead:

- Flanker: `'error'` (bare string, not an object)
- n-back attempt 1: `'error'` (bare string)
- n-back attempt 2: `{slowing_ms: <num>}` (missing `event`, `slowing_ms_min`, `slowing_ms_max`; extra `slowing_ms`)

Reading: the LLM treats `event` as the trigger label and tries to write `triggers: ["error"]` rather than `triggers: [{event: "error", ...}]`. The Stage 2 prompt (`src/experiment_bot/reasoner/prompts/stage2_behavioral.md`) does not show an example trigger, and the schema's `enum` annotation for `event` doesn't propagate visibly into the prompt. The LLM works from the abstract description and gets the shape wrong.

### Shape B — `performance.accuracy.<condition>` non-number values

Both paradigms hit this; persistent across all 3 refinement attempts in both runs. Schema (`schema.json:62-66`) requires `additionalProperties: {type: "number", minimum: 0, maximum: 1}` — i.e., bare numbers, not objects. The LLM emitted:

- Flanker: `null` (LLM left it unset)
- n-back: `{target: 0.93, rationale: "..."}` — Stage-2-style `{value, rationale}` envelope

Reading: the Stage 2 prompt instructs (`prompts/stage2_behavioral.md:24-26`):

> For each numeric parameter, also include a `rationale` string.

But `performance.accuracy` is the only `value`-style field whose schema expects a bare number, not an envelope. The prompt and schema disagree about envelope-ness. The LLM follows the prompt and gets rejected by the schema. Across 3 refinement attempts the LLM never reconciled the two.

### Shape C — `temporal_effects.lag1_pair_modulation.modulation_table[]` field-name vocabulary mismatch (Flanker only)

Flanker enabled this mechanism; n-back didn't. Schema (`schema.json:155-183`) requires `{prev: str, curr: str, delta_ms: num | (delta_ms_min, delta_ms_max): num}`. LLM (Flanker, attempt 3) emitted `{prev_condition, curr_condition, rt_offset_ms}` — same intent, different field names.

Reading: the LLM uses paradigm-natural names; the schema uses shorter abstract names. The schema's `additionalProperties: false` rejects the LLM's variants. The Stage 2 prompt does not show the required field names for `modulation_table[]` items.

### Shape D — `task_specific.key_map.rationale` length violation (n-back only)

Schema (`schema.json:99-103`) accepts `additionalProperties` for `key_map`, but constrains each value to `{type: "string", maxLength: 24, pattern: "^[A-Za-z0-9_, .-]*$"}`. The LLM put a multi-sentence rationale string at `key_map.rationale`, expecting `rationale` to be a sibling-of-the-mapping rather than another mapping entry. Persistent across all 3 attempts.

Reading: the LLM applies the "rationale everywhere" pattern to `key_map`, but `key_map` is a uniform-value mapping (condition-label → key-string), not a structured object with metadata. The schema correctly rejects, but the LLM keeps trying.

## Refinement-loop pathology

In both runs the refinement loop *regressed* previously-correct fields:

- Flanker attempt 2 fixed lag1 vocabulary errors and post_event_slowing trigger shape, but on attempt 3 the LLM regressed both fields back to invalid shapes.
- n-back attempt 2 partially fixed post_event_slowing (different invalid shape, but trigger object now present), then attempt 3 fixed it fully, but `accuracy.mismatch` and `key_map.rationale` were never resolved.

Root cause: `src/experiment_bot/reasoner/stage2_behavioral.py:74-136` regenerates the *entire* Stage 2 output on each refinement attempt rather than locking in fields that already passed validation. The LLM's stochastic re-roll on each attempt can break fields that worked before. With only 3 attempts and several independent failure slots, the probability of any one run converging is poor.

## Behavioral metrics

Not produced. No TaskCard, no sessions, no metrics in either paradigm.

## Comparison vs smoke v3 dev paradigms

| Paradigm | Stage 2 outcome (this run / sp2.5-complete) | go-trial accuracy (sp2.5-complete smoke v3) |
|---|---|---|
| expfactory_stop_signal (dev) | ✓ converged | 94.2%, 96.7% |
| expfactory_stroop (dev) | ✓ converged | 95.0%, 95.8% |
| stopit_stop_signal (dev) | ✓ converged | 95.3%, 93.8% |
| **Flanker (held-out)** | ✗ Stage 2 schema failure | N/A — no sessions |
| **n-back (held-out)** | ✗ Stage 2 schema failure | N/A — no sessions |

The Stage 2 stage *can* converge (it does for all four dev paradigms), but its convergence is contingent on the LLM landing on field shapes it learned from the dev-paradigm regen runs. Held-out paradigms reveal that this convergence is fragile.

## Interpretation

Per the SP3 spec interpretation table, the relevant row is:

> **Either paradigm fails operationally:** framework is overfit even within the conflict class (Flanker) and across paradigm classes (n-back). Catalog gap, defer fix.

Both rows apply — within-class and cross-class held-out paradigms both fail. The fix is not in SP3 (held-out policy: no prompt or TaskCard tuning). The full set of generalizable improvements is documented in `docs/sp4-stage2-robustness.md`, which is the SP4 sub-project backlog.

## Framework gaps surfaced (SP4 backlog)

See `docs/sp4-stage2-robustness.md` for the full list, prioritized by impact and grounded in specific source-file references. Headline items:

- **Stage 2 refinement loop preserves passing fields** (addresses the cross-attempt regression observed in both runs).
- **Stage 2 prompt renders schema sub-object examples inline** (addresses the post_event_slowing trigger and lag1 modulation_table shape errors).
- **`performance.accuracy` envelope discipline** (resolves the prompt↔schema contradiction that caused both paradigms to persistently fail this slot).
- **Field-name canonicalization layer between LLM output and schema validator** (lets the validator be liberal in what it accepts while the schema stays strict on canonical shape).
- **Held-out Reasoner regression tests** (capture the *current* LLM-stage-2 outputs as fixtures so future framework changes don't silently regress generalizability).

## Artifacts

- Branch: `sp3/heldout-validation` (this branch).
- Reasoner logs: `.reasoner-logs/sp3_flanker_regen.log` (gitignored), `.reasoner-logs/sp3_nback_regen.log` (gitignored).
- Failure logs: `docs/sp3-flanker-failure.md`, `docs/sp3-nback-failure.md`.
- This report: `docs/sp3-heldout-results.md`.
- SP4 proposal: `docs/sp4-stage2-robustness.md`.

No TaskCards, no sessions, no validation reports, no platform adapters were produced — those Plan tasks (3-6, 8-12) were correctly skipped per held-out policy when their respective Reasoner runs failed.

## Status

SP3 deliverable complete. The deliverable is this report + the SP4 backlog doc. The pre-defined success criterion (operational pass on both paradigms; behavioral metrics descriptive) was not met operationally. Per spec interpretation table this is itself a useful finding: the framework's generalizability claim is empirically falsified for both held-out paradigms tested, and the gap is concentrated at a specific named pipeline stage with concrete, grounded improvements proposed.

Tag `sp3-complete` applies to the commit landing this report. The next sub-project (SP4) addresses the framework gaps surfaced here.

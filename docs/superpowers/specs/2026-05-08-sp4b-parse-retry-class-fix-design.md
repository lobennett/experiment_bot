# SP4b — Parse-retry class-fix for fragile Reasoner stages

## Origin

SP4a (`docs/sp4a-results.md`) re-ran the SP3 protocol after Tier 1 fixes. Stage 2 cleared cleanly in both Flanker and n-back. The Flanker re-run then died at `stage3_citations.py:42` with `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` — the LLM's Stage 3 response was either empty or non-parseable.

Investigation revealed this is a **class problem**, not a Stage 3 problem: five Reasoner call sites do `json.loads(_extract_json(resp.text))` with no parse-retry path. Only Stage 2 has the defensive pattern. Held-out paradigms surface the bug because they're more likely to hit LLM noise; the dev paradigms have passed by luck.

| Call site | Has parse-retry? | Status |
|---|---|---|
| `stage1_structural.py:117` | ❌ (has separate validation-retry loop only) | vulnerable |
| `stage2_behavioral.py:207` | ✓ (SP1.5) | model implementation |
| `stage3_citations.py:42` | ❌ | observed-failing in SP4a Flanker |
| `stage5_sensitivity.py:17` | ❌ | vulnerable |
| `stage6_pilot.py:172` | ❌ | vulnerable |
| `norms_extractor.py:100` | ❌ | vulnerable (separate CLI) |

## Goal

Ship a single shared `parse_with_retry` helper that wraps "LLM call → JSON parse → on parse failure, append parser error to user prompt and retry up to N times". Apply it uniformly to Stages 1, 3, 5, 6 (pilot refinement) and the norms_extractor. Re-run the SP4a Flanker held-out test descriptively to provide evidence about whether the class fix resolves the observed failure.

## Success criterion

Two-tier success, mirroring SP4a's framing:

**Internal (CI-checkable, gates SP4b completion):**

- The new `parse_with_retry` helper has full unit-test coverage (success on attempt 1; retry-then-success; budget-exhausted error; empty / non-JSON / markdown-fenced inputs all handled correctly; `stage_name` propagates into errors).
- Each stage-level integration test confirms the call site successfully recovers from a stubbed parse failure on attempt 1.
- The full pre-existing test suite (492 at `sp4a-complete`) still passes.

**External (descriptive, scientific contribution):**

- SP4a's Flanker Reasoner command is re-run.
- The outcome (does Stage 3 now succeed? does the pipeline reach Stage 6? does a TaskCard get produced?) is reported descriptively in `docs/sp4b-results.md`.
- Held-out outcome is the scientific evidence; it does not gate SP4b completion. If the re-run shows the LLM returns non-JSON every time for Flanker (parse-retry loops without progress), that's a separate finding (likely a Stage 3 prompt-design gap or LLM-refusal mode) for SP4c.

## Architecture

One new module + minimal-touch edits to four pipeline files (plus the norms extractor).

### `src/experiment_bot/reasoner/parse_retry.py` (new)

Small, focused module exposing two symbols:

```python
class ParseRetryExceededError(ValueError):
    """Raised when parse_with_retry exhausts its budget. The error
    message includes a per-attempt history (truncated raw response +
    parser error) for diagnostic logs."""

async def parse_with_retry(
    client: LLMClient,
    *,
    system: str,
    user: str,
    stage_name: str,
    max_retries: int = 3,
) -> dict:
    """LLM call → JSON parse → on parse failure, append parser error
    and retry. After max_retries, raise ParseRetryExceededError.

    `stage_name` is a label included in error messages and structured
    log lines. It does not affect control flow."""
```

The retry-prompt body mirrors Stage 2's existing pattern in `stage2_behavioral.py:90-101`:

```text
{user}

## Parse error from previous attempt
Your previous output could not be parsed as JSON: `{error.msg}` at
line {error.lineno}, column {error.colno}. Regenerate the complete
response, ensuring valid JSON syntax (no trailing commas, all
strings closed, no unterminated objects/arrays).
```

`max_retries=3` matches Stage 2's `STAGE2_MAX_REFINEMENTS`. Stage 2 is left untouched in this SP; consolidating it onto the helper is future polish.

### Stage 1 (`stage1_structural.py:115-135`)

The existing function has an outer validation-retry loop. Replace the inline `partial = json.loads(_extract_json(resp.text))` at L117 with `partial = await parse_with_retry(client, system=..., user=..., stage_name="stage1")`. The validation-retry loop stays. Net retry budget worst-case: `max_retries` (validation) × `max_retries` (parse) = 3×3 = 9 LLM calls; trade-off accepted (parse failures are rare, robustness is the win).

### Stages 3, 5, 6 pilot, norms_extractor

Each replaces its two-line `resp = await client.complete(...); x = json.loads(_extract_json(resp.text))` block with one `parse_with_retry` call. Stage-specific business logic that follows (citation merge, sensitivity tagging, pilot refinement splice, norms payload) is unchanged.

### Stage 2 — UNCHANGED

`stage2_behavioral.py` keeps its existing inline parse-retry path. A docstring reference in `parse_retry.py` notes Stage 2 as "the model implementation this helper generalizes" with a TODO for a future consolidation SP if priorities shift.

## Data flow

```
caller invokes parse_with_retry(client, system=, user=, stage_name=)
    │
    ▼
attempt = 1; history = []
    │
    ▼
LLM call (system + current user message)
    │
    ▼
_extract_json(resp.text) → json.loads
    │
    ├── parses OK ──▶ return dict
    │
    └── JSONDecodeError as e
        │
        ▼
    history.append((attempt, e, resp.text[:500]))
        │
        ▼
    attempt == max_retries?
        │
        ├── yes → raise ParseRetryExceededError(stage_name, history)
        │
        └── no →
            user_msg = base_user
                + f"\n\n## Parse error from previous attempt\n
                   Your previous output could not be parsed as JSON: "
                   `{e.msg}` at line {e.lineno}, column {e.colno}. "
                   "Regenerate the complete response, ensuring valid "
                   "JSON syntax (no trailing commas, balanced braces)."
            attempt += 1; loop
```

## Test strategy

Four focused test areas:

### `tests/test_parse_retry.py` (new) — helper unit tests

- `test_success_on_first_attempt` — no retries; LLM returns valid JSON; helper returns parsed dict.
- `test_retry_then_success` — first response is empty; second is valid JSON; helper returns the parsed dict and the second user prompt contains the "Parse error from previous attempt" sentinel.
- `test_budget_exhausted_raises` — all `max_retries` responses non-JSON; helper raises `ParseRetryExceededError` whose message includes `stage_name` and the attempt history.
- `test_empty_string_treated_as_parse_error` — LLM returns `""`; helper handles gracefully (does not crash on truncation in `_extract_json`).
- `test_markdown_fenced_json_parses` — LLM returns ```` ```json\n{...}\n``` ````; helper succeeds.
- `test_stage_name_in_error_message` — helper raises with `stage_name` substring present in the error message.

Uses a stub `LLMClient` (same `_StubClient` pattern from `tests/test_stage2_refinement_locks.py`).

### Stage 1 integration

Either extend `tests/test_stage1_structural.py` or add `tests/test_stage1_parse_retry.py`:

- `test_stage1_parse_retry_does_not_consume_validation_budget` — script: response 1 is non-JSON, response 2 is valid JSON but fails Stage 1 validation, response 3 is valid+passing. Assert Stage 1 reaches success on response 3 and produces the partial; assert validation retry count is exactly 1 (not consumed by the parse-retry on response 1).

### Stage 3 / Stage 5 / Stage 6 pilot / norms_extractor integration

Group into `tests/test_parse_retry_integration.py` (new):

- `test_stage3_recovers_from_empty_first_response` — script: response 1 is `""`, response 2 is valid citations JSON. Assert `run_stage3` produces the merged TaskCard with citations applied. This directly mirrors the SP4a-observed Flanker failure.
- `test_stage5_recovers_from_empty_first_response` — analogous for sensitivity tags.
- `test_stage6_pilot_refinement_recovers_from_empty_first_response` — analogous for pilot refinement step (call into `stage6_pilot`'s refinement helper, not the full pilot loop).
- `test_norms_extractor_recovers_from_empty_first_response` — analogous for the norms-extraction CLI's parse step.

### Held-out re-run (manual, descriptive)

Re-run `experiment-bot-reason "https://deploy.expfactory.org/preview/3/" --label expfactory_flanker --pilot-max-retries 3 -v` on a fresh worktree. Capture the log to `.reasoner-logs/sp4b_flanker_regen.log`. Document the outcome in `docs/sp4b-results.md`:

- Did Stage 3 succeed (with how many parse retries)?
- Did the pipeline progress to Stage 6 pilot? Did pilot succeed?
- Did a TaskCard get produced?
- If yes, the parse-retry class fix resolved the observed Flanker failure.
- If Stage 3 still fails after retries, that's a finding (likely a Stage 3 prompt-content issue triggering consistent LLM refusal/empty-response) for SP4c.

The n-back re-run is **not** included — n-back's SP4a failure was at Stage 6 pilot stimulus detection, not at Stage 3, so re-running it doesn't directly test SP4b's fix. Including it would add wall-clock time without adding signal.

## Deliverables

- Worktree `.worktrees/sp4b` on branch `sp4b/parse-retry-class-fix`, branched off tag `sp4a-complete` (with this spec and the SP4b plan cherry-picked).
- Code changes in: `src/experiment_bot/reasoner/parse_retry.py` (new), `stage1_structural.py`, `stage3_citations.py`, `stage5_sensitivity.py`, `stage6_pilot.py`, `norms_extractor.py`. Stage 2 unchanged.
- Tests added: `tests/test_parse_retry.py`, `tests/test_parse_retry_integration.py`, plus a Stage 1 integration test (in existing test file or new `tests/test_stage1_parse_retry.py`).
- `docs/sp4b-results.md` — descriptive report of the Flanker re-run.
- Tag `sp4b-complete` on the report-landing commit. Push branch + tag to origin.
- `CLAUDE.md` sub-project history updated with SP4b completion.

## Out of scope

- **Stage 2 refactor** to use the new helper. Stage 2's existing inline parse-retry works; consolidating is future polish, not SP4b's job.
- **Tier 2 / Tier 3 backlog items** from `docs/sp4-stage2-robustness.md` (canonicalization layer, two-pass Stage 2 split, schema-as-canonical autogeneration). Each is its own SP cycle.
- **Stage 6 pilot bot-fidelity** (the n-back "0 stimulus matches" SP4a finding). That's a Stage 1 stimulus-detection / runtime-polling concern; distinct from this parse-retry class problem.
- **Investigating why the LLM returned empty/non-JSON for Flanker Stage 3** in SP4a. The class-fix lands regardless of root cause; if the held-out re-run shows the LLM still loops without progress, that's separate SP4c work.
- **Smoke sessions on the n-back TaskCard** produced by SP4a. Separate Reasoner-output validation work.
- **Adding new held-out paradigms** beyond Flanker. SP4b's re-run uses Flanker only.
- **Increasing the default `max_retries` beyond 3.** Matches Stage 2 for consistency; revisit later if observation suggests more is needed.

## Sub-project boundary check

This spec is appropriately scoped to a single implementation plan:

- One concrete deliverable (the helper + five call-site updates + Flanker re-run report).
- One bounded set of code changes (one new module + edits in five existing modules).
- One pre-defined success criterion (internal CI gate + descriptive Flanker outcome).
- A clear hand-off rule for findings (if Flanker still fails after parse-retry, that's SP4c).

If the held-out re-run reveals that the LLM consistently refuses Stage 3 for Flanker (parse-retry loops without progress), the resulting SP4c would be its own brainstorm/spec/plan cycle focused on Stage 3 prompt design or response-guard logic.

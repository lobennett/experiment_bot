# SP8 — Stage 1 prompt: multi-source response_key_js extraction

## Origin

SP7 (`docs/sp7-results.md`) ran a 4-way keypress agreement audit across 5 Flanker sessions (600 trials) and named two compounding layers responsible for per-trial response_key misalignment:

- **Layer (a):** bot's `response_key_js` evaluation is ~50% match to platform's expected (essentially random in a 2-key paradigm).
- **Layer (d):** platform records from a non-keydown source (page_received vs platform_recorded only 44%).

The original SP7-recommended Option B (runtime cross-check against `window.correctResponse`) was scrapped during SP8 brainstorm as paradigm-overfitting — `window.correctResponse` is a jsPsych-platform convention, not universal. The generalizable fix is at the Stage 1 prompt level: teach Stage 1 to emit a `response_key_js` shaped as a multi-source fallback chain that prefers the page's authoritative runtime variable when available and falls back to computed mappings only when needed.

This is **option B** from the SP8 brainstorm Q1: "Multi-source extraction prompt" — Stage 1 emits a JS expression that tries the runtime-variable read first, then a computed fallback.

n-back's existing TaskCard already shows this pattern (its `response_key_js` is `(typeof window.correctResponse!=='undefined'?window.correctResponse:null)`). Flanker's does not. SP8 brings the Flanker-style (and other dev-paradigm) extraction up to the n-back-style standard.

## Goal

Add a `## Multi-source response_key_js extraction` section to Stage 1's system prompt with three paradigm-agnostic example patterns + one anti-example. Re-generate TaskCards for all six paradigms and re-run audits to measure the per-trial alignment improvement across paradigm classes and platform variants.

The constraint per saved user feedback (`~/.claude/projects/.../memory/feedback_avoid_paradigm_overfitting.md`): no Flanker-specific selectors, condition labels, or platform-naming in the prompt examples. Pattern names are paradigm-agnostic ("runtime-variable", "dom-plus-state", "static-keymap"). The examples use generic placeholders (`<stimulus-img-selector>` etc.).

## Success criterion

Two-tier success:

**Internal (CI-checkable, gates SP8 completion):** unit tests covering:

1. The Stage 1 prompt file contains a `## Multi-source response_key_js extraction` (or similar canonical) header.
2. At least one fenced block tagged `response-key-example: runtime-variable` exists; references `window.correctResponse` and a `typeof` guard.
3. At least one fenced block tagged `response-key-example: dom-plus-state` exists; references `window.correctResponse` as the first check before any DOM-derived computation.
4. At least one fenced block tagged `response-key-anti-example` exists showing what NOT to emit (static-only without runtime-variable fallback).
5. The prompt text explains the static-keymap case (no JS needed; literal key in `task_specific.key_map`).
6. Each example JS block has balanced parens and braces (basic syntax-sanity check; not a full JS parser).
7. The full pre-existing test suite (524 at `sp7-complete`) still passes.

**External (descriptive, scientific evidence):** Re-generate TaskCards for all six paradigms, re-run 3 smoke sessions per paradigm, run `scripts/keypress_audit.py` per paradigm. Report per-paradigm `bot_intended == platform_expected` and `bot_pressed == platform_recorded` numbers compared to SP7's Flanker baseline (49.8% / 47.7%). Expected: paradigms where Stage 1 successfully emits the multi-source pattern AND the page exposes a runtime correct-key variable should land near 90%+ on `bot_intended == platform_expected`. Paradigms whose pages don't expose such a variable will still depend on the DOM-derived fallback — whether that fallback is correct depends on Stage 1's extraction quality, which the prompt improvement helps but doesn't guarantee.

Held-out outcome is descriptive; it does not gate SP8 completion. If a particular paradigm's regenerated TaskCard still emits a Pattern-A-noncompliant `response_key_js`, that's a finding (Stage 1 didn't follow the new examples cleanly) for the next SP, not a re-tuning of the SP8 prompt.

## Architecture

Three touch-points.

### Stage 1 prompt addendum

`src/experiment_bot/prompts/system.md` (confirmed during spec authoring; loaded by Stage 1 at `stage1_structural.py:110` via `PROMPTS_DIR = Path(__file__).parent.parent / "prompts"`). Append a new section.

The exact wording can vary; the structural requirements are:

1. **Section header**: `## Multi-source response_key_js extraction` (or equivalent canonical title the tests check for).
2. **Pattern A — runtime variable**: ONE example block tagged `response-key-example: runtime-variable`. Demonstrates `(typeof window.correctResponse !== 'undefined' ? window.correctResponse : null)` exactly or near-exactly.
3. **Pattern B — dom-plus-state**: ONE example block tagged `response-key-example: dom-plus-state`. Demonstrates the fallback chain: runtime-variable check FIRST, then DOM-derived computation. Uses generic placeholders (`<stimulus-img-selector>` etc.) — NO paradigm-specific selectors.
4. **Pattern C — static keymap**: TEXT explanation (no JS example needed). The prompt says: when the source code defines a fixed key-per-condition mapping with no runtime variability, leave `response_key_js` empty for that stimulus and use `task_specific.key_map` with the literal key string.
5. **Anti-example**: ONE block tagged `response-key-anti-example`. Shows DOM-only or computed-only JS without the runtime-variable check. Calls out why this is fragile.
6. **Prose framing**: a 2-3 sentence intro emphasizing that the page's authoritative runtime variable (when defined) is the highest-fidelity source and should be checked FIRST.

The exact prose is left to the implementer (within these structural constraints). The invariant test (below) enforces presence of the structural pieces but not the exact wording.

### Invariant test

`tests/test_stage1_response_key_js_prompt.py` (new). Imports the Stage 1 prompt file's contents and asserts structural properties:

```python
import re
from pathlib import Path

PROMPT_PATH = Path("src/experiment_bot/prompts/system.md")

_BLOCK_RE = re.compile(
    r"^```(?:javascript|js)\s+(response-key-example|response-key-anti-example):\s*([^\n]+?)\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)

def test_prompt_contains_multi_source_section():
    text = PROMPT_PATH.read_text()
    assert "Multi-source response_key_js extraction" in text

def test_prompt_has_runtime_variable_example():
    text = PROMPT_PATH.read_text()
    blocks = [(kind, label, body) for kind, label, body in _BLOCK_RE.findall(text)]
    examples = [b for b in blocks if b[0] == "response-key-example" and "runtime-variable" in b[1]]
    assert examples, "Missing response-key-example: runtime-variable block"
    body = examples[0][2]
    assert "window.correctResponse" in body
    assert "typeof" in body

def test_prompt_has_dom_plus_state_example():
    text = PROMPT_PATH.read_text()
    blocks = [(kind, label, body) for kind, label, body in _BLOCK_RE.findall(text)]
    examples = [b for b in blocks if b[0] == "response-key-example" and "dom-plus-state" in b[1]]
    assert examples, "Missing response-key-example: dom-plus-state block"
    body = examples[0][2]
    # Runtime-variable check must appear BEFORE any document.querySelector call —
    # the fallback chain rule.
    rv_pos = body.find("window.correctResponse")
    dq_pos = body.find("document.querySelector")
    assert rv_pos != -1, "dom-plus-state example missing window.correctResponse"
    assert dq_pos == -1 or rv_pos < dq_pos, (
        "dom-plus-state example must check window.correctResponse "
        "BEFORE DOM-derived computation (fallback chain rule)"
    )

def test_prompt_has_static_keymap_explanation():
    text = PROMPT_PATH.read_text()
    # Static keymap is described in prose; no JS example. The prompt must
    # mention task_specific.key_map and explain when JS is unnecessary.
    assert "task_specific.key_map" in text or "task_specific" in text
    # Heuristic: the words "static" or "literal" should appear near "key_map"
    # in the same prose section. Conservative regex over the new section.

def test_prompt_has_anti_example():
    text = PROMPT_PATH.read_text()
    blocks = [(kind, label, body) for kind, label, body in _BLOCK_RE.findall(text)]
    anti = [b for b in blocks if b[0] == "response-key-anti-example"]
    assert anti, "Missing response-key-anti-example block"

def test_example_js_basic_syntax_sanity():
    text = PROMPT_PATH.read_text()
    blocks = [(kind, label, body) for kind, label, body in _BLOCK_RE.findall(text)]
    for kind, label, body in blocks:
        assert body.count("(") == body.count(")"), (
            f"Unbalanced parens in {kind}: {label}"
        )
        assert body.count("{") == body.count("}"), (
            f"Unbalanced braces in {kind}: {label}"
        )
```

The test file references the Stage 1 prompt path; if the actual path differs, implementer adjusts. No paradigm names appear in the test file.

### Held-out re-generation + cross-paradigm re-run

For each of the six TaskCards (Flanker, n-back, expfactory_stop_signal, stopit_stop_signal, expfactory_stroop, cognitionrun_stroop):

1. Delete existing `taskcards/<paradigm>/` directory.
2. Run `experiment-bot-reason <URL> --label <paradigm> --pilot-max-retries 3`. (~5-25 min per paradigm.)
3. Inspect the regenerated TaskCard's `response_key_js` for each stimulus. Verify it follows Pattern A (runtime-variable only) or Pattern B (runtime-variable first, then computed fallback) or Pattern C (static keymap; no response_key_js needed for this stim).
4. Run 3 smoke sessions with seeds 8001-8003 (or 8101-8103 for n-back, 8201-8203 for stop_signal_rdoc, etc. — pick a seed-prefix scheme).
5. Run `scripts/keypress_audit.py --label <paradigm>` to compute the 4-way agreement table.

Paradigm-agnostic execution: the same Reasoner command + same smoke command + same audit script for every paradigm. No paradigm-specific code branches.

Wall time estimate: 6 paradigms × (15 min regen + 3×10 min smoke + 1 min audit) ≈ 4 hours sequential. With parallelism (regens in parallel, then sessions in parallel per paradigm), ~2 hours.

## Data flow

```
Stage 1 invocation (Reasoner time, OFFLINE):
    bundle (source code, page HTML) → Stage 1 LLM call
    system prompt NOW INCLUDES multi-source examples + anti-example
    │
    ▼
    LLM produces partial with response_key_js per stimulus
    │
    ▼ (when prompt examples followed correctly)
    Each response_key_js is one of:
      Pattern A: (typeof window.correctResponse !== 'undefined' ? window.correctResponse : null)
      Pattern B: (() => { if (typeof window.correctResponse !== 'undefined') return window.correctResponse; ... })()
      Pattern C: response_key_js empty; key_map has literal key string for the condition
    │
    ▼
    Stage 2-6 unchanged; TaskCard written
```

```
Trial-time (Executor, UNCHANGED from SP6/SP7):
    Bot detects stimulus → evaluates response_key_js
    │
    ▼
    Pattern A path: bot reads window.correctResponse → matches platform's expected → end-to-end alignment
    Pattern B path: window.correctResponse defined? → read it. Undefined? → fall back to computed.
    Pattern C path: response_key_js is empty; bot uses key_map[condition] directly.
    │
    ▼
    bot presses resolved_key; SP6 fallback handles trial-end; SP7 instrumentation logs everything
```

Nothing changes at runtime. The bot's `_resolve_response_key` logic, `_pick_wrong_key`, keypress instrumentation, and all downstream metrics are untouched.

## Test strategy

### `tests/test_stage1_response_key_js_prompt.py` (new) — 6 unit tests

See the Architecture section above. Tests verify the prompt's structural properties without prescribing exact wording.

### Cross-paradigm regression check (manual after Tasks 1-2 land)

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 530 passed, 3 skipped (524 + 6 new). No pre-existing tests should break from a prompt edit alone — but verify.

### Held-out re-runs (manual, descriptive)

For each of the six paradigms: regen + 3 sessions + audit. Per-paradigm and aggregate numbers in `docs/sp8-results.md`. Compare to SP7 Flanker baseline (49.8% bot_intended == platform_expected).

The cross-paradigm shape of the data is the scientific contribution: if SP8 improves alignment on Flanker AND doesn't regress n-back AND improves at least one stop_signal AND improves at least one stroop, the generalization claim is well-supported.

If some paradigms improve and others don't, the report names which paradigm classes the multi-source pattern works for and which it doesn't. That's still valuable evidence — it tells us where the fix's reach ends.

## Deliverables

- Worktree `.worktrees/sp8` on branch `sp8/stage1-response-key-prompt`, branched off tag `sp7-complete`.
- Spec + plan cherry-picked from `sp7/keypress-diagnostic`.
- Code changes in:
  - `src/experiment_bot/prompts/system.md` (the Stage 1 system prompt).
  - `tests/test_stage1_response_key_js_prompt.py` (new).
- 6 regenerated TaskCards under `taskcards/<paradigm>/` (committed alongside their pilot artifacts).
- 18 smoke sessions in `output/<task-name>/<timestamp>/` (gitignored).
- 6 audit outputs captured in `.reasoner-logs/sp8_audit_<paradigm>.txt` (gitignored).
- `docs/sp8-results.md` — per-paradigm + aggregate comparison vs SP7 baseline.
- Tag `sp8-complete`. Push branch + tag.
- `CLAUDE.md` sub-project history updated.

## Out of scope

- **Runtime LLM calls in the executor.** SP9 will address (deferred architectural cleanup, including timing-partition considerations the user raised).
- **Stage 2 schema validation gate for `response_key_js` shape** (option C from the earlier scope discussion). Could complement SP8's prompt improvement; deferred to keep SP8 small.
- **Other Stage 1 prompt improvements** (stimulus detection, navigation extraction, etc.). Each has its own potential SP.
- **The five other SP9-candidate fragility sources** (parallel retry mechanisms, `oneOf` envelopes, per-paradigm adapters, stage count, defensive fallback layers).
- **Cleanups from prior SPs**: `_extract_json` ownership, Tier 2/3 SP4 backlog. Each their own SP.
- **Increasing sessions-per-paradigm beyond 3.** User scoped this explicitly: "I don't need so many versions of each. I can just run a few and get a sense."

## Sub-project boundary check

This spec is appropriately scoped to a single implementation plan:

- One concrete deliverable (Stage 1 prompt addendum + invariant test + cross-paradigm audit report).
- One bounded set of code changes (one prompt file, one test file).
- One pre-defined success criterion (internal CI gate + descriptive cross-paradigm audit).
- A clear hand-off rule for findings: if some paradigms don't improve, the report names where the fix's reach ends; the next SP can decide whether to extend the fix or scope something different.

The cross-paradigm scope (6 paradigms, 3 sessions each) is the largest empirical sweep in SP-history, but the CODE scope is small — just a prompt edit and a test file. The wall-clock cost is real but bounded by the wall-clock of regens + sessions; no code complexity grows with the paradigm count.

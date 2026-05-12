"""Invariant tests for the Stage 1 system prompt's
'Multi-source response_key_js extraction' section (SP8).

The section instructs Stage 1 to emit response_key_js as a multi-
source fallback chain: try the page's authoritative runtime variable
(window.correctResponse) first; fall back to computed DOM-derived
mappings only when the runtime variable is undefined.

Tests verify structural presence and basic JS-syntax sanity without
prescribing exact wording. The actual quality of Stage 1's output
across paradigms is verified empirically by the cross-paradigm
re-run in Task 6 of SP8's plan.

No paradigm names appear in this test file (per user-feedback
constraint memorized at
~/.claude/projects/.../memory/feedback_avoid_paradigm_overfitting.md).
"""
from __future__ import annotations
import re
from pathlib import Path


PROMPT_PATH = Path("src/experiment_bot/prompts/system.md")

# Fenced JS blocks tagged with response-key example/anti-example labels:
#   ```javascript response-key-example: runtime-variable
#   ...JS...
#   ```
_BLOCK_RE = re.compile(
    r"^```(?:javascript|js)\s+(response-key-example|response-key-anti-example):\s*([^\n]+?)\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def _blocks() -> list[tuple[str, str, str]]:
    """Return [(kind, label, body), ...] for all fenced blocks in the
    Stage 1 system prompt."""
    text = PROMPT_PATH.read_text()
    return [(m.group(1), m.group(2), m.group(3)) for m in _BLOCK_RE.finditer(text)]


def test_prompt_contains_multi_source_section():
    """The new section's canonical header must be present."""
    text = PROMPT_PATH.read_text()
    assert "Multi-source response_key_js extraction" in text, (
        "Stage 1 prompt missing the SP8 multi-source section header"
    )


def test_prompt_has_runtime_variable_example():
    """At least one runtime-variable example block exists, referencing
    window.correctResponse and a typeof guard."""
    blocks = _blocks()
    candidates = [
        body for kind, label, body in blocks
        if kind == "response-key-example" and "runtime-variable" in label
    ]
    assert candidates, "Missing response-key-example: runtime-variable block"
    body = candidates[0]
    assert "window.correctResponse" in body
    assert "typeof" in body


def test_prompt_has_dom_plus_state_example():
    """At least one dom-plus-state example block exists, and the
    window.correctResponse check appears BEFORE any DOM-derived
    computation (the fallback-chain ordering rule)."""
    blocks = _blocks()
    candidates = [
        body for kind, label, body in blocks
        if kind == "response-key-example" and "dom-plus-state" in label
    ]
    assert candidates, "Missing response-key-example: dom-plus-state block"
    body = candidates[0]
    rv_pos = body.find("window.correctResponse")
    dq_pos = body.find("document.querySelector")
    assert rv_pos != -1, "dom-plus-state example missing window.correctResponse"
    if dq_pos != -1:
        assert rv_pos < dq_pos, (
            "dom-plus-state example must check window.correctResponse BEFORE "
            "any DOM-derived computation (fallback-chain rule)"
        )


def test_prompt_has_static_keymap_explanation():
    """The static-keymap case is described in prose (no JS example).
    The prompt must mention task_specific.key_map and explain when JS
    is unnecessary."""
    text = PROMPT_PATH.read_text()
    assert "task_specific.key_map" in text or "task_specific" in text, (
        "Stage 1 prompt missing reference to task_specific.key_map"
    )


def test_prompt_has_anti_example():
    """At least one anti-example block exists showing the fragile
    static-only-without-fallback pattern that SP7 quantified."""
    blocks = _blocks()
    anti = [body for kind, label, body in blocks if kind == "response-key-anti-example"]
    assert anti, "Missing response-key-anti-example block"


def test_example_js_basic_syntax_sanity():
    """Each example/anti-example block must have balanced parens and
    braces. Catches typos; not a full JS parser."""
    for kind, label, body in _blocks():
        parens = body.count("(") - body.count(")")
        braces = body.count("{") - body.count("}")
        assert parens == 0, f"Unbalanced parens in {kind}: {label}: {parens}"
        assert braces == 0, f"Unbalanced braces in {kind}: {label}: {braces}"

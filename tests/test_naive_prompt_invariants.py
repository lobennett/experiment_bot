"""Neutrality guardrails: the naive generation prompt must contain no
expert behavioral scaffolding. These invariants ARE the experiment's
scientific core — a leak here invalidates the naive arm.

I4: the scans below also cover every OTHER piece of text that gets
assembled into the live prompt outside the template file itself —
gen_cli._INTERRUPT_NOTE (spliced in for interrupt-capable tasks),
gen_cli._RETRY_PREFIX (spliced in on a gate-failure retry), and
gen_cli._EMPTY_KEY_MAP_NOTE (spliced in for {KEY_MAP} when a card's static
key_map is empty, e.g. all-dynamic key resolution). A banned term or numeric
prior hiding in one of these would leak into the live prompt exactly as if
it were in the template, so they must pass the same invariants.
"""
from pathlib import Path

from experiment_bot.behavior.gen_cli import (
    _EMPTY_KEY_MAP_NOTE, _INTERRUPT_NOTE, _RETRY_PREFIX, _RETRY_SUFFIX,
)
from experiment_bot.behavior.source_slim import (
    BLOB_MARKER, EXCLUDED_LINE, EXCLUDED_SECTION_HEADER,
)

TEMPLATE = Path("src/experiment_bot/behavior/prompts/naive_gen.md")

BANNED_TERMS = [
    # mechanism / registry vocabulary
    "autocorrelation", "fatigue_drift", "condition_repetition", "pink_noise",
    "lag1_pair_modulation", "post_event_slowing", "practice_effect",
    "vigilance_decrement",
    # distribution families
    "ex_gaussian", "ex-gaussian", "lognormal", "shifted_wald", "shifted wald",
    # phenomenon names
    "post-error slowing", "post_error", "congruency sequence", "gratton",
    "ssrt", "stop-signal reaction time", "conflict adaptation",
    "sequential effect",
]

# (name, text) — every piece of static text that can end up in a live
# generation prompt. TEMPLATE is read fresh per-test (it's a file); the
# gen_cli constants are plain strings imported above.
ASSEMBLED_PROMPT_SOURCES = [
    ("naive_gen.md template", TEMPLATE.read_text()),
    ("gen_cli._INTERRUPT_NOTE", _INTERRUPT_NOTE),
    ("gen_cli._RETRY_PREFIX", _RETRY_PREFIX),
    ("gen_cli._EMPTY_KEY_MAP_NOTE", _EMPTY_KEY_MAP_NOTE),
    ("gen_cli._RETRY_SUFFIX", _RETRY_SUFFIX),
    # The mechanical slimmer's markers are spliced into the live
    # prompt's {PAGE_SOURCE}, so they face the same neutrality scans.
    ("source_slim.BLOB_MARKER", BLOB_MARKER),
    ("source_slim.EXCLUDED_SECTION_HEADER", EXCLUDED_SECTION_HEADER),
    ("source_slim.EXCLUDED_LINE", EXCLUDED_LINE),
]


def test_template_exists_with_placeholders():
    text = TEMPLATE.read_text()
    for ph in ("{PAGE_SOURCE}", "{CONDITIONS}", "{KEY_MAP}", "{INTERRUPT_NOTE}"):
        assert ph in text


def test_template_documents_click_contract_mechanically():
    """The click wire form is documented in the contract section
    (inside the protocol code block, like the rest of the ctx fields)."""
    text = TEMPLATE.read_text()
    assert "response_elements" in text
    assert '("click", index, rt_ms)' in text


def test_template_documents_sequence_contract_mechanically():
    """Sequence-response capability: the list-return wire form and
    ctx.correct_sequence are documented in the contract section, mechanically
    (like the click contract)."""
    text = TEMPLATE.read_text()
    assert "correct_sequence" in text
    assert "list of actions" in text
    assert '[("click", i, rt_ms), ("click", j, rt_ms), ...]' in text


def test_no_banned_behavioral_terms():
    for name, text in ASSEMBLED_PROMPT_SOURCES:
        lowered = text.lower()
        for term in BANNED_TERMS:
            assert term not in lowered, f"banned term in {name}: {term!r}"


# Frozen vocabulary of the deleted expert-arm effect registry: the naive
# prompt must never name the old mechanism library either.
_LEGACY_MECHANISM_NAMES = (
    "autocorrelation", "fatigue_drift", "condition_repetition",
    "lag1_pair_modulation", "post_event_slowing", "linear_drift",
    "practice_effect", "vigilance_decrement", "pink_noise",
)


def test_no_registry_mechanism_names():
    for name, text in ASSEMBLED_PROMPT_SOURCES:
        lowered = text.lower()
        for mech_name in _LEGACY_MECHANISM_NAMES:
            assert mech_name.lower() not in lowered, (
                f"mechanism name {mech_name!r} leaked into {name}")


def test_no_numeric_behavioral_priors():
    """Static prompt text may contain numbers ONLY in the protocol
    constraints (rt bounds, seed) — never as ms/accuracy suggestions."""
    import re
    for name, text in ASSEMBLED_PROMPT_SOURCES:
        # Strip fenced code blocks (the protocol signatures may carry types).
        stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(ms|milliseconds|%)", stripped.lower()):
            raise AssertionError(
                f"numeric behavioral prior in {name}: {m.group(0)!r}")

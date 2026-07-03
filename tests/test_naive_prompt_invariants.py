"""SP21 neutrality guardrails: the naive generation prompt must contain no
expert behavioral scaffolding. These invariants ARE the experiment's
scientific core — a leak here invalidates the naive arm."""
from pathlib import Path

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


def test_template_exists_with_placeholders():
    text = TEMPLATE.read_text()
    for ph in ("{PAGE_SOURCE}", "{CONDITIONS}", "{KEY_MAP}", "{INTERRUPT_NOTE}"):
        assert ph in text


def test_no_banned_behavioral_terms():
    text = TEMPLATE.read_text().lower()
    for term in BANNED_TERMS:
        assert term not in text, f"banned term in naive prompt: {term!r}"


def test_no_registry_mechanism_names():
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    text = TEMPLATE.read_text().lower()
    for name in EFFECT_REGISTRY:
        assert name.lower() not in text


def test_no_numeric_behavioral_priors():
    """The template's static text may contain numbers ONLY in the protocol
    constraints (rt bounds, seed) — never as ms/accuracy suggestions."""
    import re
    text = TEMPLATE.read_text()
    # Strip fenced code blocks (the protocol signatures may carry types).
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(ms|milliseconds|%)", text.lower()):
        raise AssertionError(f"numeric behavioral prior in template: {m.group(0)!r}")

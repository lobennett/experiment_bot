"""Invariants for prompts/system.md (review de-anchoring).

CLAUDE.md guardrail: prompts must not carry numerical priors from the
cognitive-control literature or paradigm-named worked examples; numbers
must be bot-mechanic values or bracketed placeholders. These negative
assertions pin the de-anchored state. The registry-coverage check keeps
the static temporal-effects section from going stale again (an earlier
revision documented the deprecated pink_noise `hurst` field and omitted
two registered mechanisms entirely).
"""
from pathlib import Path

PROMPT = Path("src/experiment_bot/prompts/system.md").read_text()


def test_no_literature_citations_as_numeric_anchors():
    # Whelan (2008) justified the rt_floor default in an earlier revision.
    assert "Whelan" not in PROMPT


def test_no_paradigm_named_timing_examples():
    # An earlier revision of the cdp_dwell_ms knob carried worked examples naming
    # Stroop/Flanker/n-back/stop-signal with concrete window values.
    for anchor in ("Stroop/Flanker with 2000", "n-back with 1500",
                   "stop-signal with 250"):
        assert anchor not in PROMPT


def test_no_paradigm_class_accuracy_priors():
    # An earlier revision of the clip-range guidance carried numeric per-class priors.
    for anchor in ("[0.50, 0.85]", "[0.70, 0.85]", "75%-correct"):
        assert anchor not in PROMPT


def test_sequence_response_section_present_and_mechanical():
    """Sequence-response capability: Stage 1 is told to expose the trial's
    target order via correct_sequence_js, and the instruction is mechanical
    (no phenomenon names, no numeric priors)."""
    assert "correct_sequence_js" in PROMPT
    # No paradigm/phenomenon vocabulary leaked into the new guidance.
    lowered = PROMPT.lower()
    for banned in ("corsi", "digit span", "working memory", "serial recall",
                   "span task"):
        assert banned not in lowered






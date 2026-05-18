"""SP10: Stage 1 prompt advises emitting recommended_driver.

Under SP10, the Reasoner no longer extracts platform-specific JS
(response_key_js, navigation.phases, phase_detection, attention_check,
advance_behavior, data_capture) — the platform driver handles those at
runtime. Stage 1 instead emits a `recommended_driver` hint plus the
paradigm-agnostic literature fields.

These tests are paradigm-agnostic (per the user-feedback constraint
memorized in
~/.claude/projects/.../memory/feedback_avoid_paradigm_overfitting.md).
"""
from __future__ import annotations
from pathlib import Path


def test_stage1_prompt_includes_recommended_driver_section():
    prompt = (Path(__file__).parent.parent
              / "src/experiment_bot/prompts/system.md").read_text()
    assert "recommended_driver" in prompt
    assert "JsPsychDriver" in prompt


def test_stage1_validator_requires_recommended_driver():
    from experiment_bot.reasoner.validate import (
        Stage1ValidationError, validate_stage1_output,
    )
    import pytest
    minimal_partial = {
        "task": {"name": "stroop", "paradigm_classes": ["conflict"]},
        "stimuli": [{"id": "s1", "condition": "congruent"}],
        "performance": {"accuracy": {"default": 0.9}},
        # MISSING recommended_driver
    }
    with pytest.raises(Stage1ValidationError):
        validate_stage1_output(minimal_partial)

    # With recommended_driver: passes
    minimal_partial["recommended_driver"] = "JsPsychDriver"
    validate_stage1_output(minimal_partial)


def test_stage1_validator_rejects_unknown_driver_name():
    from experiment_bot.reasoner.validate import (
        Stage1ValidationError, validate_stage1_output,
    )
    import pytest
    p = {
        "task": {"name": "stroop", "paradigm_classes": ["conflict"]},
        "stimuli": [{"id": "s1", "condition": "congruent"}],
        "performance": {"accuracy": {"default": 0.9}},
        "recommended_driver": "MadeUpDriver",
    }
    with pytest.raises(Stage1ValidationError):
        validate_stage1_output(p)

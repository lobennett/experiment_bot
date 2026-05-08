"""Tests for the slot-locked Stage 2 refinement loop. Verify the slot
extractor maps failing error paths to the right level of granularity,
and the refinement merge logic preserves validated slots."""
from __future__ import annotations
import json
from pathlib import Path

import pytest


def test_extract_failing_slots_temporal_effects():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("temporal_effects.post_event_slowing.value.triggers.0", "msg"),
        ("temporal_effects.lag1_pair_modulation.value.modulation_table.3", "msg"),
        ("temporal_effects.lag1_pair_modulation.value.modulation_table.5", "msg"),  # dup slot
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "temporal_effects.lag1_pair_modulation",
        "temporal_effects.post_event_slowing",
    ]


def test_extract_failing_slots_performance():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("performance.accuracy.incongruent", "msg"),
        ("performance.accuracy.congruent", "msg"),
        ("performance.omission_rate.go", "msg"),
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "performance.accuracy",
        "performance.omission_rate",
    ]


def test_extract_failing_slots_task_specific():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [("task_specific.key_map.rationale", "too long")]
    slots = _extract_failing_slots(errors)
    assert slots == ["task_specific.key_map"]


def test_extract_failing_slots_between_subject_jitter():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [("between_subject_jitter.value.rt_mean_sd_ms", "negative")]
    slots = _extract_failing_slots(errors)
    assert slots == ["between_subject_jitter"]


def test_extract_failing_slots_response_distributions():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("response_distributions.go.value.mu", "negative"),
        ("response_distributions.stop.distribution", "unknown"),
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "response_distributions.go",
        "response_distributions.stop",
    ]


def test_extract_failing_slots_mixed_dedupe_and_sort():
    """Multiple errors at different granularities — final list is sorted unique."""
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("temporal_effects.post_event_slowing.value.triggers.0", "a"),
        ("performance.accuracy.incongruent", "b"),
        ("temporal_effects.post_event_slowing.value.triggers.1", "c"),
        ("performance.accuracy.congruent", "d"),
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "performance.accuracy",
        "temporal_effects.post_event_slowing",
    ]


def test_flanker_fixture_yields_three_slots():
    """End-to-end: feed the captured Flanker fixture's errors through
    the helper; expect three slots (lag1, post_event_slowing, performance.accuracy)."""
    from experiment_bot.reasoner.validate import (
        validate_stage2_schema, Stage2SchemaError,
    )
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots

    partial = json.loads(Path("tests/fixtures/stage2/sp3_flanker_attempt3.json").read_text())
    with pytest.raises(Stage2SchemaError) as ei:
        validate_stage2_schema(partial)
    slots = _extract_failing_slots(ei.value.errors)
    assert slots == [
        "performance.accuracy",
        "temporal_effects.lag1_pair_modulation",
        "temporal_effects.post_event_slowing",
    ]


def test_nback_fixture_yields_three_slots():
    """End-to-end: n-back fixture errors → slot list."""
    from experiment_bot.reasoner.validate import (
        validate_stage2_schema, Stage2SchemaError,
    )
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots

    partial = json.loads(Path("tests/fixtures/stage2/sp3_nback_attempt3.json").read_text())
    with pytest.raises(Stage2SchemaError) as ei:
        validate_stage2_schema(partial)
    slots = _extract_failing_slots(ei.value.errors)
    # The n-back fixture surfaces three failing slots under SP4a's schema:
    # performance.accuracy (mismatch field uses `target` instead of `value`),
    # task_specific.key_map (rationale too long), and temporal_effects.post_event_slowing.
    assert slots == [
        "performance.accuracy",
        "task_specific.key_map",
        "temporal_effects.post_event_slowing",
    ]


def test_render_slot_refinement_prompt_includes_failing_slots():
    from experiment_bot.reasoner.stage2_behavioral import _render_slot_refinement_prompt
    partial = {
        "task": {"name": "x"},
        "response_distributions": {"go": {"distribution": "ex_gaussian", "value": {"mu": 500, "sigma": 50, "tau": 100}}},
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.9},
        "temporal_effects": {"post_event_slowing": {"value": {"enabled": True, "triggers": ["error"]}}},
        "between_subject_jitter": {"value": {}},
    }
    failing_slots = ["temporal_effects.post_event_slowing"]
    errors = [("temporal_effects.post_event_slowing.value.triggers.0", "'error' is not of type 'object'")]
    prompt = _render_slot_refinement_prompt(partial, failing_slots, errors)

    # Sanity checks: the rendered prompt should mention failing slots and the error.
    assert "temporal_effects.post_event_slowing" in prompt
    assert "'error' is not of type 'object'" in prompt
    # Should reference previously-validated context (a marker like "do NOT modify"):
    assert "do NOT modify" in prompt or "do not modify" in prompt.lower()


def test_render_slot_refinement_prompt_locks_validated_slots():
    """Validated slots appear in the prompt as locked context;
    failing slots appear as targets for regeneration."""
    from experiment_bot.reasoner.stage2_behavioral import _render_slot_refinement_prompt
    partial = {
        "response_distributions": {"go": {"distribution": "ex_gaussian", "value": {"mu": 500, "sigma": 50, "tau": 100}}},
        "performance": {"accuracy": {"go": 0.95}},
        "temporal_effects": {"post_event_slowing": {"value": {"enabled": True, "triggers": ["error"]}}},
    }
    failing_slots = ["temporal_effects.post_event_slowing"]
    prompt = _render_slot_refinement_prompt(partial, failing_slots, [])

    # The validated content must appear in the locked-context section.
    assert "response_distributions" in prompt
    assert "performance" in prompt


class _StubClient:
    """Returns scripted text responses; tracks user prompts received."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts_received: list[str] = []

    async def complete(self, system, user, output_format=None):
        from types import SimpleNamespace
        self.prompts_received.append(user)
        if not self._responses:
            raise AssertionError("StubClient: out of scripted responses")
        return SimpleNamespace(text=self._responses.pop(0))


@pytest.mark.asyncio
async def test_stage2_slot_locked_refinement_converges():
    """Initial response has a failing post_event_slowing trigger;
    refinement response fixes only that slot. The merged partial
    validates."""
    import json
    from experiment_bot.reasoner.stage2_behavioral import run_stage2

    initial = {
        "response_distributions": {
            "go": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 50, "tau": 100},
                "rationale": "norms",
            }
        },
        "performance_omission_rate": {"go": 0.02},
        "temporal_effects": {
            "post_event_slowing": {
                "value": {"enabled": True, "triggers": ["error"]},  # invalid: bare string
                "rationale": "PES",
            }
        },
        "between_subject_jitter": {"value": {}},
    }
    refinement = {
        "temporal_effects": {
            "post_event_slowing": {
                "value": {
                    "enabled": True,
                    "triggers": [{"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}],
                },
                "rationale": "PES",
            }
        }
    }
    client = _StubClient([json.dumps(initial), json.dumps(refinement)])

    stage1_partial = {
        "task": {"name": "test", "paradigm_classes": ["conflict"]},
        "stimuli": [],
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.9},
    }
    result, step = await run_stage2(client, stage1_partial)

    # Validation should have passed on attempt 2.
    assert result["temporal_effects"]["post_event_slowing"]["value"]["triggers"][0]["event"] == "error"
    # Refinement prompt should mention the locked context (e.g.,
    # response_distributions present in second prompt).
    assert "response_distributions" in client.prompts_received[1]
    assert "do NOT modify" in client.prompts_received[1]


@pytest.mark.asyncio
async def test_stage2_slot_locked_refinement_does_not_reprompt_passing_slots():
    """If a slot validates on attempt 1, attempt 2's refinement prompt
    should not list that slot as a failing slot."""
    import json
    from experiment_bot.reasoner.stage2_behavioral import run_stage2

    # Initial: post_event_slowing is wrong; performance.accuracy is FINE.
    initial = {
        "response_distributions": {
            "go": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 50, "tau": 100},
                "rationale": "norms",
            }
        },
        "performance_omission_rate": {"go": 0.02},
        "temporal_effects": {
            "post_event_slowing": {
                "value": {"enabled": True, "triggers": ["error"]},
                "rationale": "PES",
            }
        },
        "between_subject_jitter": {"value": {}},
    }
    refinement = {
        "temporal_effects": {
            "post_event_slowing": {
                "value": {
                    "enabled": True,
                    "triggers": [{"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}],
                },
                "rationale": "PES",
            }
        }
    }
    client = _StubClient([json.dumps(initial), json.dumps(refinement)])

    stage1_partial = {
        "task": {"name": "test", "paradigm_classes": ["conflict"]},
        "stimuli": [],
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.9},
    }
    await run_stage2(client, stage1_partial)

    # The second prompt's "Failing slots to fix" section must NOT list performance.accuracy.
    refine_prompt = client.prompts_received[1]
    failing_section = refine_prompt.split("## Failing slots to fix", 1)[1].split("## Schema reminder", 1)[0]
    assert "performance.accuracy" not in failing_section
    assert "temporal_effects.post_event_slowing" in failing_section

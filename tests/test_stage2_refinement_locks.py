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

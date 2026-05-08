"""Schema and loader accept both bare-number and envelope shapes for
performance.{accuracy,omission_rate,practice_accuracy}. Backwards-compatible
with existing TaskCards (bare numbers); forward-compatible with Stage 2
LLM outputs that wrap each numeric in a {value, rationale} envelope."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from experiment_bot.reasoner.validate import (
    Stage2SchemaError, validate_stage2_schema,
)


def _minimal_partial(**overrides) -> dict:
    """Build a Stage 2 partial whose other fields are valid; tests
    isolate the field they care about via overrides."""
    base = {
        "task": {"name": "test_task"},
        "stimuli": [],
        "response_distributions": {
            "go": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 50, "tau": 100},
                "rationale": "test",
            }
        },
        "performance": {
            "accuracy": {"go": 0.95},
            "omission_rate": {"go": 0.02},
            "practice_accuracy": 0.9,
        },
        "temporal_effects": {},
        "between_subject_jitter": {"value": {}},
    }
    for path, value in overrides.items():
        node = base
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return base


def test_schema_accepts_bare_number_accuracy():
    partial = _minimal_partial()
    validate_stage2_schema(partial)  # no raise


def test_schema_accepts_envelope_accuracy():
    partial = _minimal_partial(**{
        "performance.accuracy": {"go": {"value": 0.95, "rationale": "test"}},
    })
    validate_stage2_schema(partial)  # no raise


def test_schema_rejects_null_accuracy():
    """Null accuracy was an SP3 Flanker failure mode — it must still fail."""
    partial = _minimal_partial(**{
        "performance.accuracy": {"go": None},
    })
    with pytest.raises(Stage2SchemaError) as ei:
        validate_stage2_schema(partial)
    paths = [p for p, _ in ei.value.errors]
    assert any("accuracy" in p for p in paths), f"expected accuracy error, got {paths}"


def test_schema_accepts_envelope_omission_rate():
    partial = _minimal_partial(**{
        "performance.omission_rate": {"go": {"value": 0.02, "rationale": "test"}},
    })
    validate_stage2_schema(partial)  # no raise


def test_schema_accepts_envelope_practice_accuracy():
    partial = _minimal_partial(**{"performance.practice_accuracy": {"value": 0.9, "rationale": "x"}})
    validate_stage2_schema(partial)  # no raise

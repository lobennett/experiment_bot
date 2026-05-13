"""Unit tests for the SP9a SessionAgent layer (types, page_probe, session_agent).

The agent module is paradigm-agnostic — its interface accepts a Page
and a TaskCard dict, and returns a KeyMappingDirective without knowing
which paradigm is loaded.
"""
from __future__ import annotations
import pytest

from experiment_bot.agent.types import KeyMappingDirective


def test_directive_dataclass_to_dict_roundtrip():
    """to_dict() emits the canonical run_metadata.json shape."""
    d = KeyMappingDirective(
        mapping={"congruent": "z", "incongruent": "/"},
        source="screenshot_inference",
        confidence=0.85,
        raw_llm_response="raw response text",
        elapsed_ms=2847.3,
    )
    got = d.to_dict()
    assert got == {
        "mapping": {"congruent": "z", "incongruent": "/"},
        "source": "screenshot_inference",
        "confidence": 0.85,
        "raw_llm_response": "raw response text",
        "elapsed_ms": 2847.3,
    }


def test_directive_source_must_be_one_of_known_values():
    """The source literal narrows to the documented set."""
    # Doesn't raise — typing-level constraint only, but the dataclass
    # still accepts the value at runtime. We exercise each known value
    # to make sure the dataclass is constructable with each.
    for src in (
        "window_correctresponse",
        "dom_inference",
        "screenshot_inference",
        "llm_failure_fallback",
    ):
        d = KeyMappingDirective(
            mapping={"x": "y"},
            source=src,
            confidence=1.0,
            raw_llm_response="",
            elapsed_ms=0.0,
        )
        assert d.source == src

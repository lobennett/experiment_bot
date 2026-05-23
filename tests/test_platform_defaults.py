"""Tests for Stage 1 platform-aware nav defaults (SP15 Part A)."""
from experiment_bot.reasoner.platform_defaults import (
    apply_platform_defaults,
    _match_platform,
    PLATFORM_NAV_DEFAULTS,
)


def test_platform_default_matches_expfactory_url():
    d = _match_platform("https://deploy.expfactory.org/preview/80/")
    assert d is not None
    assert d.name == "expfactory"
    # The 10-phase canonical sequence: wait/click/wait/keypress/wait/click/wait/click/wait/keypress
    assert len(d.phases) == 10
    # Anchored: starts with a wait, ends with Enter keypress
    assert d.phases[0]["action"] == "wait"
    assert d.phases[-1]["action"] == "keypress"
    assert d.phases[-1]["key"] == "Enter"


def test_platform_default_matches_cognition_run_url():
    d = _match_platform("https://strooptest.cognition.run/")
    assert d is not None
    assert d.name == "cognition.run"


def test_platform_default_matches_kywch_url():
    d = _match_platform(
        "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html"
    )
    assert d is not None
    assert d.name == "kywch.github.io"


def test_platform_default_no_match_returns_partial_unchanged():
    partial = {"navigation": {"phases": []}}
    out = apply_platform_defaults(partial, "https://example.com/unknown-platform/")
    assert out == partial
    # No match — _match_platform returns None
    assert _match_platform("https://example.com/foo") is None


def test_platform_default_backfills_empty_llm_nav():
    partial = {"navigation": {"phases": []}}
    out = apply_platform_defaults(partial, "https://deploy.expfactory.org/preview/80/")
    assert len(out["navigation"]["phases"]) == 10  # expfactory default
    # Original wasn't mutated (function returns new dict OR mutates; both acceptable
    # but we expect the returned object to have the platform default)
    assert out["navigation"]["phases"][1]["target"] == "#jspsych-fullscreen-btn"


def test_platform_default_does_not_clobber_richer_llm_nav():
    """If LLM emitted MORE phases than the platform default, trust the LLM —
    it may have paradigm-specific knowledge the default doesn't capture."""
    rich_phases = [{"action": "click", "target": f"#x{i}", "key": "", "duration_ms": 0,
                    "phase": "", "steps": []} for i in range(12)]
    partial = {"navigation": {"phases": rich_phases}}
    out = apply_platform_defaults(partial, "https://deploy.expfactory.org/preview/80/")
    assert out["navigation"]["phases"] == rich_phases  # unchanged


def test_platform_default_handles_missing_navigation_key():
    """LLM might not emit a navigation key at all; platform default still applies."""
    partial = {}
    out = apply_platform_defaults(partial, "https://deploy.expfactory.org/preview/80/")
    assert "navigation" in out
    assert len(out["navigation"]["phases"]) == 10


import pytest
from unittest.mock import AsyncMock

from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMResponse


@pytest.mark.asyncio
async def test_stage1_applies_platform_default_when_llm_emits_empty_nav():
    """Stage 1: when the LLM emits empty navigation.phases for an expfactory
    URL, platform_defaults backfills the canonical 10-phase sequence."""
    from experiment_bot.reasoner.stage1_structural import run_stage1
    bundle = SourceBundle(
        url="https://deploy.expfactory.org/preview/80/",
        source_files={"experiment.js": "// stub"},
        description_text="<html></html>",
    )
    # LLM returns a minimal valid partial with EMPTY navigation.phases
    llm_output = """{
        "task": {"name": "Test", "constructs": [], "paradigm_classes": ["speeded_choice"]},
        "stimuli": [{"id": "s1", "description": "x",
                    "detection": {"method": "dom_query", "selector": "#s"},
                    "response": {"key": "f", "condition": "c1"}}],
        "navigation": {"phases": []},
        "runtime": {"advance_behavior": {"advance_keys": [" "], "feedback_fallback_keys": ["Enter"],
                                         "feedback_selectors": []},
                    "data_capture": {"method": "js_expression",
                                     "expression": "jsPsych.data.get().json()", "format": "json"}},
        "task_specific": {"key_map": {"c1": "f"}},
        "performance": {"accuracy": {"c1": 0.95}},
        "pilot_validation_config": {"min_trials": 5, "target_conditions": ["c1"]}
    }"""
    client = AsyncMock()
    client.complete = AsyncMock(return_value=LLMResponse(text=llm_output))
    partial, step = await run_stage1(client, bundle)
    # Platform default backfilled
    assert len(partial["navigation"]["phases"]) == 10
    assert partial["navigation"]["phases"][1]["target"] == "#jspsych-fullscreen-btn"
    # Inference text mentions backfill
    assert "platform" in step.inference.lower() or "expfactory" in step.inference.lower()

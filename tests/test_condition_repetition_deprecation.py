"""SP11 Phase 2.2 — condition_repetition deprecation.

The handler stays functional (pre-SP11 TaskCards keep running) but
from_dict prints a loud stderr deprecation warning whenever
``enabled=True``. Loud-during-window discipline: never fires on the
four SP11 dev paradigms after Phase 5 TaskCard regeneration.

Per Phase 3 user note: the warning is ONCE-GATED per process — fires
on the first qualifying from_dict call only, not every load. The
test fixture resets the gate between tests so each test is
self-contained.
"""
from __future__ import annotations

import io
import sys

import pytest

from experiment_bot.core.config import (
    ConditionRepetitionConfig,
    _reset_deprecation_warnings_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_deprecation_gate():
    """Reset the module-level once-gates before every test in this
    file so each test sees a fresh stderr-warning state."""
    _reset_deprecation_warnings_for_tests()
    yield
    _reset_deprecation_warnings_for_tests()


def test_condition_repetition_disabled_no_warning():
    """A disabled config should NOT print a deprecation warning — the
    deprecation is about *use*, not presence."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = ConditionRepetitionConfig.from_dict({"enabled": False})
    finally:
        sys.stderr = old_stderr
    assert cfg.enabled is False
    assert "DEPRECATION" not in captured.getvalue()


def test_condition_repetition_enabled_prints_loud_deprecation():
    """An enabled config should print a loud DEPRECATION warning that
    names the replacement mechanism (lag1_pair_modulation)."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = ConditionRepetitionConfig.from_dict(
            {"enabled": True, "facilitation_ms": 10.0, "cost_ms": 8.0, "rationale": ""}
        )
    finally:
        sys.stderr = old_stderr
    assert cfg.enabled is True
    msg = captured.getvalue()
    assert "DEPRECATION" in msg
    assert "condition_repetition" in msg
    assert "lag1_pair_modulation" in msg
    # The warning should mention Phase 5 (the deprecation window terminator).
    assert "Phase 5" in msg
    # Once-gated discipline: explicit mention so reviewers don't think
    # the warning is silent on subsequent loads.
    assert "once per process" in msg


def test_condition_repetition_warning_is_once_gated_per_process():
    """Per Phase 3 user note: the warning must fire only on the FIRST
    qualifying from_dict call per process, not on every config load.
    Subsequent enabled-config loads in the same process produce no
    additional warning, keeping stderr clean during pytest runs and
    the 180-session Phase 7 validation."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        ConditionRepetitionConfig.from_dict(
            {"enabled": True, "facilitation_ms": 10.0, "cost_ms": 8.0}
        )
        ConditionRepetitionConfig.from_dict(
            {"enabled": True, "facilitation_ms": 15.0, "cost_ms": 12.0}
        )
        ConditionRepetitionConfig.from_dict(
            {"enabled": True, "facilitation_ms": 20.0, "cost_ms": 14.0}
        )
    finally:
        sys.stderr = old_stderr
    msg = captured.getvalue()
    assert msg.count("DEPRECATION") == 1, (
        f"expected exactly 1 DEPRECATION message, got "
        f"{msg.count('DEPRECATION')}:\n{msg}"
    )


def test_condition_repetition_handler_still_functional():
    """The deprecation does NOT break the handler — pre-SP11 TaskCards
    with condition_repetition keep producing the expected RT delta."""
    import io as _io
    import numpy as np
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    from experiment_bot.effects.handlers import SamplerState
    cfg = ConditionRepetitionConfig.from_dict(
        {"enabled": True, "facilitation_ms": 10.0, "cost_ms": 8.0, "rationale": ""}
    )
    handler = EFFECT_REGISTRY["condition_repetition"].handler
    rng = np.random.default_rng(42)
    state_repeat = SamplerState(
        mu=500.0, sigma=50.0, tau=100.0, prev_rt=600.0,
        prev_condition="incongruent", trial_index=10,
        prev_error=False, prev_interrupt_detected=False,
        condition="incongruent",
    )
    state_alternate = SamplerState(
        mu=500.0, sigma=50.0, tau=100.0, prev_rt=600.0,
        prev_condition="congruent", trial_index=10,
        prev_error=False, prev_interrupt_detected=False,
        condition="incongruent",
    )
    # Repeat: facilitation_ms applied as negative delta
    assert handler(state_repeat, cfg, rng) == -10.0
    # Alternate: cost_ms applied as positive delta
    assert handler(state_alternate, cfg, rng) == 8.0

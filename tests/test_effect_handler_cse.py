import numpy as np
import pytest
from experiment_bot.effects.handlers import SamplerState, apply_cse


def _make_state(prev_condition, condition, prev_error=False):
    return SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=600 if prev_condition else None,
        prev_condition=prev_condition,
        trial_index=1 if prev_condition else 0,
        prev_error=prev_error,
        prev_interrupt_detected=False,
        condition=condition,
    )


def _params(facilitation=30.0, cost=30.0, enabled=True):
    return {"enabled": enabled, "sequence_facilitation_ms": facilitation, "sequence_cost_ms": cost}


def test_cse_no_modulation_when_first_trial():
    state = _make_state(prev_condition=None, condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(), rng)
    assert delta == 0.0


def test_cse_facilitation_on_iI_pair():
    """Incongruent-after-incongruent: facilitation (negative delta)."""
    state = _make_state(prev_condition="incongruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(facilitation=30.0), rng)
    assert delta == -30.0


def test_cse_cost_on_cI_pair():
    """Incongruent-after-congruent: cost (positive delta)."""
    state = _make_state(prev_condition="congruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(cost=30.0), rng)
    assert delta == 30.0


def test_cse_no_modulation_on_congruent_current():
    """Current trial congruent: no CSE applies."""
    state = _make_state(prev_condition="incongruent", condition="congruent")
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(), rng)
    assert delta == 0.0


def test_cse_skipped_after_error():
    """Post-error trials skip CSE."""
    state = _make_state(prev_condition="incongruent", condition="incongruent", prev_error=True)
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(facilitation=30.0), rng)
    assert delta == 0.0


def test_cse_skipped_when_disabled():
    """Disabled effect returns 0 even on a valid pair."""
    state = _make_state(prev_condition="incongruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(enabled=False), rng)
    assert delta == 0.0


def test_cse_in_registry():
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    assert "congruency_sequence" in EFFECT_REGISTRY
    et = EFFECT_REGISTRY["congruency_sequence"]
    assert et.applicable_paradigms == frozenset({"conflict"})
    assert et.handler is not None

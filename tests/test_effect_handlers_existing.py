"""Regression test: registry-based handlers produce same RT modulation as legacy.

Runs the 6 effects through the registry-backed ResponseSampler and asserts
output is finite and well-bounded.  The fuller equivalence check is the
existing test_distributions.py / test_executor.py suite — those must
continue to pass without modification.
"""
import numpy as np
import pytest

from experiment_bot.core.config import (
    AutocorrelationConfig,
    ConditionRepetitionConfig,
    DistributionConfig,
    FatigueDriftConfig,
    PinkNoiseConfig,
    TemporalEffectsConfig,
)
from experiment_bot.core.distributions import ResponseSampler


def _make_dist(mu: float = 500, sigma: float = 50, tau: float = 80) -> dict:
    return {"default": DistributionConfig(distribution="ex_gaussian",
                                          params={"mu": mu, "sigma": sigma, "tau": tau})}


def test_autocorrelation_handler_via_registry_produces_finite_output():
    effects = TemporalEffectsConfig(
        autocorrelation=AutocorrelationConfig(enabled=True, phi=0.3),
    )
    sampler = ResponseSampler(_make_dist(), temporal_effects=effects, seed=42)
    seq = [sampler.sample_rt("default") for _ in range(10)]
    for rt in seq:
        assert 150 < rt < 5000, f"RT {rt} out of range"


def test_post_event_slowing_via_registry():
    """post_event_slowing is the generic mechanism that subsumes both
    classical PES and post-inhibition slowing. Verify the handler is
    registered and fires with the right delta when the configured
    event matches."""
    from types import SimpleNamespace
    cfg = SimpleNamespace(
        enabled=True,
        triggers=[
            {"event": "error", "slowing_ms_min": 30.0, "slowing_ms_max": 80.0},
        ],
    )
    effects = TemporalEffectsConfig(post_event_slowing=cfg)
    sampler = ResponseSampler(_make_dist(), temporal_effects=effects, seed=42)
    rt0 = sampler.sample_rt("default")
    rt1 = sampler.sample_rt("default")
    assert 150 < rt0 < 5000
    assert 150 < rt1 < 5000

    # Also exercise the handler directly via the registry.
    from experiment_bot.effects.handlers import SamplerState
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=520.0, prev_condition="default",
        trial_index=1,
        prev_error=True, prev_interrupt_detected=False,
        condition="default",
        pink_buffer=None,
    )
    rng = np.random.default_rng(99)
    delta = EFFECT_REGISTRY["post_event_slowing"].handler(state, cfg, rng)
    assert 30 <= delta <= 80, f"post-event-slowing delta {delta} outside [30, 80]"


def test_pink_noise_via_registry():
    effects = TemporalEffectsConfig(
        pink_noise=PinkNoiseConfig(enabled=True, sd_ms=30.0, hurst=0.7),
    )
    sampler = ResponseSampler(_make_dist(), temporal_effects=effects, seed=42)
    rts = [sampler.sample_rt("default") for _ in range(20)]
    for rt in rts:
        assert 150 < rt < 5000, f"RT {rt} out of range"


def test_condition_repetition_via_registry():
    effects = TemporalEffectsConfig(
        condition_repetition=ConditionRepetitionConfig(
            enabled=True, facilitation_ms=20, cost_ms=30
        ),
    )
    sampler = ResponseSampler(_make_dist(), temporal_effects=effects, seed=42)
    rt0 = sampler.sample_rt("default")
    rt1 = sampler.sample_rt("default")
    assert 150 < rt0 < 5000
    assert 150 < rt1 < 5000


def test_fatigue_drift_via_registry():
    effects = TemporalEffectsConfig(
        fatigue_drift=FatigueDriftConfig(enabled=True, drift_per_trial_ms=0.5),
    )
    sampler = ResponseSampler(_make_dist(), temporal_effects=effects, seed=42)
    rts = [sampler.sample_rt("default") for _ in range(50)]
    for rt in rts:
        assert 150 < rt < 10000, f"RT {rt} out of range"


def test_post_event_slowing_with_interrupt_trigger():
    """post_event_slowing fires for the 'interrupt' event when
    prev_interrupt_detected is True. This is the generic mechanism
    that subsumes classical post-inhibition slowing."""
    from types import SimpleNamespace
    from experiment_bot.effects.handlers import SamplerState
    from experiment_bot.effects.registry import EFFECT_REGISTRY

    cfg = SimpleNamespace(
        enabled=True,
        triggers=[
            {"event": "interrupt", "slowing_ms_min": 50.0, "slowing_ms_max": 150.0},
        ],
    )
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=520.0, prev_condition="default",
        trial_index=2,
        prev_error=False, prev_interrupt_detected=True,
        condition="default",
        pink_buffer=None,
    )
    rng = np.random.default_rng(7)
    delta = EFFECT_REGISTRY["post_event_slowing"].handler(state, cfg, rng)
    assert 50 <= delta <= 150, f"post-event-slowing delta {delta} outside [50, 150]"


def test_post_event_slowing_priority_interrupt_over_error():
    """When both error and interrupt are configured, the trigger listed
    first wins (typically interrupt). This implements the historical
    'interrupt takes priority over error' semantics through generic
    config rather than hardcoded executor logic."""
    from types import SimpleNamespace
    from experiment_bot.effects.handlers import SamplerState, apply_post_event_slowing

    cfg = SimpleNamespace(
        enabled=True,
        triggers=[
            {"event": "interrupt", "slowing_ms_min": 100.0, "slowing_ms_max": 100.0,
             "exclusive_with_prior_triggers": True},
            {"event": "error", "slowing_ms_min": 30.0, "slowing_ms_max": 30.0,
             "exclusive_with_prior_triggers": True},
        ],
    )
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=520.0, prev_condition="default",
        trial_index=2,
        prev_error=True, prev_interrupt_detected=True,  # both fired
        condition="default",
        pink_buffer=None,
    )
    rng = np.random.default_rng(0)
    delta = apply_post_event_slowing(state, cfg, rng)
    # Should be the interrupt's 100ms (first trigger wins), not error's 30ms.
    assert delta == 100.0, f"Expected 100ms (interrupt priority); got {delta}"

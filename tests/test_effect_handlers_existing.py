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
    PostErrorSlowingConfig,
    PostInterruptSlowingConfig,
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


def test_post_error_slowing_via_registry():
    # PES is applied by the executor, not the sampler.  Verify the handler
    # is registered and callable, and that sampling without error state does
    # not crash.
    effects = TemporalEffectsConfig(
        post_error_slowing=PostErrorSlowingConfig(
            enabled=True, slowing_ms_min=30, slowing_ms_max=80
        ),
    )
    sampler = ResponseSampler(_make_dist(), temporal_effects=effects, seed=42)
    rt0 = sampler.sample_rt("default")
    rt1 = sampler.sample_rt("default")
    assert 150 < rt0 < 5000
    assert 150 < rt1 < 5000

    # Also exercise the handler directly via the registry to prove it is wired.
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
    cfg = effects.post_error_slowing
    rng = np.random.default_rng(99)
    delta = EFFECT_REGISTRY["post_error_slowing"].handler(state, cfg, rng)
    assert 30 <= delta <= 80, f"PES delta {delta} outside [30, 80]"


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


def test_post_interrupt_slowing_via_registry():
    # Like PES, post_interrupt_slowing is applied by the executor. Verify the
    # handler is wired and callable.
    from experiment_bot.effects.handlers import SamplerState
    from experiment_bot.effects.registry import EFFECT_REGISTRY

    cfg = PostInterruptSlowingConfig(enabled=True, slowing_ms_min=50, slowing_ms_max=150)
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=520.0, prev_condition="default",
        trial_index=2,
        prev_error=False, prev_interrupt_detected=True,
        condition="default",
        pink_buffer=None,
    )
    rng = np.random.default_rng(7)
    delta = EFFECT_REGISTRY["post_interrupt_slowing"].handler(state, cfg, rng)
    assert 50 <= delta <= 150, f"PIS delta {delta} outside [50, 150]"

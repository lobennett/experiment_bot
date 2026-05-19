"""SP11 Phase 2.4 — vigilance_decrement mechanism tests.

Zero-mean Gaussian RT noise with linearly-growing SD across the
session. Mean RT unchanged; variance grows. Implemented as an
additive handler so it fits the existing
``handler(state, cfg, rng) → float`` interface without extension.

SP11 Phase 2 scope: RT-variance only. The omission-rate aspect
(lapse increase over session) is a separate executor-side mechanism
deferred to a future SP — see Phase 2 deliverable notes.
"""
from __future__ import annotations

import numpy as np

from experiment_bot.core.config import (
    DistributionConfig, TemporalEffectsConfig, VigilanceDecrementConfig,
)
from experiment_bot.core.distributions import ResponseSampler
from experiment_bot.effects.handlers import SamplerState, apply_vigilance_decrement
from experiment_bot.effects.registry import EFFECT_REGISTRY


def _make_state(trial_index: int) -> SamplerState:
    return SamplerState(
        mu=500.0, sigma=50.0, tau=100.0,
        prev_rt=None, prev_condition=None,
        trial_index=trial_index, prev_error=False,
        prev_interrupt_detected=False, condition="go",
    )


def test_vigilance_decrement_disabled_returns_zero():
    cfg = VigilanceDecrementConfig(enabled=False, sd_per_100_trials_ms=15.0)
    rng = np.random.default_rng(0)
    assert apply_vigilance_decrement(_make_state(500), cfg, rng) == 0.0


def test_vigilance_decrement_zero_sd_is_no_op():
    cfg = VigilanceDecrementConfig(enabled=True, sd_per_100_trials_ms=0.0)
    rng = np.random.default_rng(0)
    assert apply_vigilance_decrement(_make_state(500), cfg, rng) == 0.0


def test_vigilance_decrement_at_trial_zero_returns_zero():
    """Per the parameterization SD = sd_per_100 * (N/100), at N=0 SD=0
    and the handler short-circuits."""
    cfg = VigilanceDecrementConfig(enabled=True, sd_per_100_trials_ms=15.0)
    rng = np.random.default_rng(0)
    assert apply_vigilance_decrement(_make_state(0), cfg, rng) == 0.0


def test_vigilance_decrement_mean_unchanged_at_high_trial_count():
    """Over many invocations at a fixed trial_index, mean of returned
    deltas should be approximately zero (zero-mean Gaussian)."""
    cfg = VigilanceDecrementConfig(enabled=True, sd_per_100_trials_ms=20.0)
    rng = np.random.default_rng(42)
    samples = [
        apply_vigilance_decrement(_make_state(200), cfg, rng)
        for _ in range(2000)
    ]
    mean = sum(samples) / len(samples)
    # Expected SD at trial_index=200 is 20 * 2 = 40 ms
    # Standard error of mean over 2000 samples: 40 / sqrt(2000) ≈ 0.9 ms
    # 4-sigma tolerance ≈ 3.6 ms
    assert abs(mean) < 4.0, f"mean delta {mean} should be ~0"


def test_vigilance_decrement_sd_grows_linearly_with_trial_index():
    """At trial_index 100 the SD should be ~sd_per_100; at trial_index
    500 it should be ~5 * sd_per_100. Test empirically."""
    cfg = VigilanceDecrementConfig(enabled=True, sd_per_100_trials_ms=20.0)
    rng = np.random.default_rng(42)
    samples_100 = np.array([
        apply_vigilance_decrement(_make_state(100), cfg, rng)
        for _ in range(5000)
    ])
    samples_500 = np.array([
        apply_vigilance_decrement(_make_state(500), cfg, rng)
        for _ in range(5000)
    ])
    sd_100 = samples_100.std()
    sd_500 = samples_500.std()
    # Expected: sd_100 ≈ 20, sd_500 ≈ 100 (5x)
    assert 17 < sd_100 < 23, f"sd at t=100: {sd_100:.2f} not in [17, 23]"
    assert 90 < sd_500 < 110, f"sd at t=500: {sd_500:.2f} not in [90, 110]"


def test_vigilance_decrement_via_full_sampler_inflates_late_session_variance():
    """End-to-end: through ResponseSampler, late-session RTs should
    have higher variance than early-session RTs."""
    cfg = TemporalEffectsConfig(
        vigilance_decrement=VigilanceDecrementConfig(
            enabled=True, sd_per_100_trials_ms=30.0,
        ),
    )
    dists = {"go": DistributionConfig(distribution="ex_gaussian",
                                       params={"mu": 450, "sigma": 60, "tau": 80})}
    sampler = ResponseSampler(dists, temporal_effects=cfg, seed=42)
    # First 50 trials (early session: low vigilance-decrement SD)
    early_rts = np.array([sampler.sample_rt("go") for _ in range(50)])
    # Skip to trial 450, then capture 50 more (late session)
    for _ in range(400):
        sampler.sample_rt("go")
    late_rts = np.array([sampler.sample_rt("go") for _ in range(50)])
    # Late variance must exceed early by a meaningful margin
    assert late_rts.std() > early_rts.std() * 1.5, (
        f"early SD={early_rts.std():.1f}, late SD={late_rts.std():.1f}"
    )
    # Mean should be approximately preserved (within sampling noise of
    # the underlying ex-Gaussian + the zero-mean vigilance noise)
    early_mean = early_rts.mean()
    late_mean = late_rts.mean()
    # 50-trial sample SE on a mean ~530ms with SD ~150ms is ~21ms.
    # Two samples → comparison SE ~30ms. 3-sigma tolerance ~90ms.
    assert abs(late_mean - early_mean) < 100.0, (
        f"mean drifted: early={early_mean:.1f}, late={late_mean:.1f}"
    )


def test_vigilance_decrement_registered_in_effect_registry():
    assert "vigilance_decrement" in EFFECT_REGISTRY
    et = EFFECT_REGISTRY["vigilance_decrement"]
    assert et.handler is apply_vigilance_decrement
    assert et.config_class is VigilanceDecrementConfig


def test_vigilance_decrement_kept_separate_from_fatigue_drift():
    """SP11 design decision: vigilance_decrement and fatigue_drift
    remain SEPARATE mechanisms (different phenomena — attentional
    lapses vs effort/motor drift, different literature
    parameterizations). The registry must hold both as distinct
    entries with distinct handlers and config classes."""
    from experiment_bot.effects.handlers import apply_fatigue_drift
    from experiment_bot.core.config import FatigueDriftConfig
    assert EFFECT_REGISTRY["vigilance_decrement"].handler is apply_vigilance_decrement
    assert EFFECT_REGISTRY["fatigue_drift"].handler is apply_fatigue_drift
    assert apply_vigilance_decrement is not apply_fatigue_drift
    assert VigilanceDecrementConfig is not FatigueDriftConfig

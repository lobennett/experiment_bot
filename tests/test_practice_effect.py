"""SP11 Phase 2.3 — practice_effect mechanism tests.

Exponential block-wise RT reduction approaching asymptote_block.
Block index computed inside the handler from
``trial_index // trials_per_block``.
"""
from __future__ import annotations

import math

import numpy as np

from experiment_bot.core.config import (
    DistributionConfig, PracticeEffectConfig, TemporalEffectsConfig,
)
from experiment_bot.core.distributions import ResponseSampler
from experiment_bot.effects.handlers import SamplerState, apply_practice_effect
from experiment_bot.effects.registry import EFFECT_REGISTRY


def _make_state(trial_index: int) -> SamplerState:
    return SamplerState(
        mu=500.0, sigma=50.0, tau=100.0,
        prev_rt=None, prev_condition=None,
        trial_index=trial_index, prev_error=False,
        prev_interrupt_detected=False, condition="go",
    )


def test_practice_effect_disabled_returns_zero():
    cfg = PracticeEffectConfig(enabled=False, initial_offset_ms=50.0,
                                asymptote_block=3, trials_per_block=30,
                                decay_rate=0.7)
    rng = np.random.default_rng(0)
    assert apply_practice_effect(_make_state(0), cfg, rng) == 0.0


def test_practice_effect_block_zero_returns_initial_offset():
    """At trial 0 (block 0), delta should equal initial_offset_ms exactly
    (exp(0) = 1)."""
    cfg = PracticeEffectConfig(enabled=True, initial_offset_ms=50.0,
                                asymptote_block=3, trials_per_block=30,
                                decay_rate=0.7)
    rng = np.random.default_rng(0)
    assert apply_practice_effect(_make_state(0), cfg, rng) == 50.0


def test_practice_effect_decays_exponentially_across_blocks():
    """At block N, delta should equal initial_offset_ms * exp(-decay_rate * N)."""
    cfg = PracticeEffectConfig(enabled=True, initial_offset_ms=50.0,
                                asymptote_block=5, trials_per_block=30,
                                decay_rate=0.7)
    rng = np.random.default_rng(0)
    # Block 1: trial_index in [30, 59]
    assert math.isclose(
        apply_practice_effect(_make_state(30), cfg, rng),
        50.0 * math.exp(-0.7 * 1),
        abs_tol=1e-9,
    )
    # Block 2: trial_index in [60, 89]
    assert math.isclose(
        apply_practice_effect(_make_state(60), cfg, rng),
        50.0 * math.exp(-0.7 * 2),
        abs_tol=1e-9,
    )
    # Block 4: trial_index in [120, 149]
    assert math.isclose(
        apply_practice_effect(_make_state(120), cfg, rng),
        50.0 * math.exp(-0.7 * 4),
        abs_tol=1e-9,
    )


def test_practice_effect_zero_at_asymptote_block_and_after():
    """At asymptote_block and beyond, delta is 0 (flat plateau)."""
    cfg = PracticeEffectConfig(enabled=True, initial_offset_ms=50.0,
                                asymptote_block=3, trials_per_block=30,
                                decay_rate=0.7)
    rng = np.random.default_rng(0)
    # Block 3 (= asymptote_block): trial_index in [90, 119]
    assert apply_practice_effect(_make_state(90), cfg, rng) == 0.0
    # Block 5: well past asymptote
    assert apply_practice_effect(_make_state(150), cfg, rng) == 0.0
    # Block 100
    assert apply_practice_effect(_make_state(3000), cfg, rng) == 0.0


def test_practice_effect_zero_initial_offset_is_no_op():
    """initial_offset_ms=0 disables the effect even when enabled=True."""
    cfg = PracticeEffectConfig(enabled=True, initial_offset_ms=0.0,
                                asymptote_block=3, trials_per_block=30,
                                decay_rate=0.7)
    rng = np.random.default_rng(0)
    assert apply_practice_effect(_make_state(0), cfg, rng) == 0.0


def test_practice_effect_block_counter_resets_on_new_sampler():
    """User-note 2 invariant: each new ResponseSampler starts at
    trial_index=0, so the block counter restarts. SP11 runs single-shot
    sessions and there's no cross-session state to preserve."""
    cfg = TemporalEffectsConfig(
        practice_effect=PracticeEffectConfig(
            enabled=True, initial_offset_ms=50.0,
            asymptote_block=3, trials_per_block=30, decay_rate=0.7,
        ),
    )
    dists = {"go": DistributionConfig(distribution="ex_gaussian",
                                       params={"mu": 450, "sigma": 60, "tau": 80})}
    s1 = ResponseSampler(dists, temporal_effects=cfg, seed=42)
    assert s1._trial_index == 0
    # Drain a block worth of trials
    for _ in range(30):
        s1.sample_rt("go")
    assert s1._trial_index == 30  # advanced
    # A brand-new sampler has its OWN counter starting at 0
    s2 = ResponseSampler(dists, temporal_effects=cfg, seed=42)
    assert s2._trial_index == 0


def test_practice_effect_via_registry_lifts_block0_rt():
    """Through the full ResponseSampler pipeline: block-0 sampled RTs
    should be on average higher than block-K sampled RTs by at least
    half the initial_offset_ms."""
    cfg = TemporalEffectsConfig(
        practice_effect=PracticeEffectConfig(
            enabled=True, initial_offset_ms=60.0,
            asymptote_block=4, trials_per_block=20, decay_rate=0.5,
        ),
    )
    dists = {"go": DistributionConfig(distribution="ex_gaussian",
                                       params={"mu": 450, "sigma": 60, "tau": 80})}
    # Same seed, but the practice effect is deterministic at the
    # handler level — RTs differ across blocks only via the effect.
    sampler = ResponseSampler(dists, temporal_effects=cfg, seed=42)
    block_0_rts = [sampler.sample_rt("go") for _ in range(20)]
    # Skip past blocks 1, 2 to get to past-asymptote (block 4)
    for _ in range(60):
        sampler.sample_rt("go")
    asymptote_rts = [sampler.sample_rt("go") for _ in range(20)]
    block_0_mean = sum(block_0_rts) / len(block_0_rts)
    asymptote_mean = sum(asymptote_rts) / len(asymptote_rts)
    # Block 0 mean should exceed asymptote mean by at least 30ms
    # (half the initial offset, after sampling noise)
    assert block_0_mean - asymptote_mean > 30.0, (
        f"block_0_mean={block_0_mean:.1f}, asymptote_mean={asymptote_mean:.1f}"
    )


def test_practice_effect_registered_in_effect_registry():
    """The mechanism is registered in EFFECT_REGISTRY with a handler."""
    assert "practice_effect" in EFFECT_REGISTRY
    et = EFFECT_REGISTRY["practice_effect"]
    assert et.handler is apply_practice_effect
    assert et.config_class is PracticeEffectConfig

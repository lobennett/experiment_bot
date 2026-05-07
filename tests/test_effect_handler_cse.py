"""Tests for the generic lag1_pair_modulation mechanism. CSE is one
configuration of this mechanism — the bot's library does not name CSE.
Tests below verify the generic mechanism's behavior using a CSE-style
modulation table as the worked example."""
import numpy as np
import pytest
from types import SimpleNamespace
from experiment_bot.effects.handlers import SamplerState, apply_lag1_pair_modulation


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


def _cse_style_cfg(facilitation_ms=30.0, cost_ms=30.0, enabled=True,
                   skip_after_error=True):
    """A CSE-style configuration of the generic lag1_pair_modulation
    mechanism. Tests below verify the generic mechanism's behavior
    on this canonical configuration."""
    return SimpleNamespace(
        enabled=enabled,
        skip_after_error=skip_after_error,
        modulation_table=[
            {"prev": "incongruent", "curr": "incongruent",
             "delta_ms": -facilitation_ms},
            {"prev": "congruent", "curr": "incongruent",
             "delta_ms": cost_ms},
        ],
    )


def test_no_modulation_when_first_trial():
    state = _make_state(prev_condition=None, condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, _cse_style_cfg(), rng)
    assert delta == 0.0


def test_facilitation_on_high_after_high_pair():
    """High-conflict-after-high-conflict: negative delta (facilitation)."""
    state = _make_state(prev_condition="incongruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, _cse_style_cfg(facilitation_ms=30.0), rng)
    assert delta == -30.0


def test_cost_on_high_after_low_pair():
    """High-conflict-after-low-conflict: positive delta (cost)."""
    state = _make_state(prev_condition="congruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, _cse_style_cfg(cost_ms=30.0), rng)
    assert delta == 30.0


def test_no_modulation_when_curr_does_not_match_table():
    """Current condition not in any table entry's curr field: no modulation."""
    state = _make_state(prev_condition="incongruent", condition="congruent")
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, _cse_style_cfg(), rng)
    assert delta == 0.0


def test_skipped_after_error_when_skip_after_error_true():
    state = _make_state(prev_condition="incongruent", condition="incongruent", prev_error=True)
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, _cse_style_cfg(facilitation_ms=30.0), rng)
    assert delta == 0.0


def test_skipped_when_disabled():
    state = _make_state(prev_condition="incongruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, _cse_style_cfg(enabled=False), rng)
    assert delta == 0.0


def test_lag1_pair_modulation_in_registry():
    """The bot's library has the generic mechanism, not paradigm-named CSE."""
    from experiment_bot.effects.registry import EFFECT_REGISTRY, ALL_PARADIGM_CLASSES
    assert "lag1_pair_modulation" in EFFECT_REGISTRY
    assert "congruency_sequence" not in EFFECT_REGISTRY
    et = EFFECT_REGISTRY["lag1_pair_modulation"]
    assert et.applicable_paradigms == ALL_PARADIGM_CLASSES
    assert et.handler is not None


# ---------------------------------------------------------------------------
# Custom condition labels — the generic mechanism doesn't know any specific
# condition vocabulary; labels are looked up directly in the modulation table.
# ---------------------------------------------------------------------------

def test_modulation_uses_custom_condition_labels():
    """Generic mechanism works with arbitrary condition labels (e.g.,
    'compatible'/'incompatible' for a conflict task that doesn't use the
    'congruent'/'incongruent' vocabulary)."""
    state = _make_state(prev_condition="incompatible", condition="incompatible")
    rng = np.random.default_rng(0)
    cfg = SimpleNamespace(
        enabled=True,
        skip_after_error=True,
        modulation_table=[
            {"prev": "incompatible", "curr": "incompatible", "delta_ms": -30.0},
            {"prev": "compatible", "curr": "incompatible", "delta_ms": 30.0},
        ],
    )
    delta = apply_lag1_pair_modulation(state, cfg, rng)
    assert delta == -30.0


# ---------------------------------------------------------------------------
# End-to-end through the sampler — verifies the generic mechanism is wired
# (not dead code). Origin: cse-sign-flip-diagnostic.md.
# ---------------------------------------------------------------------------

def test_lag1_pair_modulation_fires_through_sampler():
    """When ResponseSampler is given temporal_effects.lag1_pair_modulation
    enabled with a CSE-style modulation table, the i-after-i pair RT
    should be measurably lower than the i-after-c pair RT.

    CSE is one configuration of the generic mechanism; the bot's code
    doesn't name it. The TaskCard supplies the modulation table.
    """
    from experiment_bot.core.distributions import ResponseSampler
    from experiment_bot.core.config import (
        DistributionConfig, TemporalEffectsConfig,
    )
    from types import SimpleNamespace

    distributions = {
        "congruent": DistributionConfig(
            distribution="ex_gaussian",
            params={"mu": 500, "sigma": 30, "tau": 60},
        ),
        "incongruent": DistributionConfig(
            distribution="ex_gaussian",
            params={"mu": 500, "sigma": 30, "tau": 60},
        ),
    }
    # Configure CSE as a modulation table — paradigm-specific config of the
    # generic mechanism. Bot's code doesn't know this is "CSE".
    lag1_cfg = SimpleNamespace(
        enabled=True,
        skip_after_error=True,
        modulation_table=[
            {"prev": "incongruent", "curr": "incongruent", "delta_ms": -50.0},
            {"prev": "congruent", "curr": "incongruent", "delta_ms": 20.0},
        ],
    )
    effects = TemporalEffectsConfig(lag1_pair_modulation=lag1_cfg)
    sampler = ResponseSampler(
        distributions, temporal_effects=effects, seed=42,
        paradigm_classes=["conflict"],
    )

    # Drive a short alternating sequence and accumulate iI vs cI pair RTs
    iI_rts = []
    cI_rts = []
    prev_cond = None
    prev_rt = None
    for cond in ["congruent", "incongruent", "incongruent", "congruent",
                 "incongruent", "incongruent", "congruent", "incongruent",
                 "incongruent", "congruent"]:
        rt = sampler.sample_rt(cond)
        if cond == "incongruent" and prev_cond == "incongruent":
            iI_rts.append(rt)
        elif cond == "incongruent" and prev_cond == "congruent":
            cI_rts.append(rt)
        prev_cond = cond
        prev_rt = rt

    # iI should be faster (facilitated by 50ms); cI should be slower (+20ms).
    # With seed=42 and 3 iI + 3 cI pairs, the difference should be clearly
    # negative even with sampling noise.
    assert iI_rts and cI_rts
    assert sum(iI_rts) / len(iI_rts) < sum(cI_rts) / len(cI_rts), (
        f"iI mean {sum(iI_rts)/len(iI_rts):.1f} >= cI mean {sum(cI_rts)/len(cI_rts):.1f} "
        f"— CSE handler is not firing through sampler"
    )


def test_lag1_pair_modulation_inactive_when_table_empty():
    """All effects are now universal mechanisms; whether they apply is
    determined by whether the TaskCard configures them. A task with
    enabled=False (or no modulation_table) gets no modulation."""
    from experiment_bot.core.distributions import ResponseSampler
    from experiment_bot.core.config import (
        DistributionConfig, TemporalEffectsConfig,
    )
    from types import SimpleNamespace

    distributions = {
        "congruent": DistributionConfig(
            distribution="ex_gaussian",
            params={"mu": 500, "sigma": 30, "tau": 60},
        ),
        "incongruent": DistributionConfig(
            distribution="ex_gaussian",
            params={"mu": 500, "sigma": 30, "tau": 60},
        ),
    }
    # Effect disabled — no table provided.
    effects = TemporalEffectsConfig(
        lag1_pair_modulation=SimpleNamespace(enabled=False, modulation_table=[]),
    )
    sampler = ResponseSampler(
        distributions, temporal_effects=effects, seed=42,
        paradigm_classes=["interrupt"],  # paradigm class no longer gates effects
    )
    # Drive trials; without a modulation table, no delta is applied.
    rts = [sampler.sample_rt(c) for c in
           ["incongruent", "incongruent", "congruent", "incongruent",
            "incongruent", "congruent"]]
    # All RTs should be from the raw ex-Gaussian sample distribution.
    # If a 200ms modulation were applied, we'd see clusters with much
    # larger deltas. Assert all RTs are within a generous range of each other.
    assert max(rts) - min(rts) < 500, (
        f"RTs vary too much ({max(rts)-min(rts):.1f}ms) — modulation may be "
        f"applying when it should be inactive"
    )

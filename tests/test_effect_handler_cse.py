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


def test_lag1_pair_modulation_in_registry():
    """The bot's library has the generic mechanism, not paradigm-named CSE."""
    from experiment_bot.effects.registry import EFFECT_REGISTRY, ALL_PARADIGM_CLASSES
    assert "lag1_pair_modulation" in EFFECT_REGISTRY
    assert "congruency_sequence" not in EFFECT_REGISTRY
    et = EFFECT_REGISTRY["lag1_pair_modulation"]
    assert et.applicable_paradigms == ALL_PARADIGM_CLASSES
    assert et.handler is not None


# ---------------------------------------------------------------------------
# Generalization (audit finding H1) — handler must operate on TaskCard-named
# condition labels, not hardcoded "congruent"/"incongruent" strings.
# ---------------------------------------------------------------------------

def test_cse_uses_custom_condition_labels_for_facilitation():
    """A conflict task using 'compatible'/'incompatible' labels still gets CSE."""
    state = _make_state(prev_condition="incompatible", condition="incompatible")
    rng = np.random.default_rng(0)
    params = {
        "enabled": True,
        "sequence_facilitation_ms": 30.0,
        "sequence_cost_ms": 30.0,
        "high_conflict_condition": "incompatible",
        "low_conflict_condition": "compatible",
    }
    delta = apply_cse(state, params, rng)
    assert delta == -30.0


def test_cse_uses_custom_condition_labels_for_cost():
    state = _make_state(prev_condition="compatible", condition="incompatible")
    rng = np.random.default_rng(0)
    params = {
        "enabled": True,
        "sequence_facilitation_ms": 30.0,
        "sequence_cost_ms": 30.0,
        "high_conflict_condition": "incompatible",
        "low_conflict_condition": "compatible",
    }
    delta = apply_cse(state, params, rng)
    assert delta == 30.0


def test_cse_does_not_fire_when_labels_dont_match_taskcard():
    """If TaskCard labels are 'compatible'/'incompatible' but trial uses
    'congruent'/'incongruent', CSE handler returns 0 (the trial's condition
    doesn't match the configured high-conflict label)."""
    state = _make_state(prev_condition="incongruent", condition="incongruent")
    rng = np.random.default_rng(0)
    params = {
        "enabled": True,
        "sequence_facilitation_ms": 30.0,
        "sequence_cost_ms": 30.0,
        "high_conflict_condition": "incompatible",
        "low_conflict_condition": "compatible",
    }
    delta = apply_cse(state, params, rng)
    assert delta == 0.0


def test_cse_falls_back_to_default_labels_when_unspecified():
    """For back-compat: if params omit the label keys, use 'incongruent'/'congruent'."""
    state = _make_state(prev_condition="incongruent", condition="incongruent")
    rng = np.random.default_rng(0)
    delta = apply_cse(state, _params(facilitation=30.0), rng)
    assert delta == -30.0


# ---------------------------------------------------------------------------
# End-to-end through the sampler — verifies CSE is actually wired in
# (not dead code). Audit finding from cse-sign-flip-diagnostic.md.
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

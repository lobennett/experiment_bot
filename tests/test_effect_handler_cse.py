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

def test_cse_fires_through_sampler_for_conflict_paradigm():
    """When ResponseSampler is given paradigm_classes including 'conflict'
    and temporal_effects.congruency_sequence enabled, the i-after-i pair
    RT should be measurably lower than the i-after-c pair RT."""
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
    # Use SimpleNamespace to inject CSE config directly
    cse_cfg = SimpleNamespace(
        enabled=True,
        sequence_facilitation_ms=50.0,
        sequence_cost_ms=20.0,
        high_conflict_condition="incongruent",
        low_conflict_condition="congruent",
    )
    effects = TemporalEffectsConfig(congruency_sequence=cse_cfg)
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


def test_cse_does_not_fire_for_non_conflict_paradigm():
    """If paradigm_classes doesn't include 'conflict', CSE handler should
    NOT run even when temporal_effects.congruency_sequence is configured."""
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
    cse_cfg = SimpleNamespace(
        enabled=True,
        sequence_facilitation_ms=200.0,  # large so we'd see it if applied
        sequence_cost_ms=200.0,
        high_conflict_condition="incongruent",
        low_conflict_condition="congruent",
    )
    effects = TemporalEffectsConfig(congruency_sequence=cse_cfg)
    sampler = ResponseSampler(
        distributions, temporal_effects=effects, seed=42,
        paradigm_classes=["interrupt"],  # NOT 'conflict'
    )

    rt1 = sampler.sample_rt("incongruent")
    rt2 = sampler.sample_rt("incongruent")  # this would be heavily modulated if CSE ran
    rt3 = sampler.sample_rt("congruent")
    rt4 = sampler.sample_rt("incongruent")  # also would be heavily modulated

    # If CSE ran with -200/+200ms, rt2 vs rt4 would differ by ~400ms.
    # If CSE doesn't run (paradigm filter excludes it), they should be
    # within sampling noise (a few hundred ms is conceivable but not 400+
    # systematically). We assert no CSE: check that the iI pair (rt2)
    # isn't 100ms+ faster than the cI pair (rt4) — if the filter worked,
    # both are pure samples.
    assert abs(rt2 - rt4) < 200, (
        f"rt2={rt2}, rt4={rt4} — CSE seems to be firing for non-conflict paradigm"
    )

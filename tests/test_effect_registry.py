import pytest
from experiment_bot.effects.registry import (
    EffectType, ALL_PARADIGM_CLASSES, EFFECT_REGISTRY,
)


def test_effect_type_dataclass_round_trip():
    et = EffectType(
        name="example",
        params={"x": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=lambda *a, **kw: 0.0,
        validation_metric=None,
    )
    assert et.name == "example"
    assert et.params == {"x": float}


def test_registry_contains_all_generic_mechanisms():
    """The bot's library contains generic mechanisms only — no paradigm-
    specific named effects (no congruency_sequence, no post_error_slowing,
    no post_interrupt_slowing). Each is configured per task in the
    TaskCard."""
    expected = {
        "autocorrelation",
        "fatigue_drift",
        "condition_repetition",
        "pink_noise",
        "lag1_pair_modulation",
        "post_event_slowing",
    }
    assert set(EFFECT_REGISTRY.keys()) >= expected
    # Negative assertions: paradigm-named entries are NOT in the bot's library
    assert "congruency_sequence" not in EFFECT_REGISTRY
    assert "post_error_slowing" not in EFFECT_REGISTRY
    assert "post_interrupt_slowing" not in EFFECT_REGISTRY


def test_all_registered_effects_are_universal():
    """All effects in the bot's library are universal mechanisms.
    Paradigm-class filtering is no longer used — instead, effects only
    apply when the TaskCard configures them."""
    for name, et in EFFECT_REGISTRY.items():
        assert et.applicable_paradigms == ALL_PARADIGM_CLASSES, (
            f"{name} has applicable_paradigms != ALL_PARADIGM_CLASSES; "
            f"all registered effects should be universal mechanisms"
        )


def test_eligible_effects_returns_all_universals():
    from experiment_bot.effects.registry import eligible_effects
    eligible = eligible_effects(["conflict"])
    assert "autocorrelation" in eligible
    assert "lag1_pair_modulation" in eligible
    assert "post_event_slowing" in eligible


def test_registry_lookup_unknown_effect_raises():
    from experiment_bot.effects.registry import lookup_effect
    with pytest.raises(KeyError, match="unknown_effect"):
        lookup_effect("unknown_effect")


# ---------------------------------------------------------------------------
# Extensibility (audit finding M1) — register_effect public API
# ---------------------------------------------------------------------------

def test_register_effect_adds_universal_mechanism():
    """A new effect registered without applicable_paradigms is universal
    (the recommended default — paradigm-class filtering is no longer used)."""
    from experiment_bot.effects.registry import (
        EFFECT_REGISTRY, eligible_effects, register_effect,
    )
    name = "test_speed_accuracy_tradeoff"
    EFFECT_REGISTRY.pop(name, None)

    try:
        register_effect(
            name=name,
            handler=lambda state, cfg, rng: 0.0,
            params={"threshold": float},
        )
        # Universal effect appears in eligible_effects for any paradigm class.
        assert name in eligible_effects(["perceptual_decision"])
        assert name in eligible_effects(["interrupt"])
        # Other built-ins are still listed as universal too.
        assert "lag1_pair_modulation" in eligible_effects(["perceptual_decision"])
    finally:
        EFFECT_REGISTRY.pop(name, None)


def test_register_effect_universal_when_paradigms_omitted():
    from experiment_bot.effects.registry import (
        EFFECT_REGISTRY, eligible_effects, register_effect,
    )
    name = "test_universal_effect"
    EFFECT_REGISTRY.pop(name, None)
    try:
        register_effect(name=name, handler=lambda s, c, r: 0.0)
        assert name in eligible_effects(["any_class"])
        assert name in eligible_effects(["another_class"])
    finally:
        EFFECT_REGISTRY.pop(name, None)


def test_register_effect_rejects_duplicate_name():
    from experiment_bot.effects.registry import register_effect
    with pytest.raises(KeyError, match="already_registered"):
        # Use a known existing effect name (lag1_pair_modulation is built-in)
        register_effect(name="lag1_pair_modulation", handler=lambda s, c, r: 0.0)

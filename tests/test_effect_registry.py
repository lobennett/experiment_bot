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


def test_registry_contains_all_existing_effects():
    expected = {
        "autocorrelation",
        "fatigue_drift",
        "post_error_slowing",
        "condition_repetition",
        "pink_noise",
        "post_interrupt_slowing",
    }
    assert set(EFFECT_REGISTRY.keys()) >= expected


def test_existing_effects_have_universal_applicability():
    for name in ("autocorrelation", "fatigue_drift", "post_error_slowing",
                 "condition_repetition", "pink_noise", "post_interrupt_slowing"):
        assert EFFECT_REGISTRY[name].applicable_paradigms == ALL_PARADIGM_CLASSES


def test_eligible_effects_for_paradigm_class():
    from experiment_bot.effects.registry import eligible_effects
    eligible = eligible_effects(["conflict"])
    assert "autocorrelation" in eligible
    assert "post_error_slowing" in eligible


def test_registry_lookup_unknown_effect_raises():
    from experiment_bot.effects.registry import lookup_effect
    with pytest.raises(KeyError, match="unknown_effect"):
        lookup_effect("unknown_effect")


# ---------------------------------------------------------------------------
# Extensibility (audit finding M1) — register_effect public API
# ---------------------------------------------------------------------------

def test_register_effect_adds_paradigm_specific_handler():
    """A new effect registered for a novel paradigm class shows up in
    eligible_effects for that class but not for unrelated classes."""
    from experiment_bot.effects.registry import (
        EFFECT_REGISTRY, eligible_effects, register_effect,
    )
    name = "test_speed_accuracy_tradeoff"
    EFFECT_REGISTRY.pop(name, None)

    try:
        register_effect(
            name=name,
            handler=lambda state, cfg, rng: 0.0,
            applicable_paradigms=frozenset({"perceptual_decision"}),
            params={"threshold": float},
        )
        assert name in eligible_effects(["perceptual_decision"])
        assert name not in eligible_effects(["interrupt"])
        assert "post_error_slowing" in eligible_effects(["perceptual_decision"])
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
        register_effect(name="post_error_slowing", handler=lambda s, c, r: 0.0)

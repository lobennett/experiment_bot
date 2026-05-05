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

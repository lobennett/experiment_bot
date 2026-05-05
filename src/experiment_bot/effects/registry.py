from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any


# A sentinel meaning "applicable to any paradigm class"
ALL_PARADIGM_CLASSES = frozenset({"__ALL__"})


@dataclass
class EffectType:
    name: str
    params: dict[str, type]
    applicable_paradigms: frozenset[str]
    handler: Callable[..., float] | None        # filled in by Task A2
    validation_metric: Callable[..., Any] | None  # filled in by later tasks


# Skeleton: existing 6 effects, handler/validator None for now.
EFFECT_REGISTRY: dict[str, EffectType] = {
    "autocorrelation": EffectType(
        name="autocorrelation",
        params={"phi": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "fatigue_drift": EffectType(
        name="fatigue_drift",
        params={"drift_per_trial_ms": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "post_error_slowing": EffectType(
        name="post_error_slowing",
        params={"slowing_ms_min": float, "slowing_ms_max": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "condition_repetition": EffectType(
        name="condition_repetition",
        params={"facilitation_ms": float, "cost_ms": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "pink_noise": EffectType(
        name="pink_noise",
        params={"sd_ms": float, "hurst": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "post_interrupt_slowing": EffectType(
        name="post_interrupt_slowing",
        params={"slowing_ms_min": float, "slowing_ms_max": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
}


def lookup_effect(name: str) -> EffectType:
    if name not in EFFECT_REGISTRY:
        raise KeyError(f"unknown_effect: {name!r}")
    return EFFECT_REGISTRY[name]


def eligible_effects(paradigm_classes: list[str]) -> set[str]:
    """Return effects whose applicable_paradigms intersect the task's classes.

    Universal effects (applicable_paradigms == ALL_PARADIGM_CLASSES) always eligible.
    """
    out = set()
    for name, et in EFFECT_REGISTRY.items():
        if et.applicable_paradigms == ALL_PARADIGM_CLASSES:
            out.add(name)
        elif set(paradigm_classes) & et.applicable_paradigms:
            out.add(name)
    return out

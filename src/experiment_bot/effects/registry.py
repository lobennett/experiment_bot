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


# ---------------------------------------------------------------------------
# Wire handlers into the registry (Task A2)
# ---------------------------------------------------------------------------
from experiment_bot.effects import handlers as _h  # noqa: E402

EFFECT_REGISTRY["autocorrelation"].handler = _h.apply_autocorrelation
EFFECT_REGISTRY["fatigue_drift"].handler = _h.apply_fatigue_drift
EFFECT_REGISTRY["post_error_slowing"].handler = _h.apply_post_error_slowing
EFFECT_REGISTRY["condition_repetition"].handler = _h.apply_condition_repetition
EFFECT_REGISTRY["pink_noise"].handler = _h.apply_pink_noise
EFFECT_REGISTRY["post_interrupt_slowing"].handler = _h.apply_post_interrupt_slowing

EFFECT_REGISTRY["congruency_sequence"] = EffectType(
    name="congruency_sequence",
    params={"sequence_facilitation_ms": float, "sequence_cost_ms": float},
    applicable_paradigms=frozenset({"conflict"}),
    handler=_h.apply_cse,
    validation_metric=None,  # B3 fills in
)

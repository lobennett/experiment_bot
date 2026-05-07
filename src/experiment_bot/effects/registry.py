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
    # Optional typed dataclass for the effect's configuration. When set,
    # `TemporalEffectsConfig.from_dict` instantiates this class for the
    # effect's sub-dict; the handler then receives a typed instance via
    # attribute access. When None, the sub-dict is wrapped in a
    # SimpleNamespace so attribute access still works without a typed
    # contract. New effects can register without providing one.
    config_class: type | None = None


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


def register_effect(
    name: str,
    handler: Callable[..., float],
    applicable_paradigms: frozenset[str] | None = None,
    params: dict[str, type] | None = None,
    validation_metric: Callable[..., Any] | None = None,
) -> EffectType:
    """Register a new EffectType under ``name``. Returns the registered entry.

    The effect registry is the bot's "standard library" of paradigm
    behaviors. New paradigm classes that need effects beyond the seven
    built-in entries (autocorrelation, fatigue_drift, post_error_slowing,
    condition_repetition, pink_noise, post_interrupt_slowing,
    congruency_sequence) can register their own handlers via this
    function. The handler is a Python callable so the math is auditable;
    the registration itself is a one-liner that doesn't require editing
    this file.

    `applicable_paradigms` defaults to ALL_PARADIGM_CLASSES (universal).
    Pass a frozenset of class names to scope the effect to a specific
    paradigm class. `params` is the effect's parameter schema (used by
    Stage 2 to inform the LLM what fields to populate). `validation_metric`
    is the callable the oracle uses to score this effect against
    canonical norms; pass None if the effect is sampler-side only.

    Raises KeyError if ``name`` already exists — overwriting an effect
    silently would mask configuration errors.
    """
    if name in EFFECT_REGISTRY:
        raise KeyError(f"effect_already_registered: {name!r} (use a different name)")
    EFFECT_REGISTRY[name] = EffectType(
        name=name,
        params=params or {},
        applicable_paradigms=applicable_paradigms or ALL_PARADIGM_CLASSES,
        handler=handler,
        validation_metric=validation_metric,
    )
    return EFFECT_REGISTRY[name]


# ---------------------------------------------------------------------------
# Wire handlers into the registry (Task A2)
# ---------------------------------------------------------------------------
from experiment_bot.effects import handlers as _h  # noqa: E402
from experiment_bot.effects.validation_metrics import cse_magnitude  # noqa: E402

EFFECT_REGISTRY["autocorrelation"].handler = _h.apply_autocorrelation
EFFECT_REGISTRY["fatigue_drift"].handler = _h.apply_fatigue_drift
EFFECT_REGISTRY["post_error_slowing"].handler = _h.apply_post_error_slowing
EFFECT_REGISTRY["condition_repetition"].handler = _h.apply_condition_repetition
EFFECT_REGISTRY["pink_noise"].handler = _h.apply_pink_noise
EFFECT_REGISTRY["post_interrupt_slowing"].handler = _h.apply_post_interrupt_slowing

# Wire typed config classes for the canonical six effects so
# TemporalEffectsConfig.from_dict instantiates them with full type info.
from experiment_bot.core.config import (  # noqa: E402
    AutocorrelationConfig, FatigueDriftConfig, PostErrorSlowingConfig,
    ConditionRepetitionConfig, PinkNoiseConfig, PostInterruptSlowingConfig,
)
EFFECT_REGISTRY["autocorrelation"].config_class = AutocorrelationConfig
EFFECT_REGISTRY["fatigue_drift"].config_class = FatigueDriftConfig
EFFECT_REGISTRY["post_error_slowing"].config_class = PostErrorSlowingConfig
EFFECT_REGISTRY["condition_repetition"].config_class = ConditionRepetitionConfig
EFFECT_REGISTRY["pink_noise"].config_class = PinkNoiseConfig
EFFECT_REGISTRY["post_interrupt_slowing"].config_class = PostInterruptSlowingConfig

EFFECT_REGISTRY["congruency_sequence"] = EffectType(
    name="congruency_sequence",
    params={
        "sequence_facilitation_ms": float,
        "sequence_cost_ms": float,
        # Condition labels chosen by the Reasoner per task. The handler
        # uses these instead of magic strings so paradigms with different
        # condition naming conventions (e.g. "compatible"/"incompatible")
        # work without code changes.
        "high_conflict_condition": str,
        "low_conflict_condition": str,
    },
    applicable_paradigms=frozenset({"conflict"}),
    handler=_h.apply_cse,
    validation_metric=None,  # B3 fills in
)

EFFECT_REGISTRY["congruency_sequence"].validation_metric = cse_magnitude

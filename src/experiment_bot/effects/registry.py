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


# Generic universal mechanisms only. The bot's library does not name
# any paradigm-specific effect (CSE, Gratton, post-interrupt-slowing,
# etc.) — each is a *configuration* of a generic mechanism that the
# Reasoner emits in the TaskCard from its literature scrape. Adding
# new mechanisms is a `register_effect()` call; never required for
# adding new paradigms.
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
    # Generic 2-back interaction. Subsumes CSE, sequential priming,
    # and any other mechanism whose RT delta is determined by the
    # (prev_condition, current_condition) pair. The Reasoner supplies
    # a modulation_table per task; effect inactive when table empty.
    "lag1_pair_modulation": EffectType(
        name="lag1_pair_modulation",
        params={
            "modulation_table": list,  # list of {prev, curr, delta_ms or delta_ms_min/max}
            "skip_after_error": bool,
        },
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    # Generic post-event slowing. Subsumes both post-error and
    # post-inhibition slowing. The Reasoner supplies a list of
    # triggers (event types + slowing distributions) per task.
    "post_event_slowing": EffectType(
        name="post_event_slowing",
        params={
            "triggers": list,  # list of {event, slowing_ms_min, slowing_ms_max, ...}
        },
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

    The effect registry is the bot's "standard library" of generic
    temporal mechanisms. The six built-ins (autocorrelation,
    fatigue_drift, condition_repetition, pink_noise,
    lag1_pair_modulation, post_event_slowing) are intended to cover
    most speeded-decision paradigms via per-task configuration. A new
    mechanism is justified only if at least two paradigms with
    distinct paradigm-class memberships would use it; otherwise it is
    a configuration of an existing mechanism. Mechanisms must be named
    in mechanism vocabulary (not paradigm vocabulary) and read all
    paradigm-specific data from the cfg argument.

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
from experiment_bot.effects.validation_metrics import lag1_pair_contrast  # noqa: E402

EFFECT_REGISTRY["autocorrelation"].handler = _h.apply_autocorrelation
EFFECT_REGISTRY["fatigue_drift"].handler = _h.apply_fatigue_drift
EFFECT_REGISTRY["condition_repetition"].handler = _h.apply_condition_repetition
EFFECT_REGISTRY["pink_noise"].handler = _h.apply_pink_noise
EFFECT_REGISTRY["lag1_pair_modulation"].handler = _h.apply_lag1_pair_modulation
EFFECT_REGISTRY["post_event_slowing"].handler = _h.apply_post_event_slowing

# Wire typed config classes for the canonical mechanisms so
# TemporalEffectsConfig.from_dict instantiates them with full type info.
# The two new generic mechanisms (lag1_pair_modulation, post_event_slowing)
# don't have typed config classes — their cfgs are SimpleNamespaces
# wrapping the TaskCard dict. New mechanisms can register without one.
from experiment_bot.core.config import (  # noqa: E402
    AutocorrelationConfig, FatigueDriftConfig,
    ConditionRepetitionConfig, PinkNoiseConfig,
)
EFFECT_REGISTRY["autocorrelation"].config_class = AutocorrelationConfig
EFFECT_REGISTRY["fatigue_drift"].config_class = FatigueDriftConfig
EFFECT_REGISTRY["condition_repetition"].config_class = ConditionRepetitionConfig
EFFECT_REGISTRY["pink_noise"].config_class = PinkNoiseConfig

# Validation-metric assignment: lag1_pair_contrast is the generic
# 2-back contrast computation. Specific paradigm-named metrics
# (cse_magnitude for conflict tasks) are configured per norms file
# in the oracle's METRIC_REGISTRY rather than baked into the effect.
EFFECT_REGISTRY["lag1_pair_modulation"].validation_metric = lag1_pair_contrast

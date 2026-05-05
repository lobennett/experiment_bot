"""Trial-time RT modulation handlers for each effect type.

Each handler signature: handler(state, cfg, rng) -> float (delta_rt_ms).

- ``state`` is a :class:`SamplerState` dataclass carrying per-trial context
  (mu/sigma/tau from the current distribution, prev_rt, prev_condition,
  trial_index, prev_error, prev_interrupt_detected, condition, pink_buffer).
- ``cfg`` is the typed effect config object from ``TemporalEffectsConfig``
  (e.g. ``AutocorrelationConfig``, ``FatigueDriftConfig``, …).
- ``rng`` is a ``numpy.random.Generator`` for any stochastic draws.

Handlers return a float: the RT modulation in ms to add to the raw sample.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SamplerState:
    """Snapshot of per-trial sampler state passed to every handler."""

    mu: float
    sigma: float
    tau: float
    prev_rt: float | None
    prev_condition: str | None
    trial_index: int
    prev_error: bool
    prev_interrupt_detected: bool
    condition: str
    pink_buffer: Any | None = None  # numpy array or None


# ---------------------------------------------------------------------------
# Individual effect handlers
# ---------------------------------------------------------------------------

def apply_autocorrelation(state: SamplerState, cfg, rng) -> float:
    """AR(1) pull: drift current RT toward previous RT."""
    if not cfg.enabled:
        return 0.0
    if state.prev_rt is None:
        return 0.0
    if cfg.phi <= 0:
        return 0.0
    mean_rt = state.mu + state.tau
    deviation = state.prev_rt - mean_rt
    return cfg.phi * deviation


def apply_fatigue_drift(state: SamplerState, cfg, rng) -> float:
    """Monotone upward drift across trials."""
    if not cfg.enabled:
        return 0.0
    return state.trial_index * cfg.drift_per_trial_ms


def apply_post_error_slowing(state: SamplerState, cfg, rng) -> float:
    """Uniform-random RT slowing following an error trial.

    Note: In the current architecture this effect is applied by the
    executor (``executor.py``) *after* calling ``sample_rt_with_fallback``,
    so this handler is wired into the registry but is not called from
    ``ResponseSampler._apply_temporal_effects``.  It is provided here so
    that the registry is the single source of truth and future refactors can
    move the call site into the sampler.
    """
    if not cfg.enabled:
        return 0.0
    if not state.prev_error or state.prev_interrupt_detected:
        return 0.0
    return float(rng.uniform(cfg.slowing_ms_min, cfg.slowing_ms_max))


def apply_condition_repetition(state: SamplerState, cfg, rng) -> float:
    """Gratton effect: faster on repetitions, slower on alternations."""
    if not cfg.enabled:
        return 0.0
    if state.prev_condition is None:
        return 0.0
    if state.condition == state.prev_condition:
        return -cfg.facilitation_ms
    return cfg.cost_ms


def apply_pink_noise(state: SamplerState, cfg, rng) -> float:
    """1/f (pink) noise scaled by sd_ms."""
    if not cfg.enabled:
        return 0.0
    if state.pink_buffer is None:
        return 0.0
    n = len(state.pink_buffer)
    return float(state.pink_buffer[state.trial_index % n] * cfg.sd_ms)


def apply_post_interrupt_slowing(state: SamplerState, cfg, rng) -> float:
    """Uniform-random RT slowing following a trial interrupt.

    Note: In the current architecture this effect is applied by the
    executor (``executor.py``) *after* calling ``sample_rt_with_fallback``,
    so this handler is wired into the registry but is not called from
    ``ResponseSampler._apply_temporal_effects``.  It is provided here so
    that the registry is the single source of truth.
    """
    if not cfg.enabled:
        return 0.0
    if not state.prev_interrupt_detected:
        return 0.0
    return float(rng.uniform(cfg.slowing_ms_min, cfg.slowing_ms_max))


def apply_cse(state: SamplerState, params: dict, rng) -> float:
    """Congruency sequence effect (Gratton 1992; Egner 2007).

    The conflict effect (incongruent − congruent RT) is REDUCED following
    an incongruent trial vs following a congruent trial.

    On incongruent current trials only:
      - if previous was incongruent: subtract `sequence_facilitation_ms`
      - if previous was congruent: add `sequence_cost_ms`
    Congruent current trials are not modulated. Skipped after error trials
    (error contamination).
    """
    if not params.get("enabled", False):
        return 0.0
    if state.prev_condition is None or state.prev_error:
        return 0.0
    if state.condition != "incongruent":
        return 0.0
    if state.prev_condition == "incongruent":
        return -float(params.get("sequence_facilitation_ms", 0.0))
    if state.prev_condition == "congruent":
        return float(params.get("sequence_cost_ms", 0.0))
    return 0.0

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
    """Snapshot of per-trial sampler state passed to every handler.

    `expected_rt` is the sampler's population-mean RT, used by handlers
    that need a baseline (e.g. autocorrelation). Each sampler family
    computes it from its parameters: ex-Gaussian = mu + tau,
    lognormal = exp(mu + sigma^2/2), shifted-Wald = shift + boundary/drift.

    `mu`, `sigma`, `tau` are kept for back-compat with handlers/tests
    that reference ex-Gaussian parameters directly. For non-ex-Gaussian
    samplers they are 0.0; handlers that need a generic mean should use
    `expected_rt` instead.
    """

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
    expected_rt: float = 0.0


# ---------------------------------------------------------------------------
# Individual effect handlers
# ---------------------------------------------------------------------------

def apply_autocorrelation(state: SamplerState, cfg, rng) -> float:
    """AR(1) pull: drift current RT toward previous RT.

    Uses `state.expected_rt` (population mean) as the baseline. For
    back-compat, falls back to `state.mu + state.tau` (ex-Gaussian
    convention) when `expected_rt` is 0.0 — which it is for any
    SamplerState constructed without specifying it.
    """
    if not cfg.enabled:
        return 0.0
    if state.prev_rt is None:
        return 0.0
    if cfg.phi <= 0:
        return 0.0
    mean_rt = state.expected_rt or (state.mu + state.tau)
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
    via :func:`compute_pes_delta` so that multi-trial decay can be expressed.
    This wrapper exists for the registry's benefit and matches the legacy
    one-trial behavior.
    """
    if not cfg.enabled:
        return 0.0
    if not state.prev_error or state.prev_interrupt_detected:
        return 0.0
    return float(rng.uniform(cfg.slowing_ms_min, cfg.slowing_ms_max))


def compute_pes_delta(
    decay_weights: list,
    recent_errors,
    rng,
    slowing_ms_min: float,
    slowing_ms_max: float,
) -> float:
    """Compute the PES contribution for the current trial given a decay profile.

    `recent_errors` is an iterable of booleans where index 0 is the most-recent
    completed trial, index 1 is two trials back, etc. (i.e. `appendleft`-fed
    deque). `decay_weights[i]` is the weight applied to the i-th most-recent
    trial's error contribution.

    When `decay_weights` is empty, defaults to ``[1.0]`` (one-trial PES — the
    historical behavior). When non-empty, the bot's PES contribution is the
    weighted sum across the recent window:

        sum(weight_i * uniform(ms_min, ms_max) if recent_errors[i] else 0)

    Each error draws its own uniform sample (so a 3-trial-back error can add
    a different bump than a 1-trial-back error). Sum of weights does not
    need to equal 1 — the literature defines what's plausible per paradigm.
    """
    if not decay_weights:
        decay_weights = [1.0]
    total = 0.0
    for w, was_err in zip(decay_weights, recent_errors):
        if was_err:
            total += float(w) * float(rng.uniform(slowing_ms_min, slowing_ms_max))
    return total


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


def _cfg_get(cfg, name: str, default=None):
    """Read `name` from a config that may be a dict OR a typed
    dataclass / SimpleNamespace. Lets handlers accept either shape
    so callers don't have to convert.
    """
    if isinstance(cfg, dict):
        return cfg.get(name, default)
    return getattr(cfg, name, default)


def apply_cse(state: SamplerState, cfg, rng) -> float:
    """Congruency sequence effect (Gratton 1992; Egner 2007).

    The conflict effect (high-conflict − low-conflict RT) is REDUCED
    following a high-conflict trial vs following a low-conflict trial.

    The condition labels are taken from the TaskCard via
    `cfg.high_conflict_condition` and `cfg.low_conflict_condition`,
    so paradigms with non-Stroop labels (e.g. "compatible"/"incompatible",
    "same"/"different") work without code changes. Defaults to
    "incongruent"/"congruent" when fields are missing or empty (back-compat).

    On high-conflict current trials only:
      - if previous was high-conflict: subtract `sequence_facilitation_ms`
      - if previous was low-conflict: add `sequence_cost_ms`
    Low-conflict current trials are not modulated. Skipped after error
    trials (error contamination).

    `cfg` may be a typed dataclass instance, a SimpleNamespace, or a
    raw dict (test fixtures often use dicts). `_cfg_get` reads either.
    """
    if not _cfg_get(cfg, "enabled", False):
        return 0.0
    if state.prev_condition is None or state.prev_error:
        return 0.0
    high = _cfg_get(cfg, "high_conflict_condition", "") or "incongruent"
    low = _cfg_get(cfg, "low_conflict_condition", "") or "congruent"
    if state.condition != high:
        return 0.0
    if state.prev_condition == high:
        return -float(_cfg_get(cfg, "sequence_facilitation_ms", 0.0))
    if state.prev_condition == low:
        return float(_cfg_get(cfg, "sequence_cost_ms", 0.0))
    return 0.0

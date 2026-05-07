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


def apply_lag1_pair_modulation(state: SamplerState, cfg, rng) -> float:
    """Generic lag-1 trial-pair modulation: arbitrary RT delta indexed
    by (previous_condition, current_condition).

    The bot's standard library does not name any specific paradigm
    effect (CSE, Gratton, sequence priming, etc.). Each is a
    *configuration* of this generic mechanism: the TaskCard supplies
    a modulation_table mapping condition-pair tuples to RT-delta
    values, and the handler applies the matching entry.

    Cfg fields:
      - `enabled` (bool): off by default; the TaskCard must opt in.
      - `skip_after_error` (bool, default True): if True, no
        modulation is applied on the trial after an error. The
        canonical CSE protocol skips post-error trials (error
        contamination); paradigms whose literature does not
        require this can override.
      - `modulation_table` (list of dicts): each entry has:
          - `prev` (str): the previous trial's condition label
          - `curr` (str): the current trial's condition label
          - One of:
            - `delta_ms` (float): fixed RT delta in ms
            - `delta_ms_min` and `delta_ms_max` (floats): uniform-
              random RT delta sampled at trial time
        First matching entry wins. Entries that don't specify
        either form contribute 0.

    Configurations: CSE for Stroop is e.g. modulation_table =
    [{prev: incongruent, curr: incongruent, delta_ms: -50},
     {prev: congruent, curr: incongruent, delta_ms: 20}].
    Trial-by-trial repetition priming would be a different table.
    Tasks with no 2-back interaction simply leave enabled=False.
    """
    if not _cfg_get(cfg, "enabled", False):
        return 0.0
    if state.prev_condition is None:
        return 0.0
    if _cfg_get(cfg, "skip_after_error", True) and state.prev_error:
        return 0.0
    table = _cfg_get(cfg, "modulation_table", []) or []
    for entry in table:
        prev = entry.get("prev") if isinstance(entry, dict) else getattr(entry, "prev", None)
        curr = entry.get("curr") if isinstance(entry, dict) else getattr(entry, "curr", None)
        if state.prev_condition != prev or state.condition != curr:
            continue
        get = entry.get if isinstance(entry, dict) else (lambda k, default=None: getattr(entry, k, default))
        if get("delta_ms_min") is not None and get("delta_ms_max") is not None:
            return float(rng.uniform(get("delta_ms_min"), get("delta_ms_max")))
        if get("delta_ms") is not None:
            return float(get("delta_ms"))
        return 0.0
    return 0.0


def apply_post_event_slowing(state: SamplerState, cfg, rng) -> float:
    """Generic post-event slowing: RT slowing on the trial following a
    triggering event (error, successful inhibition, etc.).

    Subsumes both classical post-error slowing (PES) and post-
    inhibition slowing under one mechanism. The bot's library has no
    paradigm-specific event names; events are configured per task.

    Cfg fields:
      - `enabled` (bool): off by default.
      - `triggers` (list of dicts in priority order): first matching
        trigger wins. Each trigger has:
          - `event` (str): one of "error" or "interrupt" (matches
            SamplerState's `prev_error` and `prev_interrupt_detected`
            respectively).
          - `slowing_ms_min`, `slowing_ms_max` (floats): uniform-
            random slowing in ms.
          - `decay_weights` (list[float], optional): per-position
            weights when multi-trial decay is documented in the
            literature for this paradigm. The most recent N trials
            (oldest first in `state.recent_*`) are weighted; only
            error-event triggers consult decay_weights for now.
            When omitted or empty, single-trial behavior applies.
          - `exclusive_with_prior_triggers` (bool, default True):
            when True, this trigger only fires if no earlier trigger
            in the list matched. This implements priority semantics
            (e.g. "interrupt takes priority over error").

    Tasks with no post-event slowing leave enabled=False.
    """
    if not _cfg_get(cfg, "enabled", False):
        return 0.0
    triggers = _cfg_get(cfg, "triggers", []) or []
    matched_already = False
    for trigger in triggers:
        get = trigger.get if isinstance(trigger, dict) else (lambda k, default=None: getattr(trigger, k, default))
        event = get("event")
        if get("exclusive_with_prior_triggers", True) and matched_already:
            continue
        # Check whether this trigger's event fired
        fired = False
        if event == "interrupt" and state.prev_interrupt_detected:
            fired = True
        elif event == "error" and state.prev_error:
            fired = True
        if not fired:
            continue
        matched_already = True
        ms_min = float(get("slowing_ms_min", 0.0) or 0.0)
        ms_max = float(get("slowing_ms_max", 0.0) or 0.0)
        return float(rng.uniform(ms_min, ms_max))
    return 0.0


def apply_cse(state: SamplerState, cfg, rng) -> float:
    """Deprecated. Retained for callers that still pass the old
    CSE-shaped config (high_conflict_condition / low_conflict_condition
    + sequence_facilitation_ms / sequence_cost_ms). Internally
    converts to the generic lag-1 modulation shape and delegates.
    Stage 2 should now emit `lag1_pair_modulation` directly.
    """
    if not _cfg_get(cfg, "enabled", False):
        return 0.0
    high = _cfg_get(cfg, "high_conflict_condition", "") or "incongruent"
    low = _cfg_get(cfg, "low_conflict_condition", "") or "congruent"
    fac = _cfg_get(cfg, "sequence_facilitation_ms", 0.0)
    cost = _cfg_get(cfg, "sequence_cost_ms", 0.0)
    from types import SimpleNamespace
    shimmed = SimpleNamespace(
        enabled=True,
        skip_after_error=True,
        modulation_table=[
            {"prev": high, "curr": high, "delta_ms": -float(fac)},
            {"prev": low, "curr": high, "delta_ms": float(cost)},
        ],
    )
    return apply_lag1_pair_modulation(state, shimmed, rng)

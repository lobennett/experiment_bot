from __future__ import annotations

import copy

import numpy as np

from experiment_bot.core.config import (
    BetweenSubjectJitterConfig,
    DistributionConfig,
    TaskConfig,
    TemporalEffectsConfig,
)
from experiment_bot.effects.registry import EFFECT_REGISTRY, eligible_effects
from experiment_bot.effects.handlers import SamplerState


class ExGaussianSampler:
    def __init__(self, mu: float, sigma: float, tau: float, seed: int | None = None):
        self.mu = mu
        self.sigma = sigma
        self.tau = tau
        self._rng = np.random.default_rng(seed)

    def sample(self) -> float:
        gaussian = self._rng.normal(self.mu, self.sigma)
        exponential = self._rng.exponential(self.tau)
        return float(gaussian + exponential)

    @property
    def expected_rt(self) -> float:
        """Population mean of the ex-Gaussian: mu + tau."""
        return self.mu + self.tau


class LogNormalSampler:
    """Lognormal RT sampler.

    Some perception/decision paradigms fit lognormal RTs better than
    ex-Gaussian. Parameterized by `mu` and `sigma` of the underlying
    normal (i.e. the parameters numpy.random.lognormal expects).

    The Reasoner picks this distribution by setting
    `response_distributions.<cond>.value.distribution = "lognormal"` with
    `params = {"mu": ..., "sigma": ...}`.
    """

    def __init__(self, mu: float, sigma: float, seed: int | None = None):
        self.mu = mu
        self.sigma = sigma
        self._rng = np.random.default_rng(seed)

    def sample(self) -> float:
        return float(self._rng.lognormal(self.mu, self.sigma))

    @property
    def expected_rt(self) -> float:
        """Population mean of lognormal: exp(mu + sigma^2 / 2)."""
        return float(np.exp(self.mu + self.sigma ** 2 / 2.0))


class ShiftedWaldSampler:
    """Shifted-Wald (inverse-Gaussian) RT sampler.

    Used for diffusion-style speeded decisions; the shift parameter
    captures non-decision time. Parameterized by `drift_rate`,
    `boundary` (inverse mean parameter), and `shift_ms`. Returns
    the sampled RT in milliseconds.

    Approximation via numpy.random.wald (inverse Gaussian) plus shift.
    The Reasoner picks this distribution by setting
    `response_distributions.<cond>.value.distribution = "shifted_wald"`
    with `params = {"drift_rate": ..., "boundary": ..., "shift_ms": ...}`.
    """

    def __init__(self, drift_rate: float, boundary: float, shift_ms: float, seed: int | None = None):
        self.drift_rate = drift_rate
        self.boundary = boundary
        self.shift_ms = shift_ms
        self._rng = np.random.default_rng(seed)

    def sample(self) -> float:
        # Inverse Gaussian: mean = boundary / drift_rate, scale = boundary**2
        # numpy.random.wald takes (mean, scale)
        mean = self.boundary / max(self.drift_rate, 1e-6)
        scale = self.boundary ** 2
        decision_time = self._rng.wald(mean, scale)
        return float(decision_time + self.shift_ms)

    @property
    def expected_rt(self) -> float:
        """Population mean: shift_ms + boundary / drift_rate."""
        return float(self.shift_ms + self.boundary / max(self.drift_rate, 1e-6))


def _build_sampler(dist_config: "DistributionConfig", seed: int | None):
    """Construct the appropriate sampler for a DistributionConfig.

    Dispatches by `dist_config.distribution`:
      - "ex_gaussian"   → ExGaussianSampler(mu, sigma, tau)
      - "lognormal"     → LogNormalSampler(mu, sigma)
      - "shifted_wald"  → ShiftedWaldSampler(drift_rate, boundary, shift_ms)

    Raises ValueError for unknown distribution names. The Reasoner picks
    the distribution per condition based on which family the literature
    reports for the paradigm.
    """
    name = dist_config.distribution
    p = dist_config.params
    if name == "ex_gaussian":
        return ExGaussianSampler(mu=p["mu"], sigma=p["sigma"], tau=p["tau"], seed=seed)
    if name == "lognormal":
        return LogNormalSampler(mu=p["mu"], sigma=p["sigma"], seed=seed)
    if name == "shifted_wald":
        return ShiftedWaldSampler(
            drift_rate=p["drift_rate"], boundary=p["boundary"],
            shift_ms=p["shift_ms"], seed=seed,
        )
    raise ValueError(
        f"Unknown distribution {name!r} (supported: ex_gaussian, lognormal, shifted_wald). "
        f"Add a sampler class + dispatch entry in core/distributions.py if your paradigm "
        f"requires a different family."
    )


def _generate_pink_noise(n: int, hurst: float, rng: np.random.Generator) -> np.ndarray:
    """Spectral synthesis of fractional Gaussian noise (1/f^alpha)."""
    alpha = 2.0 * hurst - 1.0
    freqs = np.fft.rfftfreq(n)
    freqs[0] = 1.0  # avoid div-by-zero
    power_scale = freqs ** (-alpha / 2.0)
    power_scale[0] = 0.0  # zero DC
    white = rng.standard_normal(len(freqs)) + 1j * rng.standard_normal(len(freqs))
    pink = np.fft.irfft(white * power_scale, n=n)
    std = pink.std()
    if std > 0:
        pink = (pink - pink.mean()) / std
    return pink


class ResponseSampler:
    # Effects that are applied by the executor AFTER the sampler returns,
    # not by the sampler itself. The executor invokes them with the
    # right SamplerState (`prev_error`, `prev_interrupt_detected`) at
    # the right point in the trial loop. The sampler skips them in its
    # iteration to avoid double-invocation.
    _EXECUTOR_APPLIED_EFFECTS = frozenset({"post_event_slowing"})

    def __init__(
        self,
        distributions: dict[str, DistributionConfig],
        temporal_effects: TemporalEffectsConfig | None = None,
        floor_ms: float = 150.0,
        seed: int | None = None,
        paradigm_classes: list[str] | None = None,
    ):
        if temporal_effects is None:
            temporal_effects = TemporalEffectsConfig()
        self._effects = temporal_effects
        self._paradigm_classes = list(paradigm_classes or [])
        self._floor_ms = floor_ms
        self._prev_condition: str | None = None
        self._prev_rt: float | None = None
        self._trial_index: int = 0
        self._samplers: dict[str, ExGaussianSampler] = {}
        self._rng = np.random.default_rng(seed)

        # Pink noise buffer
        if self._effects.pink_noise.enabled:
            if self._effects.pink_noise.hurst <= 0:
                raise ValueError("pink_noise.hurst must be > 0 when pink noise is enabled")
            self._pink_buffer = _generate_pink_noise(
                2048, self._effects.pink_noise.hurst, np.random.default_rng(seed)
            )
        else:
            self._pink_buffer = None

        for condition, dist_config in distributions.items():
            self._samplers[condition] = _build_sampler(dist_config, seed)

    def _apply_temporal_effects(
        self, raw_rt: float, sampler, condition: str,
        skip_condition_repetition: bool = False,
    ) -> float:
        """Apply sequential temporal effects to a raw RT sample.

        Iterates the effect registry in insertion order. Effects in
        ``_EXECUTOR_APPLIED_EFFECTS`` (currently ``post_event_slowing``)
        are applied by the executor at the right point in the trial
        loop and skipped here.

        Sampler-family-specific attributes (mu/sigma/tau for ex-Gaussian)
        are read defensively so non-ex-Gaussian samplers (lognormal,
        shifted-Wald) work too. `expected_rt` is the family-agnostic mean
        used by handlers like autocorrelation.
        """
        rt = raw_rt

        state = SamplerState(
            mu=getattr(sampler, "mu", 0.0),
            sigma=getattr(sampler, "sigma", 0.0),
            tau=getattr(sampler, "tau", 0.0),
            expected_rt=getattr(sampler, "expected_rt", 0.0),
            prev_rt=self._prev_rt,
            prev_condition=self._prev_condition,
            trial_index=self._trial_index,
            prev_error=False,
            prev_interrupt_detected=False,
            condition=condition,
            pink_buffer=self._pink_buffer,
        )

        # Iterate the effect registry, paradigm-class-filtered. Each
        # registered handler whose `applicable_paradigms` matches the
        # task's classes (or that's universal) gets invoked with its
        # config from `self._effects`. Handlers are commutative on
        # `state` (none mutate it mid-iteration), so iteration order
        # only affects floating-point summation. Effects in
        # `_EXECUTOR_APPLIED_EFFECTS` (post_event_slowing) are applied
        # by executor.py after the sampler returns; they're skipped
        # here to avoid double-invocation.
        eligible = eligible_effects(self._paradigm_classes)
        for name in EFFECT_REGISTRY:  # registry-insertion order for determinism
            if name not in eligible:
                continue
            if name in self._EXECUTOR_APPLIED_EFFECTS:
                continue
            effect_type = EFFECT_REGISTRY[name]
            if effect_type.handler is None:
                continue
            if name == "condition_repetition" and skip_condition_repetition:
                continue
            cfg = self._effects.get(name)
            if cfg is None:
                continue
            rt += effect_type.handler(state, cfg, self._rng)

        rt = max(rt, self._floor_ms)
        self._prev_rt = rt
        self._prev_condition = condition
        self._trial_index += 1
        return rt

    def sample_rt(self, condition: str, skip_condition_repetition: bool = False) -> float:
        if condition not in self._samplers:
            raise KeyError(f"Unknown condition: {condition}")
        sampler = self._samplers[condition]
        raw_rt = sampler.sample()
        return self._apply_temporal_effects(raw_rt, sampler, condition, skip_condition_repetition)

    def sample_rt_with_fallback(self, condition: str, skip_condition_repetition: bool = False) -> float:
        """Sample RT for condition, falling back to first available distribution."""
        if condition in self._samplers:
            sampler = self._samplers[condition]
        elif self._samplers:
            sampler = next(iter(self._samplers.values()))
        else:
            # No samplers configured at all — should not happen in production
            # (the Reasoner is required to emit at least one
            # response_distribution per task). Raising here surfaces the
            # configuration error instead of silently producing magic-
            # number RTs.
            raise ValueError(
                f"ResponseSampler has no distributions configured; cannot sample RT for "
                f"condition {condition!r}. Check that the TaskCard's response_distributions "
                f"block is non-empty."
            )
        raw_rt = sampler.sample()
        return self._apply_temporal_effects(raw_rt, sampler, condition, skip_condition_repetition)


def jitter_distributions(config: TaskConfig, rng: np.random.Generator) -> TaskConfig:
    """Apply between-subject jitter to distribution params and performance targets.

    Creates a deep copy of the config so the original (cached) config is not mutated.
    Each session gets slightly different parameters, mimicking natural between-subject
    variability (human SD of mean RT ~ 50-80ms).
    """
    config = copy.deepcopy(config)
    bsj = config.between_subject_jitter

    # If no jitter configured, return unchanged
    if bsj.rt_mean_sd_ms == 0 and bsj.accuracy_sd == 0:
        return config

    # Shared between-subject speed shift (a fast person is fast on all conditions)
    # preserves inter-condition differences like switch cost.
    if bsj.rt_mean_sd_ms > 0:
        shared_mu_shift = rng.normal(0, bsj.rt_mean_sd_ms)
    else:
        shared_mu_shift = 0.0

    for dist in config.response_distributions.values():
        if dist.distribution == "ex_gaussian":
            if bsj.rt_mean_sd_ms > 0 or bsj.rt_condition_sd_ms > 0:
                condition_shift = rng.normal(0, bsj.rt_condition_sd_ms) if bsj.rt_condition_sd_ms > 0 else 0.0
                dist.params["mu"] += shared_mu_shift + condition_shift
            lo, hi = bsj.sigma_tau_range
            if lo != hi:
                dist.params["sigma"] *= rng.uniform(lo, hi)
                dist.params["tau"] *= rng.uniform(lo, hi)

    # Jitter per-condition accuracy values, clipped to the configured
    # plausibility range (Reasoner-determined per paradigm class).
    if bsj.accuracy_sd > 0:
        acc_lo, acc_hi = bsj.accuracy_clip_range
        for cond, acc_base in config.performance.accuracy.items():
            config.performance.accuracy[cond] = float(
                np.clip(acc_base + rng.normal(0, bsj.accuracy_sd), acc_lo, acc_hi)
            )

    # Jitter per-condition omission rates, clipped to the configured range.
    if bsj.omission_sd > 0:
        om_lo, om_hi = bsj.omission_clip_range
        for cond, om_base in config.performance.omission_rate.items():
            config.performance.omission_rate[cond] = float(
                np.clip(om_base + rng.normal(0, bsj.omission_sd), om_lo, om_hi)
            )

    return config

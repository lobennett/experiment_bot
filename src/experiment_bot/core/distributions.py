from __future__ import annotations

import copy

import numpy as np

from experiment_bot.core.config import (
    BetweenSubjectJitterConfig,
    DistributionConfig,
    TaskConfig,
    TemporalEffectsConfig,
)


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
    def __init__(
        self,
        distributions: dict[str, DistributionConfig],
        temporal_effects: TemporalEffectsConfig | None = None,
        floor_ms: float = 150.0,
        seed: int | None = None,
    ):
        if temporal_effects is None:
            temporal_effects = TemporalEffectsConfig()
        self._effects = temporal_effects
        self._floor_ms = floor_ms
        self._prev_condition: str | None = None
        self._prev_rt: float | None = None
        self._trial_index: int = 0
        self._samplers: dict[str, ExGaussianSampler] = {}

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
            if dist_config.distribution == "ex_gaussian":
                self._samplers[condition] = ExGaussianSampler(
                    mu=dist_config.params["mu"],
                    sigma=dist_config.params["sigma"],
                    tau=dist_config.params["tau"],
                    seed=seed,
                )

    def _apply_temporal_effects(
        self, raw_rt: float, sampler: ExGaussianSampler, condition: str,
        skip_condition_repetition: bool = False,
    ) -> float:
        """Apply sequential temporal effects to a raw RT sample."""
        rt = raw_rt

        # AR(1): pull current RT toward previous RT
        if (
            self._effects.autocorrelation.enabled
            and self._prev_rt is not None
            and self._effects.autocorrelation.phi > 0
        ):
            mean_rt = sampler.mu + sampler.tau
            deviation = self._prev_rt - mean_rt
            rt += self._effects.autocorrelation.phi * deviation

        # Condition repetition (Gratton) effect
        if (
            self._effects.condition_repetition.enabled
            and not skip_condition_repetition
            and self._prev_condition is not None
        ):
            if condition == self._prev_condition:
                rt -= self._effects.condition_repetition.facilitation_ms
            else:
                rt += self._effects.condition_repetition.cost_ms

        # 1/f (pink) noise: long-range temporal correlations
        if self._pink_buffer is not None:
            pink_idx = self._trial_index % len(self._pink_buffer)
            rt += self._pink_buffer[pink_idx] * self._effects.pink_noise.sd_ms

        # Fatigue drift: slow upward trend across experiment
        if self._effects.fatigue_drift.enabled:
            rt += self._trial_index * self._effects.fatigue_drift.drift_per_trial_ms

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
            # No samplers — apply pink noise + drift without AR(1)/Gratton
            rt = 500.0
            if self._effects.fatigue_drift.enabled:
                rt += self._trial_index * self._effects.fatigue_drift.drift_per_trial_ms
            if self._pink_buffer is not None:
                pink_idx = self._trial_index % len(self._pink_buffer)
                rt += self._pink_buffer[pink_idx] * self._effects.pink_noise.sd_ms
            rt = max(rt, self._floor_ms)
            self._prev_condition = condition
            self._trial_index += 1
            return rt
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

    # Jitter per-condition accuracy values
    if bsj.accuracy_sd > 0:
        for cond, acc_base in config.performance.accuracy.items():
            config.performance.accuracy[cond] = float(
                np.clip(acc_base + rng.normal(0, bsj.accuracy_sd), 0.60, 0.995)
            )

    # Jitter per-condition omission rates
    if bsj.omission_sd > 0:
        for cond, om_base in config.performance.omission_rate.items():
            config.performance.omission_rate[cond] = float(
                np.clip(om_base + rng.normal(0, bsj.omission_sd), 0.0, 0.04)
            )

    return config

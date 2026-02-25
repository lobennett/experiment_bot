from __future__ import annotations

import copy

import numpy as np

from experiment_bot.core.config import DistributionConfig, TaskConfig


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


class ResponseSampler:
    def __init__(
        self,
        distributions: dict[str, DistributionConfig],
        floor_ms: float = 150.0,
        phi: float = 0.25,
        drift_rate: float = 0.15,
        seed: int | None = None,
    ):
        self._floor_ms = floor_ms
        self._phi = phi
        self._drift_rate = drift_rate
        self._prev_rt: float | None = None
        self._trial_index: int = 0
        self._samplers: dict[str, ExGaussianSampler] = {}
        for condition, dist_config in distributions.items():
            if dist_config.distribution == "ex_gaussian":
                self._samplers[condition] = ExGaussianSampler(
                    mu=dist_config.params["mu"],
                    sigma=dist_config.params["sigma"],
                    tau=dist_config.params["tau"],
                    seed=seed,
                )

    def _apply_temporal_effects(self, raw_rt: float, sampler: ExGaussianSampler) -> float:
        """Apply AR(1) autocorrelation and fatigue drift to a raw RT sample."""
        rt = raw_rt

        # AR(1): pull current RT toward previous RT
        if self._prev_rt is not None and self._phi > 0:
            mean_rt = sampler.mu + sampler.tau
            deviation = self._prev_rt - mean_rt
            rt += self._phi * deviation

        # Fatigue drift: slow upward trend across experiment
        rt += self._trial_index * self._drift_rate

        rt = max(rt, self._floor_ms)
        self._prev_rt = rt
        self._trial_index += 1
        return rt

    def sample_rt(self, condition: str) -> float:
        if condition not in self._samplers:
            raise KeyError(f"Unknown condition: {condition}")
        sampler = self._samplers[condition]
        raw_rt = sampler.sample()
        return self._apply_temporal_effects(raw_rt, sampler)

    def sample_rt_with_fallback(self, condition: str) -> float:
        """Sample RT for condition, falling back to first available distribution."""
        if condition in self._samplers:
            sampler = self._samplers[condition]
        elif self._samplers:
            sampler = next(iter(self._samplers.values()))
        else:
            # No samplers — return fixed value with drift only
            rt = 500.0 + self._trial_index * self._drift_rate
            self._trial_index += 1
            return max(rt, self._floor_ms)
        raw_rt = sampler.sample()
        return self._apply_temporal_effects(raw_rt, sampler)


def jitter_distributions(config: TaskConfig, rng: np.random.Generator) -> TaskConfig:
    """Apply between-subject jitter to distribution params and performance targets.

    Creates a deep copy of the config so the original (cached) config is not mutated.
    Each session gets slightly different parameters, mimicking natural between-subject
    variability (human SD of mean RT ≈ 50-80ms).
    """
    config = copy.deepcopy(config)

    # Shared between-subject speed shift (a fast person is fast on all conditions)
    # preserves inter-condition differences like switch cost.
    shared_mu_shift = rng.normal(0, 40)
    for dist in config.response_distributions.values():
        if dist.distribution == "ex_gaussian":
            dist.params["mu"] += shared_mu_shift + rng.normal(0, 15)
            dist.params["sigma"] *= rng.uniform(0.85, 1.15)
            dist.params["tau"] *= rng.uniform(0.85, 1.15)

    # Scale accuracy jitter: less jitter for high-accuracy tasks (less room to vary)
    acc_base = config.performance.go_accuracy
    acc_jitter_sd = 0.015 if acc_base >= 0.95 else 0.03
    config.performance.go_accuracy = float(
        np.clip(acc_base + rng.normal(0, acc_jitter_sd), 0.85, 0.995)
    )
    config.performance.omission_rate = float(
        np.clip(config.performance.omission_rate + rng.normal(0, 0.01), 0.0, 0.08)
    )

    return config

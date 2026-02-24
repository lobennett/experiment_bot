from __future__ import annotations

import numpy as np

from experiment_bot.core.config import DistributionConfig


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
        seed: int | None = None,
    ):
        self._floor_ms = floor_ms
        self._samplers: dict[str, ExGaussianSampler] = {}
        for condition, dist_config in distributions.items():
            if dist_config.distribution == "ex_gaussian":
                self._samplers[condition] = ExGaussianSampler(
                    mu=dist_config.params["mu"],
                    sigma=dist_config.params["sigma"],
                    tau=dist_config.params["tau"],
                    seed=seed,
                )

    def sample_rt(self, condition: str) -> float:
        if condition not in self._samplers:
            raise KeyError(f"Unknown condition: {condition}")
        rt = self._samplers[condition].sample()
        return max(rt, self._floor_ms)

    def sample_rt_with_fallback(self, condition: str) -> float:
        """Sample RT for condition, falling back to first available distribution."""
        if condition in self._samplers:
            rt = self._samplers[condition].sample()
        elif self._samplers:
            rt = next(iter(self._samplers.values())).sample()
        else:
            rt = 500.0
        return max(rt, self._floor_ms)

import numpy as np
from experiment_bot.core.distributions import ExGaussianSampler, ResponseSampler
from experiment_bot.core.config import DistributionConfig


def test_ex_gaussian_sampler_returns_float():
    sampler = ExGaussianSampler(mu=450, sigma=60, tau=80)
    rt = sampler.sample()
    assert isinstance(rt, float)
    assert rt > 0


def test_ex_gaussian_sampler_mean_approx():
    sampler = ExGaussianSampler(mu=450, sigma=60, tau=80)
    samples = [sampler.sample() for _ in range(10_000)]
    mean = np.mean(samples)
    assert 500 < mean < 560


def test_ex_gaussian_sampler_with_seed():
    s1 = ExGaussianSampler(mu=450, sigma=60, tau=80, seed=42)
    s2 = ExGaussianSampler(mu=450, sigma=60, tau=80, seed=42)
    assert s1.sample() == s2.sample()


def test_response_sampler_floor():
    config = {
        "go_correct": DistributionConfig(
            distribution="ex_gaussian",
            params={"mu": 100, "sigma": 10, "tau": 10},
        )
    }
    sampler = ResponseSampler(config, floor_ms=150)
    for _ in range(100):
        rt = sampler.sample_rt("go_correct")
        assert rt >= 150


def test_response_sampler_unknown_condition():
    sampler = ResponseSampler({}, floor_ms=150)
    try:
        sampler.sample_rt("nonexistent")
        assert False, "Should raise KeyError"
    except KeyError:
        pass

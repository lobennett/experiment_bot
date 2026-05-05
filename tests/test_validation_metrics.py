import math
import numpy as np
import pytest
from experiment_bot.effects.validation_metrics import (
    fit_ex_gaussian, lag1_autocorrelation, post_error_slowing_magnitude,
    population_sd_per_param, ssrt_integration,
)


def test_fit_ex_gaussian_recovers_known_params():
    """Synthetic ex-Gaussian samples; recovered params should be close to truth."""
    rng = np.random.default_rng(42)
    n = 5000
    mu, sigma, tau = 500, 50, 80
    samples = rng.normal(mu, sigma, n) + rng.exponential(tau, n)
    out = fit_ex_gaussian(samples.tolist())
    assert abs(out["mu"] - mu) < 30
    assert abs(out["sigma"] - sigma) < 25
    assert abs(out["tau"] - tau) < 30


def test_lag1_autocorrelation_known_signal():
    """Monotonically increasing sequence has lag-1 r near 1.0."""
    rts = [500, 510, 520, 530, 540, 550, 560, 570, 580]
    r = lag1_autocorrelation(rts)
    assert r > 0.95


def test_lag1_autocorrelation_returns_nan_with_too_few_samples():
    """Fewer than 3 samples: NaN."""
    assert math.isnan(lag1_autocorrelation([500, 510]))


def test_post_error_slowing_magnitude_positive_when_slowed():
    trials = [
        {"rt": 500, "correct": True},
        {"rt": 600, "correct": False},  # error
        {"rt": 580, "correct": True},   # post-error: slowed
        {"rt": 510, "correct": True},
        {"rt": 520, "correct": True},
        {"rt": 530, "correct": True},
    ]
    pes = post_error_slowing_magnitude(trials)
    # post_error mean = 580; post_correct mean = (510+520+530)/3 = 520
    # PES = 580 - 520 = 60
    assert abs(pes - 60) < 5


def test_post_error_slowing_returns_nan_with_no_errors():
    trials = [{"rt": 500, "correct": True} for _ in range(10)]
    assert math.isnan(post_error_slowing_magnitude(trials))


def test_population_sd_per_param():
    sessions = [
        {"mu": 500, "sigma": 50, "tau": 80},
        {"mu": 520, "sigma": 55, "tau": 85},
        {"mu": 480, "sigma": 45, "tau": 75},
    ]
    out = population_sd_per_param(sessions)
    assert "mu" in out and out["mu"] > 0
    assert "sigma" in out and out["sigma"] > 0
    assert "tau" in out and out["tau"] > 0


def test_population_sd_per_param_returns_nan_for_singleton():
    sessions = [{"mu": 500, "sigma": 50, "tau": 80}]
    out = population_sd_per_param(sessions)
    assert math.isnan(out["mu"])


def test_ssrt_integration_recovers_target():
    """SSRT = nth_percentile(go_dist, p_respond) - mean_SSD."""
    go_rts = list(range(300, 700, 4))  # uniform-like over [300, 700)
    p_respond_given_stop = 0.5
    mean_ssd = 250
    ssrt = ssrt_integration(go_rts, p_respond_given_stop, mean_ssd)
    # 50th percentile of [300..700) ≈ 500; SSRT ≈ 500 - 250 = 250
    assert abs(ssrt - 250) < 50


def test_ssrt_integration_returns_nan_on_empty():
    assert math.isnan(ssrt_integration([], 0.5, 250))


def test_ssrt_integration_returns_nan_on_invalid_p():
    assert math.isnan(ssrt_integration([400, 500], 1.5, 250))
    assert math.isnan(ssrt_integration([400, 500], -0.1, 250))

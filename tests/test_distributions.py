import numpy as np
from experiment_bot.core.distributions import (
    ExGaussianSampler,
    ResponseSampler,
    jitter_distributions,
    _generate_pink_noise,
)
from experiment_bot.core.config import (
    BetweenSubjectJitterConfig,
    DistributionConfig,
    TaskConfig,
    TemporalEffectsConfig,
    AutocorrelationConfig,
    ConditionRepetitionConfig,
    FatigueDriftConfig,
    PinkNoiseConfig,
)


# --- ExGaussianSampler tests (unchanged) ---

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


# --- Pink noise tests (unchanged) ---

def test_pink_noise_shape_and_stats():
    """Pink noise buffer has correct shape, ~zero mean, ~unit variance."""
    rng = np.random.default_rng(42)
    buf = _generate_pink_noise(2048, 0.75, rng)
    assert buf.shape == (2048,)
    assert abs(buf.mean()) < 0.1
    assert abs(buf.std() - 1.0) < 0.1


def test_pink_noise_has_long_range_correlations():
    """Lag-10 autocorrelation should be > 0.05 (not white noise)."""
    rng = np.random.default_rng(42)
    buf = _generate_pink_noise(4096, 0.75, rng)
    n = len(buf)
    mean = buf.mean()
    var = buf.var()
    lag10_cov = np.mean((buf[:n - 10] - mean) * (buf[10:] - mean))
    autocorr = lag10_cov / var
    assert autocorr > 0.05, f"Lag-10 autocorrelation {autocorr:.3f} too low for pink noise"


# --- ResponseSampler tests (new, using TemporalEffectsConfig) ---

def _make_dists():
    return {
        "a": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80}),
        "b": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80}),
    }


def test_no_effects_produces_raw_ex_gaussian():
    """With all effects disabled, output should be close to raw ex-Gaussian samples."""
    effects = TemporalEffectsConfig()  # all disabled by default
    dists = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}
    sampler = ResponseSampler(dists, temporal_effects=effects, seed=42)
    samples = [sampler.sample_rt("go") for _ in range(5000)]
    mean = np.mean(samples)
    # ex-Gaussian mean = mu + tau = 530
    assert 500 < mean < 560, f"Mean {mean:.1f} outside expected range for raw ex-Gaussian"


def test_autocorrelation_enabled():
    """With phi=0.5, lag-1 autocorrelation of RT series should be > 0.05."""
    effects = TemporalEffectsConfig(
        autocorrelation=AutocorrelationConfig(enabled=True, phi=0.5),
    )
    dists = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}
    sampler = ResponseSampler(dists, temporal_effects=effects, seed=42)
    rts = [sampler.sample_rt("go") for _ in range(2000)]
    arr = np.array(rts)
    mean = arr.mean()
    var = arr.var()
    lag1_cov = np.mean((arr[:-1] - mean) * (arr[1:] - mean))
    autocorr = lag1_cov / var
    assert autocorr > 0.05, f"Lag-1 autocorrelation {autocorr:.3f} too low with phi=0.5"


def test_condition_repetition_enabled():
    """Condition repetitions should produce faster RTs than alternations."""
    effects = TemporalEffectsConfig(
        condition_repetition=ConditionRepetitionConfig(enabled=True, facilitation_ms=8.0, cost_ms=8.0),
    )
    dists = _make_dists()

    # Alternating conditions
    sampler_alt = ResponseSampler(dists, temporal_effects=effects, seed=42)
    alt_rts = []
    conditions = ["a", "b"]
    for i in range(2000):
        rt = sampler_alt.sample_rt(conditions[i % 2])
        if i > 0:
            alt_rts.append(rt)

    # Repeating condition
    sampler_rep = ResponseSampler(dists, temporal_effects=effects, seed=42)
    rep_rts = []
    for i in range(2000):
        rt = sampler_rep.sample_rt("a")
        if i > 0:
            rep_rts.append(rt)

    assert np.mean(rep_rts) < np.mean(alt_rts), (
        f"Repetition mean {np.mean(rep_rts):.1f} should be < alternation mean {np.mean(alt_rts):.1f}"
    )


def test_pink_noise_disabled_no_buffer():
    """When pink noise is disabled, _pink_buffer should be None."""
    effects = TemporalEffectsConfig()  # pink_noise.enabled=False by default
    dists = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}
    sampler = ResponseSampler(dists, temporal_effects=effects, seed=42)
    assert sampler._pink_buffer is None


def test_pink_noise_enabled_allocates_buffer():
    """When pink noise is enabled, _pink_buffer should be a numpy array of length 2048."""
    effects = TemporalEffectsConfig(
        pink_noise=PinkNoiseConfig(enabled=True, sd_ms=12.0, hurst=0.75),
    )
    dists = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}
    sampler = ResponseSampler(dists, temporal_effects=effects, seed=42)
    assert sampler._pink_buffer is not None
    assert len(sampler._pink_buffer) == 2048


def test_pink_noise_enabled_invalid_hurst_raises():
    """Enabled pink noise with hurst <= 0 should raise ValueError."""
    effects = TemporalEffectsConfig(
        pink_noise=PinkNoiseConfig(enabled=True, sd_ms=12.0, hurst=0.0),
    )
    dists = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}
    try:
        ResponseSampler(dists, temporal_effects=effects, seed=42)
        assert False, "Should raise ValueError"
    except ValueError:
        pass


# --- jitter_distributions tests ---

MINIMAL_CONFIG = {
    "task": {"name": "Test", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {
        "go": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    },
    "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_jitter_uses_config_values():
    """With between_subject_jitter populated, mu should change."""
    config_dict = dict(MINIMAL_CONFIG)
    config_dict["between_subject_jitter"] = {
        "rt_mean_sd_ms": 40.0,
        "rt_condition_sd_ms": 15.0,
        "sigma_tau_range": [0.85, 1.15],
        "accuracy_sd": 0.015,
        "omission_sd": 0.005,
    }
    config = TaskConfig.from_dict(config_dict)
    rng = np.random.default_rng(42)
    jittered = jitter_distributions(config, rng)
    # mu should have shifted from 450
    assert jittered.response_distributions["go"].params["mu"] != 450.0


def test_jitter_no_config_no_jitter():
    """Without between_subject_jitter, mu stays at 450."""
    config = TaskConfig.from_dict(MINIMAL_CONFIG)
    rng = np.random.default_rng(42)
    jittered = jitter_distributions(config, rng)
    assert jittered.response_distributions["go"].params["mu"] == 450.0

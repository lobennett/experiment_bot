"""SP11 Phase 5a — sampler calibration adjustment tests."""
from __future__ import annotations

from experiment_bot.calibration.estimator import CalibrationResult
from experiment_bot.core.config import DistributionConfig
from experiment_bot.core.distributions import ResponseSampler


def _basic_sampler(seed: int = 42, floor_ms: float = 150.0) -> ResponseSampler:
    dists = {
        "default": DistributionConfig.from_dict({
            "distribution": "ex_gaussian",
            "params": {"mu": 500, "sigma": 80, "tau": 100},
            "source": "test",
        }),
    }
    return ResponseSampler(dists, floor_ms=floor_ms, seed=seed)


def test_calibration_default_is_none():
    sampler = _basic_sampler()
    assert sampler._calibration_result is None


def test_calibration_fixed_offset_shifts_rt_down():
    """A 30ms mean_offset means the platform records 30ms LATER than
    the bot fires. So the bot should fire 30ms EARLIER than the target
    to make the platform's recorded RT match the target."""
    sampler = _basic_sampler()
    cal = CalibrationResult(
        model="fixed_offset",
        mean_offset_ms=30.0, sd_offset_ms=2.0,
        intercept_ms=None, slope=None,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt1 = sampler.sample_rt("default")
    sampler2 = _basic_sampler()
    rt2 = sampler2.sample_rt("default")
    # With the same seed, the raw sample is identical; the calibrated
    # sample should be raw - 30ms.
    assert abs((rt1 + 30.0) - rt2) < 0.001


def test_calibration_regression_inverts_linear_model():
    """For y = slope*x + intercept, adjust returns (target - intercept) / slope."""
    sampler = _basic_sampler()
    cal = CalibrationResult(
        model="regression",
        mean_offset_ms=None, sd_offset_ms=None,
        intercept_ms=20.0, slope=1.05,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt_calibrated = sampler.sample_rt("default")
    sampler2 = _basic_sampler()
    rt_raw = sampler2.sample_rt("default")
    expected = (rt_raw - 20.0) / 1.05
    # Floor may clip; lognormal samples are well above 150ms typically
    assert abs(rt_calibrated - expected) < 0.001


def test_calibration_escalate_no_op():
    """Escalate model returns the input unchanged."""
    sampler = _basic_sampler()
    cal = CalibrationResult(
        model="escalate",
        mean_offset_ms=None, sd_offset_ms=None,
        intercept_ms=None, slope=None,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt_calibrated = sampler.sample_rt("default")
    sampler2 = _basic_sampler()
    rt_raw = sampler2.sample_rt("default")
    assert abs(rt_calibrated - rt_raw) < 0.001


def test_calibration_too_few_events_no_op():
    """too_few_events model also returns the input unchanged."""
    sampler = _basic_sampler()
    cal = CalibrationResult(
        model="too_few_events",
        mean_offset_ms=None, sd_offset_ms=None,
        intercept_ms=None, slope=None,
        n_events_total=2, n_events_correctly_recorded=2,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt_calibrated = sampler.sample_rt("default")
    sampler2 = _basic_sampler()
    rt_raw = sampler2.sample_rt("default")
    assert abs(rt_calibrated - rt_raw) < 0.001


def test_calibration_clearing_works():
    """Setting calibration to None disables adjustment."""
    sampler = _basic_sampler()
    cal = CalibrationResult(
        model="fixed_offset",
        mean_offset_ms=50.0, sd_offset_ms=2.0,
        intercept_ms=None, slope=None,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt_with = sampler.sample_rt("default")
    sampler.set_calibration_result(None)
    sampler2 = _basic_sampler()
    rt_without = sampler2.sample_rt("default")
    # Without calibration, RT should match the second sampler's value
    # (same seed, same draw).
    # The first sampler's RNG has already advanced, so resample.
    sampler3 = _basic_sampler()
    sampler3.set_calibration_result(None)
    rt_third = sampler3.sample_rt("default")
    assert abs(rt_third - rt_without) < 0.001
    # And with-calibration differed from without by 50ms
    assert abs((rt_with + 50.0) - rt_without) < 0.001


def test_calibration_respects_floor():
    """If the calibration adjustment would push RT below the
    bot's physiological floor, clip up to the floor."""
    sampler = _basic_sampler(floor_ms=200.0)
    # A huge mean_offset that subtracts 600ms — well below the floor
    cal = CalibrationResult(
        model="fixed_offset",
        mean_offset_ms=600.0, sd_offset_ms=2.0,
        intercept_ms=None, slope=None,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt = sampler.sample_rt("default")
    # Floor must clip — even though lognormal samples are around 600ms,
    # subtracting 600ms would drop us below 200ms floor.
    assert rt >= 200.0


def test_calibration_with_fallback_path():
    """sample_rt_with_fallback also applies the adjustment."""
    sampler = _basic_sampler()
    cal = CalibrationResult(
        model="fixed_offset",
        mean_offset_ms=25.0, sd_offset_ms=1.0,
        intercept_ms=None, slope=None,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    sampler.set_calibration_result(cal)
    rt = sampler.sample_rt_with_fallback("unknown_condition")
    sampler2 = _basic_sampler()
    rt_raw = sampler2.sample_rt_with_fallback("unknown_condition")
    assert abs((rt + 25.0) - rt_raw) < 0.001

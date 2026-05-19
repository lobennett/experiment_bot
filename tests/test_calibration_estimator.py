"""SP11 Phase 3.3-3.5 — calibration estimator tests.

Covers:
- Filter-to-correctly-recorded: pre-filter misrecorded and dropped
  events do not contaminate the offset estimate.
- Fixed-offset model selection (SD ≤ 30 ms threshold).
- Regression model selection (SD > 30 ms triggers regression).
- Bimodality detection (gap-statistic with >50ms separation AND
  ≥20% mass in smaller cluster).
- too_few_events escalation.
- adjust() inverse application produces the right bot-intended RT.
"""
from __future__ import annotations

import asyncio

import pytest

from experiment_bot.calibration.deliverer import MockDeliverer
from experiment_bot.calibration.estimator import (
    CalibrationResult, estimate_calibration,
)


def _run(coro):
    return asyncio.run(coro)


def _calibration_events(
    *, n=30, mean=20.0, sd=5.0, drop=0.0, misrec=0.0,
    bimodal=None, seed=42,
):
    mock = MockDeliverer(
        recording_offset_mean_ms=mean,
        recording_offset_sd_ms=sd,
        drop_rate=drop,
        misrecording_rate=misrec,
        bimodal_second_mode=bimodal,
        seed=seed,
    )
    intervals = ([200.0, 400.0, 600.0, 800.0, 1000.0] * (n // 5 + 1))[:n]
    return _run(mock.deliver_sequence(
        keys=[" "] * n,
        target_intervals_ms=intervals,
    ))


# ---------------------------------------------------------------------------
# Fixed-offset model
# ---------------------------------------------------------------------------

def test_fixed_offset_zero_noise():
    """Deterministic 20ms offset, no noise → fixed_offset model with
    mean ≈ 20, sd ≈ 0."""
    events = _calibration_events(mean=20.0, sd=0.0)
    result = estimate_calibration(events)
    assert result.model == "fixed_offset"
    assert abs(result.mean_offset_ms - 20.0) < 0.1
    assert result.sd_offset_ms < 0.1
    assert result.n_events_correctly_recorded == 30


def test_fixed_offset_low_noise_under_threshold():
    """Mean 50ms, SD 10ms → fixed_offset model (under 30ms threshold)."""
    events = _calibration_events(mean=50.0, sd=10.0, n=50)
    result = estimate_calibration(events)
    assert result.model == "fixed_offset"
    # Sample mean should be close to 50 within sampling noise
    assert 45.0 < result.mean_offset_ms < 55.0
    assert result.sd_offset_ms < 15.0


def test_fixed_offset_with_drop_filter_excludes_dropped():
    """Dropped events are filtered out before offset computation."""
    events = _calibration_events(mean=10.0, sd=2.0, drop=0.3, n=100)
    result = estimate_calibration(events)
    assert result.model == "fixed_offset"
    # ~30 events dropped at 0.3 rate over n=100, ±3-sigma is ~14
    assert 55 <= result.n_events_correctly_recorded <= 85
    assert 15 <= result.n_events_dropped <= 45
    # Mean is still recovered from the correctly-recorded events
    assert 8.0 < result.mean_offset_ms < 12.0


def test_fixed_offset_with_misrecording_filter_excludes_misrec():
    """Mis-recorded events (platform recorded wrong key) excluded
    from the offset estimate per SP7 layer-d discipline."""
    events = _calibration_events(mean=15.0, sd=2.0, misrec=0.4, n=100)
    result = estimate_calibration(events)
    assert result.model == "fixed_offset"
    # ~40 mis-recorded, ~60 correct
    assert 50 < result.n_events_correctly_recorded < 70
    assert 30 < result.n_events_misrecorded < 50
    # Estimate is still ~15 because mis-recorded events were filtered
    assert 13.0 < result.mean_offset_ms < 17.0


# ---------------------------------------------------------------------------
# Regression model — SD > 30 triggers regression
# ---------------------------------------------------------------------------

def test_regression_when_sd_exceeds_threshold():
    """SD=50ms is well above the 30ms threshold → regression model."""
    events = _calibration_events(mean=20.0, sd=50.0, n=60)
    result = estimate_calibration(events)
    assert result.model == "regression"
    assert result.sd_offset_ms > 30.0
    # The regression's slope should still be close to 1 (no systematic
    # multiplicative shift in mock data — just additive noise)
    assert 0.8 < result.slope < 1.2


# ---------------------------------------------------------------------------
# Bimodality detection — escalate
# ---------------------------------------------------------------------------

def test_bimodal_offset_escalates():
    """Two clearly separated modes (0 and 100 ms, 50/50 mix) → escalate."""
    events = _calibration_events(
        mean=0.0, sd=5.0, bimodal=(100.0, 0.5), n=100,
    )
    result = estimate_calibration(events)
    assert result.model == "escalate"
    assert result.bimodal_detected is True
    assert result.bimodal_cluster_means_ms is not None
    low, high = result.bimodal_cluster_means_ms
    assert -10 < low < 10
    assert 90 < high < 110
    assert result.bimodal_smaller_mass is not None
    assert result.bimodal_smaller_mass >= 0.20


def test_borderline_bimodal_below_separation_threshold_does_not_escalate():
    """Two modes separated by only 30ms (< 50 threshold) → not bimodal,
    falls into regression (SD is high due to mixture)."""
    events = _calibration_events(
        mean=0.0, sd=5.0, bimodal=(30.0, 0.5), n=100,
    )
    result = estimate_calibration(events)
    # Separation of 30 ms is below the 50-ms bimodality threshold; the
    # estimator treats it as a unimodal-but-noisy distribution and
    # picks regression because SD is high.
    assert result.model in ("regression", "fixed_offset")
    assert result.bimodal_detected is False


def test_borderline_bimodal_below_mass_threshold_does_not_escalate():
    """Two well-separated modes but smaller mode has only 5% mass
    (< 20% threshold) → not bimodal; the small mode is treated as
    outliers."""
    events = _calibration_events(
        mean=0.0, sd=5.0, bimodal=(100.0, 0.05), n=200,
    )
    result = estimate_calibration(events)
    # 5% mass in the second mode is below the 20% threshold; estimator
    # accepts this as unimodal-with-outliers
    assert result.bimodal_detected is False


# ---------------------------------------------------------------------------
# Insufficient events — escalate
# ---------------------------------------------------------------------------

def test_too_few_events_escalates():
    """Fewer than 5 correctly-recorded events → too_few_events model."""
    events = _calibration_events(n=10, drop=0.9, seed=42)
    result = estimate_calibration(events)
    # ~9 of 10 are dropped, leaving ~1 correctly-recorded
    assert result.model == "too_few_events"
    assert "minimum" in result.reason.lower()


def test_too_few_events_when_all_misrecorded():
    """All keypresses mis-recorded (extreme SP7 layer-d case) →
    too_few_events."""
    events = _calibration_events(n=20, misrec=1.0)
    result = estimate_calibration(events)
    assert result.model == "too_few_events"
    assert result.n_events_correctly_recorded == 0


# ---------------------------------------------------------------------------
# adjust() inverse application
# ---------------------------------------------------------------------------

def test_adjust_fixed_offset_subtracts_mean():
    """Fixed-offset model: adjust(sampler_rt) = sampler_rt − mean_offset."""
    r = CalibrationResult(
        model="fixed_offset", mean_offset_ms=30.0,
    )
    assert r.adjust(500.0) == 470.0
    assert r.adjust(1000.0) == 970.0


def test_adjust_regression_inverts_linear_model():
    """Regression model: adjust(target) solves slope * adj + intercept
    = target."""
    r = CalibrationResult(
        model="regression", slope=1.2, intercept_ms=15.0,
    )
    # If sampler targets 615 ms, deliverer fires at adj such that
    # 1.2 * adj + 15 = 615 → adj = 500
    assert abs(r.adjust(615.0) - 500.0) < 1e-6


def test_adjust_escalate_returns_input_unchanged():
    """Escalate model: adjust applies no correction."""
    r = CalibrationResult(model="escalate")
    assert r.adjust(500.0) == 500.0


def test_adjust_too_few_events_returns_input_unchanged():
    r = CalibrationResult(model="too_few_events")
    assert r.adjust(500.0) == 500.0


# ---------------------------------------------------------------------------
# End-to-end: deliverer + estimator integration
# ---------------------------------------------------------------------------

def test_end_to_end_mock_deliverer_to_estimator():
    """Full path: MockDeliverer fires sequence, estimator picks
    correct model. With a realistic 25 ms mean / 8 ms SD config,
    the model should be fixed_offset."""
    mock = MockDeliverer(
        recording_offset_mean_ms=25.0,
        recording_offset_sd_ms=8.0,
        misrecording_rate=0.1,
        drop_rate=0.05,
        seed=42,
    )
    events = _run(mock.deliver_sequence(
        keys=[" "] * 30,
        target_intervals_ms=[200.0, 400.0, 600.0, 800.0, 1000.0] * 6,
    ))
    result = estimate_calibration(events)
    assert result.model == "fixed_offset"
    # 90% of 30 = 27 candidates; 10% misrec = 24-25 correct
    assert 20 < result.n_events_correctly_recorded < 30
    assert 22.0 < result.mean_offset_ms < 28.0
    # adjust(800) should target sampler-RT of 775 ms
    assert abs(result.adjust(800.0) - (800.0 - result.mean_offset_ms)) < 0.01

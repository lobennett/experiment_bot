"""SP11 Phase 3.2 — KeypressDeliverer abstraction tests.

The mock deliverer is the test harness for Phase 3.3-3.5 (estimator,
bimodality, regression fallback). These tests verify the mock's
synthetic-event generation behaves as documented so estimator tests
can rely on its calibration.
"""
from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from experiment_bot.calibration.deliverer import (
    KeypressDeliverer, KeypressEvent, MockDeliverer,
)


def _run(coro):
    return asyncio.run(coro)


def test_keypress_event_is_correctly_recorded_property():
    """is_correctly_recorded filters platform observations: True iff
    platform recorded the same key the bot fired."""
    correct = KeypressEvent(
        key=" ", bot_intended_rt_ms=400.0,
        platform_recorded_key=" ", platform_recorded_rt_ms=425.0,
    )
    assert correct.is_correctly_recorded is True

    misrec = KeypressEvent(
        key=" ", bot_intended_rt_ms=400.0,
        platform_recorded_key=",", platform_recorded_rt_ms=425.0,
    )
    assert misrec.is_correctly_recorded is False

    dropped = KeypressEvent(
        key=" ", bot_intended_rt_ms=400.0,
        platform_recorded_key=None, platform_recorded_rt_ms=None,
    )
    assert dropped.is_correctly_recorded is False


def test_mock_deliverer_zero_offset_no_noise_returns_identity():
    """With zero offset and zero SD, platform_recorded_rt should
    equal bot_intended_rt exactly."""
    mock = MockDeliverer(
        recording_offset_mean_ms=0.0, recording_offset_sd_ms=0.0,
        seed=42,
    )
    events = _run(mock.deliver_sequence(
        keys=[" ", " ", " "],
        target_intervals_ms=[200.0, 400.0, 600.0],
    ))
    assert len(events) == 3
    # Cumulative timing: 200, 600, 1200
    assert events[0].bot_intended_rt_ms == 200.0
    assert events[1].bot_intended_rt_ms == 600.0
    assert events[2].bot_intended_rt_ms == 1200.0
    # Identity recording
    for ev in events:
        assert ev.platform_recorded_rt_ms == ev.bot_intended_rt_ms
        assert ev.platform_recorded_key == ev.key
        assert ev.is_correctly_recorded


def test_mock_deliverer_constant_offset_applied():
    """Configurable offset is added to every event."""
    mock = MockDeliverer(
        recording_offset_mean_ms=20.0, recording_offset_sd_ms=0.0,
        seed=42,
    )
    events = _run(mock.deliver_sequence(
        keys=[" "] * 10, target_intervals_ms=[100.0] * 10,
    ))
    # All offsets should be exactly 20 ms
    for ev in events:
        assert ev.platform_recorded_rt_ms == ev.bot_intended_rt_ms + 20.0


def test_mock_deliverer_gaussian_offset_distribution():
    """With non-zero SD, offsets should be Gaussian-distributed around
    the mean. Sample N events and verify sample mean/SD match within
    a generous tolerance."""
    mock = MockDeliverer(
        recording_offset_mean_ms=50.0, recording_offset_sd_ms=15.0,
        seed=42,
    )
    events = _run(mock.deliver_sequence(
        keys=[" "] * 1000, target_intervals_ms=[10.0] * 1000,
    ))
    offsets = [ev.platform_recorded_rt_ms - ev.bot_intended_rt_ms for ev in events]
    sample_mean = sum(offsets) / len(offsets)
    sample_var = sum((o - sample_mean) ** 2 for o in offsets) / (len(offsets) - 1)
    sample_sd = sample_var ** 0.5
    # SE of mean = 15/sqrt(1000) ≈ 0.47 ms; 4-sigma tolerance ≈ 2 ms
    assert abs(sample_mean - 50.0) < 2.5, f"mean offset {sample_mean} ≠ 50"
    # SD itself has SE ≈ 15/sqrt(2*1000) ≈ 0.33; tolerate ±2
    assert abs(sample_sd - 15.0) < 2.0, f"sd {sample_sd} ≠ 15"


def test_mock_deliverer_drop_rate_produces_none_events():
    """drop_rate=0.5 means ~50% of events have None platform fields."""
    mock = MockDeliverer(drop_rate=0.5, seed=42)
    events = _run(mock.deliver_sequence(
        keys=[" "] * 1000, target_intervals_ms=[10.0] * 1000,
    ))
    dropped = sum(1 for ev in events if ev.platform_recorded_key is None)
    # SE for proportion 0.5 at N=1000: sqrt(0.25/1000) ≈ 0.016
    # ±0.05 tolerance is 3-sigma
    assert 450 < dropped < 550, f"dropped count {dropped} not near 500"
    # Dropped events have BOTH key AND rt as None
    for ev in events:
        if ev.platform_recorded_key is None:
            assert ev.platform_recorded_rt_ms is None


def test_mock_deliverer_misrecording_rate_swaps_keys():
    """misrecording_rate=0.3 means ~30% of events have platform_recorded_key
    that DIFFERS from bot.key."""
    mock = MockDeliverer(
        misrecording_rate=0.3,
        misrecording_alt_keys=[",", ".", "Enter"],
        seed=42,
    )
    events = _run(mock.deliver_sequence(
        keys=[" "] * 1000, target_intervals_ms=[10.0] * 1000,
    ))
    misrec = sum(1 for ev in events
                 if ev.platform_recorded_key is not None
                 and ev.platform_recorded_key != ev.key)
    # ±3 sigma at 0.3 proportion: sqrt(0.21/1000) ≈ 0.014; tolerate 250-350
    assert 250 < misrec < 350, f"misrec count {misrec} not near 300"
    # Mis-recorded keys come from the alt set
    for ev in events:
        if ev.platform_recorded_key not in (None, " "):
            assert ev.platform_recorded_key in {",", ".", "Enter"}


def test_mock_deliverer_bimodal_offset_produces_two_modes():
    """bimodal_second_mode=(100, 0.5) means 50% of events have offset
    drawn from N(0, sd) and 50% from N(100, sd) — two clearly separated
    modes for testing the bimodality detector in Phase 3.4."""
    mock = MockDeliverer(
        recording_offset_mean_ms=0.0, recording_offset_sd_ms=5.0,
        bimodal_second_mode=(100.0, 0.5),
        seed=42,
    )
    events = _run(mock.deliver_sequence(
        keys=[" "] * 2000, target_intervals_ms=[10.0] * 2000,
    ))
    offsets = [ev.platform_recorded_rt_ms - ev.bot_intended_rt_ms for ev in events]
    # Counts in each mode
    low_mode = [o for o in offsets if o < 50.0]
    high_mode = [o for o in offsets if o >= 50.0]
    # ~50% in each
    assert 900 < len(low_mode) < 1100
    assert 900 < len(high_mode) < 1100
    # Low mode centered near 0
    assert -3 < sum(low_mode) / len(low_mode) < 3
    # High mode centered near 100
    assert 97 < sum(high_mode) / len(high_mode) < 103


def test_mock_deliverer_validates_input_length_mismatch():
    """keys and target_intervals_ms lengths must match."""
    mock = MockDeliverer()
    with pytest.raises(ValueError, match="same length"):
        _run(mock.deliver_sequence(
            keys=[" ", " "], target_intervals_ms=[100.0],
        ))


def test_mock_deliverer_implements_keypress_deliverer_protocol():
    """MockDeliverer is a concrete KeypressDeliverer for type checking
    + abstraction enforcement."""
    mock = MockDeliverer()
    assert isinstance(mock, KeypressDeliverer)


def test_keypress_event_metadata_field_passthrough():
    """The mock attaches mock_offset_ms metadata; estimator tests can
    inspect it for ground-truth verification."""
    mock = MockDeliverer(recording_offset_mean_ms=20.0, seed=42)
    events = _run(mock.deliver_sequence(
        keys=[" "] * 5, target_intervals_ms=[100.0] * 5,
    ))
    for ev in events:
        if ev.platform_recorded_key is not None:
            assert "mock_offset_ms" in ev.metadata
            assert ev.metadata["mock_offset_ms"] == 20.0

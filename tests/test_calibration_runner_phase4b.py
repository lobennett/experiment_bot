"""CalibrationRun delivery.channel summary tests.

Verifies the runner now captures the events list and per-channel
counts, so Phase 5's bot_log writer can populate the per-trial
``delivery.channel`` field.
"""
from __future__ import annotations

import asyncio

from experiment_bot.calibration.deliverer import (
    KeypressEvent, MockDeliverer,
)
from experiment_bot.calibration.runner import (
    NoGateDismisser,
    _summarize_delivery_channels,
    run_calibration,
)


def _run(coro):
    return asyncio.run(coro)


def test_summarize_delivery_channels_counts_by_channel():
    events = [
        KeypressEvent(
            key=" ", bot_intended_rt_ms=400, platform_recorded_key=" ",
            platform_recorded_rt_ms=420,
            metadata={"delivery": {"channel": "cdp_dispatchKeyEvent"}},
        ),
        KeypressEvent(
            key=" ", bot_intended_rt_ms=400, platform_recorded_key=" ",
            platform_recorded_rt_ms=420,
            metadata={"delivery": {"channel": "cdp_dispatchKeyEvent"}},
        ),
        KeypressEvent(
            key=" ", bot_intended_rt_ms=400, platform_recorded_key=" ",
            platform_recorded_rt_ms=420,
            metadata={"delivery": {"channel": "keyboard_press_fallback"}},
        ),
    ]
    counts = _summarize_delivery_channels(events)
    assert counts == {"cdp_dispatchKeyEvent": 2, "keyboard_press_fallback": 1}


def test_summarize_delivery_channels_unknown_for_missing_channel():
    """MockDeliverer doesn't populate delivery.channel; those events
    should bucket as 'unknown' so downstream writers can warn."""
    events = [
        KeypressEvent(
            key=" ", bot_intended_rt_ms=400, platform_recorded_key=" ",
            platform_recorded_rt_ms=420,
        ),
    ]
    counts = _summarize_delivery_channels(events)
    assert counts == {"unknown": 1}


def test_run_calibration_includes_events_and_channel_counts():
    """Phase 4b: CalibrationRun.events + .delivery_channel_counts must
    be populated."""
    mock = MockDeliverer(
        recording_offset_mean_ms=10.0, recording_offset_sd_ms=2.0,
        seed=42,
    )
    cal_run = _run(run_calibration(mock, NoGateDismisser()))
    assert len(cal_run.events) == cal_run.sequence_length
    # MockDeliverer doesn't tag channel, so events bucket as 'unknown'.
    # This is expected — Phase 4b's CDP/keyboard deliverers DO tag.
    assert "unknown" in cal_run.delivery_channel_counts
    assert (
        cal_run.delivery_channel_counts["unknown"] == cal_run.sequence_length
    )

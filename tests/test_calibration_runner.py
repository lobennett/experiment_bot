"""Calibration runner tests.

Runner orchestrates gate dismissal → key fire → estimate. Delivery-
channel-agnostic; tested with mock deliverer + mock gate dismisser.
"""
from __future__ import annotations

import asyncio

import pytest

from experiment_bot.calibration.deliverer import MockDeliverer
from experiment_bot.calibration.runner import (
    CalibrationRun, MockGateDismisser, NoGateDismisser, run_calibration,
)


def _run(coro):
    return asyncio.run(coro)


def test_no_gate_dismisser_returns_true_immediately():
    """The no-gate path: platforms without a gate need no dismissal."""
    g = NoGateDismisser()
    assert _run(g.dismiss()) is True


def test_run_calibration_with_no_gate_and_mock_deliverer():
    mock = MockDeliverer(recording_offset_mean_ms=15.0, recording_offset_sd_ms=3.0, seed=42)
    run = _run(run_calibration(mock))
    assert isinstance(run, CalibrationRun)
    assert run.gate_dismissed is True
    assert run.sequence_length == 30
    assert run.result.model == "fixed_offset"
    assert 12.0 < run.result.mean_offset_ms < 18.0


def test_run_calibration_with_mock_gate_dismisser_succeeded():
    """Mock gate dismisser succeeds (returns True); runner proceeds to
    deliver sequence."""
    gate = MockGateDismisser(succeeds=True)
    mock = MockDeliverer(recording_offset_mean_ms=20.0, recording_offset_sd_ms=2.0, seed=42)
    run = _run(run_calibration(mock, gate))
    assert run.gate_dismissed is True
    assert gate.dismiss_calls == 1
    assert run.result.model == "fixed_offset"


def test_run_calibration_with_failing_gate_proceeds_with_warning():
    """Gate dismisser returns False (couldn't dismiss); runner proceeds
    anyway but logs a warning. The estimator likely returns
    too_few_events because the mock deliverer's drop_rate is unaffected
    by gate state (mock doesn't model gate ↔ recording coupling). For
    a real platform with a gate, this is the surface signal that
    something is wrong."""
    gate = MockGateDismisser(succeeds=False)
    mock = MockDeliverer(seed=42)
    run = _run(run_calibration(mock, gate))
    assert run.gate_dismissed is False
    # The mock deliverer still fires; estimator gets the events. The
    # gate state affects real-platform behavior, not the mock.
    assert run.sequence_length == 30


def test_run_calibration_custom_keys_and_intervals():
    """Caller can override the default 30-key Space sequence."""
    mock = MockDeliverer(recording_offset_mean_ms=10.0, recording_offset_sd_ms=1.0, seed=42)
    run = _run(run_calibration(
        mock,
        keys=["Space", "Enter", "ArrowRight"] * 4,
        target_intervals_ms=[100.0, 200.0, 300.0] * 4,
    ))
    assert run.sequence_length == 12
    assert run.result.n_events_total == 12


def test_run_calibration_escalates_on_bimodal_offset():
    """End-to-end through runner: when deliverer produces bimodal
    offsets, the runner's CalibrationRun carries an escalate model."""
    mock = MockDeliverer(
        recording_offset_mean_ms=0.0, recording_offset_sd_ms=3.0,
        bimodal_second_mode=(80.0, 0.5),
        seed=42,
    )
    # Use more keys so the bimodality detector has enough points
    run = _run(run_calibration(
        mock,
        keys=["Space"] * 100,
        target_intervals_ms=[100.0] * 100,
    ))
    assert run.result.model == "escalate"
    assert run.result.bimodal_detected

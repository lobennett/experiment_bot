"""Calibration auto-invocation behavior.

Tests the executor's _run_calibration_pass: it runs whenever a
deliverer is configured and records the result for run_metadata;
it short-circuits when no deliverer is available.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.core.config import RuntimeConfig


def _bp_stub():
    """Minimal behavior-provider stub: TaskExecutor requires one at init;
    structural tests never execute trials through it."""
    from unittest.mock import MagicMock
    p = MagicMock()
    p.program_sha256 = "00" * 32
    p.program_path = "stub_program.py"
    p.seed = 0
    return p




def test_runtime_calibration_n_keys_default():
    """Default n_keys for the calibration pass is 30."""
    rc = RuntimeConfig()
    assert rc.calibration_n_keys == 30


def _executor_with_runtime(runtime_overrides: dict):
    from experiment_bot.core.config import TaskConfig
    from experiment_bot.core.executor import TaskExecutor
    base = {
        "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [{
            "id": "s",
            "description": "stim",
            "detection": {"method": "dom_query", "selector": "#s"},
            "response": {"key": " ", "condition": "default"},
        }],
        "response_distributions": {
            "default": {"distribution": "ex_gaussian", "params": {"mu": 500, "sigma": 80, "tau": 100}},
        },
        "performance": {"accuracy": {"default": 0.9}, "omission_rate": {"default": 0.02}, "practice_accuracy": 0.85},
        "navigation": {"phases": []},
        "runtime": runtime_overrides,
    }
    return TaskExecutor(TaskConfig.from_dict(base), behavior_provider=_bp_stub())


def test_run_calibration_pass_records_result_by_default():
    """Post-cal arm: run pass and record the CalibrationRun."""
    ex = _executor_with_runtime({})  # defaults
    from experiment_bot.calibration.estimator import CalibrationResult
    from experiment_bot.calibration.runner import CalibrationRun
    fake_result = CalibrationResult(
        model="fixed_offset",
        mean_offset_ms=15.0, sd_offset_ms=2.0,
        intercept_ms=None, slope=None,
        n_events_total=30, n_events_correctly_recorded=30,
        n_events_dropped=0, n_events_misrecorded=0,
    )
    fake_run = CalibrationRun(
        result=fake_result, gate_dismissed=True, sequence_length=30,
        events=[], delivery_channel_counts={"cdp_dispatchKeyEvent": 30},
    )
    ex._deliverer = MagicMock()
    with patch(
        "experiment_bot.calibration.runner.run_calibration",
        new=AsyncMock(return_value=fake_run),
    ), patch(
        "experiment_bot.calibration.playwright_gate_dismisser.PlaywrightGateDismisser"
    ):
        asyncio.run(ex._run_calibration_pass(MagicMock()))
    assert ex._calibration_run is fake_run
    assert ex._calibration_run.result is fake_result


def test_run_calibration_pass_skips_when_no_deliverer():
    """delivery_channel='none' or CDP unavailable → no calibration."""
    ex = _executor_with_runtime({})
    ex._deliverer = None
    asyncio.run(ex._run_calibration_pass(MagicMock()))
    assert ex._calibration_run is None

"""SP11 Phase 5b — calibration auto-invocation + apply policy.

Tests the runtime.calibration_* fields drive the executor's
_run_calibration_pass behavior correctly across the pre-cal and
post-cal arms.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.core.config import RuntimeConfig


def test_runtime_calibration_defaults_are_full_on():
    """Default behavior: run pass AND apply to sampler (post-cal arm)."""
    rc = RuntimeConfig()
    assert rc.calibration_run_pass is True
    assert rc.calibration_apply_to_sampler is True
    assert rc.calibration_n_keys == 30


def test_runtime_calibration_no_apply_round_trip():
    """Phase 7 pre-cal arm: run pass, skip application."""
    rc = RuntimeConfig.from_dict({
        "calibration_apply_to_sampler": False,
    })
    assert rc.calibration_run_pass is True  # still runs pass
    assert rc.calibration_apply_to_sampler is False
    d = rc.to_dict()
    assert d["calibration_apply_to_sampler"] is False
    assert d["calibration_run_pass"] is True


def test_runtime_calibration_full_skip_round_trip():
    """Test escape hatch: skip pass entirely."""
    rc = RuntimeConfig.from_dict({
        "calibration_run_pass": False,
    })
    assert rc.calibration_run_pass is False
    assert rc.calibration_apply_to_sampler is True  # irrelevant when pass skipped
    assert rc.to_dict()["calibration_run_pass"] is False


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
    return TaskExecutor(TaskConfig.from_dict(base))


def test_run_calibration_pass_skips_when_run_pass_false():
    """runtime.calibration_run_pass=False short-circuits the executor."""
    ex = _executor_with_runtime({"calibration_run_pass": False})
    # Plug a fake deliverer so the early-return path is the one being tested.
    ex._deliverer = MagicMock()
    # If _run_calibration_pass actually ran, it'd touch the deliverer
    asyncio.run(ex._run_calibration_pass(MagicMock()))
    assert ex._calibration_run is None
    ex._deliverer.deliver_sequence.assert_not_called()


def test_run_calibration_pass_applies_to_sampler_by_default():
    """Post-cal arm: run pass AND install on sampler."""
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
        ex._sampler.set_calibration_result = MagicMock()
        asyncio.run(ex._run_calibration_pass(MagicMock()))
    ex._sampler.set_calibration_result.assert_called_once_with(fake_result)


def test_run_calibration_pass_skips_when_no_deliverer():
    """delivery_channel='none' or CDP unavailable → no calibration."""
    ex = _executor_with_runtime({})
    ex._deliverer = None
    asyncio.run(ex._run_calibration_pass(MagicMock()))
    assert ex._calibration_run is None

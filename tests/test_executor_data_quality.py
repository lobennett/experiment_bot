"""Wiring tests for A5b: capture-time stall flags.

_stall_ceiling_ms() derives the mechanical ceiling from
task_specific.trial_timing.max_response_time_ms (x4) when present, else
falls back to the fixed 10s default. _wait_for_completion wires the result
of compute_stall_flags into self._data_quality after a successful capture.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.output.data_quality import DEFAULT_CEILING_MS


def _bp_stub():
    p = MagicMock()
    p.program_sha256 = "00" * 32
    p.program_path = "stub_program.py"
    p.seed = 0
    return p


_BASE_CONFIG = {
    "task": {"name": "Test Task", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "go",
            "description": "Go stimulus",
            "detection": {"method": "dom_query", "selector": ".go"},
            "response": {"key": "f", "condition": "go"},
        },
    ],
    "response_distributions": {},
    "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {},
    "runtime": {},
}


# ---------------------------------------------------------------------------
# _stall_ceiling_ms
# ---------------------------------------------------------------------------


def test_ceiling_derives_from_trial_timing_max_response_time_ms():
    config_data = dict(_BASE_CONFIG)
    config_data["task_specific"] = {"trial_timing": {"max_response_time_ms": 1500}}
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, behavior_provider=_bp_stub())
    assert ex._stall_ceiling_ms() == 6000.0


def test_ceiling_defaults_when_trial_timing_missing():
    config = TaskConfig.from_dict(_BASE_CONFIG)
    ex = TaskExecutor(config, behavior_provider=_bp_stub())
    assert ex._stall_ceiling_ms() == DEFAULT_CEILING_MS


def test_ceiling_defaults_when_max_response_time_ms_not_numeric():
    config_data = dict(_BASE_CONFIG)
    config_data["task_specific"] = {"trial_timing": {"max_response_time_ms": "not_a_number"}}
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, behavior_provider=_bp_stub())
    assert ex._stall_ceiling_ms() == DEFAULT_CEILING_MS


def test_ceiling_defaults_when_max_response_time_ms_zero_or_negative():
    config_data = dict(_BASE_CONFIG)
    config_data["task_specific"] = {"trial_timing": {"max_response_time_ms": 0}}
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, behavior_provider=_bp_stub())
    assert ex._stall_ceiling_ms() == DEFAULT_CEILING_MS


# ---------------------------------------------------------------------------
# _wait_for_completion wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_completion_sets_data_quality_on_clean_capture():
    config_data = dict(_BASE_CONFIG)
    config_data["task_specific"] = {"trial_timing": {"max_response_time_ms": 1000}}
    config_data["runtime"] = {
        "data_capture": {
            "method": "js_expression",
            "expression": "jsPsych.data.get().csv()",
            "format": "csv",
        },
    }
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, seed=1, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer.run_dir = "/tmp/fake"
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="rt,condition\n420,go\n610,go\n")
    await ex._wait_for_completion(page)

    assert ex._data_quality == {"stall_trials": 0, "max_rt_ms": 610.0, "ceiling_ms": 4000.0}


@pytest.mark.asyncio
async def test_wait_for_completion_flags_stall_trial():
    config_data = dict(_BASE_CONFIG)
    config_data["task_specific"] = {"trial_timing": {"max_response_time_ms": 1000}}
    config_data["runtime"] = {
        "data_capture": {
            "method": "js_expression",
            "expression": "jsPsych.data.get().csv()",
            "format": "csv",
        },
    }
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, seed=1, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer.run_dir = "/tmp/fake"
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="rt,condition\n420,go\n45000,go\n")
    await ex._wait_for_completion(page)

    assert ex._data_quality["stall_trials"] == 1
    assert ex._data_quality["max_rt_ms"] == 45000.0
    assert ex._data_quality["ceiling_ms"] == 4000.0


@pytest.mark.asyncio
async def test_wait_for_completion_leaves_default_data_quality_when_no_capture():
    """No data_capture.method configured -> data_quality stays at its
    __init__ default (never computed, since there's nothing to scan)."""
    config_data = dict(_BASE_CONFIG)
    config_data["runtime"] = {"timing": {"completion_wait_ms": 1}}
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, seed=1, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer.run_dir = "/tmp/fake"
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    await ex._wait_for_completion(page)

    assert ex._data_quality == {"stall_trials": None, "note": "no data captured"}

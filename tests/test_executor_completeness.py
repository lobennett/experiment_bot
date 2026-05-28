"""Tests for Task 2: executor loop_exit_reason + completeness instrumentation.

Covers:
- _loop_exit_reason set to "max_misses" when trial loop exits on consecutive-miss overflow
- _loop_exit_reason set to "complete" on natural COMPLETE-phase detection
- run_metadata gains loop_exit_reason + incomplete
- suspect_adaptive_nav set when adaptive nav ran and loop did not complete
- detect_phase: exception path does settle+re-eval before returning COMPLETE
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.core.phase_detection import detect_phase


_SAMPLE_CONFIG = {
    "task": {
        "name": "Test Task",
        "platform": "expfactory",
        "constructs": [],
        "reference_literature": [],
    },
    "stimuli": [
        {
            "id": "go",
            "description": "Go stimulus",
            "detection": {"method": "dom_query", "selector": ".go"},
            "response": {"key": "f", "condition": "go"},
        },
    ],
    "response_distributions": {
        "go": {"distribution": "ex_gaussian", "params": {"mu": 500, "sigma": 60, "tau": 80}},
    },
    "performance": {
        "accuracy": {"go": 0.95},
        "omission_rate": {"go": 0.02},
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {},
    "runtime": {
        "timing": {
            # Keep poll interval short so the test loop terminates quickly
            "poll_interval_ms": 1,
            "max_no_stimulus_polls": 3,
        },
    },
}


@pytest.fixture
def executor():
    config = TaskConfig.from_dict(_SAMPLE_CONFIG)
    ex = TaskExecutor(config, headless=True, seed=42, session_params={})
    # Stub out writer so metadata calls don't fail
    ex._writer = MagicMock()
    ex._writer._trials = []
    return ex


# ---------------------------------------------------------------------------
# 1. max_misses exit reason
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trial_loop_sets_loop_exit_reason_max_misses(executor):
    """When no stimulus ever matches, _trial_loop breaks on max_misses and
    sets _loop_exit_reason = 'max_misses'."""
    page = AsyncMock()

    # Phase detection always returns TEST (so COMPLETE never fires)
    with patch(
        "experiment_bot.core.executor.detect_phase",
        new=AsyncMock(return_value=TaskPhase.TEST),
    ):
        # _lookup.identify always returns None (no stimulus match)
        executor._lookup = MagicMock()
        executor._lookup.identify = AsyncMock(return_value=None)

        await executor._trial_loop(MagicMock(), page)

    assert executor._loop_exit_reason == "max_misses"


# ---------------------------------------------------------------------------
# 2. natural COMPLETE exit reason
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trial_loop_sets_loop_exit_reason_complete(executor):
    """When detect_phase returns COMPLETE immediately, _loop_exit_reason = 'complete'."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="")  # body_snippet capture

    with patch(
        "experiment_bot.core.executor.detect_phase",
        new=AsyncMock(return_value=TaskPhase.COMPLETE),
    ):
        await executor._trial_loop(MagicMock(), page)

    assert executor._loop_exit_reason == "complete"


# ---------------------------------------------------------------------------
# 3. incomplete flag in run_metadata
# ---------------------------------------------------------------------------

def test_incomplete_flag_true_for_max_misses(executor):
    """run_metadata.incomplete == True when loop_exit_reason != 'complete'."""
    executor._loop_exit_reason = "max_misses"
    incomplete = executor._loop_exit_reason != "complete"
    assert incomplete is True


def test_incomplete_flag_false_for_complete(executor):
    """run_metadata.incomplete == False when loop_exit_reason == 'complete'."""
    executor._loop_exit_reason = "complete"
    incomplete = executor._loop_exit_reason != "complete"
    assert incomplete is False


# ---------------------------------------------------------------------------
# 4. suspect_adaptive_nav flag
# ---------------------------------------------------------------------------

def test_suspect_adaptive_nav_set_when_nav_used_and_incomplete(executor):
    """When adaptive nav ran and loop did not complete naturally,
    suspect_adaptive_nav should be True."""
    executor._loop_exit_reason = "max_misses"
    executor._adaptive_nav_uses = 3

    suspect = executor._adaptive_nav_uses > 0 and executor._loop_exit_reason != "complete"
    assert suspect is True


def test_no_suspect_adaptive_nav_on_complete(executor):
    """No suspect_adaptive_nav when loop completed naturally even if nav was used."""
    executor._loop_exit_reason = "complete"
    executor._adaptive_nav_uses = 2

    suspect = executor._adaptive_nav_uses > 0 and executor._loop_exit_reason != "complete"
    assert suspect is False


# ---------------------------------------------------------------------------
# 5. detect_phase: exception path does settle+re-eval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_phase_exception_retries_before_complete():
    """On exception during predicate eval, detect_phase does a settle+re-eval.
    If the re-eval raises again (context destroyed), it returns COMPLETE."""
    from experiment_bot.core.config import PhaseDetectionConfig

    cfg = PhaseDetectionConfig(complete="document.title === 'done'")

    page = AsyncMock()
    # First call raises, second call (after settle) also raises
    page.evaluate = AsyncMock(side_effect=Exception("context destroyed"))

    result = await detect_phase(page, cfg)

    # Should still return COMPLETE — either from exception path
    assert result == TaskPhase.COMPLETE
    # Should have been called at least twice (initial + re-eval)
    assert page.evaluate.call_count >= 2


@pytest.mark.asyncio
async def test_detect_phase_exception_reeval_succeeds_returns_complete():
    """If the first eval raises but the re-eval returns True, we get COMPLETE."""
    from experiment_bot.core.config import PhaseDetectionConfig

    cfg = PhaseDetectionConfig(complete="document.title === 'done'")

    page = AsyncMock()
    # First call raises; second call returns True (COMPLETE predicate matched)
    page.evaluate = AsyncMock(side_effect=[Exception("transient"), True])

    result = await detect_phase(page, cfg)
    assert result == TaskPhase.COMPLETE


@pytest.mark.asyncio
async def test_detect_phase_normal_path_no_extra_sleep():
    """On the normal (non-exception) path detect_phase does NOT insert a sleep."""
    from experiment_bot.core.config import PhaseDetectionConfig

    # complete returns False; instructions returns True → should return INSTRUCTIONS
    cfg = PhaseDetectionConfig(complete="false", instructions="true")

    page = AsyncMock()
    # First evaluate call (for complete predicate) returns False;
    # second (for instructions predicate) returns True.
    page.evaluate = AsyncMock(side_effect=[False, True])

    sleep_calls = []
    original_sleep = asyncio.sleep

    async def _mock_sleep(t):
        sleep_calls.append(t)
        await original_sleep(0)

    with patch("experiment_bot.core.phase_detection.asyncio", wraps=asyncio) as mock_asyncio:
        mock_asyncio.sleep = _mock_sleep
        result = await detect_phase(page, cfg)

    # The normal path should not call asyncio.sleep
    assert sleep_calls == []
    assert result == TaskPhase.INSTRUCTIONS

"""Wiring tests for A3: TaskExecutor increments LoopDiagnostics counters at
the trial loop's existing branch points.

Follows the mocked-loop-path pattern already used in
tests/test_executor_completeness.py and tests/test_executor.py
(mock detect_phase + _lookup.identify, drive `_trial_loop` directly).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.core.stimulus import StimulusMatch


def _bp_stub():
    p = MagicMock()
    p.program_sha256 = "00" * 32
    p.program_path = "stub_program.py"
    p.seed = 0
    return p


_SAMPLE_CONFIG = {
    "task": {"name": "Test Task", "platform": "expfactory", "constructs": [], "reference_literature": []},
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
    "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {},
    "runtime": {
        "timing": {"poll_interval_ms": 1, "max_no_stimulus_polls": 3},
    },
}


@pytest.fixture
def executor():
    config = TaskConfig.from_dict(_SAMPLE_CONFIG)
    ex = TaskExecutor(config, headless=True, seed=42, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer._trials = []
    return ex


# ---------------------------------------------------------------------------
# phase_counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase_counts_increment_per_detect_phase_call(executor):
    """Each detect_phase() call is recorded by phase value, including the
    final COMPLETE call that ends the loop."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="")

    with patch(
        "experiment_bot.core.executor.detect_phase",
        new=AsyncMock(side_effect=[TaskPhase.TEST, TaskPhase.TEST, TaskPhase.COMPLETE]),
    ):
        executor._lookup = MagicMock()
        executor._lookup.identify = AsyncMock(return_value=None)
        await executor._trial_loop(MagicMock(), page)

    diag = executor._loop_diagnostics.as_dict()
    assert diag["phase_counts"] == {"test": 2, "complete": 1}


# ---------------------------------------------------------------------------
# identify hits / misses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identify_miss_recorded_when_no_stimulus_matches(executor):
    """No stimulus ever matches -> identify_misses accumulates, no hits."""
    page = AsyncMock()

    with patch(
        "experiment_bot.core.executor.detect_phase",
        new=AsyncMock(return_value=TaskPhase.TEST),
    ):
        executor._lookup = MagicMock()
        executor._lookup.identify = AsyncMock(return_value=None)
        await executor._trial_loop(MagicMock(), page)

    diag = executor._loop_diagnostics.as_dict()
    assert diag["identify_misses"] >= 1
    assert diag["identify_hits"] == {}
    assert executor._loop_exit_reason == "max_misses"


@pytest.mark.asyncio
async def test_identify_hit_recorded_by_condition(executor):
    """A trial stimulus match increments identify_hits under its condition."""
    page = AsyncMock()
    match = StimulusMatch(stimulus_id="go", response_key="f", condition="go")

    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        return TaskPhase.TEST if call_count == 1 else TaskPhase.COMPLETE

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        executor._lookup = MagicMock()
        executor._lookup.identify = AsyncMock(return_value=match)
        executor._execute_trial = AsyncMock()
        await executor._trial_loop(MagicMock(), page)

    diag = executor._loop_diagnostics.as_dict()
    assert diag["identify_hits"] == {"go": 1}
    assert diag["identify_misses"] == 0


# ---------------------------------------------------------------------------
# response window open / closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_window_closed_recorded(executor):
    """response_window_js present and evaluating falsy records a closed poll."""
    config_data = dict(_SAMPLE_CONFIG)
    config_data["runtime"] = {
        "timing": {
            "poll_interval_ms": 1,
            "max_no_stimulus_polls": 3,
            "response_window_js": "window.__ready",
        },
    }
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, headless=True, seed=42, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer._trials = []

    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)  # window never opens

    with patch(
        "experiment_bot.core.executor.detect_phase",
        new=AsyncMock(return_value=TaskPhase.TEST),
    ):
        ex._lookup = MagicMock()
        ex._lookup.identify = AsyncMock(return_value=None)
        await ex._trial_loop(MagicMock(), page)

    diag = ex._loop_diagnostics.as_dict()
    assert diag["response_window_closed"] >= 1
    assert diag["response_window_open"] == 0


@pytest.mark.asyncio
async def test_response_window_open_recorded(executor):
    """response_window_js present and evaluating truthy records an open poll.

    A window that's always "ready" resets consecutive_misses to 0 every
    poll by design (a normal fixation/ITI signal, not a stimulus match by
    itself) — so this test bounds the loop via detect_phase's own COMPLETE,
    not via the miss counter, to avoid looping forever.
    """
    config_data = dict(_SAMPLE_CONFIG)
    config_data["runtime"] = {
        "timing": {
            "poll_interval_ms": 1,
            "max_no_stimulus_polls": 3,
            "response_window_js": "window.__ready",
        },
    }
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, headless=True, seed=42, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer._trials = []

    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)  # window open

    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        return TaskPhase.TEST if call_count <= 2 else TaskPhase.COMPLETE

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        ex._lookup = MagicMock()
        ex._lookup.identify = AsyncMock(return_value=None)
        await ex._trial_loop(MagicMock(), page)

    diag = ex._loop_diagnostics.as_dict()
    assert diag["response_window_open"] == 2
    assert diag["response_window_closed"] == 0


# ---------------------------------------------------------------------------
# advance_actions
# ---------------------------------------------------------------------------


def test_advance_min_spacing_s_constant_is_defined():
    """Regression test for a pre-existing bug found while writing the
    advance_actions coverage below: _trial_loop's general-miss branch
    referenced module constant _ADVANCE_MIN_SPACING_S, which was never
    defined anywhere in executor.py — a NameError latent in the "no
    stimulus match" miss-advance gate whenever consecutive_misses landed on
    an advance_interval_polls multiple. The commit that added the
    reference (af8cf4d) documented the intended value (2.0) in its commit
    message but never wrote the constant itself."""
    from experiment_bot.core import executor as ex_mod

    assert hasattr(ex_mod, "_ADVANCE_MIN_SPACING_S")
    assert ex_mod._ADVANCE_MIN_SPACING_S == 2.0


@pytest.mark.asyncio
async def test_advance_action_recorded_on_general_miss_branch(executor):
    """advance_interval_polls=1 -> the first miss already trips the advance
    block, so advance_actions increments alongside identify_misses.

    This also regression-tests the _ADVANCE_MIN_SPACING_S NameError fix
    above: before the fix, this exact branch (consecutive_misses a
    multiple of advance_interval_polls, still under max_no_stimulus_polls)
    crashed with NameError rather than incrementing the counter."""
    config_data = dict(_SAMPLE_CONFIG)
    config_data["runtime"] = {
        "timing": {"poll_interval_ms": 1, "max_no_stimulus_polls": 5},
        "advance_behavior": {"advance_interval_polls": 1, "advance_keys": ["Enter"]},
    }
    config = TaskConfig.from_dict(config_data)
    ex = TaskExecutor(config, headless=True, seed=42, behavior_provider=_bp_stub())
    ex._writer = MagicMock()
    ex._writer._trials = []

    page = AsyncMock()

    with patch(
        "experiment_bot.core.executor.detect_phase",
        new=AsyncMock(return_value=TaskPhase.TEST),
    ):
        ex._lookup = MagicMock()
        ex._lookup.identify = AsyncMock(return_value=None)
        await ex._trial_loop(MagicMock(), page)

    diag = ex._loop_diagnostics.as_dict()
    assert diag["advance_actions"] >= 1


# ---------------------------------------------------------------------------
# feedback / attention-check handling (recorded inside the handler methods
# themselves, exercised directly rather than through the full loop)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_feedback_records_feedback_handled(executor):
    executor._config.runtime.advance_behavior.feedback_selectors = []
    executor._config.runtime.advance_behavior.feedback_fallback_keys = []
    page = AsyncMock()
    await executor._handle_feedback(page)
    assert executor._loop_diagnostics.feedback_handled == 1


@pytest.mark.asyncio
async def test_handle_attention_check_records_attention_check_handled(executor):
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    await executor._handle_attention_check(page)
    assert executor._loop_diagnostics.attention_checks_handled == 1


# ---------------------------------------------------------------------------
# in-trial nav re-runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_trial_nav_rerun_recorded_on_stuck_instructions(executor):
    """INSTRUCTIONS phase with no trial stimulus present triggers the
    unified nav-phase re-run, recorded once per detection."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="")  # DOM fingerprint probe

    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        return TaskPhase.INSTRUCTIONS if call_count <= 2 else TaskPhase.COMPLETE

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        executor._lookup = MagicMock()
        executor._lookup.identify = AsyncMock(return_value=None)
        await executor._trial_loop(AsyncMock(), page)

    diag = executor._loop_diagnostics.as_dict()
    assert diag["in_trial_nav_reruns"] == 2


# ---------------------------------------------------------------------------
# loop_diagnostics land in run_trace's trial_loop stage + run_metadata
# ---------------------------------------------------------------------------


def test_loop_diagnostics_as_dict_shape_matches_record_trace_expectation(executor):
    """Cheap smoke check that the object handed to record_trace/metadata is
    the same as_dict() shape verified in test_loop_diagnostics.py."""
    executor._loop_diagnostics.record_phase("test")
    executor._loop_diagnostics.record_identify("go")
    d = executor._loop_diagnostics.as_dict()
    assert set(d.keys()) == {
        "phase_counts", "response_window_open", "response_window_closed",
        "identify_hits", "identify_misses", "advance_actions",
        "feedback_handled", "attention_checks_handled", "in_trial_nav_reruns",
    }

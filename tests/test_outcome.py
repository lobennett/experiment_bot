"""Unit tests for classify_outcome (A5a)."""
from __future__ import annotations

import pytest
from playwright.async_api import Error as PlaywrightError

from experiment_bot.core.outcome import classify_outcome


def test_completed_when_no_exception_and_trials_recorded():
    assert classify_outcome("complete", 120, None) == "completed"


def test_completed_with_partial_trials_and_non_max_misses_exit():
    """A partial session (early break, e.g. window_closed) with real trials
    recorded and no exception is still 'completed' — completeness is
    tracked separately via run_metadata.incomplete."""
    assert classify_outcome("window_closed", 40, None) == "completed"


def test_zero_trials_no_exception_default_reason():
    assert classify_outcome("complete", 0, None) == "zero_trials"


def test_nav_stall_no_exception_max_misses_reason():
    assert classify_outcome("max_misses", 0, None) == "nav_stall"


def test_zero_trials_hardfail_runtimeerror_non_max_misses_reason():
    """The executor's 0-trial hard-fail RuntimeError fires regardless of
    loop_exit_reason; when the reason isn't max_misses it's the generic
    zero_trials label, not the more specific nav_stall."""
    exc = RuntimeError("Executor captured 0 trials.")
    assert classify_outcome("complete", 0, exc) == "zero_trials"
    assert classify_outcome("context_destroyed", 0, exc) == "zero_trials"
    assert classify_outcome("window_closed", 0, exc) == "zero_trials"


def test_nav_stall_hardfail_runtimeerror_max_misses_reason():
    exc = RuntimeError("Executor captured 0 trials.")
    assert classify_outcome("max_misses", 0, exc) == "nav_stall"


def test_program_error_for_protocol_violation():
    from experiment_bot.behavior.provider import ProtocolViolation

    exc = ProtocolViolation("bad tuple")
    assert classify_outcome("complete", 5, exc) == "program_error"
    assert classify_outcome("max_misses", 0, exc) == "program_error"


def test_program_error_for_arbitrary_exception_from_program():
    """A generated program's own code can raise anything (KeyError,
    ZeroDivisionError, ...); none of those are RuntimeError or a Playwright
    error, so they fall to program_error by elimination."""
    assert classify_outcome("complete", 10, ZeroDivisionError("boom")) == "program_error"
    assert classify_outcome("complete", 10, KeyError("x")) == "program_error"


def test_program_error_for_runtime_error_with_trials_recorded():
    """A RuntimeError that isn't the 0-trial hard-fail (trial_count > 0)
    isn't zero_trials/nav_stall; it falls to program_error."""
    exc = RuntimeError("some other runtime error")
    assert classify_outcome("complete", 3, exc) == "program_error"


def test_platform_error_for_playwright_error():
    exc = PlaywrightError("Target page, context or browser has been closed")
    assert classify_outcome("complete", 50, exc) == "platform_error"
    assert classify_outcome("max_misses", 0, exc) == "platform_error"


@pytest.mark.parametrize(
    "loop_exit_reason,trial_count,exc,expected",
    [
        ("complete", 200, None, "completed"),
        ("budget", 500, None, "completed"),
        ("max_misses", 0, None, "nav_stall"),
        ("window_closed", 0, None, "zero_trials"),
    ],
)
def test_matrix(loop_exit_reason, trial_count, exc, expected):
    assert classify_outcome(loop_exit_reason, trial_count, exc) == expected

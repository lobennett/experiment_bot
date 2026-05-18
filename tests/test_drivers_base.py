"""SP10: PlatformDriver Protocol contract + types."""
from __future__ import annotations
import inspect

import pytest

from experiment_bot.drivers.base import (
    DeliveryResult,
    DriverError,
    ExperimentData,
    NavigationOutcome,
    PlatformDriver,
    TrialContext,
    TrialLoopState,
    UnsupportedVersionError,
)


def test_trial_loop_state_has_three_members():
    assert {m.name for m in TrialLoopState} == {
        "NEEDS_NAVIGATION", "READY_FOR_TRIAL", "COMPLETE",
    }


def test_trial_context_required_fields():
    ctx = TrialContext(
        stimulus_id="s1",
        condition="congruent",
        allowed_responses=(",", "."),
        expected_correct=",",
        response_window_ms=None,
    )
    assert ctx.stimulus_id == "s1"
    assert ctx.allowed_responses == (",", ".")
    assert ctx.metadata == {}


def test_delivery_result_required_fields():
    r = DeliveryResult(
        success=True, delivered_at_ms=100.0, actual_rt_ms=350.0,
        method="jspsych_callback_hook",
    )
    assert r.error is None


def test_navigation_outcome_required_fields():
    o = NavigationOutcome(action="advanced_instructions")
    assert o.details == {}


def test_experiment_data_required_fields():
    d = ExperimentData(trials=[{"x": 1}], format="json", raw='[{"x":1}]')
    assert d.metadata == {}


def test_driver_error_carries_structured_info():
    err = DriverError(kind="page_torn_down", context={"url": "x"}, recoverable=True)
    assert err.kind == "page_torn_down"
    assert err.recoverable is True


def test_unsupported_version_error_subclasses_driver_error():
    err = UnsupportedVersionError(
        detected_version="9.0.0",
        supported_versions=("7.3.0", "8.0.0"),
        missing_anchors=["vendor/jspsych/9.0.0/"],
    )
    assert isinstance(err, DriverError)
    assert err.detected_version == "9.0.0"


def test_platform_driver_is_a_protocol():
    """Protocol marker for static typing — concrete drivers don't subclass
    PlatformDriver; they implement its methods. inspect-based smoke check
    that the Protocol has the documented methods."""
    methods = {n for n, _ in inspect.getmembers(PlatformDriver, predicate=inspect.isfunction)}
    expected = {
        "can_handle", "setup", "loop_state", "navigate",
        "get_trial_context", "deliver_response",
        "wait_for_trial_end", "wait_for_completion",
        "retrieve_data", "teardown",
    }
    missing = expected - methods
    assert not missing, f"PlatformDriver missing methods: {missing}"

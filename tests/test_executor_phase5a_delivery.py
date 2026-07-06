"""SP11 Phase 5a — TaskExecutor keypress delivery wiring tests.

Tests the new `_fire_response_key` helper and the delivery_channel
config field. Pure-mock; no live browser.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.core.config import RuntimeConfig, TimingConfig


def _bp_stub():
    """Minimal behavior-provider stub: TaskExecutor requires one at init;
    structural tests never execute trials through it."""
    from unittest.mock import MagicMock
    p = MagicMock()
    p.program_sha256 = "00" * 32
    p.program_path = "stub_program.py"
    p.seed = 0
    return p




_SAMPLE_CONFIG = {
    "task": {"name": "Phase5a Test", "platform": "test", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "test_stim",
            "description": "Test stimulus",
            "detection": {"method": "dom_query", "selector": "#stim"},
            "response": {"key": " ", "condition": "default"},
        },
    ],
    "response_distributions": {
        "default": {"distribution": "ex_gaussian", "params": {"mu": 600, "sigma": 100, "tau": 80}},
    },
    "performance": {"accuracy": {"default": 0.95}, "omission_rate": {"default": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
}


def _make_executor_for_test():
    """Construct a TaskExecutor with a minimal config — only the
    delivery wiring is exercised."""
    from experiment_bot.core.config import TaskConfig
    from experiment_bot.core.executor import TaskExecutor
    ex = TaskExecutor(TaskConfig.from_dict(_SAMPLE_CONFIG), behavior_provider=_bp_stub())
    return ex


def test_executor_init_has_phase5a_attributes():
    """The new Phase 5a-introduced attributes are initialized."""
    ex = _make_executor_for_test()
    assert ex._cdp_session is None
    assert ex._deliverer is None
    assert ex._calibration_run is None
    assert ex._delivery_channel_log == {}
    assert ex._fire_skip_log == []


def test_fire_response_key_falls_back_to_keyboard_press_when_no_deliverer():
    """When self._deliverer is None, the bot falls back to
    page.keyboard.press and tags channel='page_keyboard_press'."""
    ex = _make_executor_for_test()
    fake_keyboard = AsyncMock()
    fake_page = MagicMock()
    fake_page.keyboard = MagicMock(press=fake_keyboard)
    meta = asyncio.run(ex._fire_response_key(fake_page, ","))
    fake_keyboard.assert_awaited_once_with(",")
    assert meta["channel"] == "page_keyboard_press"
    assert meta["skipped"] is False
    assert ex._delivery_channel_log["page_keyboard_press"] == 1


def test_fire_response_key_uses_deliverer_when_set():
    """When self._deliverer is set, deliver_at_trial_start runs and
    its channel is logged."""
    ex = _make_executor_for_test()
    # Construct a fake deliverer mimicking CDPDeliverer surface
    from experiment_bot.calibration.cdp_deliverer import _FireRecord
    fake_deliverer = MagicMock()
    fake_deliverer.DELIVERY_CHANNEL = "cdp_dispatchKeyEvent"
    fake_deliverer.deliver_at_trial_start = AsyncMock(
        return_value=_FireRecord(
            key=",", intended_dwell_ms=0.0, observed_dwell_ms=0.0,
            trial_marker_at_fire=5, skipped=False, skip_reason=None,
            fired_at_monotonic=1.0, cdp_fields={},
        )
    )
    ex._deliverer = fake_deliverer
    fake_page = MagicMock()
    meta = asyncio.run(ex._fire_response_key(fake_page, ","))
    fake_deliverer.deliver_at_trial_start.assert_awaited_once_with(",", dwell_ms=0.0)
    assert meta["channel"] == "cdp_dispatchKeyEvent"
    assert meta["trial_marker_at_fire"] == 5
    assert meta["skipped"] is False
    assert ex._delivery_channel_log["cdp_dispatchKeyEvent"] == 1


def test_fire_response_key_logs_skip_on_verify_failure():
    """If the deliverer's four-step protocol skips (trial advanced
    during dwell etc.), self._fire_skip_log captures the diagnostic
    and meta surfaces skipped=True."""
    ex = _make_executor_for_test()
    from experiment_bot.calibration.cdp_deliverer import _FireRecord
    fake_deliverer = MagicMock()
    fake_deliverer.DELIVERY_CHANNEL = "cdp_dispatchKeyEvent"
    fake_deliverer.deliver_at_trial_start = AsyncMock(
        return_value=_FireRecord(
            key=",", intended_dwell_ms=0.0, observed_dwell_ms=0.0,
            trial_marker_at_fire=5, skipped=True,
            skip_reason="trial_advanced_during_dwell",
            fired_at_monotonic=None, cdp_fields={},
        )
    )
    ex._deliverer = fake_deliverer
    fake_page = MagicMock()
    meta = asyncio.run(ex._fire_response_key(fake_page, ","))
    assert meta["skipped"] is True
    assert meta["skip_reason"] == "trial_advanced_during_dwell"
    assert len(ex._fire_skip_log) == 1
    assert ex._fire_skip_log[0]["skip_reason"] == "trial_advanced_during_dwell"


def test_runtime_config_delivery_channel_default_is_cdp():
    rc = RuntimeConfig()
    assert rc.delivery_channel == "cdp"


def test_runtime_config_delivery_channel_round_trip():
    rc = RuntimeConfig.from_dict({"delivery_channel": "keyboard"})
    assert rc.delivery_channel == "keyboard"
    assert rc.to_dict()["delivery_channel"] == "keyboard"


def test_runtime_config_delivery_channel_none_legacy():
    """delivery_channel='none' preserves the legacy SP10-era flow."""
    rc = RuntimeConfig.from_dict({"delivery_channel": "none"})
    assert rc.delivery_channel == "none"


def test_timing_config_cdp_dwell_ms_default_is_200():
    tc = TimingConfig()
    assert tc.cdp_dwell_ms == 200.0


def test_timing_config_cdp_dwell_ms_round_trip():
    """A regenerated TaskCard for stop-signal will pin a lower dwell."""
    tc = TimingConfig.from_dict({"cdp_dwell_ms": 100.0})
    assert tc.cdp_dwell_ms == 100.0
    assert tc.to_dict()["cdp_dwell_ms"] == 100.0


def test_timing_config_trial_marker_js_jspsych6_override():
    """stopit's jsPsych 6 override per Phase 5a.0 probe."""
    js = "() => window.jsPsych.progress().current_trial_global"
    tc = TimingConfig.from_dict({"trial_marker_js": js})
    assert tc.trial_marker_js == js
    assert tc.to_dict()["trial_marker_js"] == js

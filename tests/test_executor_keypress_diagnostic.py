"""Unit tests for SP7 keypress diagnostic instrumentation.

The executor injects a generic page-level keydown listener at session
start and drains it once per trial, adding two new fields to each
trial log entry: `resolved_key_pre_error` (the bot's raw resolution
before `_pick_wrong_key`) and `page_received_keys` (the events the
page's listener captured).

The listener and drain are paradigm-agnostic (document.addEventListener
on 'keydown', no platform-specific assumptions). Stub-based tests
verify the executor evaluates the right JS without invoking a real
Playwright page.
"""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from experiment_bot.core.executor import TaskExecutor


def _stub_executor(poll_interval_ms: int = 10) -> TaskExecutor:
    stub = TaskExecutor.__new__(TaskExecutor)
    timing = SimpleNamespace(poll_interval_ms=poll_interval_ms)
    runtime = SimpleNamespace(timing=timing)
    stub._config = SimpleNamespace(runtime=runtime)
    stub._stimulus_detection_js_cache = {}
    return stub


@pytest.mark.asyncio
async def test_install_keydown_listener_evaluates_correct_js():
    stub = _stub_executor()
    page = AsyncMock()
    await stub._install_keydown_listener(page)
    assert page.evaluate.call_count == 1
    js = page.evaluate.call_args.args[0]
    # Listener installation JS must:
    # - Initialize the storage array.
    # - Attach a 'keydown' listener.
    # - Capture key, code, and time per event.
    # - Use capture-phase (third arg true) so the listener sees events
    #   before any application-level handler.
    assert "window.__bot_keydown_log" in js
    assert "addEventListener('keydown'" in js
    assert "e.key" in js and "e.code" in js
    assert "Date.now()" in js
    assert ", true)" in js  # capture-phase flag


@pytest.mark.asyncio
async def test_install_keydown_listener_resets_log():
    """A second injection re-initializes window.__bot_keydown_log (idempotent)."""
    stub = _stub_executor()
    page = AsyncMock()
    await stub._install_keydown_listener(page)
    await stub._install_keydown_listener(page)
    # Both injections must reset the log: every call starts with `window.__bot_keydown_log = []`.
    for call in page.evaluate.call_args_list:
        js = call.args[0]
        assert "window.__bot_keydown_log = []" in js


@pytest.mark.asyncio
async def test_drain_keydown_log_returns_captured_keys():
    stub = _stub_executor()
    page = AsyncMock()
    captured = [{"key": ",", "code": "Comma", "time": 12345}]
    page.evaluate = AsyncMock(return_value=captured)
    result = await stub._drain_keydown_log(page)
    assert result == captured
    page.evaluate.assert_called_once()
    js = page.evaluate.call_args.args[0]
    # Drain JS must:
    # - Read window.__bot_keydown_log (or default to []).
    # - Clear the array after reading (so next trial doesn't double-count).
    assert "window.__bot_keydown_log" in js
    assert "= []" in js  # the reset


@pytest.mark.asyncio
async def test_drain_keydown_log_returns_empty_when_no_events():
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    result = await stub._drain_keydown_log(page)
    assert result == []


@pytest.mark.asyncio
async def test_drain_keydown_log_returns_none_on_evaluate_failure():
    """If page.evaluate raises (page tearing down), drain returns None
    rather than propagating the exception. Trial logging must continue."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    result = await stub._drain_keydown_log(page)
    assert result is None


@pytest.mark.asyncio
async def test_log_trial_includes_new_keypress_fields():
    """After Task 3 wiring: the trial log entry must include
    resolved_key_pre_error and page_received_keys."""
    from unittest.mock import MagicMock
    stub = _stub_executor()
    # Stub _writer to capture log_trial calls.
    log_calls = []
    stub._writer = MagicMock()
    stub._writer.log_trial = lambda payload: log_calls.append(payload)
    # Stub page with a drainable log.
    page = AsyncMock()
    captured_keys = [{"key": ",", "code": "Comma", "time": 1000}]
    page.evaluate = AsyncMock(return_value=captured_keys)

    payload = {
        "trial": 1,
        "stimulus_id": "go",
        "condition": "congruent",
        "response_key": ",",  # post-_pick_wrong_key
    }
    await stub._log_trial_with_keypress_diag(
        page=page,
        base_payload=payload,
        resolved_key_pre_error=".",
    )
    assert len(log_calls) == 1
    written = log_calls[0]
    # Existing fields preserved
    assert written["trial"] == 1
    assert written["response_key"] == ","
    # New fields added
    assert written["resolved_key_pre_error"] == "."
    assert written["page_received_keys"] == captured_keys


@pytest.mark.asyncio
async def test_log_trial_with_keypress_diag_handles_drain_failure():
    """If drain fails, page_received_keys=None but trial still logs."""
    from unittest.mock import MagicMock
    stub = _stub_executor()
    log_calls = []
    stub._writer = MagicMock()
    stub._writer.log_trial = lambda payload: log_calls.append(payload)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))

    payload = {"trial": 1, "response_key": ","}
    await stub._log_trial_with_keypress_diag(
        page=page,
        base_payload=payload,
        resolved_key_pre_error=".",
    )
    assert log_calls[0]["page_received_keys"] is None
    assert log_calls[0]["trial"] == 1
    assert log_calls[0]["response_key"] == ","

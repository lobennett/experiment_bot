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

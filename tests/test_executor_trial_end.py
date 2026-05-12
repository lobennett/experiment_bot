"""Unit tests for executor trial-end fallback helpers (SP6).

`_wait_for_trial_end` previously skipped the wait entirely when
`response_window_js` was None. SP6 adds a `fallback_js` parameter so
the executor can poll the stimulus's own detection JS until it stops
matching. This prevents the polling loop from re-detecting the same
stimulus and double-firing the trial handler — the SP5-observed
over-firing bug.
"""
from __future__ import annotations
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.core.executor import TaskExecutor


def _stub_executor(poll_interval_ms: int = 10) -> TaskExecutor:
    """Build a stub TaskExecutor whose only initialized state is the
    `_config.runtime.timing.poll_interval_ms` field used by
    `_wait_for_trial_end` and the cache field used by
    `_stimulus_detection_js`."""
    stub = TaskExecutor.__new__(TaskExecutor)
    timing = SimpleNamespace(poll_interval_ms=poll_interval_ms)
    runtime = SimpleNamespace(timing=timing)
    stub._config = SimpleNamespace(runtime=runtime)
    stub._stimulus_detection_js_cache = {}
    return stub


@pytest.mark.asyncio
async def test_wait_returns_immediately_when_both_none():
    stub = _stub_executor()
    page = AsyncMock()
    await stub._wait_for_trial_end(page, None, fallback_js=None, timeout_s=1.0)
    page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_wait_uses_response_window_js_when_present():
    """response_window_js takes precedence over fallback_js when set."""
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=[True, True, False])
    await stub._wait_for_trial_end(
        page, "preferred_js", fallback_js="fallback_should_be_ignored",
        timeout_s=1.0,
    )
    # Three evaluate calls; all use preferred_js.
    assert page.evaluate.call_count == 3
    for call in page.evaluate.call_args_list:
        assert call.args[0] == "preferred_js"


@pytest.mark.asyncio
async def test_wait_falls_back_to_stimulus_js_when_response_window_none():
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=[True, False])
    await stub._wait_for_trial_end(
        page, None, fallback_js="!!(stim_detect)", timeout_s=1.0,
    )
    assert page.evaluate.call_count == 2
    for call in page.evaluate.call_args_list:
        assert call.args[0] == "!!(stim_detect)"


@pytest.mark.asyncio
async def test_wait_returns_on_timeout():
    """If JS keeps returning truthy, function exits within timeout."""
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    import time as _time
    t0 = _time.monotonic()
    await stub._wait_for_trial_end(
        page, "always_true_js", fallback_js=None, timeout_s=0.05,
    )
    elapsed = _time.monotonic() - t0
    assert elapsed < 0.5, f"timeout not honored: elapsed={elapsed}s"


@pytest.mark.asyncio
async def test_wait_returns_on_evaluate_exception():
    """If page.evaluate raises (page navigated away), function returns gracefully."""
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    # Should not raise:
    await stub._wait_for_trial_end(
        page, "any_js", fallback_js=None, timeout_s=1.0,
    )
    page.evaluate.assert_called_once()

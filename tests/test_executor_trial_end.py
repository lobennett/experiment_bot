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


def _stim(method: str, selector: str, stim_id: str = "test_stim"):
    """Build a stimulus stub with .id, .detection.method, .detection.selector."""
    detection = SimpleNamespace(method=method, selector=selector)
    return SimpleNamespace(id=stim_id, detection=detection)


def test_stimulus_detection_js_dom_query():
    stub = _stub_executor()
    stim = _stim("dom_query", ".foo")
    js = stub._stimulus_detection_js(stim)
    assert js == "document.querySelector('.foo') !== null"


def test_stimulus_detection_js_js_eval():
    stub = _stub_executor()
    stim = _stim("js_eval", "window.x === 1")
    js = stub._stimulus_detection_js(stim)
    assert js == "!!(window.x === 1)"


def test_stimulus_detection_js_canvas_state():
    stub = _stub_executor()
    stim = _stim("canvas_state", "ctx.getImageData(0,0,1,1)[0] > 100")
    js = stub._stimulus_detection_js(stim)
    assert js == "!!(ctx.getImageData(0,0,1,1)[0] > 100)"


def test_stimulus_detection_js_quotes_safely():
    """A dom_query selector containing a single quote must be escaped
    so the resulting JS is valid (mirrors _build_interrupt_check_js's
    pattern of replacing `'` with `\\'` before string interpolation)."""
    stub = _stub_executor()
    stim = _stim("dom_query", "div[data-name='foo']")
    js = stub._stimulus_detection_js(stim)
    assert js == "document.querySelector('div[data-name=\\'foo\\']') !== null"


def test_stimulus_detection_js_caches():
    """Same stimulus -> result cached; second call returns identical
    string and does not re-build."""
    stub = _stub_executor()
    stim = _stim("js_eval", "expr", stim_id="cache_me")
    js1 = stub._stimulus_detection_js(stim)
    # Mutate the underlying selector after first call; cached result must NOT change.
    stim.detection.selector = "MUTATED"
    js2 = stub._stimulus_detection_js(stim)
    assert js2 == js1


def test_stimulus_detection_js_returns_none_for_empty_selector():
    stub = _stub_executor()
    stim = _stim("js_eval", "")
    assert stub._stimulus_detection_js(stim) is None


def test_stimulus_detection_js_returns_none_for_unknown_method():
    stub = _stub_executor()
    stim = _stim("unknown_method", "anything")
    assert stub._stimulus_detection_js(stim) is None

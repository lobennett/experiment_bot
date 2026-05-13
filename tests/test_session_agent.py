"""Unit tests for the SP9a SessionAgent layer (types, page_probe, session_agent).

The agent module is paradigm-agnostic — its interface accepts a Page
and a TaskCard dict, and returns a KeyMappingDirective without knowing
which paradigm is loaded.
"""
from __future__ import annotations
import pytest

from experiment_bot.agent.types import KeyMappingDirective


def test_directive_dataclass_to_dict_roundtrip():
    """to_dict() emits the canonical run_metadata.json shape."""
    d = KeyMappingDirective(
        mapping={"congruent": "z", "incongruent": "/"},
        source="screenshot_inference",
        confidence=0.85,
        raw_llm_response="raw response text",
        elapsed_ms=2847.3,
    )
    got = d.to_dict()
    assert got == {
        "mapping": {"congruent": "z", "incongruent": "/"},
        "source": "screenshot_inference",
        "confidence": 0.85,
        "raw_llm_response": "raw response text",
        "elapsed_ms": 2847.3,
    }


def test_directive_source_must_be_one_of_known_values():
    """The source literal narrows to the documented set."""
    # Doesn't raise — typing-level constraint only, but the dataclass
    # still accepts the value at runtime. We exercise each known value
    # to make sure the dataclass is constructable with each.
    for src in (
        "window_correctresponse",
        "dom_inference",
        "screenshot_inference",
        "llm_failure_fallback",
    ):
        d = KeyMappingDirective(
            mapping={"x": "y"},
            source=src,
            confidence=1.0,
            raw_llm_response="",
            elapsed_ms=0.0,
        )
        assert d.source == src


from unittest.mock import AsyncMock

from experiment_bot.agent import page_probe


@pytest.mark.asyncio
async def test_snapshot_window_globals_returns_dict_from_page_evaluate():
    """snapshot_window_globals evaluates a JS expression that returns a
    dict of matching window keys → string-truncated values."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={
        "correctResponse": "f",
        "responseKey": "j",
    })
    got = await page_probe.snapshot_window_globals(page)
    assert got == {"correctResponse": "f", "responseKey": "j"}
    # JS must filter on the response/correct/key/stim regex and stringify values
    js = page.evaluate.call_args.args[0]
    assert "response|correct|key|stim" in js
    assert "200" in js  # value truncation length


@pytest.mark.asyncio
async def test_snapshot_window_globals_returns_empty_dict_on_evaluate_failure():
    """If evaluate raises (page torn down, etc.), return {} not raise."""
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    got = await page_probe.snapshot_window_globals(page)
    assert got == {}


@pytest.mark.asyncio
async def test_snapshot_dom_summary_truncates_to_20kb():
    """DOM summary is capped at 20480 characters."""
    page = AsyncMock()
    page.content = AsyncMock(return_value="x" * 50000)
    got = await page_probe.snapshot_dom_summary(page)
    assert len(got) <= 20480


@pytest.mark.asyncio
async def test_snapshot_dom_summary_returns_full_when_under_limit():
    """Small DOM returns unchanged."""
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>tiny</body></html>")
    got = await page_probe.snapshot_dom_summary(page)
    assert got == "<html><body>tiny</body></html>"


@pytest.mark.asyncio
async def test_capture_screenshot_returns_bytes_from_page():
    """capture_screenshot is a thin wrapper around page.screenshot()."""
    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG-bytes")
    got = await page_probe.capture_screenshot(page)
    assert got == b"\x89PNG-bytes"
    # Must request PNG with viewport-only (not full_page)
    kwargs = page.screenshot.call_args.kwargs
    assert kwargs.get("type") == "png"
    assert kwargs.get("full_page") is False


@pytest.mark.asyncio
async def test_capture_screenshot_returns_empty_bytes_on_failure():
    """If screenshot raises, return b'' not raise."""
    page = AsyncMock()
    page.screenshot = AsyncMock(side_effect=Exception("page closed"))
    got = await page_probe.capture_screenshot(page)
    assert got == b""

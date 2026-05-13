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


import json
from unittest.mock import AsyncMock, MagicMock

from experiment_bot.agent.session_agent import SessionAgent
from experiment_bot.llm.protocol import LLMResponse


def _scripted_client(text: str):
    """Stub LLMClient whose complete() returns LLMResponse(text=text)."""
    client = MagicMock()
    client.complete = AsyncMock(return_value=LLMResponse(text=text))
    return client


def _stub_page(globals_dict: dict, dom: str, screenshot: bytes):
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=globals_dict)
    page.content = AsyncMock(return_value=dom)
    page.screenshot = AsyncMock(return_value=screenshot)
    return page


@pytest.mark.asyncio
async def test_resolve_key_mapping_returns_directive_from_llm_response():
    """Happy path: LLM returns valid JSON with mapping + source + confidence."""
    llm_text = json.dumps({
        "mapping": {"congruent": "z", "incongruent": "/"},
        "source": "screenshot_inference",
        "confidence": 0.85,
    })
    client = _scripted_client(llm_text)
    page = _stub_page({}, "<html></html>", b"png")
    task_card = {"task_specific": {"key_map": {"congruent": "z", "incongruent": "/"}}}

    agent = SessionAgent(client=client)
    directive = await agent.resolve_key_mapping(page=page, task_card=task_card)

    assert directive.mapping == {"congruent": "z", "incongruent": "/"}
    assert directive.source == "screenshot_inference"
    assert directive.confidence == 0.85
    assert directive.raw_llm_response == llm_text
    assert directive.elapsed_ms > 0


@pytest.mark.asyncio
async def test_resolve_key_mapping_handles_llm_failure_returns_static_fallback():
    """When LLM.complete raises, return a directive with source='llm_failure_fallback'
    and mapping taken from task_card.task_specific.key_map."""
    client = MagicMock()
    client.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
    page = _stub_page({}, "<html></html>", b"png")
    task_card = {"task_specific": {"key_map": {"congruent": "z", "incongruent": "/"}}}

    agent = SessionAgent(client=client)
    directive = await agent.resolve_key_mapping(page=page, task_card=task_card)

    assert directive.source == "llm_failure_fallback"
    assert directive.mapping == {"congruent": "z", "incongruent": "/"}
    assert directive.confidence == 0.0


@pytest.mark.asyncio
async def test_resolve_key_mapping_handles_malformed_llm_response():
    """When the LLM returns non-JSON or missing fields, fall back to static."""
    client = _scripted_client("not-json-at-all")
    page = _stub_page({}, "<html></html>", b"png")
    task_card = {"task_specific": {"key_map": {"congruent": "z"}}}

    agent = SessionAgent(client=client)
    directive = await agent.resolve_key_mapping(page=page, task_card=task_card)

    assert directive.source == "llm_failure_fallback"
    assert directive.mapping == {"congruent": "z"}


@pytest.mark.asyncio
async def test_resolve_key_mapping_passes_screenshot_to_llm():
    """SessionAgent must call client.complete with images=[screenshot_bytes]."""
    llm_text = json.dumps({
        "mapping": {"a": "b"},
        "source": "screenshot_inference",
        "confidence": 0.9,
    })
    client = _scripted_client(llm_text)
    page = _stub_page({}, "<html></html>", b"\x89PNG-screenshot-bytes")
    task_card = {"task_specific": {"key_map": {}}}

    agent = SessionAgent(client=client)
    await agent.resolve_key_mapping(page=page, task_card=task_card)

    call_kwargs = client.complete.call_args.kwargs
    assert call_kwargs["images"] == [b"\x89PNG-screenshot-bytes"]


@pytest.mark.asyncio
async def test_resolve_key_mapping_truncates_dom_in_prompt():
    """A 100KB DOM is truncated when included in the user prompt."""
    llm_text = json.dumps({"mapping": {"a": "b"}, "source": "dom_inference", "confidence": 0.5})
    client = _scripted_client(llm_text)
    page = _stub_page({}, "x" * 100000, b"png")
    task_card = {"task_specific": {"key_map": {}}}

    agent = SessionAgent(client=client)
    await agent.resolve_key_mapping(page=page, task_card=task_card)

    user_prompt = client.complete.call_args.kwargs["user"]
    # The prompt embeds the DOM (truncated to 20KB) plus framing text.
    # Total prompt length should be well under 50KB.
    assert len(user_prompt) < 50000


@pytest.mark.asyncio
async def test_resolve_key_mapping_includes_window_globals_in_prompt():
    """When the page exposes window.correctResponse, the JSON-stringified
    globals dict is in the user prompt — the LLM can see it directly."""
    llm_text = json.dumps({
        "mapping": {"congruent": "f", "incongruent": "j"},
        "source": "window_correctresponse",
        "confidence": 0.95,
    })
    client = _scripted_client(llm_text)
    page = _stub_page(
        {"correctResponse": "f", "stimType": "congruent"},
        "<html></html>", b"png",
    )
    task_card = {"task_specific": {"key_map": {}}}

    agent = SessionAgent(client=client)
    await agent.resolve_key_mapping(page=page, task_card=task_card)

    user_prompt = client.complete.call_args.kwargs["user"]
    assert "correctResponse" in user_prompt
    assert "stimType" in user_prompt

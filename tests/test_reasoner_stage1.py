import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage1_structural import run_stage1
from experiment_bot.llm.protocol import LLMResponse
from experiment_bot.core.config import SourceBundle
from tests.fixtures.fake_llm_responses import STAGE1_STROOP_RESPONSE


@pytest.mark.asyncio
async def test_stage1_returns_partial_taskcard():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE1_STROOP_RESPONSE))
    bundle = SourceBundle(
        url="http://example.com/stroop",
        source_files={"main.js": "..."},
        description_text="<html>...</html>",
    )
    partial = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"
    assert "stroop_congruent" in {s["id"] for s in partial["stimuli"]}
    assert partial["performance"]["accuracy"]["congruent"] == 0.97
    fake.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_stage1_extracts_json_from_markdown_fence():
    fake = AsyncMock()
    wrapped = "```json\n" + STAGE1_STROOP_RESPONSE + "\n```"
    fake.complete = AsyncMock(return_value=LLMResponse(text=wrapped))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    partial = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"


@pytest.mark.asyncio
async def test_stage1_extracts_json_from_preamble_postamble():
    """Claude sometimes wraps JSON in narrative text."""
    fake = AsyncMock()
    wrapped = "Here is the config:\n\n" + STAGE1_STROOP_RESPONSE + "\n\nLet me know if you have questions."
    fake.complete = AsyncMock(return_value=LLMResponse(text=wrapped))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    partial = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"

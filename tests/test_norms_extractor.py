import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.norms_extractor import extract_norms, NormsSchemaError
from experiment_bot.llm.protocol import LLMResponse


CONFLICT_NORMS_RESPONSE = """
{
  "paradigm_class": "conflict",
  "metrics": {
    "rt_distribution": {
      "mu_range": [430, 580],
      "sigma_range": [40, 90],
      "tau_range": [50, 130],
      "citations": [{"doi": "10.0000/whelan", "authors": "Whelan", "year": 2008,
                      "title": "x", "table_or_figure": "T1", "page": 1,
                      "quote": "...", "confidence": "high"}]
    },
    "cse_magnitude": {
      "range_ms": [-55, -15],
      "citations": [{"doi": "10.1016/j.tics.2007.08.005", "authors": "Egner", "year": 2007,
                      "title": "x", "table_or_figure": "T1", "page": 1,
                      "quote": "...", "confidence": "high"}]
    }
  }
}
"""


@pytest.mark.asyncio
async def test_extract_norms_returns_validated_dict():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=CONFLICT_NORMS_RESPONSE))
    out = await extract_norms("conflict", llm_client=fake)
    assert out["paradigm_class"] == "conflict"
    assert "rt_distribution" in out["metrics"]
    assert "produced_by" in out  # extractor adds the envelope
    assert out["produced_by"]["extraction_prompt_sha256"]  # not empty
    fake.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_norms_prompt_warns_against_primary_studies():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=CONFLICT_NORMS_RESPONSE))
    await extract_norms("conflict", llm_client=fake)
    sent_system = fake.complete.await_args.kwargs["system"]
    sent_user = fake.complete.await_args.kwargs["user"]
    sent = sent_system + "\n" + sent_user
    sent_lower = sent.lower()
    assert "meta-analyses" in sent_lower or "meta-analysis" in sent_lower or "review" in sent_lower
    assert "circular" in sent_lower  # explicit warning


@pytest.mark.asyncio
async def test_extract_norms_raises_on_invalid_llm_output():
    """Schema-invalid LLM output is caught by validate_norms_dict."""
    bad_response = '{"paradigm_class": "conflict", "metrics": {"rt_distribution": {"citations": []}}}'
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=bad_response))
    with pytest.raises(NormsSchemaError):
        await extract_norms("conflict", llm_client=fake)


@pytest.mark.asyncio
async def test_extract_norms_extracts_json_from_markdown_fence():
    fake = AsyncMock()
    wrapped = "```json\n" + CONFLICT_NORMS_RESPONSE + "\n```"
    fake.complete = AsyncMock(return_value=LLMResponse(text=wrapped))
    out = await extract_norms("conflict", llm_client=fake)
    assert out["paradigm_class"] == "conflict"

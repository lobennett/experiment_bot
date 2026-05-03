import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage5_sensitivity import run_stage5
from experiment_bot.llm.protocol import LLMResponse


@pytest.mark.asyncio
async def test_stage5_tags_each_parameter():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text="""
    {
      "response_distributions/congruent/mu": "high",
      "response_distributions/congruent/sigma": "medium",
      "response_distributions/congruent/tau": "medium"
    }
    """))
    partial = {
        "response_distributions": {
            "congruent": {"value": {"mu": 580, "sigma": 80, "tau": 100}}
        }
    }
    out = await run_stage5(client=fake, partial=partial)
    cong = out["response_distributions"]["congruent"]
    assert cong["sensitivity"] == {"mu": "high", "sigma": "medium", "tau": "medium"}


@pytest.mark.asyncio
async def test_stage5_tags_temporal_effects():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text="""
    {
      "temporal_effects/post_error_slowing/slowing_ms_min": "medium",
      "temporal_effects/post_error_slowing/slowing_ms_max": "low"
    }
    """))
    partial = {
        "temporal_effects": {
            "post_error_slowing": {
                "value": {"enabled": True, "slowing_ms_min": 30, "slowing_ms_max": 80}
            }
        }
    }
    out = await run_stage5(client=fake, partial=partial)
    pes = out["temporal_effects"]["post_error_slowing"]
    assert pes["sensitivity"] == {"slowing_ms_min": "medium", "slowing_ms_max": "low"}


@pytest.mark.asyncio
async def test_stage5_does_not_mutate_partial():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text="""
    {"response_distributions/c/mu": "high"}
    """))
    partial = {"response_distributions": {"c": {"value": {"mu": 100}}}}
    snapshot = {"response_distributions": {"c": {"value": {"mu": 100}}}}
    await run_stage5(client=fake, partial=partial)
    assert partial == snapshot

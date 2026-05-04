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
    out, step = await run_stage5(client=fake, partial=partial)
    cong = out["response_distributions"]["congruent"]
    assert cong["sensitivity"] == {"mu": "high", "sigma": "medium", "tau": "medium"}
    from experiment_bot.taskcard.types import ReasoningStep
    assert isinstance(step, ReasoningStep)
    assert step.step == "stage5_sensitivity"


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
    out, _step = await run_stage5(client=fake, partial=partial)
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
    await run_stage5(client=fake, partial=partial)  # tuple return; discard both values
    assert partial == snapshot


@pytest.mark.asyncio
async def test_stage5_handles_two_part_jitter_path():
    """LLM may return paths like 'between_subject_jitter/rt_mean_sd_ms' (2 parts)."""
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text="""
    {
      "between_subject_jitter/rt_mean_sd_ms": "high",
      "between_subject_jitter/accuracy_sd": "medium"
    }
    """))
    partial = {
        "between_subject_jitter": {
            "value": {"rt_mean_sd_ms": 60, "accuracy_sd": 0.02},
        }
    }
    out, _step = await run_stage5(client=fake, partial=partial)
    bsj = out["between_subject_jitter"]
    assert bsj["sensitivity"]["rt_mean_sd_ms"] == "high"
    assert bsj["sensitivity"]["accuracy_sd"] == "medium"

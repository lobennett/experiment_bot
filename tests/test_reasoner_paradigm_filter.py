import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage2_behavioral import run_stage2
from experiment_bot.llm.protocol import LLMResponse


STAGE2_RESPONSE = """
{
  "response_distributions": {"go": {"distribution": "ex_gaussian",
    "value": {"mu": 500, "sigma": 60, "tau": 80}, "rationale": ""}},
  "performance_omission_rate": {"go": 0.005},
  "temporal_effects": {"post_error_slowing": {"value": {"enabled": true,
    "slowing_ms_min": 30, "slowing_ms_max": 80}, "rationale": ""}},
  "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}, "rationale": ""}
}
"""


@pytest.mark.asyncio
async def test_stage2_prompt_includes_cse_for_conflict_paradigm():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stroop", "paradigm_classes": ["conflict", "speeded_choice"]}}
    await run_stage2(client=fake, partial=partial)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "congruency_sequence" in user_msg
    assert "conflict" in user_msg


@pytest.mark.asyncio
async def test_stage2_prompt_excludes_cse_for_interrupt_paradigm():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stop Signal", "paradigm_classes": ["interrupt", "speeded_choice"]}}
    await run_stage2(client=fake, partial=partial)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "congruency_sequence" not in user_msg


@pytest.mark.asyncio
async def test_stage2_prompt_includes_universal_effects_for_any_paradigm():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "x", "paradigm_classes": ["interrupt"]}}
    await run_stage2(client=fake, partial=partial)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "autocorrelation" in user_msg
    assert "post_error_slowing" in user_msg

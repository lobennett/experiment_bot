import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage2_behavioral import run_stage2
from experiment_bot.llm.protocol import LLMResponse


STAGE2_RESPONSE = """
{
  "response_distributions": {"default": {"distribution": "ex_gaussian",
    "value": {"mu": 500, "sigma": 60, "tau": 80}, "rationale": ""}},
  "performance_omission_rate": {"default": 0.005},
  "temporal_effects": {"post_event_slowing": {"value": {"enabled": true,
    "triggers": [{"event": "error", "slowing_ms_min": 30,
                  "slowing_ms_max": 80}]}, "rationale": ""}},
  "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}, "rationale": ""}
}
"""


@pytest.mark.asyncio
async def test_stage2_prompt_does_not_inject_paradigm_named_effects():
    """The bot's library has no paradigm-specific effect names. The
    Stage 2 catalog should never mention paradigm-conventional effect
    names — only generic mechanisms."""
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "AnyTask", "paradigm_classes": ["conflict", "speeded_choice"]}}
    await run_stage2(client=fake, partial=partial)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "`congruency_sequence`" not in user_msg
    assert "`post_error_slowing`" not in user_msg
    assert "`post_interrupt_slowing`" not in user_msg


@pytest.mark.asyncio
async def test_stage2_prompt_includes_generic_mechanisms_for_any_paradigm():
    """Stage 2 catalog includes generic mechanisms (lag1_pair_modulation,
    post_event_slowing) for any paradigm class. The Reasoner decides per
    task which to enable based on literature, not on paradigm-class
    pre-filtering."""
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    for classes in (["conflict", "speeded_choice"], ["interrupt"], ["working_memory"]):
        partial = {"task": {"name": "x", "paradigm_classes": classes}}
        await run_stage2(client=fake, partial=partial)
        user_msg = fake.complete.await_args.kwargs["user"]
        assert "lag1_pair_modulation" in user_msg, f"missing for {classes}"
        assert "post_event_slowing" in user_msg, f"missing for {classes}"
        assert "autocorrelation" in user_msg, f"missing for {classes}"

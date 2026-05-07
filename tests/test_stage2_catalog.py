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
async def test_stage2_self_corrects_via_validator_feedback():
    """When Stage 2's first output violates the runtime schema, Stage 2 should
    feed the validator's error list back to the LLM and accept the corrected
    second response. The LLM's corrections come entirely from the validator —
    no paradigm-specific hints in the refinement turn.
    """
    bad_response = """{
      "response_distributions": {"default": {"distribution": "ex_gaussian",
        "value": {"mu": 500, "sigma": 60, "tau": 80}, "rationale": ""}},
      "performance_omission_rate": {"default": 0.005},
      "temporal_effects": {"post_event_slowing": {"value": {"enabled": true,
        "triggers": [{"condition": "stop_signal", "slowing_ms": 25.0}]
      }, "rationale": ""}},
      "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}, "rationale": ""}
    }"""
    good_response = """{
      "response_distributions": {"default": {"distribution": "ex_gaussian",
        "value": {"mu": 500, "sigma": 60, "tau": 80}, "rationale": ""}},
      "performance_omission_rate": {"default": 0.005},
      "temporal_effects": {"post_event_slowing": {"value": {"enabled": true,
        "triggers": [{"event": "interrupt",
                      "slowing_ms_min": 80, "slowing_ms_max": 200}]
      }, "rationale": ""}},
      "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}, "rationale": ""}
    }"""
    fake = AsyncMock()
    fake.complete = AsyncMock(side_effect=[
        LLMResponse(text=bad_response),
        LLMResponse(text=good_response),
    ])
    partial = {"task": {"name": "x", "paradigm_classes": ["interrupt"]}}
    result, step = await run_stage2(client=fake, partial=partial)
    # Refinement happened: the second LLM call's user message should
    # contain the validator's error list.
    assert fake.complete.await_count == 2
    second_user = fake.complete.await_args_list[1].kwargs["user"]
    assert "Validation errors from previous attempt" in second_user
    assert "post_event_slowing" in second_user
    # Final result should be the corrected (good) shape.
    triggers = result["temporal_effects"]["post_event_slowing"]["value"]["triggers"]
    assert triggers[0]["event"] == "interrupt"
    # Reasoning step records the self-correction.
    assert "refinement" in step.inference.lower()


@pytest.mark.asyncio
async def test_stage2_propagates_error_after_max_refinements():
    """When the LLM keeps emitting schema violations, Stage 2 raises
    Stage2SchemaError after the cap so the pipeline doesn't silently
    accept malformed output."""
    from experiment_bot.reasoner.validate import Stage2SchemaError
    bad_response = """{
      "response_distributions": {"default": {"distribution": "ex_gaussian",
        "value": {"mu": 500, "sigma": 60, "tau": 80}, "rationale": ""}},
      "performance_omission_rate": {"default": 0.005},
      "temporal_effects": {"post_event_slowing": {"value": {"enabled": true,
        "triggers": [{"condition": "stop_signal"}]
      }, "rationale": ""}},
      "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}, "rationale": ""}
    }"""
    fake = AsyncMock()
    # Always returns malformed output — refinements never converge.
    fake.complete = AsyncMock(return_value=LLMResponse(text=bad_response))
    partial = {"task": {"name": "x", "paradigm_classes": ["interrupt"]}}
    with pytest.raises(Stage2SchemaError):
        await run_stage2(client=fake, partial=partial)


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

import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage2_behavioral import run_stage2, _sanitize_distribution_values
from experiment_bot.llm.protocol import LLMResponse


def test_sanitize_distribution_values_strips_rationale_in_value():
    """A prose `rationale` nested inside `value` is removed (value stays numeric-only)
    and folded into the distribution-level rationale when that is empty."""
    rd = {
        "congruent": {
            "value": {"mu": 480, "sigma": 45, "tau": 130,
                      "rationale": "congruent RTs near 600 ms..."},
            "rationale": "",
        },
        "incongruent": {  # already clean + has a rationale -> untouched
            "value": {"mu": 520, "sigma": 50, "tau": 140},
            "rationale": "interference shifts the mean up",
        },
    }
    _sanitize_distribution_values(rd)
    assert rd["congruent"]["value"] == {"mu": 480, "sigma": 45, "tau": 130}
    assert rd["congruent"]["rationale"] == "congruent RTs near 600 ms..."  # folded in
    assert rd["incongruent"]["value"] == {"mu": 520, "sigma": 50, "tau": 140}
    assert rd["incongruent"]["rationale"] == "interference shifts the mean up"


STAGE2_RESPONSE = """
{
  "response_distributions": {
    "congruent": {"distribution": "ex_gaussian",
                  "value": {"mu": 580, "sigma": 80, "tau": 100},
                  "rationale": "Stroop congruent norms"},
    "incongruent": {"distribution": "ex_gaussian",
                    "value": {"mu": 650, "sigma": 95, "tau": 130},
                    "rationale": "Stroop interference effect"}
  },
  "performance_omission_rate": {"congruent": 0.005, "incongruent": 0.005},
  "temporal_effects": {
    "post_event_slowing": {"value": {"enabled": true, "triggers": [
        {"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 80}
    ]}, "rationale": "Rabbitt 1966"}
  },
  "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60, "accuracy_sd": 0.02},
                              "rationale": "individual differences"}
}
"""


@pytest.mark.asyncio
async def test_stage2_appends_behavioral_to_partial():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stroop"}, "performance": {"accuracy": {"congruent": 0.97}}}
    out, step = await run_stage2(client=fake, partial=partial)
    assert out["response_distributions"]["congruent"]["value"]["mu"] == 580
    assert out["temporal_effects"]["post_event_slowing"]["value"]["enabled"] is True
    # partial is preserved
    assert out["task"]["name"] == "Stroop"
    # omission rates merged into performance
    assert out["performance"]["omission_rate"]["congruent"] == 0.005
    from experiment_bot.taskcard.types import ReasoningStep
    assert isinstance(step, ReasoningStep)
    assert step.step == "stage2_behavioral"
    assert step.inference


@pytest.mark.asyncio
async def test_stage2_does_not_mutate_partial():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stroop"}, "performance": {"accuracy": {"c": 0.97}}}
    snapshot = {"task": {"name": "Stroop"}, "performance": {"accuracy": {"c": 0.97}}}
    await run_stage2(client=fake, partial=partial)
    # Original partial unchanged (deep equal to snapshot)
    assert partial == snapshot

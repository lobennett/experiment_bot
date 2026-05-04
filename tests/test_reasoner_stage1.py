import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage1_structural import run_stage1
from experiment_bot.llm.protocol import LLMResponse
from experiment_bot.core.config import SourceBundle
from experiment_bot.taskcard.types import ReasoningStep


COMPLETE_STROOP_RESPONSE = """
{
  "task": {"name": "Stroop", "constructs": ["cognitive control"], "reference_literature": []},
  "stimuli": [
    {"id": "stroop_congruent", "description": "color matches word",
     "detection": {"method": "dom_query", "selector": ".congruent"},
     "response": {"key": null, "condition": "congruent", "response_key_js": "..."}}
  ],
  "navigation": {"phases": []},
  "runtime": {
    "advance_behavior": {
      "advance_keys": [" "],
      "feedback_fallback_keys": ["Enter"],
      "feedback_selectors": []
    },
    "data_capture": {
      "method": "js_expression",
      "expression": "jsPsych.data.get().json()",
      "format": "json"
    }
  },
  "task_specific": {"key_map": {"red": "r", "blue": "b"}},
  "performance": {"accuracy": {"congruent": 0.97, "incongruent": 0.92}},
  "pilot_validation_config": {"min_trials": 20, "target_conditions": ["congruent", "incongruent"]}
}
"""

INCOMPLETE_STROOP_RESPONSE = """
{
  "task": {"name": "Stroop", "constructs": []},
  "stimuli": [],
  "navigation": {"phases": []},
  "runtime": {"advance_behavior": {}, "data_capture": {}},
  "task_specific": {},
  "performance": {"accuracy": {}}
}
"""


@pytest.mark.asyncio
async def test_stage1_returns_partial_and_reasoning_step():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=COMPLETE_STROOP_RESPONSE))
    bundle = SourceBundle(
        url="http://example.com/stroop",
        source_files={"main.js": "..."},
        description_text="<html>...</html>",
    )
    partial, step = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"
    assert isinstance(step, ReasoningStep)
    assert step.step == "stage1_structural"
    assert step.inference  # non-empty
    fake.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_stage1_calls_validator_and_raises_on_incomplete_output():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=INCOMPLETE_STROOP_RESPONSE))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    from experiment_bot.reasoner.validate import Stage1ValidationError
    with pytest.raises(Stage1ValidationError):
        await run_stage1(client=fake, bundle=bundle)


@pytest.mark.asyncio
async def test_stage1_user_message_includes_required_fields_checklist():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=COMPLETE_STROOP_RESPONSE))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    await run_stage1(client=fake, bundle=bundle)
    call_kwargs = fake.complete.await_args.kwargs
    user_msg = call_kwargs["user"]
    assert "REQUIRED runtime fields" in user_msg
    assert "advance_keys" in user_msg
    assert "data_capture.method" in user_msg


@pytest.mark.asyncio
async def test_stage1_extracts_json_from_markdown_fence():
    fake = AsyncMock()
    wrapped = "```json\n" + COMPLETE_STROOP_RESPONSE + "\n```"
    fake.complete = AsyncMock(return_value=LLMResponse(text=wrapped))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    partial, _step = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"

"""Stage 1 has both parse-retry (new in SP4b) and validation-retry
(pre-existing). This test verifies the two retry concerns are
independent: a parse failure on attempt N does not consume a
validation-retry budget slot."""
from __future__ import annotations
import json
from types import SimpleNamespace

import pytest


class _StubClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts_received: list[str] = []

    async def complete(self, system, user, output_format=None):
        self.prompts_received.append(user)
        if not self._responses:
            raise AssertionError("StubClient: out of scripted responses")
        return SimpleNamespace(text=self._responses.pop(0))


@pytest.mark.asyncio
async def test_stage1_parse_retry_does_not_consume_validation_budget():
    """Script:
    - response 1: empty (parse failure -> parse retry)
    - response 2: valid JSON but fails Stage 1 validation (validation retry triggers)
    - response 3: valid JSON, passes validation
    Stage 1 should succeed on response 3 with validation_retries=1
    (NOT validation_retries=2 - the parse failure consumed a parse-retry
    slot, not a validation-retry slot)."""
    from experiment_bot.reasoner.stage1_structural import run_stage1
    from experiment_bot.core.config import SourceBundle

    valid_invalid_partial = {
        # Missing required SP10 fields -> fails Stage 1 validation
        # (no paradigm_classes, no stimuli, no recommended_driver)
        "task": {"name": "test"},
        "stimuli": [],
        "performance": {"accuracy": {}},
    }
    valid_passing_partial = {
        "task": {"name": "test", "paradigm_classes": ["speeded_choice"]},
        "stimuli": [
            {"id": "s1", "condition": "go"},
        ],
        "performance": {
            "accuracy": {"go": 0.95},
            "omission_rate": {"go": 0.02},
        },
        "recommended_driver": "JsPsychDriver",
    }
    client = _StubClient([
        "",  # parse failure
        json.dumps(valid_invalid_partial),  # parses OK, fails validation
        json.dumps(valid_passing_partial),  # parses + validates
    ])

    bundle = SourceBundle(
        url="http://test",
        source_files={},
        description_text="test page",
    )
    # max_retries=2 means up to 2 validation retries (so 3 attempts allowed).
    # The parse failure on attempt 1 must NOT consume one of the validation slots.
    result, step = await run_stage1(client, bundle, max_retries=2)

    # 3 LLM calls total: parse-fail, validation-fail, success.
    assert len(client.prompts_received) == 3
    assert result["task"]["name"] == "test"

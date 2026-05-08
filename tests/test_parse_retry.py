"""Unit tests for parse_with_retry helper. The helper generalizes
Stage 2's existing inline parse-retry pattern into a reusable function
applied to Stages 1, 3, 5, 6 (pilot refinement), and the norms_extractor.

Stub LLM client mirrors the _StubClient pattern in
tests/test_stage2_refinement_locks.py."""
from __future__ import annotations
import json

import pytest


class _StubClient:
    """Returns scripted text responses; tracks user prompts received."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts_received: list[str] = []

    async def complete(self, system, user, output_format=None):
        from types import SimpleNamespace
        self.prompts_received.append(user)
        if not self._responses:
            raise AssertionError("StubClient: out of scripted responses")
        return SimpleNamespace(text=self._responses.pop(0))


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    from experiment_bot.reasoner.parse_retry import parse_with_retry
    client = _StubClient([json.dumps({"a": 1})])
    result = await parse_with_retry(
        client, system="sys", user="usr", stage_name="test", max_retries=3,
    )
    assert result == {"a": 1}
    assert len(client.prompts_received) == 1


@pytest.mark.asyncio
async def test_retry_then_success():
    from experiment_bot.reasoner.parse_retry import parse_with_retry
    client = _StubClient(["", json.dumps({"b": 2})])
    result = await parse_with_retry(
        client, system="sys", user="usr", stage_name="test", max_retries=3,
    )
    assert result == {"b": 2}
    assert len(client.prompts_received) == 2
    # Second prompt must include the parse-error feedback.
    assert "Parse error from previous attempt" in client.prompts_received[1]


@pytest.mark.asyncio
async def test_budget_exhausted_raises():
    from experiment_bot.reasoner.parse_retry import (
        parse_with_retry, ParseRetryExceededError,
    )
    client = _StubClient(["", "", ""])
    with pytest.raises(ParseRetryExceededError) as ei:
        await parse_with_retry(
            client, system="sys", user="usr", stage_name="stage_x", max_retries=3,
        )
    msg = str(ei.value)
    assert "stage_x" in msg
    # Each attempt's parser error should appear in the message.
    assert msg.count("attempt") >= 3 or len(ei.value.history) == 3


@pytest.mark.asyncio
async def test_empty_string_treated_as_parse_error():
    """LLM returns "" — _extract_json returns "", json.loads raises;
    helper catches and retries (does not crash on truncation)."""
    from experiment_bot.reasoner.parse_retry import parse_with_retry
    client = _StubClient(["", json.dumps({"c": 3})])
    result = await parse_with_retry(
        client, system="sys", user="usr", stage_name="test", max_retries=2,
    )
    assert result == {"c": 3}


@pytest.mark.asyncio
async def test_markdown_fenced_json_parses():
    """LLM returns ```json\\n{...}\\n``` — _extract_json strips, helper succeeds."""
    from experiment_bot.reasoner.parse_retry import parse_with_retry
    fenced = "```json\n" + json.dumps({"d": 4}) + "\n```"
    client = _StubClient([fenced])
    result = await parse_with_retry(
        client, system="sys", user="usr", stage_name="test", max_retries=2,
    )
    assert result == {"d": 4}


@pytest.mark.asyncio
async def test_stage_name_in_error_message():
    from experiment_bot.reasoner.parse_retry import (
        parse_with_retry, ParseRetryExceededError,
    )
    client = _StubClient(["not json", "still not json"])
    with pytest.raises(ParseRetryExceededError) as ei:
        await parse_with_retry(
            client, system="sys", user="usr",
            stage_name="my_distinctive_stage_label", max_retries=2,
        )
    assert "my_distinctive_stage_label" in str(ei.value)

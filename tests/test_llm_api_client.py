import pytest
from unittest.mock import AsyncMock, MagicMock

from experiment_bot.llm.api_client import ClaudeAPIClient


@pytest.mark.asyncio
async def test_api_client_calls_anthropic_messages_create():
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text="response text")],
            stop_reason="end_turn",
        )
    )
    client = ClaudeAPIClient(client=fake, model="claude-opus-4-7")
    result = await client.complete(system="sys", user="usr")
    fake.messages.create.assert_called_once()
    kwargs = fake.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "usr"}]
    assert result.text == "response text"
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_api_client_uses_max_tokens_arg():
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text="x")],
            stop_reason="end_turn",
        )
    )
    client = ClaudeAPIClient(client=fake)
    await client.complete(system="s", user="u", max_tokens=8000)
    assert fake.messages.create.call_args.kwargs["max_tokens"] == 8000

import base64
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


@pytest.mark.asyncio
async def test_api_client_sends_images_as_base64_content_blocks():
    """When images=list[bytes] is passed, the API client builds a
    content-block list with one text block and one image block per image."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.stop_reason = "end_turn"

    fake_sdk = MagicMock()
    fake_sdk.messages.create = AsyncMock(return_value=fake_response)

    client = ClaudeAPIClient(client=fake_sdk, model="claude-haiku-4-5")
    png_bytes = b"\x89PNG\r\n\x1a\nfake-image-data"
    await client.complete(system="sys", user="usr", images=[png_bytes])

    call_kwargs = fake_sdk.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "usr"}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "image/png"
    assert content[1]["source"]["data"] == base64.b64encode(png_bytes).decode("ascii")


@pytest.mark.asyncio
async def test_api_client_no_images_keeps_string_content():
    """Without images, content is a plain string (backward compatibility)."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.stop_reason = "end_turn"

    fake_sdk = MagicMock()
    fake_sdk.messages.create = AsyncMock(return_value=fake_response)

    client = ClaudeAPIClient(client=fake_sdk, model="claude-haiku-4-5")
    await client.complete(system="sys", user="usr")

    call_kwargs = fake_sdk.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["content"] == "usr"

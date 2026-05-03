import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.llm.cli_client import ClaudeCLIClient


@pytest.mark.asyncio
async def test_cli_client_invokes_claude_with_print_and_json_output():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(
            json.dumps({"result": "response text", "stop_reason": "end_turn"}).encode(),
            b"",
        )
    )
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        client = ClaudeCLIClient(claude_binary="claude")
        result = await client.complete(system="sys", user="usr", output_format="json")
        args = mock_exec.call_args.args
        assert "claude" in args[0]
        assert "--print" in args
        assert "--output-format" in args
        assert "json" in args
        assert result.text == "response text"


@pytest.mark.asyncio
async def test_cli_client_quota_exceeded_signals_clearly():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(b"", b"Error: usage limit reached. Reset in 4h.")
    )
    proc.returncode = 1
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        client = ClaudeCLIClient(claude_binary="claude")
        with pytest.raises(RuntimeError, match="usage limit"):
            await client.complete(system="sys", user="usr")


@pytest.mark.asyncio
async def test_cli_client_includes_model_flag_when_specified():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(json.dumps({"result": "ok"}).encode(), b"")
    )
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        client = ClaudeCLIClient(claude_binary="claude", model="claude-opus-4-7")
        await client.complete(system="sys", user="usr")
        args = mock_exec.call_args.args
        assert "--model" in args
        assert "claude-opus-4-7" in args


@pytest.mark.asyncio
async def test_cli_client_handles_non_json_output():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(b"plain text response", b"")
    )
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        client = ClaudeCLIClient(claude_binary="claude")
        result = await client.complete(system="sys", user="usr")
        assert result.text == "plain text response"


@pytest.mark.asyncio
async def test_cli_client_failure_raises_with_stderr():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(b"", b"Error: some other failure mode")
    )
    proc.returncode = 1
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        client = ClaudeCLIClient(claude_binary="claude")
        with pytest.raises(RuntimeError, match="some other failure"):
            await client.complete(system="sys", user="usr")

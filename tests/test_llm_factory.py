import os
import pytest
from unittest.mock import patch
from experiment_bot.llm.factory import build_default_client
from experiment_bot.llm.cli_client import ClaudeCLIClient
from experiment_bot.llm.api_client import ClaudeAPIClient


def test_factory_picks_cli_when_env_var_says_cli():
    with patch.dict(os.environ, {"EXPERIMENT_BOT_LLM_CLIENT": "cli"}):
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            client = build_default_client()
            assert isinstance(client, ClaudeCLIClient)


def test_factory_picks_api_when_env_var_says_api():
    with patch.dict(os.environ, {
        "EXPERIMENT_BOT_LLM_CLIENT": "api",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }):
        client = build_default_client()
        assert isinstance(client, ClaudeAPIClient)


def test_factory_default_picks_cli_if_claude_on_path():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXPERIMENT_BOT_LLM_CLIENT", None)
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            client = build_default_client()
            assert isinstance(client, ClaudeCLIClient)


def test_factory_falls_back_to_api_if_no_claude_cli():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
        os.environ.pop("EXPERIMENT_BOT_LLM_CLIENT", None)
        with patch("shutil.which", return_value=None):
            client = build_default_client()
            assert isinstance(client, ClaudeAPIClient)


def test_factory_raises_if_no_path_available():
    with patch.dict(os.environ, {}, clear=True):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="no LLM client available"):
                build_default_client()


def test_factory_explicit_cli_raises_if_no_claude():
    with patch.dict(os.environ, {"EXPERIMENT_BOT_LLM_CLIENT": "cli"}, clear=True):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="claude.*PATH"):
                build_default_client()


def test_factory_explicit_api_raises_if_no_key():
    with patch.dict(os.environ, {"EXPERIMENT_BOT_LLM_CLIENT": "api"}, clear=True):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            build_default_client()

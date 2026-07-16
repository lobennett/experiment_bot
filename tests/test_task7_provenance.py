"""Tests for Task 7: provenance hashes, single model id, LLMClient.model property.

Covers:
- DEFAULT_MODEL constant exists and equals 'claude-opus-4-8' (overridable via env var)
- LLMClient Protocol: ClaudeCLIClient and ClaudeAPIClient expose .model property
- _wrap_for_taskcard produces non-empty prompt_sha256 and source_sha256
- _wrap_for_taskcard records the live client's .model (not a hardcoded literal)
"""
from __future__ import annotations
import os
import hashlib
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from experiment_bot.llm.models import DEFAULT_MODEL
from experiment_bot.llm.cli_client import ClaudeCLIClient
from experiment_bot.llm.api_client import ClaudeAPIClient
from experiment_bot.llm.protocol import LLMResponse
from experiment_bot.reasoner.cli import _wrap_for_taskcard


# ---------------------------------------------------------------------------
# DEFAULT_MODEL constant
# ---------------------------------------------------------------------------

def test_default_model_is_current_model_id():
    """DEFAULT_MODEL must equal claude-opus-4-8 (or env override)."""
    env_override = os.environ.get("EXPERIMENT_BOT_MODEL")
    if env_override:
        assert DEFAULT_MODEL == env_override
    else:
        assert DEFAULT_MODEL == "claude-opus-4-8"


def test_default_model_env_override(monkeypatch):
    """EXPERIMENT_BOT_MODEL overrides DEFAULT_MODEL."""
    monkeypatch.setenv("EXPERIMENT_BOT_MODEL", "claude-test-model")
    import importlib
    import experiment_bot.llm.models as models_mod
    importlib.reload(models_mod)
    try:
        assert models_mod.DEFAULT_MODEL == "claude-test-model"
    finally:
        importlib.reload(models_mod)  # restore


# ---------------------------------------------------------------------------
# LLMClient.model property on both concrete clients
# ---------------------------------------------------------------------------

def test_cli_client_model_property_returns_model():
    client = ClaudeCLIClient(model="claude-opus-4-8")
    assert client.model == "claude-opus-4-8"


def test_cli_client_model_default_is_default_model():
    client = ClaudeCLIClient()
    assert client.model == DEFAULT_MODEL


def test_api_client_model_property_returns_model():
    fake_sdk = MagicMock()
    client = ClaudeAPIClient(client=fake_sdk, model="claude-opus-4-8")
    assert client.model == "claude-opus-4-8"


def test_api_client_model_default_is_default_model():
    fake_sdk = MagicMock()
    client = ClaudeAPIClient(client=fake_sdk)
    assert client.model == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# _wrap_for_taskcard: real hashes + live model
# ---------------------------------------------------------------------------

class _FakeBundle:
    url = "http://x"
    source_files = {"a.js": "console.log('hello');", "b.js": "var x = 1;"}
    description_text = ""
    hint = ""
    metadata = {}


class _FakeClient:
    @property
    def model(self):
        return "claude-opus-4-8"


def test_wrap_for_taskcard_produces_non_empty_prompt_sha256(tmp_path):
    """prompt_sha256 is a 64-char hex string derived from the system prompt."""
    partial = {}
    result = _wrap_for_taskcard(partial, "http://x", bundle=_FakeBundle(), llm_client=_FakeClient())
    pb = result["produced_by"]
    sha = pb["prompt_sha256"]
    # Should be a non-empty hex string (64 chars for sha256) OR empty only if file is missing
    assert isinstance(sha, str)
    # It must be non-empty if system.md exists
    from experiment_bot.reasoner.cli import _SYSTEM_PROMPT_PATH
    if _SYSTEM_PROMPT_PATH.exists():
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)


def test_wrap_for_taskcard_produces_non_empty_source_sha256():
    """source_sha256 is computed from the bundle's source_files."""
    partial = {}
    result = _wrap_for_taskcard(partial, "http://x", bundle=_FakeBundle(), llm_client=_FakeClient())
    pb = result["produced_by"]
    sha = pb["source_sha256"]
    assert isinstance(sha, str)
    assert len(sha) == 64, f"Expected 64-char sha256 hex, got: {sha!r}"
    assert all(c in "0123456789abcdef" for c in sha)


def test_wrap_for_taskcard_source_sha256_deterministic():
    """Same source files → same hash."""
    partial1 = {}
    partial2 = {}
    h1 = _wrap_for_taskcard(partial1, "http://x", bundle=_FakeBundle(), llm_client=_FakeClient())
    h2 = _wrap_for_taskcard(partial2, "http://x", bundle=_FakeBundle(), llm_client=_FakeClient())
    assert h1["produced_by"]["source_sha256"] == h2["produced_by"]["source_sha256"]


def test_wrap_for_taskcard_records_live_client_model():
    """model in produced_by must come from the client's .model, not a literal."""
    class _SentinelClient:
        @property
        def model(self):
            return "sentinel-model-xyz"

    partial = {}
    result = _wrap_for_taskcard(partial, "http://x", bundle=_FakeBundle(), llm_client=_SentinelClient())
    assert result["produced_by"]["model"] == "sentinel-model-xyz"


def test_wrap_for_taskcard_no_bundle_yields_empty_source_sha256():
    """When no bundle is provided, source_sha256 falls back to empty string."""
    partial = {}
    result = _wrap_for_taskcard(partial, "http://x", bundle=None, llm_client=_FakeClient())
    assert result["produced_by"]["source_sha256"] == ""


def test_wrap_for_taskcard_does_not_overwrite_existing_produced_by():
    """If produced_by already set (pipeline filled it), _wrap_for_taskcard leaves it alone."""
    partial = {
        "produced_by": {"model": "existing-model", "prompt_sha256": "abc", "scraper_version": "1.0.0",
                        "source_sha256": "def", "timestamp": "ts", "taskcard_sha256": ""},
    }
    result = _wrap_for_taskcard(partial, "http://x", bundle=_FakeBundle(), llm_client=_FakeClient())
    assert result["produced_by"]["model"] == "existing-model"

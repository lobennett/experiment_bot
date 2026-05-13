from __future__ import annotations
import os
import shutil
from experiment_bot.llm.cli_client import ClaudeCLIClient
from experiment_bot.llm.api_client import ClaudeAPIClient


def build_default_client(model: str | None = None):
    """Pick LLM client based on environment.

    Resolution order:
      1. EXPERIMENT_BOT_LLM_CLIENT="cli" -> CLI (require claude on PATH)
      2. EXPERIMENT_BOT_LLM_CLIENT="api" -> API (require ANTHROPIC_API_KEY)
      3. Default: CLI if claude on PATH, else API if key present, else raise.

    Args:
        model: Optional model override. When provided, both CLI and API
            paths construct the client with this model id instead of
            their respective defaults.
    """
    explicit = os.environ.get("EXPERIMENT_BOT_LLM_CLIENT", "").lower()
    has_cli = shutil.which("claude") is not None
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if explicit == "cli":
        if not has_cli:
            raise RuntimeError("EXPERIMENT_BOT_LLM_CLIENT=cli but `claude` not on PATH")
        return _build_cli_client(model)
    if explicit == "api":
        if not has_api_key:
            raise RuntimeError("EXPERIMENT_BOT_LLM_CLIENT=api but ANTHROPIC_API_KEY unset")
        return _build_api_client(model)

    if has_cli:
        return _build_cli_client(model)
    if has_api_key:
        return _build_api_client(model)
    raise RuntimeError(
        "no LLM client available: neither `claude` on PATH nor ANTHROPIC_API_KEY set"
    )


def _build_cli_client(model: str | None) -> ClaudeCLIClient:
    if model is None:
        return ClaudeCLIClient()
    return ClaudeCLIClient(model=model)


def _build_api_client(model: str | None) -> ClaudeAPIClient:
    from anthropic import AsyncAnthropic
    api_key = os.environ["ANTHROPIC_API_KEY"]
    sdk = AsyncAnthropic(api_key=api_key)
    if model is None:
        return ClaudeAPIClient(client=sdk)
    return ClaudeAPIClient(client=sdk, model=model)

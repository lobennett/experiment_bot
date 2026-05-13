"""Integration tests for the SP9a SessionAgent ↔ TaskExecutor wiring.

These tests build a stub TaskExecutor by bypassing __init__ (using
__new__) and patching only the fields the test exercises. The pattern
mirrors tests/test_executor_keypress_diagnostic.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.agent.types import KeyMappingDirective
from experiment_bot.core.executor import TaskExecutor


def _stub_match(condition: str, response_key: str = "", stimulus_id: str = "stim1") -> SimpleNamespace:
    return SimpleNamespace(
        condition=condition,
        response_key=response_key,
        stimulus_id=stimulus_id,
    )


def _stub_config_with_static_keymap(key_map: dict) -> SimpleNamespace:
    """Build the minimum config view _resolve_response_key reads from."""
    return SimpleNamespace(
        task_specific={"key_map": dict(key_map)},
        stimuli=[],
    )


def _stub_executor_for_resolve_response_key(
    config,
    runtime_key_mapping: dict | None,
    static_key_map: dict | None = None,
) -> TaskExecutor:
    stub = TaskExecutor.__new__(TaskExecutor)
    stub._config = config
    stub._runtime_key_mapping = runtime_key_mapping
    stub._key_map = static_key_map if static_key_map is not None else dict(config.task_specific.get("key_map", {}))
    stub._seen_response_keys = set()
    return stub


@pytest.mark.asyncio
async def test_resolve_response_key_prefers_runtime_mapping_over_static():
    """When self._runtime_key_mapping is set and contains the condition,
    return that key without consulting per-stim JS or static fallback."""
    cfg = _stub_config_with_static_keymap({"congruent": "a", "incongruent": "b"})
    runtime_mapping = {"congruent": "f", "incongruent": "j"}
    stub = _stub_executor_for_resolve_response_key(cfg, runtime_mapping)

    got = await stub._resolve_response_key(_stub_match("congruent"), page=None)

    assert got == "f"  # runtime mapping wins
    assert "f" in stub._seen_response_keys


@pytest.mark.asyncio
async def test_resolve_response_key_falls_back_when_condition_missing_from_runtime_mapping():
    """When the runtime mapping lacks the condition, the existing fallback
    chain (static key_map, etc.) still runs."""
    cfg = _stub_config_with_static_keymap({"congruent": "a", "novel_cond": "x"})
    runtime_mapping = {"congruent": "f"}  # 'novel_cond' missing
    stub = _stub_executor_for_resolve_response_key(cfg, runtime_mapping)

    got = await stub._resolve_response_key(_stub_match("novel_cond"), page=None)

    assert got == "x"  # static fallback


@pytest.mark.asyncio
async def test_resolve_response_key_uses_static_when_runtime_mapping_is_none():
    """When _runtime_key_mapping is None (SessionAgent disabled / not run),
    behavior is identical to pre-SP9a."""
    cfg = _stub_config_with_static_keymap({"congruent": "a"})
    stub = _stub_executor_for_resolve_response_key(cfg, runtime_key_mapping=None)

    got = await stub._resolve_response_key(_stub_match("congruent"), page=None)

    assert got == "a"


@pytest.mark.asyncio
async def test_invoke_session_agent_caches_directive_into_runtime_mapping():
    """When _invoke_session_agent is called with a stub agent, its directive's
    mapping ends up in self._runtime_key_mapping and the directive itself
    in self._session_agent_directive."""
    directive = KeyMappingDirective(
        mapping={"congruent": "z", "incongruent": "/"},
        source="screenshot_inference",
        confidence=0.85,
        raw_llm_response="raw",
        elapsed_ms=2000.0,
    )
    agent = MagicMock()
    agent.resolve_key_mapping = AsyncMock(return_value=directive)

    stub = TaskExecutor.__new__(TaskExecutor)
    stub._session_agent = agent
    stub._taskcard = None
    stub._config = SimpleNamespace(
        task_specific={},
        runtime=SimpleNamespace(session_agent_enabled=True),
    )
    stub._config.to_dict = lambda: {"task_specific": {}, "task": {"name": "test"}}
    stub._runtime_key_mapping = None
    stub._session_agent_directive = None

    page = AsyncMock()
    await stub._invoke_session_agent(page)

    assert stub._runtime_key_mapping == {"congruent": "z", "incongruent": "/"}
    assert stub._session_agent_directive is directive
    agent.resolve_key_mapping.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_session_agent_skipped_when_flag_disabled():
    """When config.runtime.session_agent_enabled is False, _invoke_session_agent
    does NOT call the agent and leaves _runtime_key_mapping as None."""
    agent = MagicMock()
    agent.resolve_key_mapping = AsyncMock()

    stub = TaskExecutor.__new__(TaskExecutor)
    stub._session_agent = agent
    stub._taskcard = None
    stub._config = SimpleNamespace(
        task_specific={},
        runtime=SimpleNamespace(session_agent_enabled=False),
    )
    stub._config.to_dict = lambda: {}
    stub._runtime_key_mapping = None
    stub._session_agent_directive = None

    page = AsyncMock()
    await stub._invoke_session_agent(page)

    assert stub._runtime_key_mapping is None
    assert stub._session_agent_directive is None
    agent.resolve_key_mapping.assert_not_called()


@pytest.mark.asyncio
async def test_invoke_session_agent_skipped_when_no_agent_attached():
    """When the executor was built without a session agent (e.g. tests
    that don't need one), _invoke_session_agent is a no-op."""
    stub = TaskExecutor.__new__(TaskExecutor)
    stub._session_agent = None
    stub._taskcard = None
    stub._config = SimpleNamespace(
        task_specific={},
        runtime=SimpleNamespace(session_agent_enabled=True),
    )
    stub._config.to_dict = lambda: {}
    stub._runtime_key_mapping = None
    stub._session_agent_directive = None

    page = AsyncMock()
    await stub._invoke_session_agent(page)

    assert stub._runtime_key_mapping is None

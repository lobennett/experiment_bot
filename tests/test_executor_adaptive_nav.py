"""Tests for SP16 adaptive nav step in TaskExecutor's trial loop."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.core.executor import (
    TaskExecutor, _ADAPTIVE_NAV_BUDGET, _ADAPTIVE_NAV_STUCK_POLLS,
)
from experiment_bot.core.config import TaskConfig
from experiment_bot.llm.protocol import LLMResponse


# Minimal config matching the pattern in tests/test_executor.py
_SAMPLE_CONFIG = {
    "task": {
        "name": "Test Task",
        "platform": "expfactory",
        "constructs": [],
        "reference_literature": [],
    },
    "stimuli": [
        {
            "id": "go",
            "description": "Go stimulus",
            "detection": {"method": "dom_query", "selector": ".go"},
            "response": {"key": "f", "condition": "go"},
        },
    ],
    "response_distributions": {
        "go": {"distribution": "ex_gaussian", "params": {"mu": 500, "sigma": 60, "tau": 80}},
    },
    "performance": {
        "accuracy": {"go": 0.95},
        "omission_rate": {"go": 0.02},
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {},
    "runtime": {},
}


@pytest.fixture
def make_executor():
    """Factory for a minimal TaskExecutor with optional AsyncMock LLM client."""
    def _make(with_llm_client: bool = False):
        config = TaskConfig.from_dict(_SAMPLE_CONFIG)
        fake_client = None
        if with_llm_client:
            fake_client = MagicMock()
            fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
        executor = TaskExecutor(
            config,
            headless=True,
            seed=42,
            session_params={},
            llm_client=fake_client,
        )
        return executor
    return _make


def test_taskexecutor_accepts_llm_client_kwarg(make_executor):
    """TaskExecutor.__init__ accepts an optional llm_client kwarg without
    breaking existing callers."""
    e1 = make_executor(with_llm_client=False)
    assert e1._llm_client is None  # default
    assert e1._adaptive_nav_uses == 0

    e2 = make_executor(with_llm_client=True)
    assert e2._llm_client is not None
    assert e2._adaptive_nav_uses == 0


@pytest.mark.asyncio
async def test_adaptive_nav_step_advances_dom(make_executor):
    """When LLM proposes a valid phase and DOM changes, _adaptive_nav_step
    returns True and logs to bot_log."""
    executor = make_executor(with_llm_client=True)
    executor._llm_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "next", "action": "click", "target": "#next",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    session_mock = AsyncMock()
    session_mock.dom_snapshot = AsyncMock(side_effect=["<div>before</div>", "<div>after</div>"])
    session_mock.try_phase = AsyncMock(
        return_value=MagicMock(success=True, error=None, dom_after="")
    )

    advanced = await executor._adaptive_nav_step(session_mock, MagicMock())
    assert advanced is True
    assert executor._adaptive_nav_uses == 1
    log_entries = [e for e in executor._bot_log if e.get("type") == "adaptive_nav"]
    assert len(log_entries) == 1
    assert log_entries[0]["advanced"] is True
    assert log_entries[0]["success"] is True


@pytest.mark.asyncio
async def test_adaptive_nav_step_no_advance_on_same_dom(make_executor):
    """When DOM doesn't change after try_phase, advanced=False."""
    executor = make_executor(with_llm_client=True)
    executor._llm_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "x", "action": "keypress", "target": "", "key": " ",
        "duration_ms": 0, "steps": []
    }"""))
    session_mock = AsyncMock()
    session_mock.dom_snapshot = AsyncMock(return_value="<div>same</div>")
    session_mock.try_phase = AsyncMock(
        return_value=MagicMock(success=True, error=None, dom_after="")
    )

    advanced = await executor._adaptive_nav_step(session_mock, MagicMock())
    assert advanced is False
    assert executor._adaptive_nav_uses == 1
    # Entry is still logged even when no DOM advance
    assert len([e for e in executor._bot_log if e.get("type") == "adaptive_nav"]) == 1


@pytest.mark.asyncio
async def test_adaptive_nav_step_llm_failure_counted_against_budget(make_executor):
    """If the LLM proposal raises, the step counts against the budget (no infinite
    loop), and the function returns False."""
    executor = make_executor(with_llm_client=True)
    with patch(
        "experiment_bot.reasoner.stage6_pilot._propose_next_phase",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        session_mock = AsyncMock()
        session_mock.dom_snapshot = AsyncMock(return_value="<div>x</div>")
        result = await executor._adaptive_nav_step(session_mock, MagicMock())
    assert result is False
    assert executor._adaptive_nav_uses == 1


@pytest.mark.asyncio
async def test_taskexecutor_constants_match_spec():
    """SP16 budget constants match the spec values."""
    assert _ADAPTIVE_NAV_STUCK_POLLS == 20
    assert _ADAPTIVE_NAV_BUDGET == 10


def test_run_metadata_has_adaptive_nav_summary(make_executor):
    """run_metadata.json's adaptive_nav block summarizes per-session
    adaptive nav usage. _bot_log is a read-only property backed by
    _writer._trials, so entries are seeded there directly."""
    executor = make_executor(with_llm_client=False)  # llm_disabled=True
    # Seed bot_log via the underlying _writer._trials list
    executor._writer._trials.extend([
        {"type": "adaptive_nav", "success": True, "advanced": True},
        {"type": "adaptive_nav", "success": True, "advanced": False},
        {"type": "trial", "trial_index": 1},
    ])
    executor._adaptive_nav_uses = 2
    summary = executor._compute_adaptive_nav_summary()
    assert summary["uses"] == 2
    assert summary["successful_proposals"] == 2
    assert summary["dom_advances"] == 1
    assert summary["llm_disabled"] is True
    assert summary["budget"] == _ADAPTIVE_NAV_BUDGET

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.executor import TaskExecutor


def _bp_stub():
    """Minimal behavior-provider stub: TaskExecutor requires one at init;
    structural tests never execute trials through it."""
    from unittest.mock import MagicMock
    p = MagicMock()
    p.program_sha256 = "00" * 32
    p.program_path = "stub_program.py"
    p.seed = 0
    return p




FULL_CONFIG = {
    "task": {
        "name": "Stop Signal Task",
        "platform": "expfactory",
        "constructs": ["inhibitory_control"],
        "reference_literature": ["Logan 1994"],
    },
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow go trial",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        },
        {
            "id": "go_right",
            "description": "Right arrow go trial",
            "detection": {"method": "dom_query", "selector": ".arrow-right"},
            "response": {"key": "/", "condition": "go"},
        },
        {
            "id": "stop_trial",
            "description": "Stop signal trial",
            "detection": {"method": "dom_query", "selector": ".stop-signal"},
            "response": {"key": None, "condition": "stop"},
        },
    ],
    "response_distributions": {
        "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
        "go_error": {"distribution": "ex_gaussian", "params": {"mu": 380, "sigma": 70, "tau": 100}},
        "stop_failure": {"distribution": "ex_gaussian", "params": {"mu": 400, "sigma": 50, "tau": 60}},
    },
    "performance": {
        "accuracy": {"go": 0.95, "stop": 0.50},
        "omission_rate": {"go": 0.02},
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
}


def test_full_config_parses():
    config = TaskConfig.from_dict(FULL_CONFIG)
    assert config.task.name == "Stop Signal Task"
    assert len(config.stimuli) == 3



def test_executor_constructs_from_config():
    config = TaskConfig.from_dict(FULL_CONFIG)
    executor = TaskExecutor(config, seed=42, behavior_provider=_bp_stub())
    # Verify the lookup has all stimulus rules
    assert len(executor._lookup._rules) == 3
    # Structural projection retains distribution keys (trial-condition identity)
    assert "go_correct" in executor._config.response_distributions
    assert "stop_failure" in executor._config.response_distributions


def test_executor_works_with_runtime_config_only():
    """Executor works purely from config — no platform-specific code needed."""
    config_dict = {
        "task": {
            "name": "Generic Task",
            "platform": "generic",
            "constructs": ["attention"],
            "reference_literature": [],
        },
        "stimuli": [
            {
                "id": "target",
                "description": "Target stimulus",
                "detection": {"method": "js_eval", "selector": "true"},
                "response": {"key": "a", "condition": "go"},
            }
        ],
        "response_distributions": {
            "go_correct": {
                "distribution": "ex_gaussian",
                "params": {"mu": 400, "sigma": 50, "tau": 60},
            }
        },
        "performance": {
            "accuracy": {"go": 0.95, "stop": 0.5},
            "omission_rate": {"go": 0.02},
            "practice_accuracy": 0.9,
        },
        "navigation": {"phases": []},
        "task_specific": {"key_map": {"go": "a"}},
        "runtime": {
            "phase_detection": {
                "method": "js_eval",
                "complete": "document.title === 'Done'",
                "test": "true",
            },
            "timing": {
                "max_no_stimulus_polls": 100,
                "completion_wait_ms": 1000,
                "poll_interval_ms": 50,
            },
            "advance_behavior": {
                "advance_keys": [" "],
                "feedback_selectors": ["button"],
                "feedback_fallback_keys": ["Enter"],
            },
            "trial_interrupt": {},
        },
    }
    config = TaskConfig.from_dict(config_dict)
    executor = TaskExecutor(config, seed=42, behavior_provider=_bp_stub())
    # Verify all runtime config values are accessible
    assert executor._config.runtime.timing.max_no_stimulus_polls == 100
    assert executor._config.runtime.timing.completion_wait_ms == 1000
    assert executor._config.runtime.timing.poll_interval_ms == 50
    assert executor._config.runtime.advance_behavior.advance_keys == [" "]
    assert executor._config.runtime.trial_interrupt.detection_condition == ""
    # Verify key_map works
    assert executor._key_map == {"go": "a"}

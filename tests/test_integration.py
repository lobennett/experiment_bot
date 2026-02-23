import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.executor import TaskExecutor


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
        "go_accuracy": 0.95,
        "stop_accuracy": 0.50,
        "omission_rate": 0.02,
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
}


def test_full_config_parses():
    config = TaskConfig.from_dict(FULL_CONFIG)
    assert config.task.name == "Stop Signal Task"
    assert len(config.stimuli) == 3


def test_config_cache_round_trip(tmp_path):
    config = TaskConfig.from_dict(FULL_CONFIG)
    cache = ConfigCache(cache_dir=tmp_path)
    cache.save("expfactory", "9", config)
    loaded = cache.load("expfactory", "9")
    assert loaded.task.name == "Stop Signal Task"
    assert len(loaded.stimuli) == 3
    assert loaded.response_distributions["go_correct"].params["mu"] == 450


def test_executor_constructs_from_config():
    config = TaskConfig.from_dict(FULL_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    # Verify the lookup has all stimulus rules
    assert len(executor._lookup._rules) == 3
    # Verify sampler has all distributions
    assert "go_correct" in executor._sampler._samplers
    assert "stop_failure" in executor._sampler._samplers

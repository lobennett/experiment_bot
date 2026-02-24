import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.core.config import TaskConfig
from experiment_bot.core.stimulus import StimulusMatch


SAMPLE_CONFIG = {
    "task": {"name": "Stop Signal", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        },
        {
            "id": "stop_trial",
            "description": "Stop signal",
            "detection": {"method": "dom_query", "selector": ".stop-signal"},
            "response": {"key": None, "condition": "stop"},
        },
    ],
    "response_distributions": {
        "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    },
    "performance": {"go_accuracy": 0.95, "stop_accuracy": 0.50, "omission_rate": 0.02, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
}


def test_executor_init():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._config.task.name == "Stop Signal"


def test_should_respond_correctly_on_go():
    """On go trials with high accuracy, bot should usually respond correctly."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    correct_count = sum(1 for _ in range(100) if executor._should_respond_correctly("go"))
    assert 85 < correct_count < 100


def test_should_omit_rarely():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    omit_count = sum(1 for _ in range(1000) if executor._should_omit())
    assert 5 < omit_count < 50


def test_parse_attention_check_direct_key():
    """Test 'Press the X key' format returns the letter lowercased."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")

    assert executor._parse_attention_check_key("Press the Q key") == "q"
    assert executor._parse_attention_check_key("press the A key") == "a"
    assert executor._parse_attention_check_key("Press the Z key") == "z"


def test_parse_attention_check_ordinal():
    """Test 'Press the key for the Nth letter' format returns correct letter."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")

    # Test "third" → "c"
    assert executor._parse_attention_check_key("Press the key for the third letter of the English alphabet") == "c"

    # Test "twenty-sixth" → "z"
    assert executor._parse_attention_check_key("Press the key for the twenty-sixth letter of the English alphabet") == "z"

    # Test other ordinals
    assert executor._parse_attention_check_key("Press the key for the first letter of the English alphabet") == "a"
    assert executor._parse_attention_check_key("Press the key for the tenth letter of the English alphabet") == "j"


def test_parse_attention_check_last():
    """Test 'last letter' maps to 'z'."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")

    assert executor._parse_attention_check_key("Press the key for the last letter of the English alphabet") == "z"


def test_parse_attention_check_unknown():
    """Test unrecognized format and empty string return None."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")

    # Unrecognized format
    assert executor._parse_attention_check_key("Click the button to continue") is None
    assert executor._parse_attention_check_key("This is just random text") is None

    # Empty string
    assert executor._parse_attention_check_key("") is None

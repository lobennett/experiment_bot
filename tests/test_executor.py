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


TASK_SWITCHING_CONFIG = {
    "task": {"name": "Cued Task Switching", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "parity_even",
            "description": "Even number with parity cue",
            "detection": {"method": "js_eval", "selector": "window.currTask === 'parity' && window.currStim.number % 2 === 0"},
            "response": {"key": "dynamic", "condition": "parity_even"},
        },
        {
            "id": "magnitude_high",
            "description": "Number > 5 with magnitude cue",
            "detection": {"method": "js_eval", "selector": "window.currTask === 'magnitude' && window.currStim.number > 5"},
            "response": {"key": "dynamic", "condition": "magnitude_high"},
        },
    ],
    "response_distributions": {
        "task_switch": {"distribution": "ex_gaussian", "params": {"mu": 580, "sigma": 70, "tau": 100}},
    },
    "performance": {"go_accuracy": 0.88, "stop_accuracy": 0, "omission_rate": 0.03, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {
        "default_group_index": 1,
        "group_index_mappings": {
            "0_to_4": {"higher": ",", "lower": ".", "odd": ",", "even": "."},
            "5_to_9": {"higher": ",", "lower": ".", "odd": ".", "even": ","},
        },
    },
}


def test_resolve_key_mapping_task_switching():
    """Verify key_map has correct mappings for group_index 1 (0_to_4 mapping)."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    key_map = executor._resolve_key_mapping(config)

    # For group_index 1, uses 0_to_4 mapping
    assert key_map["parity_even"] == "."
    assert key_map["parity_odd"] == ","
    assert key_map["magnitude_high"] == ","
    assert key_map["magnitude_low"] == "."


def test_resolve_response_key_dynamic():
    """Create a StimulusMatch with response_key='dynamic' and condition='parity_even', verify _resolve_response_key returns '.'."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")

    # Create a StimulusMatch with dynamic key
    stimulus_match = StimulusMatch(
        stimulus_id="parity_even",
        response_key="dynamic",
        condition="parity_even"
    )

    resolved_key = executor._resolve_response_key(stimulus_match)
    assert resolved_key == "."


def test_resolve_response_key_static():
    """Create a StimulusMatch with response_key='z', verify it returns 'z' unchanged."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")

    # Create a StimulusMatch with static key
    stimulus_match = StimulusMatch(
        stimulus_id="go_left",
        response_key="z",
        condition="go"
    )

    resolved_key = executor._resolve_response_key(stimulus_match)
    assert resolved_key == "z"


def test_direct_key_map_from_config():
    """Key map uses task_specific.key_map directly when present."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["task_specific"] = {
        "key_map": {
            "go_left": "b",
            "go_right": "n",
            "parity_even": "z",
            "parity_odd": "m",
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, platform_name="test")
    assert executor._key_map == config.task_specific["key_map"]


def test_direct_key_map_overrides_legacy():
    """When key_map is present, legacy group_index_mappings are ignored."""
    config_data = dict(TASK_SWITCHING_CONFIG)
    config_data["task_specific"]["key_map"] = {
        "parity_even": "a",
        "parity_odd": "s",
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, platform_name="test")
    assert executor._key_map["parity_even"] == "a"
    assert executor._key_map["parity_odd"] == "s"


def test_executor_uses_runtime_timing():
    """Executor reads timing from runtime config, not hardcoded values."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "timing": {
            "poll_interval_ms": 50,
            "max_no_stimulus_polls": 1000,
            "stuck_timeout_s": 15.0,
            "completion_wait_ms": 10000,
            "rt_floor_ms": 200.0,
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, platform_name="test")
    assert executor._config.runtime.timing.poll_interval_ms == 50
    assert executor._config.runtime.timing.max_no_stimulus_polls == 1000
    assert executor._config.runtime.timing.stuck_timeout_s == 15.0
    assert executor._config.runtime.timing.rt_floor_ms == 200.0


def test_executor_no_platform_name_dependency():
    """Executor should not branch on platform name."""
    import inspect
    from experiment_bot.core.executor import TaskExecutor
    source = inspect.getsource(TaskExecutor)
    assert 'platform_name == "psytoolkit"' not in source
    assert 'platform_name == "expfactory"' not in source


def test_executor_sampler_uses_config_floor():
    """ResponseSampler receives floor_ms from runtime config."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {"timing": {"rt_floor_ms": 200.0}}
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, platform_name="test", seed=42)
    # The sampler should use 200.0 as floor, not the default 150.0
    assert executor._sampler._floor_ms == 200.0


def test_sampler_fallback_to_first_distribution():
    """When requested condition doesn't exist, sampler falls back to first available."""
    from experiment_bot.core.distributions import ResponseSampler
    from experiment_bot.core.config import DistributionConfig
    dists = {
        "task_switch": DistributionConfig(distribution="ex_gaussian", params={"mu": 580, "sigma": 70, "tau": 100}),
    }
    sampler = ResponseSampler(dists, seed=42)
    rt = sampler.sample_rt_with_fallback("go_correct")
    assert 150 < rt < 2000

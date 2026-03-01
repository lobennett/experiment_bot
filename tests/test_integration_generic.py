"""Integration tests for the platform-agnostic (generic) pipeline.

These tests verify that a config with no platform-specific fields
round-trips through JSON and constructs a working executor.
"""
import json

from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.config import (
    AttentionCheckConfig,
    DataCaptureConfig,
    DistributionConfig,
    NavigationConfig,
    PerformanceConfig,
    PhaseDetectionConfig,
    RuntimeConfig,
    StimulusConfig,
    TaskConfig,
    TaskMetadata,
    TimingConfig,
)
from experiment_bot.core.executor import TaskExecutor


GENERIC_CONFIG = {
    "task": {
        "name": "Flanker Task",
        "constructs": ["attention", "inhibitory_control"],
        "reference_literature": ["Eriksen & Eriksen 1974"],
    },
    "stimuli": [
        {
            "id": "congruent",
            "description": "Congruent flanker (e.g. <<<<<)",
            "detection": {"method": "js_eval", "selector": "window.stimType === 'congruent'"},
            "response": {"key": "f", "condition": "go"},
        },
        {
            "id": "incongruent",
            "description": "Incongruent flanker (e.g. <<><<)",
            "detection": {"method": "js_eval", "selector": "window.stimType === 'incongruent'"},
            "response": {"key": "j", "condition": "go"},
        },
    ],
    "response_distributions": {
        "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 420, "sigma": 50, "tau": 70}},
        "go_error": {"distribution": "ex_gaussian", "params": {"mu": 380, "sigma": 60, "tau": 90}},
    },
    "performance": {
        "accuracy": {"go": 0.92},
        "omission_rate": {"go": 0.03},
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {"key_map": {"congruent": "f", "incongruent": "j"}},
    "runtime": {
        "phase_detection": {
            "method": "js_eval",
            "complete": "document.querySelector('#complete') !== null",
            "test": "window.phase === 'trial'",
            "instructions": "window.phase === 'instructions'",
            "feedback": "window.phase === 'feedback'",
        },
        "timing": {
            "max_no_stimulus_polls": 80,
            "completion_wait_ms": 2000,
            "poll_interval_ms": 40,
        },
        "data_capture": {
            "method": "js_expression",
            "expression": "JSON.stringify(window.trialData)",
            "format": "json",
        },
        "attention_check": {
            "text_selector": "#attention-prompt",
        },
    },
}


def test_generic_config_round_trip():
    """A config with no platform field round-trips through JSON."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    d = config.to_dict()
    restored = TaskConfig.from_dict(d)

    assert restored.task.name == "Flanker Task"
    assert restored.task.platform == ""
    assert len(restored.stimuli) == 2
    assert restored.runtime.data_capture.method == "js_expression"
    assert restored.runtime.attention_check.text_selector == "#attention-prompt"
    assert restored.runtime.timing.poll_interval_ms == 40


def test_generic_config_json_serializable():
    """Config serializes to valid JSON without platform field."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    json_str = json.dumps(config.to_dict(), indent=2)
    reloaded = json.loads(json_str)

    assert "platform" not in reloaded["task"] or reloaded["task"]["platform"] == ""
    assert reloaded["runtime"]["data_capture"]["method"] == "js_expression"


def test_generic_config_cache_round_trip(tmp_path):
    """Cache stores and retrieves a platform-free config by URL hash."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    cache = ConfigCache(cache_dir=tmp_path)
    url = "https://example.com/flanker-experiment/"

    cache.save(url, config)
    loaded = cache.load(url)

    assert loaded is not None
    assert loaded.task.name == "Flanker Task"
    assert loaded.task.platform == ""
    assert loaded.runtime.data_capture.expression == "JSON.stringify(window.trialData)"


def test_generic_config_cache_with_label(tmp_path):
    """Cache supports label-based storage alongside URL hash."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    cache = ConfigCache(cache_dir=tmp_path)
    url = "https://example.com/flanker-experiment/"

    cache.save(url, config, label="my_flanker")
    loaded = cache.load(url, label="my_flanker")

    assert loaded is not None
    assert loaded.task.name == "Flanker Task"

    # URL-hash lookup should NOT find label-stored config
    assert cache.load(url) is None


def test_generic_executor_constructs():
    """Executor constructs from generic config without platform_name."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    executor = TaskExecutor(config, seed=42)

    assert len(executor._lookup._rules) == 2
    assert "go_correct" in executor._sampler._samplers
    assert executor._key_map == {"congruent": "f", "incongruent": "j"}


def test_generic_executor_runtime_config_accessible():
    """All runtime config values are accessible through the executor."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    executor = TaskExecutor(config, seed=42)

    assert executor._config.runtime.timing.max_no_stimulus_polls == 80
    assert executor._config.runtime.timing.completion_wait_ms == 2000
    assert executor._config.runtime.phase_detection.complete == "document.querySelector('#complete') !== null"
    assert executor._config.runtime.data_capture.format == "json"


def test_generic_executor_samples_rt():
    """Response sampler produces plausible RTs from generic config."""
    config = TaskConfig.from_dict(GENERIC_CONFIG)
    executor = TaskExecutor(config, seed=42)

    rts = [executor._sampler.sample_rt_with_fallback("go_correct") for _ in range(100)]
    assert all(100 < rt < 3000 for rt in rts)
    # Mean should be near mu + tau = 420 + 70 = 490
    mean_rt = sum(rts) / len(rts)
    assert 350 < mean_rt < 650

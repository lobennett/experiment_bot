import hashlib
import json
import pytest
from pathlib import Path

from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.config import TaskConfig


SAMPLE_CONFIG_DICT = {
    "task": {"name": "Test", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"accuracy": {"go": 0.9, "stop": 0.5}, "omission_rate": {"go": 0.01}, "practice_accuracy": 0.8},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_cache_miss(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    result = cache.load("https://example.com/experiment/")
    assert result is None


def test_cache_save_and_load(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    url = "https://example.com/experiment/"
    cache.save(url, config)
    loaded = cache.load(url)
    assert loaded is not None
    assert loaded.task.name == "Test"


def test_cache_url_key(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    url = "https://example.com/experiment/"
    expected_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = cache._config_path(url)
    assert expected_hash in str(path)


def test_cache_with_label(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    url = "https://example.com/experiment/"
    cache.save(url, config, label="my_experiment")
    loaded = cache.load(url, label="my_experiment")
    assert loaded is not None
    assert loaded.task.name == "Test"
    # Verify it's stored under the label, not URL hash
    expected_path = tmp_path / "my_experiment" / "config.json"
    assert expected_path.exists()

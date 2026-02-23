import json
import pytest
from pathlib import Path

from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.config import TaskConfig


SAMPLE_CONFIG_DICT = {
    "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_cache_miss(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    result = cache.load("expfactory", "9")
    assert result is None


def test_cache_save_and_load(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    cache.save("expfactory", "9", config)
    loaded = cache.load("expfactory", "9")
    assert loaded is not None
    assert loaded.task.name == "Test"


def test_cache_file_location(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    cache.save("expfactory", "9", config)
    expected_path = tmp_path / "expfactory" / "9" / "config.json"
    assert expected_path.exists()

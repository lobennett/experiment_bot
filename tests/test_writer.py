import json
import pytest
from pathlib import Path

from experiment_bot.output.writer import OutputWriter
from experiment_bot.core.config import TaskConfig


SAMPLE_CONFIG_DICT = {
    "task": {"name": "Test", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_writer_creates_output_dir(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("expfactory", "stop_signal_rdoc", config)
    assert run_dir.exists()
    assert (run_dir / "config.json").exists()


def test_writer_logs_trial(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("expfactory", "test_task", config)
    trial = {"trial": 1, "stimulus_id": "go_left", "sampled_rt_ms": 450}
    writer.log_trial(trial)
    writer.finalize()
    log_path = run_dir / "bot_log.json"
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert len(data) == 1
    assert data[0]["trial"] == 1

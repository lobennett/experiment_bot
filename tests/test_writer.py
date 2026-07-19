import json
import pytest
from pathlib import Path

from experiment_bot.output.writer import OutputWriter
from experiment_bot.core.config import TaskConfig


SAMPLE_CONFIG_DICT = {
    "task": {"name": "Test", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"accuracy": {"go": 0.9, "stop": 0.5}, "omission_rate": {"go": 0.01}, "practice_accuracy": 0.8},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_writer_creates_output_dir(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("stop_signal_rdoc", config)
    assert run_dir.exists()
    assert (run_dir / "config.json").exists()


def test_writer_logs_trial(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("test_task", config)
    trial = {"trial": 1, "stimulus_id": "go_left", "sampled_rt_ms": 450}
    writer.log_trial(trial)
    writer.finalize()
    log_path = run_dir / "bot_log.json"
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert len(data) == 1
    assert data[0]["trial"] == 1


def test_save_task_data_writes_csv(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    writer.create_run("test_task", config)
    writer.save_task_data("col1,col2\nval1,val2\n", "experiment_data.csv")
    saved = (writer.run_dir / "experiment_data.csv").read_text()
    assert "col1,col2" in saved


def test_save_task_data_writes_tsv(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    writer.create_run("stopsignal", config)
    writer.save_task_data("go\tleft\t423\n", "experiment_data.tsv")
    saved = (writer.run_dir / "experiment_data.tsv").read_text()
    assert "go\tleft\t423" in saved


def test_writer_sanitizes_slash_in_task_name(tmp_path):
    """A card name with '/' (e.g. 'Go/No-Go (RDoC)') must produce a single
    path segment, not a nested two-level dir that hides the session from
    per-task tooling."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("Go/No-Go (RDoC)", config)
    assert run_dir.exists()
    # one level under base: base_dir / <sanitized> / <timestamp>
    assert run_dir.parent.parent == tmp_path
    assert "/" not in run_dir.parent.name
    assert run_dir.parent.name == "Go_No-Go (RDoC)"

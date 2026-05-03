import json
from pathlib import Path
import pytest
from experiment_bot.taskcard.loader import save_taskcard, load_latest, load_by_hash
from experiment_bot.taskcard.types import TaskCard


@pytest.fixture
def minimal_taskcard_dict():
    return {
        "schema_version": "2.0",
        "produced_by": {
            "model": "claude-opus-4-7",
            "prompt_sha256": "p",
            "scraper_version": "1.0.0",
            "source_sha256": "s",
            "timestamp": "2026-04-23T12:00:00Z",
            "taskcard_sha256": "",
        },
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "navigation": {"phases": []},
        "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {},
        "temporal_effects": {},
        "between_subject_jitter": {},
        "reasoning_chain": [],
        "pilot_validation": {},
    }


def test_save_writes_hashed_filename(tmp_path, minimal_taskcard_dict):
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    path = save_taskcard(tc, tmp_path / "taskcards", label="stroop")
    assert path.exists()
    assert path.parent == tmp_path / "taskcards" / "stroop"
    assert path.suffix == ".json"
    assert len(path.stem) == 8


def test_save_updates_taskcard_sha256(tmp_path, minimal_taskcard_dict):
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    assert tc.produced_by.taskcard_sha256 == ""
    path = save_taskcard(tc, tmp_path / "taskcards", label="stroop")
    loaded = json.loads(path.read_text())
    assert loaded["produced_by"]["taskcard_sha256"] != ""
    assert path.stem == loaded["produced_by"]["taskcard_sha256"][:8]


def test_load_latest_returns_most_recent(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    p1 = save_taskcard(tc, base, label="stroop")
    minimal_taskcard_dict["task"]["name"] = "stroop_v2"
    tc2 = TaskCard.from_dict(minimal_taskcard_dict)
    p2 = save_taskcard(tc2, base, label="stroop")
    latest = load_latest(base, label="stroop")
    assert latest.task.name == "stroop_v2"


def test_load_by_hash(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    path = save_taskcard(tc, base, label="stroop")
    loaded = load_by_hash(base, label="stroop", hash_prefix=path.stem)
    assert loaded.schema_version == "2.0"


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest(tmp_path / "taskcards", label="nonexistent")

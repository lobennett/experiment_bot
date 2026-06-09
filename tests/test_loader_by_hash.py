import json
from pathlib import Path
import pytest
from experiment_bot.taskcard.loader import save_taskcard, load_latest, load_by_hash
from experiment_bot.taskcard.hashing import taskcard_sha256
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


def _hash_of(path: Path) -> str:
    return taskcard_sha256(json.loads(path.read_text()))


def test_load_by_hash_returns_matching_card(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc1 = TaskCard.from_dict(minimal_taskcard_dict)
    p1 = save_taskcard(tc1, base, label="stroop")
    minimal_taskcard_dict["task"]["name"] = "stroop_v2"
    tc2 = TaskCard.from_dict(minimal_taskcard_dict)
    p2 = save_taskcard(tc2, base, label="stroop")

    h1 = _hash_of(p1)
    h2 = _hash_of(p2)
    assert h1 != h2

    loaded1 = load_by_hash(base, "stroop", h1)
    assert loaded1.task.name == "stroop"
    loaded2 = load_by_hash(base, "stroop", h2)
    assert loaded2.task.name == "stroop_v2"


def test_load_by_hash_accepts_unambiguous_prefix(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    p = save_taskcard(tc, base, label="stroop")
    h = _hash_of(p)
    loaded = load_by_hash(base, "stroop", h[:8])
    assert loaded.task.name == "stroop"


def test_load_by_hash_no_match_raises(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    save_taskcard(tc, base, label="stroop")
    with pytest.raises(FileNotFoundError):
        load_by_hash(base, "stroop", "deadbeef" * 8)


def test_load_by_hash_missing_label_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_by_hash(tmp_path / "taskcards", "nonexistent", "abc123")


def test_load_by_hash_ambiguous_prefix_raises(tmp_path, minimal_taskcard_dict):
    # Search the task name space for two distinct cards sharing a 1-hex prefix
    # so prefix lookup is deterministically ambiguous.
    base = tmp_path / "taskcards"
    by_prefix: dict[str, str] = {}
    pair = None
    for i in range(64):
        minimal_taskcard_dict["task"]["name"] = f"stroop_{i}"
        h = taskcard_sha256(minimal_taskcard_dict)
        if h[0] in by_prefix and by_prefix[h[0]] != h:
            pair = (by_prefix[h[0]], h, h[0])
            break
        by_prefix[h[0]] = h
    assert pair is not None, "could not synthesize a shared-prefix pair"

    h1, h2, shared_prefix = pair
    # Save the two colliding cards.
    for name in (f"stroop_{n}" for n in range(64)):
        pass
    # Re-derive and save both members.
    saved = 0
    for i in range(64):
        minimal_taskcard_dict["task"]["name"] = f"stroop_{i}"
        if taskcard_sha256(minimal_taskcard_dict) in (h1, h2):
            save_taskcard(TaskCard.from_dict(minimal_taskcard_dict), base, label="stroop")
            saved += 1
    assert saved == 2

    with pytest.raises(FileNotFoundError):
        load_by_hash(base, "stroop", shared_prefix)


def test_load_latest_roundtrips_through_its_own_hash(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    save_taskcard(tc, base, label="stroop")
    latest = load_latest(base, label="stroop")
    recorded_hash = latest.produced_by.taskcard_sha256
    assert recorded_hash != ""
    by_hash = load_by_hash(base, "stroop", recorded_hash)
    assert by_hash.task.name == latest.task.name
    assert by_hash.produced_by.taskcard_sha256 == recorded_hash

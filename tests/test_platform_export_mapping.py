"""TaskCard-declared platform-export mapping (SP18, additive).

The per-paradigm adapter knowledge in validation/platform_adapters.py is
meant to live in the TaskCard (the module docstring has said so since SP2).
adapter_from_export_config builds a trial loader from a declarative
runtime.platform_export config; resolve_trial_loader prefers it and falls
back to the hand-written registry. Hand-written adapters stay canonical
until cards are regenerated with the config.
"""
import csv
import json
from pathlib import Path

import pytest

from experiment_bot.core.config import RuntimeConfig
from experiment_bot.taskcard.hashing import taskcard_sha256
from experiment_bot.taskcard.loader import load_by_hash
from experiment_bot.validation.platform_adapters import (
    adapter_from_export_config,
    read_expfactory_stroop,
    read_stopit_stop_signal,
    resolve_trial_loader,
)

REPO = Path(__file__).resolve().parents[1]

STROOP_EXPORT_CFG = {
    "row_filter": {"equals": {"trial_id": "test_trial"}},
    "fields": {
        "condition": {"column": "condition"},
        "rt": {"column": "rt", "parse": "float"},
        "correct": {"column": "correct_trial", "parse": "truthy"},
    },
}

STOPIT_EXPORT_CFG = {
    "row_filter": {"one_of": {"block_i": ["1", "2", "3", "4"]}},
    "fields": {
        "condition": {"column": "signal",
                      "value_map": {"yes": "stop", "no": "go"}, "default": ""},
        "rt": {"column": "rt", "parse": "float"},
        "correct": {"column": "correct", "parse": "truthy"},
        "ssd": {"column": "SSD", "parse": "float"},
    },
}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_export_config_reproduces_stroop_adapter(tmp_path):
    """The declarative mapping must produce the SAME canonical trials as the
    hand-written read_expfactory_stroop on the same export."""
    _write_csv(tmp_path / "experiment_data.csv",
               ["trial_id", "condition", "rt", "correct_trial"],
               [
                   {"trial_id": "test_trial", "condition": "congruent", "rt": "512.3", "correct_trial": "1"},
                   {"trial_id": "test_trial", "condition": "incongruent", "rt": "", "correct_trial": "0"},
                   {"trial_id": "fixation", "condition": "", "rt": "100", "correct_trial": "0"},
                   {"trial_id": "test_trial", "condition": "incongruent", "rt": "640.0", "correct_trial": "0"},
               ])
    declarative = adapter_from_export_config(STROOP_EXPORT_CFG)(tmp_path)
    hand_written = read_expfactory_stroop(tmp_path)
    assert declarative == hand_written
    assert len(declarative) == 3
    assert declarative[1]["omission"] is True


def test_export_config_reproduces_stopit_adapter(tmp_path):
    _write_csv(tmp_path / "experiment_data.csv",
               ["block_i", "signal", "rt", "correct", "SSD"],
               [
                   {"block_i": "0", "signal": "no", "rt": "400", "correct": "true", "SSD": ""},
                   {"block_i": "1", "signal": "no", "rt": "455.5", "correct": "true", "SSD": ""},
                   {"block_i": "2", "signal": "yes", "rt": "NaN", "correct": "true", "SSD": "250"},
                   {"block_i": "3", "signal": "yes", "rt": "410", "correct": "false", "SSD": "150"},
               ])
    declarative = adapter_from_export_config(STOPIT_EXPORT_CFG)(tmp_path)
    hand_written = read_stopit_stop_signal(tmp_path)
    assert declarative == hand_written
    assert len(declarative) == 3  # practice block 0 dropped
    assert declarative[0]["condition"] == "go"
    assert declarative[1] == {"condition": "stop", "rt": None, "correct": True,
                              "ssd": 250.0, "omission": True}


def test_export_config_requires_condition_and_rt():
    with pytest.raises(ValueError, match="condition"):
        adapter_from_export_config({"fields": {"rt": {"column": "rt"}}})


def test_resolve_prefers_taskcard_config_falls_back_to_registry(tmp_path):
    # Card WITH platform_export -> taskcard loader wins.
    card_dir = tmp_path / "with_cfg"
    card_dir.mkdir()
    base = json.loads(
        next((REPO / "taskcards" / "expfactory_stroop").glob("*.json")).read_text()
    )
    base["runtime"]["platform_export"] = STROOP_EXPORT_CFG
    (card_dir / "ffffffff.json").write_text(json.dumps(base))

    loader, source = resolve_trial_loader("with_cfg", tmp_path)
    assert source == "taskcard_platform_export"
    assert loader is not None

    # No card -> registry fallback for a known label.
    loader2, source2 = resolve_trial_loader("stroop_rdoc", tmp_path)
    assert source2 == "registry_adapter"
    assert loader2 is read_expfactory_stroop

    # No card, unknown label -> none.
    loader3, source3 = resolve_trial_loader("nonexistent_paradigm", tmp_path)
    assert loader3 is None and source3 == "none"


# The four PRODUCTION dev cards (hashes pinned in docs/validation-results.md)
# round-trip exactly under the current schema; legacy flanker/n_back cards
# predate newer schema fields and already do not (pre-existing
# schema-evolution lossiness, unrelated to platform_export). Loaded by
# content hash, NOT load_latest: mtime ordering is nondeterministic on fresh
# checkouts (all files share the checkout mtime), so on CI load_latest can
# pick a legacy card.
PRODUCTION_CARDS = [
    ("cognitionrun_stroop", "b16c7891"),
    ("expfactory_stop_signal", "e29f22de"),
    ("expfactory_stroop", "45751cfe"),
    ("stopit_stop_signal", "6fc729c3"),
]


def test_platform_export_omitted_when_empty():
    """to_dict must omit an empty platform_export — it feeds the canonical
    content hash, so an unconditional key would change every committed
    card's recomputed hash and break hermetic replay."""
    assert "platform_export" not in RuntimeConfig.from_dict({}).to_dict()
    cfg = {"row_filter": {}, "fields": {"condition": {"column": "c"}, "rt": {"column": "rt"}}}
    assert RuntimeConfig.from_dict({"platform_export": cfg}).to_dict()["platform_export"] == cfg


@pytest.mark.parametrize("label,sha_prefix", PRODUCTION_CARDS)
def test_production_card_hashes_unperturbed(label, sha_prefix):
    """The production dev cards must keep their recorded content hashes
    (hermetic replay recomputes and matches them)."""
    tc = load_by_hash(REPO / "taskcards", label, sha_prefix)
    payload = tc.to_dict()
    assert taskcard_sha256(payload) == payload["produced_by"]["taskcard_sha256"], label
    assert payload["produced_by"]["taskcard_sha256"].startswith(sha_prefix)


def test_prompt_documents_platform_export_generically():
    prompt = (REPO / "src" / "experiment_bot" / "prompts" / "system.md").read_text()
    section = prompt[prompt.index("## Platform-export mapping"):]
    assert "row_filter" in section and "value_map" in section
    # Prompt guardrail: no paradigm-specific vocabulary in the new section.
    for forbidden in ("stroop", "stop_signal", "stop signal", "flanker",
                      "n-back", "congruent", "incongruent"):
        assert forbidden not in section.lower(), forbidden

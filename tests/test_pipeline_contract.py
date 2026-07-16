"""Pipeline contract test: the COMMITTED TaskCards are the Reasoner's
contract artifacts — they must parse under the CURRENT schema so the
executor (naive arm) can read navigation/detection/key facts from them.
No network, no browser."""
from pathlib import Path

import pytest

from experiment_bot.taskcard.loader import load_latest

REPO = Path(__file__).resolve().parents[1]
TASKCARDS = REPO / "taskcards"
DEV_LABELS = sorted(
    p.name for p in TASKCARDS.iterdir()
    if p.is_dir() and any(p.glob("*.json"))
)


@pytest.mark.parametrize("label", DEV_LABELS)
def test_every_committed_taskcard_loads(label):
    """Committed cards must parse under the current schema and expose the
    structural facts the naive arm needs (stimuli, navigation, runtime)."""
    tc = load_latest(TASKCARDS, label)
    assert tc.task.name
    assert tc.stimuli, label
    for stim in tc.stimuli:
        assert stim.detection.selector, (label, stim.id)
    assert tc.runtime is not None
    assert tc.navigation is not None


def test_structural_pipeline_scrubs_stray_behavioral_fields():
    """Live-run regression (flanker, 2026-07-06): Stage 1's LLM emitted
    performance={'accuracy': 0.8} (bare float) though the structural prompt
    doesn't ask for it; Stage 6's PerformanceConfig.from_dict crashed on
    .items(). The pipeline must drop stray behavioral fields."""
    from experiment_bot.reasoner.pipeline import _scrub_behavioral_fields
    partial = {"task": {"name": "x"}, "stimuli": [],
               "performance": {"accuracy": 0.8, "omission": 0.1},
               "response_distributions": {"go": {}},
               "temporal_effects": {"anything": 1},
               "between_subject_jitter": {"value": {}},
               "_reasoning_chain": []}
    _scrub_behavioral_fields(partial)
    for k in ("performance", "response_distributions", "temporal_effects",
              "between_subject_jitter"):
        assert k not in partial
    assert partial["task"] == {"name": "x"}

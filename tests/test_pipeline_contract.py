"""Pipeline contract test (audit finding: no test exercised the
TaskCard -> sampling -> session-data -> oracle -> comparison chain, so a
schema drift between stages surfaced only at human review).

No network, no browser: uses the COMMITTED TaskCards as the Reasoner-output
fixture (which also guards that every committed card parses under the
current schema), synthesizes a platform-format session from the sampled
parameters, and runs the real adapter + oracle + human comparison over it.
"""
import csv
import json
import math
import random
from pathlib import Path

import pytest

from experiment_bot.taskcard.loader import load_latest
from experiment_bot.taskcard.sampling import sample_session_params
from experiment_bot.validation.human_reference import compare_metrics
from experiment_bot.validation.oracle import validate_session_set
from experiment_bot.validation.platform_adapters import read_expfactory_stroop

REPO = Path(__file__).resolve().parents[1]
TASKCARDS = REPO / "taskcards"
DEV_LABELS = sorted(
    p.name for p in TASKCARDS.iterdir()
    if p.is_dir() and any(p.glob("*.json"))
)


@pytest.mark.parametrize("label", DEV_LABELS)
def test_every_committed_taskcard_loads_and_samples(label):
    """Committed cards are the Reasoner's contract artifacts: they must parse
    under the CURRENT schema and survive session-parameter sampling."""
    tc = load_latest(TASKCARDS, label)
    assert tc.task.name
    assert tc.response_distributions, label
    sampled = sample_session_params(tc.to_dict(), seed=1234)
    assert isinstance(sampled, dict)
    for cond, params in sampled.items():
        for v in params.values():
            assert isinstance(v, (int, float)), (label, cond, params)


def _synth_stroop_session(base: Path, name: str, mu: float, seed: int) -> Path:
    """Write a session dir in the expfactory-stroop platform-export format,
    with RTs around the sampled mu — the executor's output contract."""
    rng = random.Random(seed)
    d = base / "stroop_rdoc" / name
    d.mkdir(parents=True)
    rows = []
    for i in range(60):
        cond = "congruent" if i % 2 == 0 else "incongruent"
        rt = rng.gauss(mu + (0 if cond == "congruent" else 60), 50)
        rows.append({
            "trial_id": "test_trial", "condition": cond,
            "rt": max(200.0, rt), "correct_trial": 1 if rng.random() < 0.95 else 0,
        })
    with (d / "experiment_data.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["trial_id", "condition", "rt", "correct_trial"])
        w.writeheader()
        w.writerows(rows)
    (d / "run_metadata.json").write_text(json.dumps({"total_trials": len(rows)}))
    return d


def test_taskcard_to_oracle_to_comparison_chain(tmp_path):
    """Full downstream chain over the committed stroop card: sample params,
    synthesize platform data from them, score with the real norms + adapter,
    compare against a synthetic human reference via the committed map."""
    tc = load_latest(TASKCARDS, "expfactory_stroop")
    sampled = sample_session_params(tc.to_dict(), seed=99)
    # Use a sampled mu when present; the chain must not depend on a specific
    # condition vocabulary in this test.
    mu = next(
        (p["mu"] for p in sampled.values() if isinstance(p, dict) and "mu" in p),
        500.0,
    )

    dirs = [
        _synth_stroop_session(tmp_path, f"s{i}", mu=float(mu), seed=i)
        for i in range(3)
    ]

    # Oracle over the real conflict norms file + real adapter.
    norms = json.loads((REPO / "norms" / "conflict.json").read_text())
    report = validate_session_set(
        "conflict", dirs, norms, trial_loader=read_expfactory_stroop,
    )
    assert report.n_used == 3
    metric_names = {
        m.name for p in report.pillar_results.values() for m in p.metrics.values()
    }
    assert {"mu", "sigma", "tau", "post_error_slowing"} <= metric_names
    fitted_mu = next(
        m.bot_value for p in report.pillar_results.values()
        for m in p.metrics.values() if m.name == "mu"
    )
    assert fitted_mu is not None and abs(fitted_mu - float(mu)) < 150

    # Human comparison via the committed map.
    metrics_map = json.loads(
        (REPO / "data" / "human" / "comparison_maps" / "stroop_rdoc.json").read_text()
    )["metrics"]
    human_rows = [
        {"congruent_rt": str(500 + 10 * i), "incongruent_rt": str(570 + 10 * i),
         "congruent_accuracy": "0.96", "incongruent_accuracy": "0.92",
         "congruent_omission_rate": "0.005", "incongruent_omission_rate": "0.01"}
        for i in range(5)
    ]
    out = compare_metrics(dirs, read_expfactory_stroop, human_rows, metrics_map)
    assert out["congruent_rt"]["bot_n"] == 3
    assert out["congruent_rt"]["z"] is not None
    assert not math.isnan(out["stroop_effect"]["bot_mean"])

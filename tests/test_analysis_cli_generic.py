"""Wave C3: per-subject CLI accepts unknown labels via the card-declared
export mapping + generic metrics (clearly marked; no human comparison)."""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from click.testing import CliRunner

from experiment_bot.analysis.cli import main
from experiment_bot.taskcard.hashing import taskcard_sha256

REPO = Path(__file__).resolve().parents[1]
_FLANKER_CARD = REPO / "taskcards" / "expfactory_flanker" / "41e68e61.json"


def _setup(tmp_path):
    tdir = tmp_path / "taskcards" / "expfactory_flanker"
    tdir.mkdir(parents=True)
    shutil.copy(_FLANKER_CARD, tdir / "41e68e61.json")
    full_hash = taskcard_sha256(json.loads(_FLANKER_CARD.read_text()))
    sd = tmp_path / "out" / "flanker_rdoc" / "2026-01-01_00-00-00"
    sd.mkdir(parents=True)
    pd.DataFrame({
        "trial_id": ["test_trial"] * 4,
        "condition": ["congruent", "congruent", "incongruent", "incongruent"],
        "rt": [400.0, 420.0, 500.0, np.nan],
        "correct_trial": [1, 1, 1, 0],
    }).to_csv(sd / "experiment_data.csv", index=False)
    (sd / "run_metadata.json").write_text(json.dumps({"taskcard_sha256": full_hash}))


def test_cli_unknown_label_computes_generic_metrics(tmp_path):
    _setup(tmp_path)
    result = CliRunner().invoke(main, [
        "--label", "expfactory_flanker",
        "--output-dir", str(tmp_path / "out"),
        "--out-dir", str(tmp_path / "res"),
        "--taskcards-dir", str(tmp_path / "taskcards"),
    ])
    assert result.exit_code == 0, result.output
    assert "GENERIC" in result.output
    csv_path = tmp_path / "res" / "per_subject_expfactory_flanker_bot.csv"
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    assert len(df) == 1
    assert df.iloc[0]["metrics"] == "generic"
    assert df.iloc[0]["congruent_rt"] == 410.0
    report = (tmp_path / "res" / "generic_expfactory_flanker.md").read_text()
    assert "GENERIC" in report
    assert "No human-reference comparison" in report
    assert "congruent_rt" in report


def test_cli_unknown_label_needs_no_human_csv(tmp_path):
    """Unlike known labels, the generic path must not demand --human-*."""
    _setup(tmp_path)
    result = CliRunner().invoke(main, [
        "--label", "expfactory_flanker",
        "--output-dir", str(tmp_path / "out"),
        "--out-dir", str(tmp_path / "res"),
        "--taskcards-dir", str(tmp_path / "taskcards"),
    ])
    assert result.exit_code == 0
    assert "human" not in Path(tmp_path / "res" / "generic_expfactory_flanker.md").name

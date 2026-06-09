"""experiment-bot-compare CLI: end-to-end over a synthetic session dir using
the REAL stroop adapter and the committed comparison map."""
import csv
import json
from pathlib import Path

from click.testing import CliRunner

from experiment_bot.validation.compare_cli import main

REPO = Path(__file__).resolve().parents[1]


def _make_stroop_session(base: Path, name: str, cong_rt: float, incong_rt: float):
    d = base / "stroop_rdoc" / name
    d.mkdir(parents=True)
    rows = []
    for i in range(10):
        rows.append({"trial_id": "test_trial", "condition": "congruent",
                     "rt": cong_rt, "correct_trial": 1})
        rows.append({"trial_id": "test_trial", "condition": "incongruent",
                     "rt": incong_rt, "correct_trial": 1})
    with (d / "experiment_data.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["trial_id", "condition", "rt", "correct_trial"])
        w.writeheader()
        w.writerows(rows)
    return d


def _make_human_csv(path: Path):
    rows = [
        {"congruent_rt": 575, "incongruent_rt": 642, "congruent_accuracy": 0.96,
         "incongruent_accuracy": 0.92, "congruent_omission_rate": 0.01,
         "incongruent_omission_rate": 0.02, "Session-Level Exclusions": "Include"},
        {"congruent_rt": 525, "incongruent_rt": 600, "congruent_accuracy": 0.98,
         "incongruent_accuracy": 0.95, "congruent_omission_rate": 0.0,
         "incongruent_omission_rate": 0.01, "Session-Level Exclusions": "Include"},
        {"congruent_rt": 999, "incongruent_rt": 999, "congruent_accuracy": 0.10,
         "incongruent_accuracy": 0.10, "congruent_omission_rate": 0.9,
         "incongruent_omission_rate": 0.9, "Session-Level Exclusions": "Exclude"},
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def test_compare_cli_end_to_end(tmp_path):
    out_dir = tmp_path / "output"
    _make_stroop_session(out_dir, "s1", cong_rt=500, incong_rt=580)
    _make_stroop_session(out_dir, "s2", cong_rt=520, incong_rt=610)
    human = _make_human_csv(tmp_path / "human.csv")
    reports = tmp_path / "reports"

    result = CliRunner().invoke(main, [
        "--label", "stroop_rdoc",
        "--human-csv", str(human),
        "--map", str(REPO / "data" / "human" / "comparison_maps" / "stroop_rdoc.json"),
        "--output-dir", str(out_dir),
        "--reports-dir", str(reports),
    ])
    assert result.exit_code == 0, result.output
    # Excluded human row must not be in the reference n.
    assert "(2 sessions after exclusions)" in result.output

    report_files = list(reports.glob("compare_stroop_rdoc_*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text())
    r = report["results"]["congruent_rt"]
    # bot mean (500+520)/2=510; human mean (575+525)/2=550, sd≈35.36
    assert abs(r["bot_mean"] - 510.0) < 1e-6
    assert abs(r["human_mean"] - 550.0) < 1e-6
    assert r["human_n"] == 2
    assert abs(r["z"] - (510.0 - 550.0) / r["human_sd"]) < 1e-9
    # Derived metric present and sensible: bot stroop effect (580+610)/2-(510)=85
    assert abs(report["results"]["stroop_effect"]["bot_mean"] - 85.0) < 1e-6


def test_compare_cli_metrics_subset_keeps_subtract_operands(tmp_path):
    out_dir = tmp_path / "output"
    _make_stroop_session(out_dir, "s1", cong_rt=500, incong_rt=580)
    human = _make_human_csv(tmp_path / "human.csv")

    result = CliRunner().invoke(main, [
        "--label", "stroop_rdoc",
        "--human-csv", str(human),
        "--map", str(REPO / "data" / "human" / "comparison_maps" / "stroop_rdoc.json"),
        "--metrics", "stroop_effect",
        "--output-dir", str(out_dir),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert result.exit_code == 0, result.output
    report = json.loads(next((tmp_path / "reports").glob("*.json")).read_text())
    # Only the requested metric is reported (operands computed internally).
    assert list(report["results"].keys()) == ["stroop_effect"]
    assert abs(report["results"]["stroop_effect"]["bot_mean"] - 80.0) < 1e-6

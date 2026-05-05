import json
from pathlib import Path
from click.testing import CliRunner
from experiment_bot.validation.cli import main as validate_main


def test_validate_cli_writes_report(tmp_path):
    runner = CliRunner()

    # Set up a minimal norms file
    norms_dir = tmp_path / "norms"
    norms_dir.mkdir()
    (norms_dir / "conflict.json").write_text(json.dumps({
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                  "tau_range": [50, 130], "citations": []},
        },
    }))

    # Set up a minimal session output dir
    sessions_dir = tmp_path / "output" / "stroop"
    sessions_dir.mkdir(parents=True)
    sess = sessions_dir / "2026-05-04_12-00-00"
    sess.mkdir()
    (sess / "bot_log.json").write_text(json.dumps([
        {"trial": i, "actual_rt_ms": 500, "condition": "congruent",
         "intended_error": False, "omission": False} for i in range(50)
    ]))

    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "stroop",
        "--norms-dir", str(norms_dir),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert result.exit_code == 0, result.output
    reports = list((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 1
    saved = json.loads(reports[0].read_text())
    assert saved["paradigm_class"] == "conflict"
    assert "overall_pass" in saved


def test_validate_cli_errors_on_missing_norms(tmp_path):
    runner = CliRunner()
    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "stroop",
        "--norms-dir", str(tmp_path / "nonexistent"),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert result.exit_code != 0
    assert "norms" in result.output.lower() or "extract-norms" in result.output


def test_validate_cli_errors_on_missing_sessions(tmp_path):
    runner = CliRunner()
    norms_dir = tmp_path / "norms"
    norms_dir.mkdir()
    (norms_dir / "conflict.json").write_text(json.dumps({
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {"rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                          "tau_range": [50, 130], "citations": []}},
    }))
    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "stroop_missing",
        "--norms-dir", str(norms_dir),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert result.exit_code != 0

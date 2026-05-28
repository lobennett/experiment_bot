import json
from pathlib import Path
from click.testing import CliRunner
import pytest
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
        "--allow-bot-log",  # 'stroop' has no registered adapter; opt-in bypass
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


def _make_norms_dir(tmp_path: Path) -> Path:
    """Helper: write a minimal conflict norms file."""
    norms_dir = tmp_path / "norms"
    norms_dir.mkdir(exist_ok=True)
    (norms_dir / "conflict.json").write_text(json.dumps({
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                  "tau_range": [50, 130], "citations": []},
        },
    }))
    return norms_dir


def _make_session_dir(tmp_path: Path, label: str) -> Path:
    """Helper: write a minimal session under output/{label}/."""
    sessions_dir = tmp_path / "output" / label
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sess = sessions_dir / "2026-05-04_12-00-00"
    sess.mkdir(exist_ok=True)
    (sess / "bot_log.json").write_text(json.dumps([
        {"trial": i, "actual_rt_ms": 500, "condition": "congruent",
         "intended_error": False, "omission": False} for i in range(50)
    ]))
    return sessions_dir


# ---------------------------------------------------------------------------
# Task 6: anti-circularity gate
# ---------------------------------------------------------------------------


def test_validate_cli_unregistered_label_no_flag_hard_fails(tmp_path):
    """Unregistered label without --allow-bot-log raises ClickException naming circularity."""
    runner = CliRunner()
    norms_dir = _make_norms_dir(tmp_path)
    _make_session_dir(tmp_path, "novel_paradigm")

    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "novel_paradigm",
        "--norms-dir", str(norms_dir),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    # Must hard-fail (non-zero exit code)
    assert result.exit_code != 0
    # Must name the circularity problem in the output
    output_lower = result.output.lower()
    assert any(kw in output_lower for kw in (
        "circularity", "bot grades", "homework", "platform_adapters", "allow-bot-log"
    ))


def test_validate_cli_unregistered_label_with_flag_proceeds(tmp_path):
    """Unregistered label WITH --allow-bot-log proceeds and stamps data_source."""
    runner = CliRunner()
    norms_dir = _make_norms_dir(tmp_path)
    _make_session_dir(tmp_path, "novel_paradigm")

    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "novel_paradigm",
        "--norms-dir", str(norms_dir),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
        "--allow-bot-log",
    ])
    assert result.exit_code == 0, result.output
    # Report JSON must exist and record the self-graded bypass
    reports = list((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 1
    saved = json.loads(reports[0].read_text())
    assert saved.get("data_source") == "bot_log_self_graded"


def test_validate_cli_registered_label_unaffected(tmp_path):
    """A registered label (expfactory_stroop) continues to work without --allow-bot-log."""
    runner = CliRunner()
    norms_dir = _make_norms_dir(tmp_path)
    # expfactory_stroop IS registered in PLATFORM_ADAPTERS
    sessions_dir = tmp_path / "output" / "expfactory_stroop"
    sessions_dir.mkdir(parents=True)
    sess = sessions_dir / "2026-05-04_12-00-00"
    sess.mkdir()
    # Platform data for the adapter
    (sess / "experiment_data.json").write_text(json.dumps([
        {"trial_id": "test_trial", "condition": "congruent", "rt": 500,
         "correct_trial": 1, "response": "f", "correct_response": "f"}
        for _ in range(50)
    ]))

    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "expfactory_stroop",
        "--norms-dir", str(norms_dir),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert result.exit_code == 0, result.output

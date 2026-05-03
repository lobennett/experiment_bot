import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from click.testing import CliRunner
from experiment_bot.cli import main


def _minimal_taskcard_payload():
    return {
        "schema_version": "2.0",
        "produced_by": {"model": "x", "prompt_sha256": "", "scraper_version": "1.0",
                        "source_sha256": "", "timestamp": "2026-04-23T12:00:00Z",
                        "taskcard_sha256": ""},
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {}, "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500.0, "sigma": 60.0, "tau": 80.0},
                "rationale": "",
            }
        },
        "temporal_effects": {}, "between_subject_jitter": {},
        "reasoning_chain": [], "pilot_validation": {},
    }


def test_cli_loads_taskcard_and_runs_executor(tmp_path):
    runner = CliRunner()

    fake_taskcard_path = tmp_path / "taskcards" / "stroop"
    fake_taskcard_path.mkdir(parents=True)
    (fake_taskcard_path / "abcd1234.json").write_text(
        json.dumps(_minimal_taskcard_payload())
    )

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()

    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor):
        result = runner.invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
        ])
    assert result.exit_code == 0, result.output
    fake_executor.run.assert_awaited_once_with("http://example.com/stroop")


def test_cli_errors_on_missing_taskcard(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, [
        "http://example.com/x",
        "--label", "nonexistent",
        "--taskcards-dir", str(tmp_path / "empty_taskcards"),
        "--headless",
    ])
    assert result.exit_code != 0
    assert "TaskCard" in result.output or "not found" in result.output.lower()


def test_cli_samples_session_params_at_start(tmp_path):
    """Session-level draw of mu/sigma/tau happens before executor runs."""
    runner = CliRunner()
    fake_taskcard_path = tmp_path / "taskcards" / "stroop"
    fake_taskcard_path.mkdir(parents=True)
    (fake_taskcard_path / "abcd1234.json").write_text(
        json.dumps(_minimal_taskcard_payload())
    )

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()

    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor), \
         patch("experiment_bot.cli.sample_session_params",
               return_value={"default": {"mu": 510.0, "sigma": 65.0, "tau": 85.0}}) as samp:
        result = runner.invoke(main, [
            "http://example.com/x",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
        ])
    assert result.exit_code == 0, result.output
    samp.assert_called_once()


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "experiment-bot" in result.output.lower() or "usage" in result.output.lower()


def test_cli_shows_url_argument():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "url" in result.output.lower()


def test_cli_shows_label_option():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--label" in result.output


def test_cli_missing_url():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0  # Should fail without URL

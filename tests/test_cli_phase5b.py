"""SP11 Phase 5b — CLI guard + flag tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from experiment_bot.cli import main


def _minimal_taskcard_payload(*, sp11_supported: bool | None = None,
                              sp11_unsupported_reason: str | None = None):
    payload = {
        "schema_version": "2.0",
        "produced_by": {
            "model": "x", "prompt_sha256": "", "scraper_version": "1.0",
            "source_sha256": "", "timestamp": "2026-04-23T12:00:00Z",
            "taskcard_sha256": "",
        },
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
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
    if sp11_supported is False:
        payload["task_specific"]["sp11_supported"] = False
        if sp11_unsupported_reason is not None:
            payload["task_specific"]["sp11_unsupported_reason"] = sp11_unsupported_reason
    return payload


def _stage_taskcard(tmp_path: Path, label: str, payload: dict) -> None:
    folder = tmp_path / "taskcards" / label
    folder.mkdir(parents=True)
    (folder / "abcd1234.json").write_text(json.dumps(payload))


def test_cli_refuses_unsupported_paradigm(tmp_path):
    """sp11_supported=False causes the CLI to refuse to run."""
    _stage_taskcard(
        tmp_path, "stroop",
        _minimal_taskcard_payload(
            sp11_supported=False,
            sp11_unsupported_reason="API drift on stage 4 (3 attempts).",
        ),
    )
    runner = CliRunner()
    fake_executor = MagicMock()
    fake_executor.run = AsyncMock()
    with patch("experiment_bot.cli.TaskExecutor", return_value=fake_executor):
        result = runner.invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
        ])
    assert result.exit_code != 0
    assert "sp11_supported=False" in result.output
    # Executor must not have been constructed/run
    fake_executor.run.assert_not_awaited()


def test_cli_runs_when_sp11_supported_is_true(tmp_path):
    """Default behavior (no sp11_supported field) lets the CLI proceed."""
    _stage_taskcard(tmp_path, "stroop", _minimal_taskcard_payload())
    runner = CliRunner()
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
    fake_executor.run.assert_awaited_once()


def test_cli_no_calibration_flag_sets_apply_to_false(tmp_path):
    """--no-calibration toggles calibration_apply_to_sampler=False
    on the TaskCard's runtime, before the executor is constructed."""
    _stage_taskcard(tmp_path, "stroop", _minimal_taskcard_payload())
    runner = CliRunner()

    captured = {"taskcard": None}

    def capture_init(tc, **kw):
        captured["taskcard"] = tc
        fake = MagicMock()
        fake.run = AsyncMock()
        return fake

    with patch("experiment_bot.cli.TaskExecutor", side_effect=capture_init):
        result = runner.invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
            "--no-calibration",
        ])
    assert result.exit_code == 0, result.output
    tc = captured["taskcard"]
    assert tc.runtime.calibration_apply_to_sampler is False
    # Pass still runs
    assert tc.runtime.calibration_run_pass is True


def test_cli_skip_calibration_pass_flag(tmp_path):
    """--skip-calibration-pass disables the pass entirely."""
    _stage_taskcard(tmp_path, "stroop", _minimal_taskcard_payload())
    runner = CliRunner()
    captured = {"taskcard": None}

    def capture_init(tc, **kw):
        captured["taskcard"] = tc
        fake = MagicMock()
        fake.run = AsyncMock()
        return fake

    with patch("experiment_bot.cli.TaskExecutor", side_effect=capture_init):
        result = runner.invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
            "--skip-calibration-pass",
        ])
    assert result.exit_code == 0, result.output
    tc = captured["taskcard"]
    assert tc.runtime.calibration_run_pass is False


def test_cli_default_calibration_settings_unchanged(tmp_path):
    """Without flags, calibration is on and applied (post-cal arm)."""
    _stage_taskcard(tmp_path, "stroop", _minimal_taskcard_payload())
    runner = CliRunner()
    captured = {"taskcard": None}

    def capture_init(tc, **kw):
        captured["taskcard"] = tc
        fake = MagicMock()
        fake.run = AsyncMock()
        return fake

    with patch("experiment_bot.cli.TaskExecutor", side_effect=capture_init):
        runner.invoke(main, [
            "http://example.com/stroop",
            "--label", "stroop",
            "--taskcards-dir", str(tmp_path / "taskcards"),
            "--headless",
        ])
    tc = captured["taskcard"]
    assert tc.runtime.calibration_run_pass is True
    assert tc.runtime.calibration_apply_to_sampler is True

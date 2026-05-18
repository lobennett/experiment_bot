"""SP10 Stage 6 pilot tests — driver-based thin smoke."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.reasoner.stage6_pilot import (
    MIN_TRIALS, PilotResult, _build_pilot_md, run_pilot,
)


def test_pilot_result_dataclass_shape():
    r = PilotResult(
        status="pass", n_trials=5,
        diagnostic_report_path=None, error=None,
        pilot_md="",
    )
    assert r.status == "pass"
    assert r.n_trials == 5


def test_build_pilot_md_renders_status_and_trials():
    r = PilotResult(
        status="pass", n_trials=12,
        diagnostic_report_path=None, error=None, pilot_md="",
    )
    md = _build_pilot_md({"task": {"name": "stroop"}, "recommended_driver": "JsPsychDriver"}, r)
    assert "stroop" in md
    assert "PASS" in md
    assert "12" in md
    assert "JsPsychDriver" in md


def test_build_pilot_md_includes_error_when_present():
    r = PilotResult(
        status="fail", n_trials=0,
        diagnostic_report_path="/tmp/driver_needed.md",
        error="DiagnosticDriver fired",
        pilot_md="",
    )
    md = _build_pilot_md({}, r)
    assert "FAIL" in md
    assert "DiagnosticDriver fired" in md


@pytest.mark.asyncio
async def test_run_pilot_returns_fail_on_executor_exception():
    """When TaskExecutor.run raises, run_pilot returns status='fail'."""
    fake_executor = MagicMock()
    fake_executor.run = AsyncMock(side_effect=RuntimeError("boom"))
    fake_executor._trial_count = 0
    fake_executor._writer = MagicMock()
    fake_executor._writer.run_dir = None
    # TaskExecutor is imported locally inside run_pilot (to avoid the
    # circular dep with core.executor); patch the source module so the
    # local import resolves to the fake.
    with patch("experiment_bot.core.executor.TaskExecutor",
               lambda *a, **kw: fake_executor):
        # Build a tiny taskcard-like object
        tc = MagicMock()
        tc.to_dict = MagicMock(return_value={
            "task": {"name": "x"}, "recommended_driver": "JsPsychDriver",
        })
        result = await run_pilot(tc, "http://example.com/x", max_runtime_s=5.0)
    assert result.status == "fail"
    assert "boom" in (result.error or "")
    assert "x" in result.pilot_md
    assert "FAIL" in result.pilot_md


@pytest.mark.asyncio
async def test_run_pilot_returns_fail_on_timeout():
    """When TaskExecutor.run takes too long, run_pilot returns status='fail'."""
    import asyncio

    async def slow_run(url):
        await asyncio.sleep(10)

    fake_executor = MagicMock()
    fake_executor.run = slow_run
    fake_executor._trial_count = 0
    fake_executor._writer = MagicMock()
    fake_executor._writer.run_dir = None
    with patch("experiment_bot.core.executor.TaskExecutor",
               lambda *a, **kw: fake_executor):
        tc = MagicMock()
        tc.to_dict = MagicMock(return_value={"task": {"name": "x"}})
        result = await run_pilot(tc, "http://example.com/x", max_runtime_s=0.05)
    assert result.status == "fail"
    assert "max_runtime_s" in (result.error or "")


@pytest.mark.asyncio
async def test_run_pilot_returns_pass_on_ok_status_with_min_trials(tmp_path):
    """When executor finishes ok and trials >= MIN_TRIALS, pilot passes."""
    import json
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_metadata.json").write_text(json.dumps({
        "status": "ok", "total_trials": 5,
    }))

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock(return_value=None)
    fake_executor._trial_count = MIN_TRIALS + 2
    fake_executor._writer = MagicMock()
    fake_executor._writer.run_dir = run_dir

    with patch("experiment_bot.core.executor.TaskExecutor",
               lambda *a, **kw: fake_executor):
        tc = MagicMock()
        tc.to_dict = MagicMock(return_value={
            "task": {"name": "stroop"}, "recommended_driver": "JsPsychDriver",
        })
        result = await run_pilot(tc, "http://example.com/x")
    assert result.status == "pass"
    assert result.n_trials == MIN_TRIALS + 2
    assert result.error is None
    assert "PASS" in result.pilot_md


@pytest.mark.asyncio
async def test_run_pilot_returns_fail_with_diagnostic_path_on_diagnostic_mode(tmp_path):
    """When run_metadata.status == 'diagnostic_mode', pilot reports
    diagnostic_report_path and fails."""
    import json
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    diag = str(run_dir / "driver_needed.md")
    (run_dir / "run_metadata.json").write_text(json.dumps({
        "status": "diagnostic_mode",
        "diagnostic_report_path": diag,
    }))

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock(return_value=None)
    fake_executor._trial_count = 0
    fake_executor._writer = MagicMock()
    fake_executor._writer.run_dir = run_dir

    with patch("experiment_bot.core.executor.TaskExecutor",
               lambda *a, **kw: fake_executor):
        tc = MagicMock()
        tc.to_dict = MagicMock(return_value={"task": {"name": "x"}})
        result = await run_pilot(tc, "http://example.com/x")
    assert result.status == "fail"
    assert result.diagnostic_report_path == diag
    assert result.error == "DiagnosticDriver fired"


@pytest.mark.asyncio
async def test_run_pilot_returns_fail_when_trials_below_min(tmp_path):
    """ok status but insufficient trials -> fail."""
    import json
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_metadata.json").write_text(json.dumps({"status": "ok"}))

    fake_executor = MagicMock()
    fake_executor.run = AsyncMock(return_value=None)
    fake_executor._trial_count = max(0, MIN_TRIALS - 1)
    fake_executor._writer = MagicMock()
    fake_executor._writer.run_dir = run_dir

    with patch("experiment_bot.core.executor.TaskExecutor",
               lambda *a, **kw: fake_executor):
        tc = MagicMock()
        tc.to_dict = MagicMock(return_value={"task": {"name": "x"}})
        result = await run_pilot(tc, "http://example.com/x")
    assert result.status == "fail"
    assert str(MIN_TRIALS) in (result.error or "")

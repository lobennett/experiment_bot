"""Narrated stdout test."""
from __future__ import annotations

from unittest.mock import MagicMock

from experiment_bot.core.executor import TaskExecutor


def test_narrated_stdout_has_five_stage_lines(capsys):
    """A clean session emits one stdout line per major stage.

    Expected stages, in order:
      1. navigate
      2. calibration
      3. trial_loop
      4. wait_completion
      5. save
    """
    # Bypass __init__ via __new__ so we don't need a real config
    ex = TaskExecutor.__new__(TaskExecutor)
    ex._narrate = TaskExecutor._narrate.__get__(ex, TaskExecutor)
    ex._narrate("navigate", "ok")
    ex._narrate("calibration", "model=fixed_offset n=30")
    ex._narrate("trial_loop", "trials=120")
    ex._narrate("wait_completion", "ok")
    ex._narrate("save", "written")
    out = capsys.readouterr().out
    lines = [l for l in out.split("\n") if l.startswith("[sp12]")]
    assert len(lines) == 5, f"expected 5 [sp12] lines, got {len(lines)}: {lines}"
    for i, stage in enumerate(["navigate", "calibration", "trial_loop",
                                "wait_completion", "save"]):
        assert stage in lines[i], f"line {i} missing stage {stage}: {lines[i]}"

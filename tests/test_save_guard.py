"""Save-path guard: a failure while persisting session outputs must leave a
visible `.incomplete` marker instead of a silently partial run directory
(audit finding: the save_metadata→finalize sequence in the executor's finally
block was unguarded, so a mid-save exception produced a plausible-looking but
partial session)."""
from unittest.mock import MagicMock

import pytest

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.output.writer import OutputWriter


def _bp_stub():
    """Minimal behavior-provider stub: TaskExecutor requires one at init;
    structural tests never execute trials through it."""
    from unittest.mock import MagicMock
    p = MagicMock()
    p.program_sha256 = "00" * 32
    p.program_path = "stub_program.py"
    p.seed = 0
    return p



MINIMAL_CONFIG = {
    "task": {"name": "Stroop", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "word",
            "description": "color word",
            "detection": {"method": "dom_query", "selector": ".word"},
            "response": {"key": "r", "condition": "congruent"},
        },
    ],
    "response_distributions": {
        "congruent": {"distribution": "ex_gaussian", "params": {"mu": 500, "sigma": 50, "tau": 80}},
    },
    "performance": {"accuracy": {"congruent": 0.95}},
    "navigation": {"phases": []},
    "task_specific": {},
    "runtime": {},
}


def _executor():
    return TaskExecutor(TaskConfig.from_dict(MINIMAL_CONFIG), behavior_provider=_bp_stub())


def _writer_with_run(tmp_path):
    writer = OutputWriter(base_dir=tmp_path)
    writer.create_run("stroop", TaskConfig.from_dict(MINIMAL_CONFIG))
    return writer


def test_writer_mark_incomplete_writes_marker(tmp_path):
    writer = _writer_with_run(tmp_path)
    writer.mark_incomplete("disk full while saving metadata")
    marker = writer.run_dir / ".incomplete"
    assert marker.exists()
    assert "disk full" in marker.read_text()


def test_save_outputs_failure_marks_incomplete_and_raises(tmp_path):
    """No in-flight exception: the save error itself must propagate."""
    ex = _executor()
    ex._writer = _writer_with_run(tmp_path)
    run_dir = ex._writer.run_dir
    ex._writer.save_metadata = MagicMock(side_effect=OSError("disk full"))

    with pytest.raises(OSError, match="disk full"):
        ex._save_outputs({"total_trials": 5})
    assert (run_dir / ".incomplete").exists()


def test_save_outputs_failure_does_not_mask_inflight_exception(tmp_path):
    """In-flight exception (the finally-block case): the ORIGINAL error
    propagates; the save failure is recorded via the marker, not raised."""
    ex = _executor()
    ex._writer = _writer_with_run(tmp_path)
    run_dir = ex._writer.run_dir
    ex._writer.save_metadata = MagicMock(side_effect=OSError("disk full"))

    with pytest.raises(ValueError, match="original task error"):
        try:
            raise ValueError("original task error")
        finally:
            ex._save_outputs({"total_trials": 5})
    assert (run_dir / ".incomplete").exists()


def test_save_outputs_success_writes_all_files_no_marker(tmp_path):
    ex = _executor()
    ex._writer = _writer_with_run(tmp_path)
    run_dir = ex._writer.run_dir

    ex._save_outputs({"total_trials": 5})
    assert (run_dir / "run_metadata.json").exists()
    assert (run_dir / "bot_log.json").exists()
    assert (run_dir / "run_trace.json").exists()
    assert not (run_dir / ".incomplete").exists()

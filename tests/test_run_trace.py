"""SP12 Phase 2 — run_trace.json writer test."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from experiment_bot.output.writer import OutputWriter


def test_run_trace_records_stage_entries(tmp_path):
    """run_trace.json contains one entry per recorded stage."""
    w = OutputWriter(base_dir=tmp_path)
    # Minimal config stub
    cfg = MagicMock()
    cfg.to_dict.return_value = {}
    cfg.task.name = "test"
    w.create_run("test", cfg)
    w.record_trace("navigate", {"loaded": "ok"}, duration_s=1.2)
    w.record_trace("calibration", {"model": "fixed_offset", "n": 30}, duration_s=6.5)
    w.finalize()
    trace_path = w._run_dir / "run_trace.json"
    assert trace_path.exists(), "run_trace.json not written"
    trace = json.loads(trace_path.read_text())
    assert len(trace["stages"]) == 2
    assert trace["stages"][0]["stage"] == "navigate"
    assert trace["stages"][0]["duration_s"] == 1.2
    assert trace["stages"][1]["stage"] == "calibration"
    assert trace["stages"][1]["data"]["model"] == "fixed_offset"

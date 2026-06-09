"""Human-reference comparison (experiment-bot-compare).

Ports the abstract's analysis — bot metrics z-positioned within the human
RDoC reference distribution — into the tested package. Audit finding: the
paper's Results methodology previously lived only in a stale notebook
(scripts/analysis.ipynb) with broken data paths.
"""
import csv
import json
import math
from pathlib import Path

import pytest

from experiment_bot.validation.human_reference import (
    load_human_reference,
    human_metric_values,
    bot_session_metrics,
    compare_metrics,
)


# ---------------------------------------------------------------------------
# Human CSV loading + exclusion filter
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def test_load_human_reference_applies_include_filter(tmp_path):
    p = _write_csv(tmp_path / "h.csv", [
        {"go_rt": "500", "Session-Level Exclusions": "Include", "Task-Level Exclusions": "Include"},
        {"go_rt": "900", "Session-Level Exclusions": "Exclude", "Task-Level Exclusions": "Include"},
        {"go_rt": "510", "Session-Level Exclusions": "Include", "Task-Level Exclusions": "Include"},
    ])
    rows = load_human_reference(p)
    assert len(rows) == 2
    assert all(r["go_rt"] in ("500", "510") for r in rows)


def test_load_human_reference_no_exclusion_columns_keeps_all(tmp_path):
    p = _write_csv(tmp_path / "h.csv", [{"go_rt": "500"}, {"go_rt": "600"}])
    assert len(load_human_reference(p)) == 2


def test_human_metric_values_column_and_subtract():
    rows = [
        {"go_rt": "500", "mean_SSD": "200"},
        {"go_rt": "600", "mean_SSD": "300"},
        {"go_rt": "", "mean_SSD": "100"},      # blank go_rt -> dropped for column metric
        {"go_rt": "nan", "mean_SSD": "100"},   # nan -> dropped
    ]
    vals = human_metric_values(rows, {"column": "go_rt"})
    assert vals == [500.0, 600.0]
    diffs = human_metric_values(rows, {"subtract": ["go_rt", "mean_SSD"]})
    assert diffs == [300.0, 300.0]


# ---------------------------------------------------------------------------
# Bot-side per-session metric kinds (generic; paradigm knowledge in the map)
# ---------------------------------------------------------------------------

GO = {"condition": "go", "rt": 500.0, "correct": True, "omission": False}
GO_ERR = {"condition": "go", "rt": 400.0, "correct": False, "omission": False}
GO_OMIT = {"condition": "go", "rt": None, "correct": False, "omission": True}
STOP_OK = {"condition": "stop", "rt": None, "correct": True, "omission": True, "ssd": 250.0}
STOP_FAIL = {"condition": "stop", "rt": 420.0, "correct": False, "omission": False, "ssd": 150.0}

MAP_SS = {
    "metrics": {
        "go_rt": {"bot": {"kind": "rt_mean", "condition": "go", "correct_only": True},
                  "human": {"column": "go_rt"}},
        "go_rt_all": {"bot": {"kind": "rt_mean", "condition": "go", "correct_only": False},
                      "human": {"column": "go_rt_all_responses"}},
        "go_accuracy": {"bot": {"kind": "accuracy", "condition": "go"},
                        "human": {"column": "go_accuracy"}},
        "go_omission_rate": {"bot": {"kind": "omission_rate", "condition": "go"},
                             "human": {"column": "go_omission_rate"}},
        "stop_accuracy": {"bot": {"kind": "omission_rate", "condition": "stop"},
                          "human": {"column": "stop_accuracy"}},
        "mean_ssd": {"bot": {"kind": "field_mean", "field": "ssd", "condition": "stop"},
                     "human": {"column": "mean_SSD"}},
        "ssrt_mean_method": {"bot": {"kind": "subtract", "a": "go_rt", "b": "mean_ssd"},
                             "human": {"subtract": ["go_rt", "mean_SSD"]}},
    }
}


def test_bot_session_metrics_kinds():
    trials = [GO, GO, GO_ERR, GO_OMIT, STOP_OK, STOP_FAIL]
    m = bot_session_metrics(trials, MAP_SS["metrics"])
    assert m["go_rt"] == 500.0                       # correct-only go mean
    assert m["go_rt_all"] == pytest.approx((500 + 500 + 400) / 3)
    assert m["go_accuracy"] == pytest.approx(2 / 3)  # among responded go trials
    assert m["go_omission_rate"] == pytest.approx(1 / 4)
    assert m["stop_accuracy"] == pytest.approx(1 / 2)  # inhibited / stop trials
    assert m["mean_ssd"] == pytest.approx(200.0)
    assert m["ssrt_mean_method"] == pytest.approx(500.0 - 200.0)


def test_bot_session_metrics_rt_window_drops_glitches():
    glitch = {"condition": "go", "rt": 1_000_000.0, "correct": True, "omission": False}
    m = bot_session_metrics([GO, glitch], {"go_rt": MAP_SS["metrics"]["go_rt"]})
    assert m["go_rt"] == 500.0


def test_bot_session_metrics_nan_when_no_trials():
    m = bot_session_metrics([GO], {"stop_accuracy": MAP_SS["metrics"]["stop_accuracy"]})
    assert math.isnan(m["stop_accuracy"])


# ---------------------------------------------------------------------------
# End-to-end comparison: z = (bot_mean - human_mean) / human_sd
# ---------------------------------------------------------------------------

def test_compare_metrics_z_math(tmp_path):
    # Two bot sessions with go_rt means 500 and 520 -> bot_mean 510.
    sessions = {"s1": [GO, STOP_OK], "s2": [dict(GO, rt=520.0), STOP_FAIL]}
    dirs = []
    for name in sessions:
        d = tmp_path / name
        d.mkdir()
        dirs.append(d)

    def loader(session_dir: Path) -> list[dict]:
        return sessions[session_dir.name]

    # Human distribution for go_rt: mean 600, sd 100 -> z = (510-600)/100 = -0.9
    human_rows = [{"go_rt": str(v)} for v in (500, 550, 600, 650, 700)]
    metrics_map = {"go_rt": MAP_SS["metrics"]["go_rt"]}

    out = compare_metrics(dirs, loader, human_rows, metrics_map)
    r = out["go_rt"]
    assert r["bot_n"] == 2
    assert r["bot_mean"] == pytest.approx(510.0)
    assert r["human_n"] == 5
    assert r["human_mean"] == pytest.approx(600.0)
    assert r["z"] == pytest.approx((510.0 - 600.0) / r["human_sd"])
    assert r["within_1sd"] == (abs(r["z"]) < 1.0)


def test_compare_metrics_skips_incomplete_marked_sessions(tmp_path):
    d1 = tmp_path / "s1"; d1.mkdir()
    d2 = tmp_path / "s2"; d2.mkdir()
    (d2 / ".incomplete").write_text("save failed")

    def loader(session_dir: Path) -> list[dict]:
        return [GO]

    out = compare_metrics([d1, d2], loader, [{"go_rt": "500"}],
                          {"go_rt": MAP_SS["metrics"]["go_rt"]})
    assert out["go_rt"]["bot_n"] == 1


# ---------------------------------------------------------------------------
# Committed comparison maps parse and reference only generic kinds
# ---------------------------------------------------------------------------

def test_committed_comparison_maps_are_valid():
    repo = Path(__file__).resolve().parents[1]
    maps_dir = repo / "data" / "human" / "comparison_maps"
    found = sorted(maps_dir.glob("*.json"))
    assert found, "no committed comparison maps"
    allowed = {"rt_mean", "accuracy", "omission_rate", "field_mean", "subtract"}
    for p in found:
        m = json.loads(p.read_text())
        assert m["metrics"], p.name
        for name, spec in m["metrics"].items():
            assert spec["bot"]["kind"] in allowed, f"{p.name}:{name}"
            assert ("column" in spec["human"]) or ("subtract" in spec["human"])

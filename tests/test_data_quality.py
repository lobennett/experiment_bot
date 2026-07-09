"""Unit tests for compute_stall_flags (A5b)."""
from __future__ import annotations

import json

from experiment_bot.output.data_quality import compute_stall_flags


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_csv_clean_no_stalls():
    data = "rt,condition,correct\n420,go,1\n610,go,1\n505,stop,0\n"
    result = compute_stall_flags(data, "csv", ceiling_ms=6000.0)
    assert result == {"stall_trials": 0, "max_rt_ms": 610.0, "ceiling_ms": 6000.0}


def test_csv_one_stall_trial():
    data = "rt,condition\n420,go\n15000,go\n505,go\n"
    result = compute_stall_flags(data, "csv", ceiling_ms=6000.0)
    assert result["stall_trials"] == 1
    assert result["max_rt_ms"] == 15000.0
    assert result["ceiling_ms"] == 6000.0


def test_csv_no_rt_column():
    data = "condition,correct\ngo,1\nstop,0\n"
    result = compute_stall_flags(data, "csv", ceiling_ms=6000.0)
    assert result["stall_trials"] is None
    assert "note" in result


def test_csv_renamed_rt_column_is_found():
    """A paradigm that names its column response_time_ms instead of rt."""
    data = "response_time_ms,condition\n300,go\n20000,go\n"
    result = compute_stall_flags(data, "csv", ceiling_ms=6000.0)
    assert result["stall_trials"] == 1
    assert result["max_rt_ms"] == 20000.0


def test_csv_null_and_non_numeric_rt_values_ignored():
    """Omission rows ('null'/empty rt) shouldn't crash or count as stalls."""
    data = "rt,condition\n420,go\nnull,go\n,go\n610,go\n"
    result = compute_stall_flags(data, "csv", ceiling_ms=6000.0)
    assert result["stall_trials"] == 0
    assert result["max_rt_ms"] == 610.0


def test_csv_empty_body_no_rows():
    data = "rt,condition\n"
    result = compute_stall_flags(data, "csv", ceiling_ms=6000.0)
    assert result["stall_trials"] is None
    assert "note" in result


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_clean_no_stalls():
    rows = [
        {"rt": 420, "condition": "go"},
        {"rt": 610, "condition": "go"},
    ]
    result = compute_stall_flags(json.dumps(rows), "json", ceiling_ms=6000.0)
    assert result == {"stall_trials": 0, "max_rt_ms": 610.0, "ceiling_ms": 6000.0}


def test_json_one_stall_trial():
    rows = [
        {"rt": 420, "condition": "go"},
        {"rt": 55000, "condition": "go"},
        {"rt": 505, "condition": "go"},
    ]
    result = compute_stall_flags(json.dumps(rows), "json", ceiling_ms=6000.0)
    assert result["stall_trials"] == 1
    assert result["max_rt_ms"] == 55000.0


def test_json_no_rt_column():
    rows = [{"condition": "go", "correct": 1}]
    result = compute_stall_flags(json.dumps(rows), "json", ceiling_ms=6000.0)
    assert result["stall_trials"] is None
    assert "note" in result


def test_json_wrapped_in_top_level_key():
    """Some exports wrap the trial array under a key (e.g. {'trials': [...]})."""
    payload = {"trials": [{"rt": 400, "condition": "go"}, {"rt": 12000, "condition": "go"}]}
    result = compute_stall_flags(json.dumps(payload), "json", ceiling_ms=6000.0)
    assert result["stall_trials"] == 1


def test_json_malformed_does_not_raise():
    result = compute_stall_flags("{not valid json", "json", ceiling_ms=6000.0)
    assert result["stall_trials"] is None
    assert "note" in result


def test_json_empty_list():
    result = compute_stall_flags("[]", "json", ceiling_ms=6000.0)
    assert result["stall_trials"] is None
    assert "note" in result


def test_format_defaults_to_csv_when_missing():
    data = "rt,condition\n420,go\n"
    result = compute_stall_flags(data, "", ceiling_ms=6000.0)
    assert result["stall_trials"] == 0

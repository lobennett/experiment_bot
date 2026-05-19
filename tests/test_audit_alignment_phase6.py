"""SP11 Phase 6 — audit-script parametrized tests.

Covers:
- Auto-detection of pairing method from bot_log delivery presence
- Per-paradigm test-row predicate dispatch
- Trial-counter pairing on synthetic SP11 input-layer logs
- RT-match pairing on synthetic SP10 driver legacy logs
- Type coercion for trial_index (CSV string vs JSON int)
- Per-channel breakdown for delivery.channel
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT = Path("scripts/audit_alignment.py")
spec = importlib.util.spec_from_file_location("audit_alignment", _SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


# -----------------------------------------------------------------
# Pairing-method auto-detect
# -----------------------------------------------------------------


def test_detect_pairing_returns_trial_counter_when_marker_present():
    bot = [
        {"condition": "congruent", "response_key": ",",
         "delivery": {"trial_marker_at_fire": 5, "channel": "cdp_dispatchKeyEvent"}},
    ]
    assert audit.detect_pairing_method(bot) == "trial_counter"


def test_detect_pairing_returns_rt_match_when_no_delivery():
    bot = [{"condition": "go", "response_key": "z", "actual_rt_ms": 425.3}]
    assert audit.detect_pairing_method(bot) == "rt_match"


def test_detect_pairing_returns_rt_match_when_marker_is_none():
    """A bot trial that has a delivery block but no marker_at_fire
    (e.g., skipped fire) shouldn't tip the auto-detect to trial_counter."""
    bot = [
        {"condition": "go", "response_key": "z", "actual_rt_ms": 400.0,
         "delivery": {"trial_marker_at_fire": None, "skipped": True,
                      "channel": "cdp_dispatchKeyEvent"}},
    ]
    assert audit.detect_pairing_method(bot) == "rt_match"


# -----------------------------------------------------------------
# Type coercion for trial_index
# -----------------------------------------------------------------


def test_normalize_marker_handles_int_string_none():
    assert audit._normalize_marker(5) == 5
    assert audit._normalize_marker("245") == 245
    assert audit._normalize_marker(None) is None
    assert audit._normalize_marker("") is None
    assert audit._normalize_marker("garbage") is None


def test_canonicalize_key_handles_arrow_variants():
    """jsPsych v7 fires ArrowLeft via CDP; jsPsych v6 records leftarrow.
    Both should canonicalize to 'left' so within-pair comparison works."""
    assert audit._canonicalize_key("ArrowLeft") == "left"
    assert audit._canonicalize_key("ArrowRight") == "right"
    assert audit._canonicalize_key("leftarrow") == "left"
    assert audit._canonicalize_key("rightarrow") == "right"
    assert audit._canonicalize_key("ArrowUp") == "up"
    assert audit._canonicalize_key("uparrow") == "up"


def test_canonicalize_key_lowercases_punctuation_and_space():
    assert audit._canonicalize_key(",") == ","
    assert audit._canonicalize_key("A") == "a"
    assert audit._canonicalize_key(" ") == "space"
    assert audit._canonicalize_key("Space") == "space"


def test_canonicalize_key_handles_none_and_empty():
    assert audit._canonicalize_key(None) is None
    assert audit._canonicalize_key("") is None


def test_keys_equivalent_cross_engine_variants():
    """The function should return True for v7-bot ↔ v6-platform pairs."""
    assert audit._keys_equivalent("ArrowLeft", "leftarrow") is True
    assert audit._keys_equivalent("ArrowRight", "rightarrow") is True
    assert audit._keys_equivalent("ArrowLeft", "ArrowLeft") is True
    assert audit._keys_equivalent("leftarrow", "leftarrow") is True
    # Mismatches return False
    assert audit._keys_equivalent("ArrowLeft", "rightarrow") is False
    # None or empty on either side: False (treat as missing, not equivalent)
    assert audit._keys_equivalent(None, "leftarrow") is False
    assert audit._keys_equivalent("ArrowLeft", None) is False


# -----------------------------------------------------------------
# Trial-counter pairing on synthetic data
# -----------------------------------------------------------------


def _bot_trial(trial_idx: int, key: str, marker: int,
               channel: str = "cdp_dispatchKeyEvent",
               skipped: bool = False) -> dict:
    return {
        "trial": trial_idx,
        "condition": "congruent",
        "response_key": key,
        "stimulus_id": "test_stim",
        "delivery": {
            "trial_marker_at_fire": None if skipped else marker,
            "channel": channel,
            "skipped": skipped,
            "skip_reason": "trial_advanced_during_dwell" if skipped else None,
        },
    }


def _plat_test_trial(idx, response, correct_response="."):
    """Note: idx is intentionally a string here to mimic CSV reads
    (the production code coerces via _normalize_marker)."""
    return {
        "trial_index": str(idx),
        "trial_id": "test_trial",
        "response": response,
        "correct_response": correct_response,
        "rt": "250.5",
        "condition": "congruent",
    }


def test_trial_counter_audit_all_match():
    """When bot markers map cleanly to platform trial_index, all
    paired and pressed_eq_recorded == paired."""
    bot = [
        _bot_trial(0, ",", 10),
        _bot_trial(1, ".", 11),
        _bot_trial(2, "/", 12),
    ]
    plat = [
        _plat_test_trial(10, ",", "."),  # bot pressed ',', platform recorded ','
        _plat_test_trial(11, ".", "."),
        _plat_test_trial(12, "/", "."),
    ]
    result = audit.trial_counter_audit(bot, plat)
    assert result["counts"]["paired"] == 3
    assert result["counts"]["pressed_eq_recorded"] == 3
    assert result["per_channel"]["cdp_dispatchKeyEvent"]["paired"] == 3


def test_trial_counter_audit_handles_skipped_fires():
    """Skipped fires count separately, not as 'plat_no_match'."""
    bot = [
        _bot_trial(0, ",", 10),
        _bot_trial(1, ".", 11, skipped=True),
    ]
    plat = [_plat_test_trial(10, ",", ".")]
    result = audit.trial_counter_audit(bot, plat)
    assert result["counts"]["bot_skipped"] == 1
    assert result["counts"]["paired"] == 1
    assert result["counts"].get("plat_no_match", 0) == 0


def test_trial_counter_audit_handles_mis_recording():
    """Bot fires ',', platform records '.' (SP7 layer-d). The pair
    counts as paired but NOT as pressed_eq_recorded."""
    bot = [_bot_trial(0, ",", 10)]
    plat = [_plat_test_trial(10, ".", ".")]  # platform recorded different key
    result = audit.trial_counter_audit(bot, plat)
    assert result["counts"]["paired"] == 1
    assert result["counts"].get("pressed_eq_recorded", 0) == 0


def test_trial_counter_audit_handles_no_platform_record():
    """Bot fires on marker=10 but platform has no trial_index=10."""
    bot = [_bot_trial(0, ",", 10)]
    plat = [_plat_test_trial(99, ".", ".")]
    result = audit.trial_counter_audit(bot, plat)
    assert result["counts"].get("plat_no_match", 0) == 1
    assert result["counts"].get("paired", 0) == 0


# -----------------------------------------------------------------
# Per-channel breakdown
# -----------------------------------------------------------------


def test_trial_counter_per_channel_breakdown_splits_by_channel():
    bot = [
        _bot_trial(0, ",", 10, channel="cdp_dispatchKeyEvent"),
        _bot_trial(1, ".", 11, channel="cdp_dispatchKeyEvent"),
        _bot_trial(2, "/", 12, channel="keyboard_press_fallback"),
    ]
    plat = [
        _plat_test_trial(10, ",", "."),
        _plat_test_trial(11, ".", "."),
        _plat_test_trial(12, "/", "."),
    ]
    result = audit.trial_counter_audit(bot, plat)
    pc = result["per_channel"]
    assert pc["cdp_dispatchKeyEvent"]["paired"] == 2
    assert pc["cdp_dispatchKeyEvent"]["pressed_eq_recorded"] == 2
    assert pc["keyboard_press_fallback"]["paired"] == 1
    assert pc["keyboard_press_fallback"]["pressed_eq_recorded"] == 1


# -----------------------------------------------------------------
# RT-match pairing on legacy SP10 logs (no delivery field)
# -----------------------------------------------------------------


def test_rt_match_audit_pairs_by_rt_proximity():
    """SP10 driver legacy: bot trials have actual_rt_ms but no
    delivery block."""
    bot = [
        {"trial": 0, "condition": "go", "response_key": "z", "actual_rt_ms": 420.3},
        {"trial": 1, "condition": "go", "response_key": "z", "actual_rt_ms": 510.7},
    ]
    plat = [
        {"trial_id": "test_trial", "rt": "420.3", "response": "z", "correct_response": "z"},
        {"trial_id": "test_trial", "rt": "510.7", "response": "z", "correct_response": "z"},
    ]
    result = audit.rt_match_audit(bot, plat)
    assert result["counts"]["matched"] == 2
    assert result["counts"]["pressed_eq_recorded"] == 2


def test_rt_match_audit_handles_plat_none_rt():
    """Platform rows with rt='None' or NaN are counted as plat_none,
    not matched."""
    bot = [{"response_key": "z", "actual_rt_ms": 420.0}]
    plat = [
        {"trial_id": "test_trial", "rt": "None", "response": None},
        {"trial_id": "test_trial", "rt": "420.0", "response": "z"},
    ]
    result = audit.rt_match_audit(bot, plat)
    assert result["counts"]["plat_none"] == 1
    assert result["counts"]["matched"] == 1


# -----------------------------------------------------------------
# Per-paradigm dispatch via test_row_predicate_for_label
# -----------------------------------------------------------------


@pytest.mark.parametrize("label", [
    "expfactory_stroop", "expfactory_stop_signal",
    "stopit_stop_signal", "cognitionrun_stroop",
    "expfactory_flanker", "expfactory_n_back",
])
def test_audit_session_dispatches_predicate_per_label(tmp_path, label):
    """For every label registered in TEST_ROW_PREDICATES, the audit
    script should accept it without 'no predicate' error."""
    # Minimal session: empty bot_log + empty experiment_data
    sd = tmp_path / "synthetic"
    sd.mkdir()
    (sd / "bot_log.json").write_text("[]")
    (sd / "experiment_data.json").write_text("[]")
    result = audit.audit_session(sd, label=label, pairing="auto")
    assert result["label"] == label
    # No data → no errors. Whichever pairing was auto-selected is fine.


def test_audit_session_errors_on_unknown_label(tmp_path):
    """An unregistered label should fail loudly per the
    drop-from-scope discipline ('no silent fall-through')."""
    sd = tmp_path / "synthetic"
    sd.mkdir()
    (sd / "bot_log.json").write_text("[]")
    (sd / "experiment_data.json").write_text("[]")
    with pytest.raises(SystemExit, match="No test-row predicate"):
        audit.audit_session(sd, label="nonexistent_paradigm", pairing="auto")


def test_audit_session_errors_on_unknown_pairing(tmp_path):
    sd = tmp_path / "synthetic"
    sd.mkdir()
    (sd / "bot_log.json").write_text("[]")
    (sd / "experiment_data.json").write_text("[]")
    with pytest.raises(SystemExit, match="Unknown pairing"):
        audit.audit_session(sd, label="expfactory_stroop", pairing="not_a_method")


# -----------------------------------------------------------------
# End-to-end on a synthetic SP11 session
# -----------------------------------------------------------------


def test_end_to_end_trial_counter_pairing_with_csv_platform(tmp_path):
    """Mimic the actual Phase 5a pilot data shape: bot_log.json + CSV
    platform export with string trial_index values. The type-coercion
    fix should let pairing succeed."""
    import csv
    sd = tmp_path / "session"
    sd.mkdir()
    bot = [
        _bot_trial(0, ",", 6),
        _bot_trial(1, ".", 10),
        _bot_trial(2, "/", 14),
    ]
    (sd / "bot_log.json").write_text(json.dumps(bot))
    rows = [
        {"trial_index": "6", "trial_id": "test_trial",
         "response": ",", "correct_response": ".", "rt": "250", "condition": "c"},
        {"trial_index": "10", "trial_id": "test_trial",
         "response": ".", "correct_response": ".", "rt": "300", "condition": "i"},
        {"trial_index": "14", "trial_id": "test_trial",
         "response": "/", "correct_response": "/", "rt": "275", "condition": "c"},
    ]
    with (sd / "experiment_data.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    result = audit.audit_session(sd, label="expfactory_stroop", pairing="auto")
    assert result["method"] == "trial_counter"
    assert result["counts"]["paired"] == 3
    assert result["counts"]["pressed_eq_recorded"] == 3

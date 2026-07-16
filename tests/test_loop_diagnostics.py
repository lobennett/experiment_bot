"""Unit tests for LoopDiagnostics (A3)."""
from __future__ import annotations

from experiment_bot.core.loop_diagnostics import LoopDiagnostics


def test_starts_at_zero():
    d = LoopDiagnostics()
    assert d.as_dict() == {
        "phase_counts": {},
        "response_window_open": 0,
        "response_window_closed": 0,
        "identify_hits": {},
        "identify_misses": 0,
        "advance_actions": 0,
        "feedback_handled": 0,
        "attention_checks_handled": 0,
        "in_trial_nav_reruns": 0,
    }


def test_record_phase_accumulates_by_name():
    d = LoopDiagnostics()
    d.record_phase("test")
    d.record_phase("test")
    d.record_phase("instructions")
    assert d.as_dict()["phase_counts"] == {"test": 2, "instructions": 1}


def test_record_window_open_and_closed():
    d = LoopDiagnostics()
    d.record_window_open()
    d.record_window_open()
    d.record_window_closed()
    assert d.response_window_open == 2
    assert d.response_window_closed == 1


def test_record_identify_hit_by_condition():
    d = LoopDiagnostics()
    d.record_identify("go")
    d.record_identify("go")
    d.record_identify("stop")
    assert d.as_dict()["identify_hits"] == {"go": 2, "stop": 1}
    assert d.identify_misses == 0


def test_record_identify_none_is_a_miss():
    d = LoopDiagnostics()
    d.record_identify(None)
    d.record_identify(None)
    d.record_identify("go")
    assert d.identify_misses == 2
    assert d.as_dict()["identify_hits"] == {"go": 1}


def test_record_advance_feedback_attention_nav_rerun():
    d = LoopDiagnostics()
    d.record_advance()
    d.record_advance()
    d.record_feedback()
    d.record_attention_check()
    d.record_nav_rerun()
    d.record_nav_rerun()
    d.record_nav_rerun()
    out = d.as_dict()
    assert out["advance_actions"] == 2
    assert out["feedback_handled"] == 1
    assert out["attention_checks_handled"] == 1
    assert out["in_trial_nav_reruns"] == 3


def test_as_dict_returns_independent_copies():
    """Mutating the dataclass after as_dict() must not mutate the returned dict
    (run_metadata is written once; a later mutation shouldn't retroactively
    change an already-captured snapshot)."""
    d = LoopDiagnostics()
    d.record_phase("test")
    snapshot = d.as_dict()
    d.record_phase("test")
    assert snapshot["phase_counts"] == {"test": 1}
    assert d.as_dict()["phase_counts"] == {"test": 2}

"""Mechanical simulation gate."""
from pathlib import Path

import pytest

from experiment_bot.behavior.simgate import ALLOWED_IMPORTS, run_gate, scan_imports

TOY = Path("tests/fixtures/toy_participant.py")
CONDS = ["go", "stop"]
KEYS = {"go": "z"}


def test_toy_program_passes_gate():
    report = run_gate(TOY, conditions=CONDS, key_map=KEYS, has_interrupt=True,
                      n_trials=200, interrupt_condition="stop")
    assert report.passed, report.failures
    assert report.stats["n_trials"] == 200
    assert report.to_dict()["passed"] is True


def test_import_scan_flags_disallowed(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\nimport numpy\n"
                   "def make_participant(seed):\n    return None\n")
    assert scan_imports(bad) == ["os"]
    assert "numpy" in ALLOWED_IMPORTS


def test_gate_fails_on_crash(tmp_path):
    bad = tmp_path / "crash.py"
    bad.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            raise ValueError('boom')\n"
        "    return P()\n")
    report = run_gate(bad, conditions=["go"], key_map=KEYS, has_interrupt=False,
                      n_trials=10)
    assert not report.passed
    assert any("boom" in f or "respond" in f for f in report.failures)


def test_gate_fails_on_nondeterminism(tmp_path):
    bad = tmp_path / "nondet.py"
    bad.write_text(
        "import random\n"
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.correct_key, 200.0 + random.random())\n"  # unseeded
        "    return P()\n")
    report = run_gate(bad, conditions=["go"], key_map=KEYS, has_interrupt=False,
                      n_trials=10)
    assert not report.passed
    assert any("determin" in f for f in report.failures)


def test_gate_fails_on_constructor_crash(tmp_path):
    bad = tmp_path / "ctor_crash.py"
    bad.write_text(
        "def make_participant(seed):\n"
        "    raise RuntimeError('ctor boom')\n")
    report = run_gate(bad, conditions=["go"], key_map=KEYS, has_interrupt=False,
                      n_trials=10)
    assert report.passed is False
    assert any("ctor boom" in f for f in report.failures)


def test_gate_interrupts_named_condition_not_last(tmp_path):
    """I2 regression: interrupt trials are the ones whose condition ==
    interrupt_condition, NOT conditions[-1]. 'b' here is the interrupt
    condition but 'c' (last) is not — a probe program raises if on_interrupt
    is ever invoked for the wrong condition, which would happen if the gate
    still gated on conditions[-1]."""
    prog = tmp_path / "probe.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.correct_key, 300.0 + seed)\n"
        "        def on_interrupt(self, ctx, ssd_ms, intended):\n"
        "            if ctx.condition != 'b':\n"
        "                raise AssertionError(f'on_interrupt fired for {ctx.condition!r}')\n"
        "            return None\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["a", "b", "c"],
                      key_map={"a": "f", "b": "j", "c": "k"},
                      has_interrupt=True, n_trials=30, interrupt_condition="b")
    assert report.passed, report.failures


def test_gate_fails_on_seed_clones(tmp_path):
    bad = tmp_path / "clone.py"
    bad.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.correct_key, 400.0)\n"  # identical across seeds
        "    return P()\n")
    report = run_gate(bad, conditions=["go"], key_map=KEYS, has_interrupt=False,
                      n_trials=10)
    assert not report.passed
    assert any("distinct" in f for f in report.failures)


# --- explicit condition streams ---

def _crash_on_condition_program(tmp_path, bad_condition: str) -> Path:
    prog = tmp_path / "cond_crash.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        f"            if ctx.condition == {bad_condition!r}:\n"
        "                raise ValueError('bad condition reached')\n"
        "            return (ctx.correct_key, 300.0 + seed)\n"
        "    return P()\n")
    return prog


def test_gate_replays_supplied_condition_stream(tmp_path):
    """When condition_stream is supplied, the gate replays THAT sequence
    (cycled to n_trials) instead of round-robin over `conditions`."""
    prog = _crash_on_condition_program(tmp_path, "b")
    # Round-robin over ["a", "b"] hits "b" on trial 1 -> fails.
    rr = run_gate(prog, conditions=["a", "b"], key_map={"a": "f", "b": "j"},
                  has_interrupt=False, n_trials=10)
    assert not rr.passed
    # Pilot-observed stream never contains "b" -> main traces pass.
    streamed = run_gate(prog, conditions=["a", "b"], key_map={"a": "f", "b": "j"},
                        has_interrupt=False, n_trials=10,
                        condition_stream=["a", "a", "a"])
    assert streamed.passed, streamed.failures
    assert streamed.stats["condition_stream_source"] == "supplied"
    assert rr.stats.get("condition_stream_source", "round_robin") == "round_robin"


def test_gate_condition_stream_cycles_to_n_trials(tmp_path):
    """A short observed stream is cycled to cover all n_trials."""
    prog = tmp_path / "count.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.correct_key, 300.0 + seed + ctx.trial_index * 0.001)\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["a", "b"], key_map={"a": "f", "b": "j"},
                      has_interrupt=False, n_trials=50, condition_stream=["a", "b", "a"])
    assert report.passed, report.failures
    assert report.stats["n_trials"] == 50


# --- protocol fuzz cases ---

def test_fuzz_first_trial_none_history_named_failure(tmp_path):
    """A program assuming prev_* history exists crashes on the fuzz first-trial
    case and fails the gate with a named fuzz failure."""
    from experiment_bot.behavior.simgate import GateReport, _fuzz_protocol, program_sha256
    prog = tmp_path / "needs_history.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            _ = ctx.prev_rt_ms + 1.0  # TypeError when prev_rt_ms is None\n"
        "            return (ctx.correct_key, 300.0 + seed)\n"
        "    return P()\n")
    report = GateReport(program_sha256=program_sha256(prog))
    _fuzz_protocol(prog, conditions=["go"], key_map={"go": "z"},
                   has_interrupt=False, report=report)
    assert not report.passed
    assert any(f.startswith("fuzz:first_trial") for f in report.failures), report.failures


def test_fuzz_unseen_condition_named_failure(tmp_path):
    """A program that hard-indexes a per-condition table crashes on an unseen
    condition label; the gate names the fuzz case."""
    prog = tmp_path / "cond_table.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        _table = {'go': 300.0}\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.correct_key, self._table[ctx.condition] + seed)\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["go"], key_map={"go": "z"},
                      has_interrupt=False, n_trials=10)
    assert not report.passed
    assert any(f.startswith("fuzz:unseen_condition") for f in report.failures), report.failures


def test_fuzz_empty_available_keys_named_failure(tmp_path):
    """A program indexing ctx.available_keys crashes when the inventory is
    empty (dynamic-key card before any key is observed)."""
    prog = tmp_path / "keys_index.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.available_keys[0], 300.0 + seed)\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["go"], key_map={"go": "z"},
                      has_interrupt=False, n_trials=10)
    assert not report.passed
    assert any(f.startswith("fuzz:empty_available_keys") for f in report.failures), report.failures


def test_fuzz_extreme_ssd_named_failure(tmp_path):
    """A program assuming a bounded SSD crashes at the extreme fuzz values
    (1.0 / 5000.0 ms); the gate names the fuzz case. Only interrupt tasks."""
    prog = tmp_path / "ssd_bound.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return (ctx.correct_key, 300.0 + seed)\n"
        "        def on_interrupt(self, ctx, ssd_ms, intended):\n"
        "            assert 50.0 <= ssd_ms <= 1000.0, 'ssd out of expected range'\n"
        "            return None\n"
        "    return P()\n")
    report = run_gate(prog, conditions=CONDS, key_map=KEYS, has_interrupt=True,
                      n_trials=20, interrupt_condition="stop")
    assert not report.passed
    assert any(f.startswith("fuzz:interrupt_extreme_ssd") for f in report.failures), report.failures


# --- click response modality ---

def _click_program(tmp_path, index_expr="0"):
    prog = tmp_path / "clicker.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            if ctx.response_elements:\n"
        f"                return ('click', {index_expr}, 300.0 + seed)\n"
        "            return (ctx.correct_key, 300.0 + seed)\n"
        "    return P()\n")
    return prog


def test_gate_passes_click_program_with_elements(tmp_path):
    prog = _click_program(tmp_path, index_expr="ctx.trial_index % len(ctx.response_elements)")
    report = run_gate(prog, conditions=["choice"], key_map={},
                      has_interrupt=False, n_trials=50,
                      response_elements={"choice": ["Left", "Right"]})
    assert report.passed, report.failures


def test_gate_fails_click_out_of_range_named_failure(tmp_path):
    prog = _click_program(tmp_path, index_expr="2")  # only 2 elements: 0..1
    report = run_gate(prog, conditions=["choice"], key_map={},
                      has_interrupt=False, n_trials=10,
                      response_elements={"choice": ["Left", "Right"]})
    assert not report.passed
    assert any("element_index" in f for f in report.failures), report.failures


def test_gate_fails_click_without_configured_elements(tmp_path):
    """A program clicking on a card that declares no response_elements is a
    protocol violation, reported as a named trial failure."""
    prog = tmp_path / "blind_clicker.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return ('click', 0, 300.0 + seed)\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["go"], key_map={"go": "z"},
                      has_interrupt=False, n_trials=10)
    assert not report.passed
    assert any("response_elements" in f for f in report.failures), report.failures


def test_gate_click_trace_distinct_across_seeds_and_deterministic(tmp_path):
    """Click traces participate in the determinism/distinctness checks."""
    prog = tmp_path / "same_click.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            return ('click', 0, 400.0)\n"  # identical across seeds
        "    return P()\n")
    report = run_gate(prog, conditions=["choice"], key_map={},
                      has_interrupt=False, n_trials=10,
                      response_elements={"choice": ["Left", "Right"]})
    assert not report.passed
    assert any("distinct" in f for f in report.failures), report.failures


def test_fuzz_passes_for_click_program_with_elements(tmp_path):
    """Fuzz cases present the same ctx shape as real trials: for a card with
    response_elements the fuzz contexts carry a plausible elements tuple, so
    a click program is not spuriously failed."""
    prog = _click_program(tmp_path)
    report = run_gate(prog, conditions=["choice"], key_map={},
                      has_interrupt=False, n_trials=20,
                      response_elements={"choice": ["Left", "Right"]})
    assert report.passed, report.failures
    assert not any(f.startswith("fuzz:") for f in report.failures)


# --- Sequence-response capability ---

def _sequence_program(tmp_path, body_line):
    prog = tmp_path / "seq.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            if ctx.correct_sequence is not None:\n"
        f"                {body_line}\n"
        "            return (ctx.correct_key, 300.0 + seed)\n"
        "    return P()\n")
    return prog


def test_gate_passes_valid_sequence_program(tmp_path):
    prog = _sequence_program(
        tmp_path,
        "return [('click', i, 250.0 + seed) for i in ctx.correct_sequence]")
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=50,
                      response_elements={"recall": ["A", "B", "C"]},
                      correct_sequence={"recall": [0, 1, 2]})
    assert report.passed, report.failures


def test_gate_synthesizes_sequence_when_only_flag_set(tmp_path):
    """A plausible correct_sequence is carried into ctx so a program that
    reproduces it passes; the gate never runs the card's JS."""
    prog = _sequence_program(
        tmp_path,
        "return [('click', i, 250.0 + seed) for i in ctx.correct_sequence]")
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=20,
                      response_elements={"recall": ["A", "B"]},
                      correct_sequence={"recall": [0, 1]})
    assert report.passed, report.failures


def test_gate_fails_empty_sequence_is_valid_withhold(tmp_path):
    """An empty sequence is a valid no-response — the gate must NOT fail it
    on the mechanical contract."""
    prog = _sequence_program(tmp_path, "return []")
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=20,
                      response_elements={"recall": ["A", "B"]},
                      correct_sequence={"recall": [0, 1]})
    # Empty sequence every trial is deterministic and identical across seeds
    # -> caught as "not distinct", proving the sequence trace participates in
    # the determinism/distinctness checks.
    assert not report.passed
    assert any("distinct" in f for f in report.failures), report.failures


def test_gate_fails_sequence_out_of_range_index(tmp_path):
    prog = _sequence_program(
        tmp_path, "return [('click', 5, 250.0 + seed)]")  # only 2 elements
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=10,
                      response_elements={"recall": ["A", "B"]},
                      correct_sequence={"recall": [0, 1]})
    assert not report.passed
    assert any("element_index" in f for f in report.failures), report.failures


def test_gate_fails_over_long_sequence(tmp_path):
    prog = _sequence_program(
        tmp_path,
        "return [('click', 0, 59000.0 + seed), ('click', 1, 2000.0)]")
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=10,
                      response_elements={"recall": ["A", "B"]},
                      correct_sequence={"recall": [0, 1]})
    assert not report.passed
    assert any("total" in f for f in report.failures), report.failures


def test_gate_fails_non_list_sequence_element(tmp_path):
    prog = _sequence_program(
        tmp_path, "return [('click', 0, 300.0), 'not-a-tuple']")
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=10,
                      response_elements={"recall": ["A", "B"]},
                      correct_sequence={"recall": [0, 1]})
    assert not report.passed
    assert any("action 1" in f for f in report.failures), report.failures


def test_fuzz_cases_pass_for_toy_program():
    """The reference toy program survives every fuzz case (gate still green)."""
    report = run_gate(TOY, conditions=CONDS, key_map=KEYS, has_interrupt=True,
                      n_trials=50, interrupt_condition="stop")
    assert report.passed, report.failures
    assert not any(f.startswith("fuzz:") for f in report.failures)


def test_gate_key_sequence_prev_correct_is_unknown(tmp_path):
    """SEQUENCE OUTCOME HONESTY (gate mirror): key-delivered reproductions
    are unscoreable, so the synthetic session must feed prev_correct=None —
    a program observing False on every trial would be seeing a fabricated
    outcome the live harness never measured."""
    prog = tmp_path / "key_seq.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            if ctx.trial_index > 0 and ctx.prev_correct is False:\n"
        "                raise RuntimeError('fabricated False outcome')\n"
        "            rt = 200.0 + seed + ctx.trial_index\n"
        "            return [('ArrowLeft', rt), (' ', rt)]\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["recall"], key_map={},
                      has_interrupt=False, n_trials=20,
                      response_elements={"recall": ["A", "B", "C"]},
                      correct_sequence={"recall": [0, 2]})
    assert report.passed, report.failures


def test_fuzz_program_crashing_on_feedback_text_fails_named(tmp_path):
    """A program that assumes ctx.feedback_text is always None crashes in
    the fuzz pass with a named failure — live sessions hand it real text."""
    prog = tmp_path / "feedback_fragile.py"
    prog.write_text(
        "def make_participant(seed):\n"
        "    class P:\n"
        "        def respond(self, ctx):\n"
        "            if ctx.feedback_text is not None:\n"
        "                raise RuntimeError('unexpected feedback text')\n"
        "            return ('z', 300.0 + seed)\n"
        "    return P()\n")
    report = run_gate(prog, conditions=["go"], key_map={"go": "z"},
                      has_interrupt=False, n_trials=10)
    assert not report.passed
    assert any("fuzz:feedback_text_present" in f for f in report.failures), \
        report.failures

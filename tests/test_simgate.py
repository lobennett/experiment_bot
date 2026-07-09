"""SP21 Task 4: mechanical simulation gate."""
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


# --- Wave A4a: explicit condition streams ---

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


# --- Wave A4b: protocol fuzz cases ---

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


def test_fuzz_cases_pass_for_toy_program():
    """The reference toy program survives every fuzz case (gate still green)."""
    report = run_gate(TOY, conditions=CONDS, key_map=KEYS, has_interrupt=True,
                      n_trials=50, interrupt_condition="stop")
    assert report.passed, report.failures
    assert not any(f.startswith("fuzz:") for f in report.failures)

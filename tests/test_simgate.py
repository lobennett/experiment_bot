"""SP21 Task 4: mechanical simulation gate."""
from pathlib import Path

import pytest

from experiment_bot.behavior.simgate import ALLOWED_IMPORTS, run_gate, scan_imports

TOY = Path("tests/fixtures/toy_participant.py")
CONDS = ["go", "stop"]
KEYS = {"go": "z"}


def test_toy_program_passes_gate():
    report = run_gate(TOY, conditions=CONDS, key_map=KEYS, has_interrupt=True,
                      n_trials=200)
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

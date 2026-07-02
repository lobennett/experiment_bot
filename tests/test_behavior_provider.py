"""SP21 Task 1: provider contract, program loading, session validation."""
import hashlib
from pathlib import Path

import pytest

from experiment_bot.behavior.provider import (
    BehaviorSession, ProtocolViolation, Response, TrialContext,
    load_program, program_sha256, resolve_program,
)

TOY = Path("tests/fixtures/toy_participant.py")
KEYS = ("f", "j")


def _session(seed=42):
    return BehaviorSession(load_program(TOY), seed=seed, available_keys=KEYS,
                           program_path=TOY)


def test_load_program_and_hash():
    mod = load_program(TOY)
    assert callable(mod.make_participant)
    assert program_sha256(TOY) == hashlib.sha256(TOY.read_bytes()).hexdigest()


def test_respond_returns_validated_response():
    s = _session()
    r = s.respond(condition="go", correct_key="f", trial_index=0)
    assert isinstance(r, Response)
    assert r.key in (None, "f", "j")
    assert r.rt_ms > 0


def test_deterministic_per_seed_and_distinct_across_seeds():
    a = [_session(1).respond("go", "f", i).rt_ms for i in range(5)]
    b = [_session(1).respond("go", "f", i).rt_ms for i in range(5)]
    c = [_session(2).respond("go", "f", i).rt_ms for i in range(5)]
    assert a == b
    assert a != c


def test_history_flows_into_context():
    s = _session()
    s.respond("go", "f", 0)
    s.record_outcome("go", correct=False, rt_ms=480.0, interrupted=False)
    ctx = s.build_context("go", "f", 1)
    assert ctx.prev_condition == "go"
    assert ctx.prev_correct is False
    assert ctx.prev_rt_ms == 480.0
    assert ctx.prev_interrupted is False


def test_on_interrupt_withhold_or_response():
    s = _session()
    s.respond("stop", "f", 0)
    out = s.on_interrupt(ssd_ms=250.0)
    assert out is None or (isinstance(out, Response) and out.rt_ms > 0)


def test_bad_key_raises_protocol_violation():
    class _Bad:
        def respond(self, ctx):
            return ("q", 400.0)  # not in available_keys
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _Bad())})
    s = BehaviorSession(mod, seed=1, available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="key"):
        s.respond("go", "f", 0)


def test_bad_rt_raises_protocol_violation():
    class _Bad:
        def respond(self, ctx):
            return ("f", float("nan"))
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _Bad())})
    s = BehaviorSession(mod, seed=1, available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="rt"):
        s.respond("go", "f", 0)


def test_on_interrupt_requires_prior_respond():
    s = _session()
    with pytest.raises(ProtocolViolation, match="respond"):
        s.on_interrupt(ssd_ms=100.0)


def test_resolve_program_by_hash_prefix(tmp_path):
    d = tmp_path / "stroop"
    d.mkdir()
    p = d / "prog.py"
    p.write_text(TOY.read_text())
    sha = program_sha256(p)
    p2 = d / f"{sha}.py"
    p.rename(p2)
    assert resolve_program(f"stroop/{sha[:8]}", root=tmp_path) == p2
    with pytest.raises(FileNotFoundError):
        resolve_program("stroop/ffffffff", root=tmp_path)

"""Provider contract, program loading, session validation."""
import hashlib
from pathlib import Path

import pytest

from experiment_bot.behavior.provider import (
    BehaviorSession, ClickResponse, ProtocolViolation, Response, TrialContext,
    load_program, program_sha256, resolve_program, stim_response_elements,
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


def test_unpressable_key_raises_protocol_violation():
    """A multi-char non-key string (prose / sentinel) is not pressable."""
    class _Bad:
        def respond(self, ctx):
            return ("dynamic", 400.0)  # not None, not a char, not a key name
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _Bad())})
    s = BehaviorSession(mod, seed=1, available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="key"):
        s.respond("go", "f", 0)


def test_unobserved_pressable_key_accepted():
    """spatial_task_switching regression: on a dynamic-key card only the
    trial's correct_key is observed at trial 1, but a 2-AFC program
    legitimately presses the OTHER choice as an error injection. A
    syntactically-pressable key (single char, or a known key name) must be
    accepted even when not yet in available_keys — the contract is 'return a
    pressable key', not 'return an already-observed key'."""
    class _Err:
        def respond(self, ctx):
            return (",", 400.0)  # single char, not observed, != correct_key
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _Err())})
    s = BehaviorSession(mod, seed=1, available_keys=(".",))
    r = s.respond("switch", ".", 0)
    assert r.key == ","
    # and a known multi-char key name is also pressable
    class _Arrow:
        def respond(self, ctx):
            return ("ArrowLeft", 400.0)
    s2 = BehaviorSession(type("M",(),{"make_participant":staticmethod(lambda s:_Arrow())}),
                         seed=1, available_keys=("ArrowRight",))
    assert s2.respond("c", "ArrowRight", 0).key == "ArrowLeft"


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


def test_observe_key_grows_available_keys():
    """Runtime-resolved literal keys (mirrors the executor's dynamic key
    resolution) join the static inventory exposed via ctx.available_keys."""
    s = _session()
    assert s.available_keys == KEYS
    s.observe_key("q")
    ctx = s.build_context("go", "q", 0)
    assert set(ctx.available_keys) == {"f", "j", "q"}
    # None / empty observations are no-ops.
    s.observe_key(None)
    s.observe_key("")
    assert set(s.available_keys) == {"f", "j", "q"}


def test_validate_accepts_correct_key_not_in_available_keys():
    """A program may press ctx.correct_key even before it has been observed
    (information parity with the executor's dynamic key resolution)."""
    class _PressCorrect:
        def respond(self, ctx):
            return (ctx.correct_key, 400.0)
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _PressCorrect())})
    s = BehaviorSession(mod, seed=1, available_keys=KEYS)
    r = s.respond("go", "q", 0)  # "q" not in KEYS but IS the correct_key
    assert r.key == "q"


def test_pressable_key_boundary():
    """The corrected contract: a key is accepted if pressable (single
    printable char OR a known key name) even when unobserved; non-pressable
    values (multi-char non-names, empty, control chars) still raise."""
    def press(val, avail=KEYS, correct="f"):
        mod = type("M", (), {"make_participant":
                             staticmethod(lambda seed: type("P", (), {
                                 "respond": lambda self, ctx: (val, 400.0)})())})
        return BehaviorSession(mod, seed=1, available_keys=avail).respond("go", correct, 0)
    # accepted: unobserved single char, and a known multi-char key name
    assert press("z").key == "z"
    assert press("Enter").key == "Enter"
    # rejected: multi-char non-key-name garbage and empty string
    for bad in ("zz", "press z", "withhold", ""):
        with pytest.raises(ProtocolViolation, match="key"):
            press(bad)


# --- stimulus_text in TrialContext ---

def test_context_stimulus_text_defaults_to_none():
    s = _session()
    ctx = s.build_context("go", "f", 0)
    assert ctx.stimulus_text is None


def test_respond_threads_stimulus_text_to_program():
    seen = {}

    class _Capture:
        def respond(self, ctx):
            seen["stimulus_text"] = ctx.stimulus_text
            return ("f", 400.0)
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _Capture())})
    s = BehaviorSession(mod, seed=1, available_keys=KEYS)
    s.respond("go", "f", 0, stimulus_text="RED")
    assert seen["stimulus_text"] == "RED"
    s.respond("go", "f", 1)
    assert seen["stimulus_text"] is None


def test_on_interrupt_sees_same_ctx_with_stimulus_text():
    seen = {}

    class _Stopper:
        def respond(self, ctx):
            return ("f", 400.0)

        def on_interrupt(self, ctx, ssd_ms, intended):
            seen["stimulus_text"] = ctx.stimulus_text
            return None
    mod = type("M", (), {"make_participant": staticmethod(lambda seed: _Stopper())})
    s = BehaviorSession(mod, seed=1, available_keys=KEYS)
    s.respond("stop", "f", 0, stimulus_text="cue-text")
    s.on_interrupt(ssd_ms=250.0)
    assert seen["stimulus_text"] == "cue-text"


# --- click response modality ---

def _program(respond_fn, on_interrupt_fn=None):
    attrs = {"respond": lambda self, ctx: respond_fn(ctx)}
    if on_interrupt_fn is not None:
        attrs["on_interrupt"] = lambda self, ctx, ssd_ms, intended: \
            on_interrupt_fn(ctx, ssd_ms, intended)
    cls = type("_P", (), attrs)
    return type("M", (), {"make_participant": staticmethod(lambda seed: cls())})

ELEMENTS = ("Left option", "Right option")


def test_context_response_elements_default_empty():
    s = _session()
    assert s.build_context("go", "f", 0).response_elements == ()


def test_click_tuple_validates_to_click_response():
    s = BehaviorSession(_program(lambda ctx: ("click", 1, 500.0)), seed=1,
                        available_keys=KEYS)
    r = s.respond("choice", None, 0, response_elements=ELEMENTS)
    assert isinstance(r, ClickResponse)
    assert r.element_index == 1
    assert r.rt_ms == 500.0


def test_click_rejected_when_no_response_elements():
    s = BehaviorSession(_program(lambda ctx: ("click", 0, 400.0)), seed=1,
                        available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="response_elements"):
        s.respond("go", "f", 0)  # keypress trial: no elements


@pytest.mark.parametrize("idx", [2, -1, 0.0, "0", True, None])
def test_click_bad_index_rejected(idx):
    s = BehaviorSession(_program(lambda ctx: ("click", idx, 400.0)), seed=1,
                        available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="element_index"):
        s.respond("choice", None, 0, response_elements=ELEMENTS)


def test_click_bad_rt_rejected():
    s = BehaviorSession(_program(lambda ctx: ("click", 0, float("inf"))), seed=1,
                        available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="rt"):
        s.respond("choice", None, 0, response_elements=ELEMENTS)


def test_key_tuple_still_valid_when_elements_present():
    """The 2-tuple keypress contract is untouched by response_elements."""
    s = BehaviorSession(_program(lambda ctx: ("f", 400.0)), seed=1,
                        available_keys=KEYS)
    r = s.respond("choice", "f", 0, response_elements=ELEMENTS)
    assert isinstance(r, Response) and r.key == "f"


def test_respond_threads_response_elements_to_program():
    seen = {}

    def _respond(ctx):
        seen["elements"] = ctx.response_elements
        return ("click", 0, 350.0)
    s = BehaviorSession(_program(_respond), seed=1, available_keys=KEYS)
    s.respond("choice", None, 0, response_elements=ELEMENTS)
    assert seen["elements"] == ELEMENTS


def test_on_interrupt_intended_carries_click_shape():
    seen = {}

    def _on_interrupt(ctx, ssd_ms, intended):
        seen["intended"] = intended
        return None
    s = BehaviorSession(_program(lambda ctx: ("click", 1, 600.0), _on_interrupt),
                        seed=1, available_keys=KEYS)
    s.respond("choice", None, 0, response_elements=ELEMENTS)
    assert s.on_interrupt(ssd_ms=200.0) is None
    assert seen["intended"] == ("click", 1, 600.0)


def test_on_interrupt_click_return_validated_against_last_elements():
    s = BehaviorSession(
        _program(lambda ctx: ("click", 0, 600.0),
                 lambda ctx, ssd, intended: ("click", 1, 700.0)),
        seed=1, available_keys=KEYS)
    s.respond("choice", None, 0, response_elements=ELEMENTS)
    d = s.on_interrupt(ssd_ms=200.0)
    assert isinstance(d, ClickResponse) and d.element_index == 1

    s2 = BehaviorSession(
        _program(lambda ctx: ("f", 600.0),
                 lambda ctx, ssd, intended: ("click", 0, 700.0)),
        seed=1, available_keys=KEYS)
    s2.respond("go", "f", 0)  # no elements this trial
    with pytest.raises(ProtocolViolation, match="response_elements"):
        s2.on_interrupt(ssd_ms=200.0)


def test_stim_response_elements_reads_dict_shape():
    stim = {"response": {"condition": "choice", "key": None,
                         "response_elements": [
                             {"label": "Left option", "selector": "#opt-left"},
                             {"label": "Right option", "selector": "#opt-right"},
                             {"selector": "#no-label-dropped"},
                         ]}}
    assert stim_response_elements(stim) == (
        ("Left option", "#opt-left"), ("Right option", "#opt-right"))


def test_stim_response_elements_reads_typed_shape():
    from experiment_bot.core.config import StimulusConfig
    stim = StimulusConfig.from_dict({
        "id": "choice", "description": "choice grid",
        "detection": {"method": "dom_query", "selector": ".grid"},
        "response": {"condition": "choice", "key": None,
                     "response_elements": [
                         {"label": "A", "selector": ".opt-a"}]},
    })
    assert stim_response_elements(stim) == (("A", ".opt-a"),)


def test_stim_response_elements_empty_when_absent():
    assert stim_response_elements({"response": {"condition": "go", "key": "f"}}) == ()
    assert stim_response_elements({}) == ()


# --- Sequence-response capability (2026-07-12 spec) ---

def test_context_correct_sequence_defaults_to_none():
    s = _session()
    assert s.build_context("recall", None, 0).correct_sequence is None


def test_respond_threads_correct_sequence_to_program():
    seen = {}

    def _respond(ctx):
        seen["correct_sequence"] = ctx.correct_sequence
        return ("click", 0, 350.0)
    s = BehaviorSession(_program(_respond), seed=1, available_keys=KEYS)
    s.respond("recall", None, 0, response_elements=ELEMENTS,
              correct_sequence=(1, 0))
    assert seen["correct_sequence"] == (1, 0)
    s.respond("recall", None, 1, response_elements=ELEMENTS)
    assert seen["correct_sequence"] is None


def test_list_of_clicks_returns_sequence_response():
    from experiment_bot.behavior.provider import SequenceResponse
    s = BehaviorSession(
        _program(lambda ctx: [("click", 1, 500.0), ("click", 0, 400.0)]),
        seed=1, available_keys=KEYS)
    r = s.respond("recall", None, 0, response_elements=ELEMENTS,
                  correct_sequence=(1, 0))
    assert isinstance(r, SequenceResponse)
    assert len(r.actions) == 2
    assert all(isinstance(a, ClickResponse) for a in r.actions)
    assert [a.element_index for a in r.actions] == [1, 0]
    assert [a.rt_ms for a in r.actions] == [500.0, 400.0]


def test_sequence_may_mix_keys_and_clicks():
    from experiment_bot.behavior.provider import SequenceResponse
    s = BehaviorSession(
        _program(lambda ctx: [("f", 300.0), ("click", 0, 450.0)]),
        seed=1, available_keys=KEYS)
    r = s.respond("recall", None, 0, response_elements=ELEMENTS)
    assert isinstance(r, SequenceResponse)
    assert isinstance(r.actions[0], Response) and r.actions[0].key == "f"
    assert isinstance(r.actions[1], ClickResponse)


def test_empty_list_is_no_response_sequence():
    from experiment_bot.behavior.provider import SequenceResponse
    s = BehaviorSession(_program(lambda ctx: []), seed=1, available_keys=KEYS)
    r = s.respond("recall", None, 0, response_elements=ELEMENTS)
    assert isinstance(r, SequenceResponse)
    assert r.actions == ()


def test_bare_single_action_is_not_a_sequence():
    """Backward compat: a bare tuple keeps the existing single-action path
    even on trials that carry a correct_sequence."""
    s = BehaviorSession(_program(lambda ctx: ("f", 400.0)), seed=1,
                        available_keys=KEYS)
    r = s.respond("recall", "f", 0, response_elements=ELEMENTS,
                  correct_sequence=(0, 1))
    assert isinstance(r, Response) and r.key == "f"
    s2 = BehaviorSession(_program(lambda ctx: ("click", 1, 500.0)), seed=1,
                         available_keys=KEYS)
    r2 = s2.respond("recall", None, 0, response_elements=ELEMENTS,
                    correct_sequence=(0,))
    assert isinstance(r2, ClickResponse) and r2.element_index == 1


def test_sequence_with_one_bad_action_raises():
    s = BehaviorSession(
        _program(lambda ctx: [("click", 0, 400.0), "not-a-tuple"]),
        seed=1, available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="action 1"):
        s.respond("recall", None, 0, response_elements=ELEMENTS)


def test_sequence_out_of_range_click_raises():
    s = BehaviorSession(
        _program(lambda ctx: [("click", 0, 400.0), ("click", 2, 400.0)]),
        seed=1, available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="element_index"):
        s.respond("recall", None, 0, response_elements=ELEMENTS)


def test_sequence_bad_rt_raises():
    s = BehaviorSession(
        _program(lambda ctx: [("click", 0, 400.0), ("click", 1, -1.0)]),
        seed=1, available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="rt"):
        s.respond("recall", None, 0, response_elements=ELEMENTS)


def test_sequence_cumulative_rt_over_cap_raises():
    """Over-long sequence: the per-action rt bound generalizes to the sum —
    a sequence may not declare more total time than one action's 60s cap."""
    actions = [("click", 0, 59_000.0), ("click", 1, 2_000.0)]
    s = BehaviorSession(_program(lambda ctx: list(actions)), seed=1,
                        available_keys=KEYS)
    with pytest.raises(ProtocolViolation, match="total"):
        s.respond("recall", None, 0, response_elements=ELEMENTS)


def test_validate_sequence_returns_validated_action_list():
    from experiment_bot.behavior.provider import _validate_sequence
    out = _validate_sequence([("f", 300.0), ("click", 1, 400.0)],
                             KEYS, "f", "respond(trial 0)",
                             response_elements=ELEMENTS)
    assert isinstance(out, list) and len(out) == 2
    assert isinstance(out[0], Response) and isinstance(out[1], ClickResponse)
    assert _validate_sequence([], KEYS, None, "respond(trial 0)",
                              response_elements=ELEMENTS) == []


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


def test_on_interrupt_after_sequence_is_protocol_violation():
    """An interrupt landing on a sequence trial is unsupported — the session
    must raise ProtocolViolation (named, gate-legible), not AttributeError
    from poking .key on a SequenceResponse."""
    class P:
        def respond(self, ctx):
            return [("ArrowLeft", 200.0), (" ", 150.0)]

        def on_interrupt(self, ctx, ssd_ms, intended):
            return None

    mod = type("M", (), {"make_participant": staticmethod(lambda s: P())})
    session = BehaviorSession(mod, seed=1, available_keys=("z",))
    session.respond("recall", None, 0,
                    response_elements=("A", "B"), correct_sequence=(0, 1))
    with pytest.raises(ProtocolViolation, match="sequence"):
        session.on_interrupt(ssd_ms=250.0)

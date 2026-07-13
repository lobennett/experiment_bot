"""SP21 mechanical simulation gate. Purely mechanical checks — it never
evaluates whether the behavior looks human (pre-registered rule)."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from experiment_bot.behavior.provider import (
    BehaviorSession, ClickResponse, ProtocolViolation, SequenceResponse,
    load_program, program_sha256,
)

ALLOWED_IMPORTS = frozenset({
    "math", "random", "itertools", "functools", "collections",
    "dataclasses", "statistics", "typing", "numpy",
})

# Synthetic per-trial key inventory for dynamic-key cards (empty key_map,
# e.g. "dynamic"/"dynamic_mapping" sentinel entries filtered out upstream by
# gen_cli.mechanical_facts). Two keys so the gate can still exercise "press a
# different key" behavior even when no static key_map exists.
DYNAMIC_KEY_FALLBACK = ("f", "j")

# Protocol-fuzz constants (Wave A4b). The label is deliberately synthetic —
# it must never collide with a real card's condition vocabulary.
_FUZZ_UNSEEN_CONDITION = "__gate_fuzz_unseen_condition__"
# Extreme interrupt latencies a live session can legitimately produce
# (near-instant detection; very late signal on a slow page).
_FUZZ_INTERRUPT_SSDS = (1.0, 5000.0)


@dataclass
class GateReport:
    program_sha256: str
    passed: bool = True
    failures: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.passed = False
        self.failures.append(msg)

    def to_dict(self) -> dict:
        return {"program_sha256": self.program_sha256, "passed": self.passed,
                "failures": self.failures, "stats": self.stats}


def scan_imports(program_path: Path) -> list[str]:
    tree = ast.parse(Path(program_path).read_text())
    bad = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            bad.add(node.module.split(".")[0])
    return sorted(bad - ALLOWED_IMPORTS)


def _trace(program_path: Path, seed: int, conditions: list[str],
           key_map: dict[str, str], has_interrupt: bool, n_trials: int,
           report: GateReport, interrupt_condition: str | None = None,
           condition_stream: list[str] | None = None,
           response_elements: dict[str, list[str]] | None = None,
           correct_sequence: dict[str, list[int]] | None = None) -> list[tuple]:
    """One synthetic session; returns [(key, rt), ...] — click responses
    trace as ("click", element_index, rt). Failures -> report.

    `response_elements` (Wave B1) maps condition -> clickable option labels
    from the structural card; trials of those conditions carry the labels
    in ctx.response_elements so click-returning programs are exercised. A
    click whose index is out of range (or on a trial with no elements) is a
    ProtocolViolation and fails the gate as a named trial failure.

    An interrupt trial is one whose condition == interrupt_condition (NOT
    conditions[-1] — a card's interrupt-detection condition need not be the
    last condition in the structural stimulus list). For interrupt trials,
    the synthetic correct_key passed to respond() is None, matching live
    execution where the withhold sentinel resolves to None (see
    core.executor._resolve_response_key). For non-interrupt trials on
    dynamic-key cards (empty key_map), the correct_key is synthesized
    deterministically from a fixed 2-key set rather than a static key_map
    lookup, since no static mapping exists.

    `condition_stream`, when supplied (e.g. the pilot-observed trial
    sequence), is replayed verbatim — cycled to n_trials — instead of the
    round-robin over `conditions`. The gate stays behavior-blind: the
    stream orders MECHANICAL facts, it carries no behavioral content.
    """
    filtered_keys = tuple(sorted({v for v in key_map.values() if v}))
    keys = filtered_keys or DYNAMIC_KEY_FALLBACK
    stream = condition_stream or conditions
    try:
        session = BehaviorSession(load_program(program_path), seed=seed,
                                  available_keys=keys, program_path=program_path)
    except Exception as e:  # noqa: BLE001 — the gate reports every failure mode
        report.fail(f"make_participant(seed={seed}): {type(e).__name__}: {e}")
        return []
    out = []
    for i in range(n_trials):
        cond = stream[i % len(stream)]
        elems = tuple((response_elements or {}).get(cond, ()))
        cseq = (correct_sequence or {}).get(cond)
        cseq = tuple(cseq) if cseq is not None else None
        is_interrupt_trial = has_interrupt and cond == interrupt_condition
        if is_interrupt_trial:
            correct = None
        elif cond in key_map:
            correct = key_map[cond]
        else:
            # Dynamic-key card: no static mapping for this condition — pick a
            # stable (not RNG-driven) key from the fixed fallback set.
            # (A supplied stream may in principle carry a label absent from
            # `conditions`; index 0 keeps the choice deterministic.)
            cond_idx = conditions.index(cond) if cond in conditions else 0
            correct = keys[cond_idx % len(keys)]
        try:
            r = session.respond(cond, correct, i, response_elements=elems,
                                 correct_sequence=cseq)
            interrupted = False
            if is_interrupt_trial:
                # Deterministic synthetic SSD schedule: 100..400ms cycle.
                d = session.on_interrupt(ssd_ms=100.0 + (i % 4) * 100.0)
                if d is not None:
                    r = d
                interrupted = True
            if isinstance(r, SequenceResponse):
                # A reproduction trace: the ordered action tuples plus total
                # rt participate in the determinism/distinctness checks.
                actions = tuple(
                    ("click", a.element_index, round(a.rt_ms, 6))
                    if isinstance(a, ClickResponse)
                    else (a.key, round(a.rt_ms, 6))
                    for a in r.actions)
                produced = tuple(a.element_index for a in r.actions
                                 if isinstance(a, ClickResponse))
                total_rt = sum(a.rt_ms for a in r.actions)
                session.record_outcome(
                    cond, correct=(cseq is not None and produced == cseq),
                    rt_ms=(total_rt if r.actions else None),
                    interrupted=interrupted)
                out.append(("sequence", actions))
            elif isinstance(r, ClickResponse):
                resolved = elems[r.element_index]
                session.record_outcome(cond, correct=(resolved == correct),
                                       rt_ms=r.rt_ms, interrupted=interrupted)
                out.append(("click", r.element_index, round(r.rt_ms, 6)))
            else:
                session.record_outcome(cond, correct=(r.key == correct),
                                       rt_ms=r.rt_ms, interrupted=interrupted)
                out.append((r.key, round(r.rt_ms, 6)))
        except Exception as e:  # noqa: BLE001 — the gate reports every failure mode
            report.fail(f"trial {i} ({cond}): {type(e).__name__}: {e}")
            return out
    return out


def _fuzz_protocol(program_path: Path, conditions: list[str],
                   key_map: dict[str, str], has_interrupt: bool,
                   report: GateReport, interrupt_condition: str | None = None,
                   seed: int = 3,
                   response_elements: dict[str, list[str]] | None = None,
                   correct_sequence: dict[str, list[int]] | None = None) -> None:
    """Protocol fuzz cases (Wave A4b) — still purely mechanical.

    A live session can present contexts the round-robin trace never does:
    the very first trial (all prev_* None), a condition label the card
    didn't list, an empty key inventory (dynamic-key card before any key
    is observed), and interrupt signals at extreme latencies. A program
    crashing on any of these fails the gate with a named `fuzz:<case>`
    failure. No behavioral judgment — only "does not crash / stays within
    the protocol contract".

    Fuzz contexts carry the same response_elements shape real trials do
    (Wave B1): each known condition gets its configured labels, and the
    unseen-condition case gets the first condition's labels as a plausible
    stand-in. On cards with no response_elements every fuzz ctx has an
    empty tuple, so a program that clicks anyway is rejected by the
    boundary validator and fails the gate with a named fuzz failure.
    """
    if not conditions:
        return
    filtered_keys = tuple(sorted({v for v in key_map.values() if v}))
    keys = filtered_keys or DYNAMIC_KEY_FALLBACK

    def _fresh(available_keys: tuple[str, ...]):
        return BehaviorSession(load_program(program_path), seed=seed,
                               available_keys=available_keys,
                               program_path=program_path)

    def _correct_for(cond: str) -> str | None:
        if has_interrupt and cond == interrupt_condition:
            return None
        return key_map.get(cond, keys[0])

    def _elems_for(cond: str) -> tuple[str, ...]:
        return tuple((response_elements or {}).get(cond, ()))

    def _cseq_for(cond: str) -> tuple[int, ...] | None:
        seq = (correct_sequence or {}).get(cond)
        return tuple(seq) if seq is not None else None

    cases: list[tuple[str, object]] = []

    def _first_trial(s):
        cond = conditions[0]
        s.respond(cond, _correct_for(cond), 0, response_elements=_elems_for(cond),
                  correct_sequence=_cseq_for(cond))
    cases.append(("first_trial", _first_trial))

    def _unseen_condition(s):
        s.respond(_FUZZ_UNSEEN_CONDITION, keys[0], 0,
                  response_elements=_elems_for(conditions[0]),
                  correct_sequence=_cseq_for(conditions[0]))
    cases.append(("unseen_condition", _unseen_condition))

    def _empty_available_keys(s):
        cond = conditions[0]
        s.respond(cond, _correct_for(cond), 0, response_elements=_elems_for(cond),
                  correct_sequence=_cseq_for(cond))
    cases.append(("empty_available_keys", _empty_available_keys))

    if has_interrupt and interrupt_condition is not None:
        def _extreme_ssd(s):
            for i, ssd in enumerate(_FUZZ_INTERRUPT_SSDS):
                r = s.respond(interrupt_condition, None, i,
                              response_elements=_elems_for(interrupt_condition))
                d = s.on_interrupt(ssd_ms=ssd)
                if d is not None:
                    r = d
                withheld = not isinstance(r, ClickResponse) and r.key is None
                s.record_outcome(interrupt_condition, correct=withheld,
                                 rt_ms=r.rt_ms, interrupted=True)
        cases.append(("interrupt_extreme_ssd", _extreme_ssd))

    for name, fn in cases:
        try:
            session = _fresh(() if name == "empty_available_keys" else keys)
            fn(session)
        except Exception as e:  # noqa: BLE001 — every crash is a named gate failure
            report.fail(f"fuzz:{name}: {type(e).__name__}: {e}")


def run_gate(program_path: Path, conditions: list[str], key_map: dict[str, str],
             has_interrupt: bool, n_trials: int = 1000,
             seeds: tuple[int, ...] = (1, 2),
             interrupt_condition: str | None = None,
             condition_stream: list[str] | None = None,
             response_elements: dict[str, list[str]] | None = None,
             correct_sequence: dict[str, list[int]] | None = None) -> GateReport:
    report = GateReport(program_sha256=program_sha256(program_path))
    bad_imports = scan_imports(program_path)
    if bad_imports:
        report.fail(f"disallowed imports: {bad_imports}")
        return report
    t1 = _trace(program_path, seeds[0], conditions, key_map, has_interrupt,
                n_trials, report, interrupt_condition=interrupt_condition,
                condition_stream=condition_stream,
                response_elements=response_elements,
                correct_sequence=correct_sequence)
    if not report.passed:
        return report
    t1_again = _trace(program_path, seeds[0], conditions, key_map, has_interrupt,
                      n_trials, report, interrupt_condition=interrupt_condition,
                      condition_stream=condition_stream,
                      response_elements=response_elements,
                      correct_sequence=correct_sequence)
    if t1 != t1_again:
        report.fail("non-deterministic: same seed produced different traces")
    t2 = _trace(program_path, seeds[1], conditions, key_map, has_interrupt,
                n_trials, report, interrupt_condition=interrupt_condition,
                condition_stream=condition_stream,
                response_elements=response_elements,
                correct_sequence=correct_sequence)
    if report.passed and t1 == t2:
        report.fail("seeds not distinct: different seeds produced identical traces")
    if report.passed:
        _fuzz_protocol(program_path, conditions, key_map, has_interrupt,
                       report, interrupt_condition=interrupt_condition,
                       response_elements=response_elements,
                       correct_sequence=correct_sequence)
    report.stats = {"n_trials": len(t1), "seeds": list(seeds),
                    "n_conditions": len(conditions),
                    "condition_stream_source": (
                        "supplied" if condition_stream else "round_robin"),
                    }
    return report

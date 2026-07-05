"""SP21 mechanical simulation gate. Purely mechanical checks — it never
evaluates whether the behavior looks human (pre-registered rule)."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from experiment_bot.behavior.provider import (
    BehaviorSession, ProtocolViolation, load_program, program_sha256,
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
           report: GateReport, interrupt_condition: str | None = None) -> list[tuple]:
    """One synthetic session; returns [(key, rt), ...]. Failures -> report.

    An interrupt trial is one whose condition == interrupt_condition (NOT
    conditions[-1] — a card's interrupt-detection condition need not be the
    last condition in the structural stimulus list). For interrupt trials,
    the synthetic correct_key passed to respond() is None, matching live
    execution where the withhold sentinel resolves to None (see
    core.executor._resolve_response_key). For non-interrupt trials on
    dynamic-key cards (empty key_map), the correct_key is synthesized
    deterministically from a fixed 2-key set rather than a static key_map
    lookup, since no static mapping exists.
    """
    filtered_keys = tuple(sorted({v for v in key_map.values() if v}))
    keys = filtered_keys or DYNAMIC_KEY_FALLBACK
    try:
        session = BehaviorSession(load_program(program_path), seed=seed,
                                  available_keys=keys, program_path=program_path)
    except Exception as e:  # noqa: BLE001 — the gate reports every failure mode
        report.fail(f"make_participant(seed={seed}): {type(e).__name__}: {e}")
        return []
    out = []
    for i in range(n_trials):
        cond = conditions[i % len(conditions)]
        is_interrupt_trial = has_interrupt and cond == interrupt_condition
        if is_interrupt_trial:
            correct = None
        elif cond in key_map:
            correct = key_map[cond]
        else:
            # Dynamic-key card: no static mapping for this condition — pick a
            # stable (not RNG-driven) key from the fixed fallback set.
            correct = keys[conditions.index(cond) % len(keys)]
        try:
            r = session.respond(cond, correct, i)
            interrupted = False
            if is_interrupt_trial:
                # Deterministic synthetic SSD schedule: 100..400ms cycle.
                d = session.on_interrupt(ssd_ms=100.0 + (i % 4) * 100.0)
                if d is not None:
                    r = d
                interrupted = True
            session.record_outcome(cond, correct=(r.key == correct),
                                   rt_ms=r.rt_ms, interrupted=interrupted)
            out.append((r.key, round(r.rt_ms, 6)))
        except Exception as e:  # noqa: BLE001 — the gate reports every failure mode
            report.fail(f"trial {i} ({cond}): {type(e).__name__}: {e}")
            return out
    return out


def run_gate(program_path: Path, conditions: list[str], key_map: dict[str, str],
             has_interrupt: bool, n_trials: int = 1000,
             seeds: tuple[int, ...] = (1, 2),
             interrupt_condition: str | None = None) -> GateReport:
    report = GateReport(program_sha256=program_sha256(program_path))
    bad_imports = scan_imports(program_path)
    if bad_imports:
        report.fail(f"disallowed imports: {bad_imports}")
        return report
    t1 = _trace(program_path, seeds[0], conditions, key_map, has_interrupt,
                n_trials, report, interrupt_condition=interrupt_condition)
    if not report.passed:
        return report
    t1_again = _trace(program_path, seeds[0], conditions, key_map, has_interrupt,
                      n_trials, report, interrupt_condition=interrupt_condition)
    if t1 != t1_again:
        report.fail("non-deterministic: same seed produced different traces")
    t2 = _trace(program_path, seeds[1], conditions, key_map, has_interrupt,
                n_trials, report, interrupt_condition=interrupt_condition)
    if report.passed and t1 == t2:
        report.fail("seeds not distinct: different seeds produced identical traces")
    report.stats = {"n_trials": len(t1), "seeds": list(seeds),
                    "n_conditions": len(conditions)}
    return report

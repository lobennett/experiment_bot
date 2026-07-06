"""SP21 naive-builder behavior provider.

A *program* is a Python file exposing ``make_participant(seed) ->
participant`` where ``participant.respond(ctx)`` returns a plain
``(key_or_None, rt_ms)`` tuple and (for interrupt-capable tasks)
``participant.on_interrupt(ctx, ssd_ms, intended)`` returns ``None``
(withhold) or a tuple. Programs are stdlib+numpy only and cannot import
this package — hence the tuple wire format. ``BehaviorSession`` wraps a
program: it builds TrialContext (with previous-trial history), validates
every return value at the boundary (no silent coercion), and normalizes
tuples into ``Response``.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
from dataclasses import dataclass
from pathlib import Path


# Sentinel key_map/response-key values that are not literal, presseable keys:
# withhold instructions (mirrors core.executor.TaskExecutor._WITHHOLD_SENTINELS)
# plus the "dynamic"/"dynamic_mapping" values the executor treats as "resolve
# this key per-trial via JS, not from the static map" (core/executor.py
# _resolve_response_key ~L418/462). Shared by cli.py and behavior/gen_cli.py
# so both helpers that build a *static* key inventory exclude the same
# non-literal values the executor itself never presses. Comparisons are
# case-insensitive (`.lower()`) at the call site.
NON_LITERAL_KEY_SENTINELS = frozenset({
    "", "none", "null",
    "withhold", "no_response", "noresponse",
    "no_key", "nokey", "suppress", "skip", "pass",
    "dynamic", "dynamic_mapping",
})


def stim_condition_and_key(stim) -> tuple[str | None, str | None]:
    """(response.condition, response.key) of a stimulus, tolerant of both
    TaskCard shapes: raw dicts (tests, stage partials) and the typed
    StimulusConfig/ResponseConfig objects the loaders return. The loaders'
    typed shape is what production sees — a dict-only reader silently
    extracts nothing from every real committed card (final-review N1)."""
    resp = stim.get("response") if isinstance(stim, dict) else getattr(stim, "response", None)
    if resp is None:
        return None, None
    if isinstance(resp, dict):
        return resp.get("condition"), resp.get("key")
    return getattr(resp, "condition", None), getattr(resp, "key", None)


class ProtocolViolation(Exception):
    """A generated program returned something outside the contract."""


@dataclass(frozen=True)
class Response:
    key: str | None
    rt_ms: float


@dataclass(frozen=True)
class TrialContext:
    condition: str
    correct_key: str | None
    available_keys: tuple[str, ...]
    trial_index: int
    prev_condition: str | None = None
    prev_correct: bool | None = None
    prev_rt_ms: float | None = None
    prev_interrupted: bool | None = None


def program_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_program(path: Path):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"naive_program_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "make_participant", None)):
        raise ProtocolViolation(f"{path}: program must define make_participant(seed)")
    return mod


def resolve_program(spec_str: str, root: Path = Path("naive_programs")) -> Path:
    """Resolve a program spec: a direct file path, or '<label>/<hash-prefix>'."""
    direct = Path(spec_str)
    if direct.is_file():
        return direct
    if "/" in spec_str:
        label, prefix = spec_str.split("/", 1)
        matches = sorted((Path(root) / label).glob(f"{prefix}*.py"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise FileNotFoundError(f"ambiguous program prefix {spec_str!r}: {matches}")
    raise FileNotFoundError(f"no naive program matches {spec_str!r}")


def _validate(raw, available_keys: tuple[str, ...], correct_key: str | None,
              where: str) -> Response:
    """A returned key is valid if it is None, equals the trial's correct_key,
    or is in available_keys. The correct_key carve-out gives the naive
    program information parity with the expert executor: on tasks where the
    key inventory is discovered trial-by-trial (dynamic key resolution), the
    executor learns a key only once `response_key_js` resolves it — see
    `core.executor.TaskExecutor._seen_response_keys` — but it always knows
    THIS trial's correct key up front. A program that presses ctx.correct_key
    must never be rejected merely because that key hasn't been observed yet.
    """
    if not (isinstance(raw, tuple) and len(raw) == 2):
        raise ProtocolViolation(f"{where}: expected (key, rt_ms) tuple, got {raw!r}")
    key, rt = raw
    if key is not None and key != correct_key and key not in available_keys:
        raise ProtocolViolation(
            f"{where}: key {key!r} not in available_keys {available_keys} "
            f"(correct_key={correct_key!r})")
    if not isinstance(rt, (int, float)) or not math.isfinite(rt) or rt <= 0 or rt > 60_000:
        raise ProtocolViolation(f"{where}: rt_ms {rt!r} not a finite value in (0, 60000]")
    return Response(key=key, rt_ms=float(rt))


class BehaviorSession:
    """One participant (= one seed) executing one program."""

    def __init__(self, program_module, seed: int, available_keys: tuple[str, ...],
                 program_path: Path | None = None):
        self.seed = seed
        self._static_keys = tuple(sorted(set(available_keys)))
        self._observed_keys: set[str] = set()
        self.program_sha256 = program_sha256(program_path) if program_path else None
        self.program_path = str(program_path) if program_path else None
        self._participant = program_module.make_participant(seed)
        self._prev: dict = {}
        self._last_ctx: TrialContext | None = None
        self._last_response: Response | None = None

    @property
    def available_keys(self) -> tuple[str, ...]:
        """Static key inventory unioned with every literal key resolved so
        far at runtime (see observe_key)."""
        return tuple(sorted(set(self._static_keys) | self._observed_keys))

    def observe_key(self, key: str | None) -> None:
        """Record a runtime-resolved literal key so future trials' ctx.available_keys
        includes it. Mirrors the expert executor's `_seen_response_keys`: on
        dynamic-key tasks, the key inventory is discovered trial-by-trial as
        `response_key_js` resolves each condition's key, not known up front.
        """
        if isinstance(key, str) and key:
            self._observed_keys.add(key)

    def build_context(self, condition: str, correct_key: str | None,
                      trial_index: int) -> TrialContext:
        return TrialContext(
            condition=condition, correct_key=correct_key,
            available_keys=self.available_keys, trial_index=trial_index,
            prev_condition=self._prev.get("condition"),
            prev_correct=self._prev.get("correct"),
            prev_rt_ms=self._prev.get("rt_ms"),
            prev_interrupted=self._prev.get("interrupted"),
        )

    def respond(self, condition: str, correct_key: str | None,
                trial_index: int) -> Response:
        ctx = self.build_context(condition, correct_key, trial_index)
        resp = _validate(self._participant.respond(ctx), ctx.available_keys, correct_key,
                         f"respond(trial {trial_index})")
        self._last_ctx, self._last_response = ctx, resp
        return resp

    def on_interrupt(self, ssd_ms: float) -> Response | None:
        if self._last_ctx is None or self._last_response is None:
            raise ProtocolViolation("on_interrupt called before respond()")
        fn = getattr(self._participant, "on_interrupt", None)
        if fn is None:
            raise ProtocolViolation("program lacks on_interrupt for an interrupt task")
        intended = (self._last_response.key, self._last_response.rt_ms)
        raw = fn(self._last_ctx, ssd_ms, intended)
        if raw is None:
            return None
        return _validate(raw, self._last_ctx.available_keys, self._last_ctx.correct_key,
                         "on_interrupt")

    def record_outcome(self, condition: str, correct: bool, rt_ms: float | None,
                       interrupted: bool) -> None:
        self._prev = {"condition": condition, "correct": correct,
                      "rt_ms": rt_ms, "interrupted": interrupted}

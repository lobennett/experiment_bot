"""SP21 naive-builder behavior provider.

A *program* is a Python file exposing ``make_participant(seed) ->
participant`` where ``participant.respond(ctx)`` returns a plain
``(key_or_None, rt_ms)`` tuple — or, on trials whose ctx carries
``response_elements``, ``("click", element_index, rt_ms)`` (Wave B1) — and
(for interrupt-capable tasks) ``participant.on_interrupt(ctx, ssd_ms,
intended)`` returns ``None`` (withhold) or a tuple. Programs are
stdlib+numpy only and cannot import this package — hence the tuple wire
format. ``BehaviorSession`` wraps a program: it builds TrialContext (with
previous-trial history), validates every return value at the boundary (no
silent coercion), and normalizes tuples into ``Response``/``ClickResponse``.
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


def stim_response_elements(stim) -> tuple[tuple[str, str], ...]:
    """(label, selector) pairs of a stimulus's clickable response options
    (Wave B1), tolerant of the same shapes as stim_condition_and_key: raw
    dicts and typed StimulusConfig/ResponseConfig objects. Each entry may
    itself be a {label, selector} dict or an object with those attributes;
    entries without a label are dropped. Returns () when the stimulus
    declares no response_elements (keypress tasks)."""
    resp = stim.get("response") if isinstance(stim, dict) else getattr(stim, "response", None)
    if resp is None:
        return ()
    raw = (resp.get("response_elements") if isinstance(resp, dict)
           else getattr(resp, "response_elements", None))
    out = []
    for entry in raw or []:
        if isinstance(entry, dict):
            label, sel = entry.get("label"), entry.get("selector")
        else:
            label, sel = getattr(entry, "label", None), getattr(entry, "selector", None)
        if label:
            out.append((str(label), str(sel or "")))
    return tuple(out)


class ProtocolViolation(Exception):
    """A generated program returned something outside the contract."""


@dataclass(frozen=True)
class Response:
    key: str | None
    rt_ms: float


@dataclass(frozen=True)
class ClickResponse:
    """Wave B1: a program's click on an on-screen response option. The
    index selects into the trial context's response_elements labels; the
    executor resolves the matching selector and clicks it. Kept as a
    separate frozen dataclass (not a field on Response) so the existing
    keypress contract and every consumer of Response.key stay untouched."""
    element_index: int
    rt_ms: float


@dataclass(frozen=True)
class SequenceResponse:
    """A program's ordered multi-action response for one trial (sequence-
    response capability). ``actions`` holds already-validated Response /
    ClickResponse objects, delivered by the executor in order — each
    action's rt_ms is the gap before that action fires. An empty tuple is
    the no-response sentinel (the program returned ``[]``). Kept as a
    separate frozen wrapper so single-action callers never see it: respond
    returns it ONLY when the program returns a list."""
    actions: tuple


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
    # Wave B3: the trial's visible context text (the executor's
    # trial_context_js/cue value) when the task exposes one, else None.
    stimulus_text: str | None = None
    # Wave B1: human-readable labels of the trial's clickable response
    # options; empty for keypress tasks.
    response_elements: tuple[str, ...] = ()
    # Sequence-response capability: the ordered indices into
    # response_elements that constitute THIS trial's correct reproduction
    # (None for trials without a target sequence).
    correct_sequence: tuple[int, ...] | None = None


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


# Playwright key names that are legitimate multi-character response keys.
# A program may press one of these even before it has been runtime-observed
# on a dynamic-key card (spatial_task_switching regression). Single-character
# keys are always pressable; anything else (prose, sentinels, garbage) is not.
_KNOWN_KEY_NAMES = frozenset({
    "Enter", "Space", "Tab", "Escape", "Backspace",
    "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
})


def _is_pressable_key(key) -> bool:
    """Whether `key` is something the executor can actually deliver: a single
    printable character, or a known Playwright key name. This is the real
    contract — 'return a pressable key' — as opposed to the stricter
    'return an already-observed key', which crashed sessions when a 2-AFC
    program pressed its other (legitimate) choice before that key had been
    resolved at runtime."""
    if not isinstance(key, str) or not key:
        return False
    if len(key) == 1 and key.isprintable():
        return True
    return key in _KNOWN_KEY_NAMES


def _validate_rt(rt, where: str) -> float:
    # Exact check the 2-tuple path has always applied (byte-identical
    # backward compatibility), factored out so clicks share it.
    if not isinstance(rt, (int, float)) or not math.isfinite(rt) or rt <= 0 or rt > 60_000:
        raise ProtocolViolation(f"{where}: rt_ms {rt!r} not a finite value in (0, 60000]")
    return float(rt)


def _validate(raw, available_keys: tuple[str, ...], correct_key: str | None,
              where: str,
              response_elements: tuple[str, ...] = ()) -> Response | ClickResponse:
    """A returned key is valid if it is None, equals the trial's correct_key,
    or is in available_keys. The correct_key carve-out gives the naive
    program information parity with the expert executor: on tasks where the
    key inventory is discovered trial-by-trial (dynamic key resolution), the
    executor learns a key only once `response_key_js` resolves it — see
    `core.executor.TaskExecutor._seen_response_keys` — but it always knows
    THIS trial's correct key up front. A program that presses ctx.correct_key
    must never be rejected merely because that key hasn't been observed yet.

    Wave B1: a program may instead return ("click", element_index, rt_ms) —
    valid only when the trial has response_elements and the index is in
    range. Nothing is silently coerced, same as the keypress path.
    """
    if isinstance(raw, tuple) and len(raw) == 3 and raw[0] == "click":
        _, idx, rt = raw
        if not response_elements:
            raise ProtocolViolation(
                f"{where}: click returned but this trial has no response_elements")
        if isinstance(idx, bool) or not isinstance(idx, int) \
                or not (0 <= idx < len(response_elements)):
            raise ProtocolViolation(
                f"{where}: click element_index {idx!r} not in "
                f"range(0, {len(response_elements)})")
        return ClickResponse(element_index=idx, rt_ms=_validate_rt(rt, where))
    if not (isinstance(raw, tuple) and len(raw) == 2):
        raise ProtocolViolation(
            f"{where}: expected (key, rt_ms) or (\"click\", element_index, rt_ms) "
            f"tuple, got {raw!r}")
    key, rt = raw
    if key is not None and key != correct_key and key not in available_keys \
            and not _is_pressable_key(key):
        raise ProtocolViolation(
            f"{where}: key {key!r} is not pressable and not in available_keys "
            f"{available_keys} (correct_key={correct_key!r})")
    return Response(key=key, rt_ms=_validate_rt(rt, where))


def _validate_sequence(raw, available_keys: tuple[str, ...], correct_key: str | None,
                       where: str,
                       response_elements: tuple[str, ...] = ()) -> list:
    """Validate a program's sequence return: a list/tuple OF actions, each
    itself a single action validated by ``_validate`` (2-tuple keypress or
    3-tuple click). Returns a list of Response/ClickResponse; an empty input
    returns ``[]`` (the no-response sentinel). Nothing is silently coerced —
    a bad action raises ProtocolViolation naming its position, and the
    summed rt may not exceed one action's 60s cap (over-long sequences are
    rejected the same way a single over-long rt is)."""
    if not isinstance(raw, (list, tuple)):
        raise ProtocolViolation(
            f"{where}: expected a list of actions, got {raw!r}")
    out: list = []
    total_rt = 0.0
    for i, action in enumerate(raw):
        resp = _validate(action, available_keys, correct_key,
                         f"{where} action {i}",
                         response_elements=response_elements)
        total_rt += resp.rt_ms
        out.append(resp)
    if total_rt > 60_000:
        raise ProtocolViolation(
            f"{where}: total sequence rt_ms {total_rt!r} exceeds 60000")
    return out


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
        self._last_response: Response | ClickResponse | None = None

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
                      trial_index: int,
                      stimulus_text: str | None = None,
                      response_elements: tuple[str, ...] = (),
                      correct_sequence: tuple[int, ...] | None = None) -> TrialContext:
        return TrialContext(
            condition=condition, correct_key=correct_key,
            available_keys=self.available_keys, trial_index=trial_index,
            prev_condition=self._prev.get("condition"),
            prev_correct=self._prev.get("correct"),
            prev_rt_ms=self._prev.get("rt_ms"),
            prev_interrupted=self._prev.get("interrupted"),
            stimulus_text=stimulus_text,
            response_elements=tuple(response_elements),
            correct_sequence=(tuple(correct_sequence)
                              if correct_sequence is not None else None),
        )

    def respond(self, condition: str, correct_key: str | None,
                trial_index: int,
                stimulus_text: str | None = None,
                response_elements: tuple[str, ...] = (),
                correct_sequence: tuple[int, ...] | None = None
                ) -> Response | ClickResponse | SequenceResponse:
        ctx = self.build_context(condition, correct_key, trial_index,
                                 stimulus_text=stimulus_text,
                                 response_elements=response_elements,
                                 correct_sequence=correct_sequence)
        raw = self._participant.respond(ctx)
        # A LIST return is a sequence; a bare tuple keeps the existing
        # single-action path byte-unchanged (backward compat).
        if isinstance(raw, list):
            actions = _validate_sequence(raw, ctx.available_keys, correct_key,
                                         f"respond(trial {trial_index})",
                                         response_elements=ctx.response_elements)
            resp: Response | ClickResponse | SequenceResponse = SequenceResponse(
                actions=tuple(actions))
        else:
            resp = _validate(raw, ctx.available_keys, correct_key,
                             f"respond(trial {trial_index})",
                             response_elements=ctx.response_elements)
        self._last_ctx, self._last_response = ctx, resp
        return resp

    def on_interrupt(self, ssd_ms: float) -> Response | ClickResponse | None:
        if self._last_ctx is None or self._last_response is None:
            raise ProtocolViolation("on_interrupt called before respond()")
        fn = getattr(self._participant, "on_interrupt", None)
        if fn is None:
            raise ProtocolViolation("program lacks on_interrupt for an interrupt task")
        if isinstance(self._last_response, ClickResponse):
            intended = ("click", self._last_response.element_index,
                        self._last_response.rt_ms)
        else:
            intended = (self._last_response.key, self._last_response.rt_ms)
        raw = fn(self._last_ctx, ssd_ms, intended)
        if raw is None:
            return None
        return _validate(raw, self._last_ctx.available_keys, self._last_ctx.correct_key,
                         "on_interrupt",
                         response_elements=self._last_ctx.response_elements)

    def record_outcome(self, condition: str, correct: bool, rt_ms: float | None,
                       interrupted: bool) -> None:
        self._prev = {"condition": condition, "correct": correct,
                      "rt_ms": rt_ms, "interrupted": interrupted}

# SP21 Naive-Builder Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "naive builder" arm to experiment_bot: Fable-generated freeform Python participant programs drive the executor's behavioral layer (navigation/detection/capture unchanged), collected N=30 × dev-4 under pre-registration, scored with the existing per-subject battery.

**Architecture:** A new `src/experiment_bot/behavior/` package defines a provider contract (programs return plain `(key, rt_ms)` tuples; a `BehaviorSession` wrapper validates and tracks history), the executor gets a `behavior_provider` bypass in `_execute_trial`, and two new CLIs handle generation (`experiment-bot-naive-gen`) and the mechanical simulation gate (`experiment-bot-naive-sim`). Programs are content-addressed artifacts like TaskCards.

**Tech Stack:** Python 3.11+, click, numpy, pytest, existing `LLMClient` protocol (`llm/factory.build_default_client`), existing `core/scraper.scrape_experiment_source`.

**Spec:** `docs/superpowers/specs/2026-07-02-naive-builder-experiment-design.md` — read it first; its decisions are binding.

## Global Constraints

- Branch: `sp21/naive-builder`. Commit after every task with the trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Generated programs may import ONLY: `math`, `random`, `itertools`, `functools`, `collections`, `dataclasses`, `statistics`, `typing`, `numpy`. No I/O, network, or clock modules — enforced by the simulation gate's import scan.
- Programs return plain tuples `(key: str | None, rt_ms: float)` — never objects from our package (they cannot import it).
- The generation prompt template must contain no mechanism names from `EFFECT_REGISTRY`, no distribution-family names (`ex_gaussian`, `lognormal`, `shifted_wald`, `ex-Gaussian`), no phenomenon names (post-error slowing, congruency sequence, SSRT, autocorrelation…), no numeric behavioral priors. Invariant-tested.
- No behavioral iteration: regeneration only on mechanical gate failure, max 2 retries, all attempts archived.
- Never modify `docs/preregistration.md` or `norms/*.json`. New pre-reg goes in `docs/preregistration-naive.md`.
- Run the full suite (`uv run pytest -q`) before each commit; it must stay green (873 passed at plan time).

---

### Task 1: Behavior provider contract (`behavior/provider.py`)

**Files:**
- Create: `src/experiment_bot/behavior/__init__.py` (empty)
- Create: `src/experiment_bot/behavior/provider.py`
- Create: `tests/fixtures/toy_participant.py`
- Test: `tests/test_behavior_provider.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces (used by Tasks 2–4, 6):
  - `@dataclass(frozen=True) TrialContext(condition, correct_key, available_keys, trial_index, prev_condition, prev_correct, prev_rt_ms, prev_interrupted)`
  - `@dataclass(frozen=True) Response(key: str | None, rt_ms: float)`
  - `class ProtocolViolation(Exception)`
  - `load_program(path: Path) -> module` and `program_sha256(path: Path) -> str`
  - `resolve_program(spec: str, root: Path = Path("naive_programs")) -> Path` (direct path, or `<label>/<hash-prefix>`)
  - `class BehaviorSession`: `BehaviorSession(program_module, seed, available_keys, program_path=None)`, attributes `.program_sha256`, `.seed`, methods `.respond(condition, correct_key, trial_index) -> Response`, `.on_interrupt(ssd_ms) -> Response | None`, `.record_outcome(condition, correct, rt_ms, interrupted)`

- [ ] **Step 1: Write the toy fixture program** (stdlib+numpy only; used by tests in Tasks 1, 2, 4)

```python
# tests/fixtures/toy_participant.py
"""Hand-written reference participant program for tests.

Follows the SP21 naive-program contract exactly: stdlib+numpy only,
deterministic per seed, returns plain (key, rt_ms) tuples.
"""
import numpy as np


def make_participant(seed):
    return _Toy(seed)


class _Toy:
    def __init__(self, seed):
        self._rng = np.random.default_rng(seed)
        self._speed = 500.0 + self._rng.normal(0.0, 50.0)

    def respond(self, ctx):
        rt = max(160.0, self._speed + self._rng.normal(0.0, 60.0))
        if self._rng.random() < 0.05:  # occasional error: press a non-correct key
            others = [k for k in ctx.available_keys if k != ctx.correct_key]
            if others:
                return (others[int(self._rng.integers(len(others)))], rt)
        return (ctx.correct_key, rt)

    def on_interrupt(self, ctx, ssd_ms, intended):
        # Longer SSD -> harder to stop.
        p_stop = max(0.1, 0.9 - ssd_ms / 500.0)
        if self._rng.random() < p_stop:
            return None
        return (intended[0], max(200.0, ssd_ms + 150.0))
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_behavior_provider.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_behavior_provider.py -q`
Expected: FAIL / collection error with `ModuleNotFoundError: No module named 'experiment_bot.behavior'`

- [ ] **Step 4: Implement `provider.py`**

```python
# src/experiment_bot/behavior/provider.py
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


def _validate(raw, available_keys: tuple[str, ...], where: str) -> Response:
    if not (isinstance(raw, tuple) and len(raw) == 2):
        raise ProtocolViolation(f"{where}: expected (key, rt_ms) tuple, got {raw!r}")
    key, rt = raw
    if key is not None and key not in available_keys:
        raise ProtocolViolation(
            f"{where}: key {key!r} not in available_keys {available_keys}")
    if not isinstance(rt, (int, float)) or not math.isfinite(rt) or rt <= 0 or rt > 60_000:
        raise ProtocolViolation(f"{where}: rt_ms {rt!r} not a finite value in (0, 60000]")
    return Response(key=key, rt_ms=float(rt))


class BehaviorSession:
    """One participant (= one seed) executing one program."""

    def __init__(self, program_module, seed: int, available_keys: tuple[str, ...],
                 program_path: Path | None = None):
        self.seed = seed
        self.available_keys = tuple(available_keys)
        self.program_sha256 = program_sha256(program_path) if program_path else None
        self.program_path = str(program_path) if program_path else None
        self._participant = program_module.make_participant(seed)
        self._prev: dict = {}
        self._last_ctx: TrialContext | None = None
        self._last_response: Response | None = None

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
        resp = _validate(self._participant.respond(ctx), self.available_keys,
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
        return _validate(raw, self.available_keys, "on_interrupt")

    def record_outcome(self, condition: str, correct: bool, rt_ms: float | None,
                       interrupted: bool) -> None:
        self._prev = {"condition": condition, "correct": correct,
                      "rt_ms": rt_ms, "interrupted": interrupted}
```

Also create the empty `src/experiment_bot/behavior/__init__.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_behavior_provider.py -q`
Expected: 9 passed

- [ ] **Step 6: Full suite, then commit**

Run: `uv run pytest -q` — expected: 882 passed (873 + 9), 7 skipped.

```bash
git add src/experiment_bot/behavior/ tests/test_behavior_provider.py tests/fixtures/toy_participant.py
git commit -m "feat(behavior): SP21 provider contract, program loading, session validation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Executor integration (`behavior_provider` bypass)

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (constructor ~line 81; jitter block ~line 100; `_execute_trial` top ~line 1148; run_metadata block ~line 654)
- Test: `tests/test_executor.py` (append)

**Interfaces:**
- Consumes: `BehaviorSession` from Task 1 (`.respond(condition, correct_key, trial_index)`, `.on_interrupt(ssd_ms)`, `.record_outcome(...)`, `.program_sha256`).
- Produces: `TaskExecutor(..., behavior_provider: BehaviorSession | None = None)`; a new private coroutine `_execute_trial_via_provider(page, match, cue)`; `run_metadata["behavior_program"]` = `{"sha256": ..., "path": ..., "seed": ...}` when the provider is set.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_executor.py`)

```python
# --- SP21: behavior-provider bypass ---
from pathlib import Path as _Path
from experiment_bot.behavior.provider import BehaviorSession, load_program

_TOY = _Path("tests/fixtures/toy_participant.py")


def _toy_session(seed=42):
    return BehaviorSession(load_program(_TOY), seed=seed,
                           available_keys=("z",), program_path=_TOY)


def test_executor_accepts_behavior_provider():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    ex = TaskExecutor(config, seed=42, behavior_provider=_toy_session())
    assert ex._behavior_provider is not None


def test_provider_skips_between_subject_jitter():
    """Provider path bypasses the behavioral layer entirely — including
    the SP20 jitter (config params stay untouched)."""
    d = dict(SAMPLE_CONFIG)
    d["between_subject_jitter"] = {"rt_mean_sd_ms": 60.0}
    ex = TaskExecutor(TaskConfig.from_dict(d), seed=42,
                      behavior_provider=_toy_session())
    assert ex._config.response_distributions["go_correct"].params["mu"] == 450

@pytest.mark.asyncio
async def test_provider_trial_fires_program_key_not_sampler():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    ex = TaskExecutor(config, seed=42, behavior_provider=_toy_session())
    ex._sampler = MagicMock()  # must never be consulted
    ex._writer = MagicMock()
    ex._fire_response_key = AsyncMock(return_value={})
    ex._resolve_response_key = AsyncMock(return_value="z")
    ex._check_interrupt = AsyncMock(return_value=False)
    page = AsyncMock()
    match = StimulusMatch(stimulus_id="go_left", condition="go")
    with patch("asyncio.sleep", new=AsyncMock()):
        await ex._execute_trial(page, match, cue=None)
    ex._fire_response_key.assert_awaited_once()
    assert ex._fire_response_key.await_args.args[1] == "z"
    ex._sampler.sample_rt_with_fallback.assert_not_called()
    logged = ex._writer.log_trial.call_args.args[0]
    assert logged["behavior_provider"] is True
    assert logged["sampled_rt_ms"] > 0


@pytest.mark.asyncio
async def test_provider_interrupt_handoff_withhold():
    """When the interrupt fires and the program withholds, no key is sent
    and the trial logs the withheld condition."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)

    class _Stopper:
        def respond(self, ctx):
            return ("z", 5000.0)  # slow, so the interrupt poll wins
        def on_interrupt(self, ctx, ssd_ms, intended):
            return None
    mod = type("M", (), {"make_participant": staticmethod(lambda s: _Stopper())})
    session = BehaviorSession(mod, seed=1, available_keys=("z",))
    ex = TaskExecutor(config, seed=42, behavior_provider=session)
    ex._writer = MagicMock()
    ex._fire_response_key = AsyncMock(return_value={})
    ex._resolve_response_key = AsyncMock(return_value="z")
    ex._check_interrupt = AsyncMock(return_value=True)  # interrupt immediately
    page = AsyncMock()
    match = StimulusMatch(stimulus_id="stop_trial", condition="stop")
    with patch("asyncio.sleep", new=AsyncMock()):
        await ex._execute_trial(page, match, cue=None)
    ex._fire_response_key.assert_not_awaited()
    logged = ex._writer.log_trial.call_args.args[0]
    assert logged["condition"] == "stop_withheld"
    assert ex._prev_interrupt_detected is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_executor.py -k "provider" -q`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'behavior_provider'`

- [ ] **Step 3: Implement the executor changes**

In `__init__` signature add `behavior_provider=None` after `calibrate`; store and gate jitter:

```python
        calibrate: bool = True,  # run the startup keypress-latency calibration pass
        behavior_provider=None,  # SP21: BehaviorSession replacing the behavioral layer
    ):
```

Change the SP20 jitter block so the provider path skips it (the provider IS the behavioral layer):

```python
        self._behavior_provider = behavior_provider
        if behavior_provider is None:
            jitter_rng = np.random.default_rng(
                None if seed is None else [seed, _BSJ_SEED_STREAM]
            )
            config = jitter_distributions(config, jitter_rng)
        bsj = config.between_subject_jitter
```

At the very top of `_execute_trial` (immediately after `condition = match.condition`), add the dispatch:

```python
        if self._behavior_provider is not None:
            await self._execute_trial_via_provider(page, match, cue)
            return
```

Add the new method (place it directly above `_execute_trial`); it mirrors the expert path's timing/delivery/logging but asks the program instead of the sampler:

```python
    async def _execute_trial_via_provider(self, page, match, cue=None) -> None:
        """SP21 naive arm: the behavior program supplies (key, rt); the
        executor supplies navigation, detection, delivery, and logging.
        No omission draw, no accuracy draw, no sampler, no temporal
        effects — a program expresses omission by returning key=None."""
        provider = self._behavior_provider
        trial_start = time.monotonic()
        condition = match.condition
        timing = self._config.runtime.timing
        if timing.response_window_js and not self._response_window_confirmed:
            await self._wait_for_response_window(page, timing.response_window_js)
            trial_start = time.monotonic()

        correct_key = await self._resolve_response_key(match, page)
        resp = provider.respond(condition, correct_key, self._trial_count)
        rt_ms = resp.rt_ms

        interrupt_detected = False
        if self._interrupt_js:
            poll_interval = timing.poll_interval_ms / 1000.0
            while (time.monotonic() - trial_start) < rt_ms / 1000.0:
                if await self._check_interrupt(page, self._interrupt_js):
                    interrupt_detected = True
                    break
                await asyncio.sleep(poll_interval)

        interrupt_cfg = self._config.runtime.trial_interrupt
        if interrupt_detected:
            ssd_ms = (time.monotonic() - trial_start) * 1000
            decision = provider.on_interrupt(ssd_ms)
            if decision is None:
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": f"{interrupt_cfg.detection_condition}_withheld",
                    "response_key": None,
                    "sampled_rt_ms": round(rt_ms, 1),
                    "actual_rt_ms": None,
                    "omission": False,
                    "behavior_provider": True,
                })
                provider.record_outcome(condition, correct=True, rt_ms=None,
                                        interrupted=True)
                self._recent_errors.appendleft(False)
                self._prev_interrupt_detected = True
                await asyncio.sleep(interrupt_cfg.inhibit_wait_ms / 1000.0)
                return
            remaining_s = (decision.rt_ms / 1000.0) - (time.monotonic() - trial_start)
            if remaining_s > 0:
                await asyncio.sleep(remaining_s)
            actual_rt = (time.monotonic() - trial_start) * 1000
            delivery_meta = await self._fire_response_key(page, decision.key)
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": f"{interrupt_cfg.detection_condition}_responded",
                "response_key": decision.key,
                "sampled_rt_ms": round(decision.rt_ms, 1),
                "actual_rt_ms": round(actual_rt, 1),
                "omission": False,
                "delivery": delivery_meta,
                "behavior_provider": True,
            })
            provider.record_outcome(condition, correct=False,
                                    rt_ms=decision.rt_ms, interrupted=True)
            self._recent_errors.appendleft(True)
            self._prev_interrupt_detected = True
            return

        remaining = (rt_ms / 1000.0) - (time.monotonic() - trial_start)
        if remaining > 0:
            await asyncio.sleep(remaining)
        actual_rt = (time.monotonic() - trial_start) * 1000

        if resp.key is None:
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": None,
                "sampled_rt_ms": round(rt_ms, 1),
                "actual_rt_ms": None,
                "omission": False,
                "withheld": True,
                "behavior_provider": True,
            })
            provider.record_outcome(condition, correct=(correct_key is None),
                                    rt_ms=None, interrupted=False)
            self._recent_errors.appendleft(correct_key is not None)
            self._prev_interrupt_detected = False
            return

        delivery_meta = await self._fire_response_key(page, resp.key)
        is_correct = (resp.key == correct_key)
        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": resp.key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
            "delivery": delivery_meta,
            "behavior_provider": True,
            "cue": cue,
        })
        provider.record_outcome(condition, correct=is_correct,
                                rt_ms=resp.rt_ms, interrupted=False)
        self._recent_errors.appendleft(not is_correct)
        self._prev_interrupt_detected = False
```

In the run_metadata `finally` block (after the `between_subject_jitter` line), add:

```python
                if self._behavior_provider is not None:
                    metadata["behavior_program"] = {
                        "sha256": self._behavior_provider.program_sha256,
                        "path": self._behavior_provider.program_path,
                        "seed": self._behavior_provider.seed,
                    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_executor.py -k "provider" -q`
Expected: 4 passed

- [ ] **Step 5: Full suite, then commit**

Run: `uv run pytest -q` — expected: 886 passed, 7 skipped.

```bash
git add src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "feat(executor): SP21 behavior-provider bypass with interrupt handoff

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Run-CLI flag `--behavior-program`

**Files:**
- Modify: `src/experiment_bot/cli.py` (options block lines 78–101; body lines 52–72)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `resolve_program`, `load_program`, `BehaviorSession` (Task 1); `TaskExecutor(behavior_provider=...)` (Task 2).
- Produces: `experiment-bot URL --label L --behavior-program <path-or-label/hash>` runs the naive arm. Available keys for the session come from the structural card: `task_specific.key_map` values plus per-stimulus static `response.key` values (helper `_available_keys_from_taskcard(taskcard) -> tuple[str, ...]`, exported from `cli.py` for tests).

- [ ] **Step 1: Write the failing test** (append to `tests/test_cli.py`; follow the file's existing patch style at line ~81)

```python
# --- SP21: --behavior-program wiring ---
from experiment_bot.cli import _available_keys_from_taskcard


def test_available_keys_from_taskcard():
    class _TC:
        task_specific = {"key_map": {"go": "z", "stop": "withhold"}}
        stimuli = [{"response": {"key": "m", "condition": "go"}},
                   {"response": {"key": None, "condition": "stop"}}]
    keys = _available_keys_from_taskcard(_TC())
    assert set(keys) == {"z", "m"}  # withhold sentinels and None excluded


def test_behavior_program_flag_builds_session(tmp_path):
    prog = tmp_path / "p.py"
    prog.write_text(Path("tests/fixtures/toy_participant.py").read_text())
    from click.testing import CliRunner
    from experiment_bot import cli as cli_mod

    captured = {}

    class _FakeExecutor:
        def __init__(self, *a, **kw):
            captured.update(kw)
        async def run(self, url):
            return None

    with patch.object(cli_mod, "TaskExecutor", _FakeExecutor), \
         patch.object(cli_mod, "load_taskcard_for_label") as load_tc, \
         patch.object(cli_mod, "sample_session_params", return_value={}), \
         patch.object(cli_mod, "build_default_client", return_value=None):
        load_tc.return_value = MagicMock(
            task_specific={"key_map": {"go": "z"}}, stimuli=[],
            response_distributions={}, to_dict=lambda: {})
        result = CliRunner().invoke(cli_mod.main, [
            "http://x", "--label", "t", "--headless", "--seed", "7",
            "--no-llm-client", "--behavior-program", str(prog)])
    assert result.exit_code == 0, result.output
    bp = captured["behavior_provider"]
    assert bp is not None and bp.seed == 7
```

Note: match the *actual* loader symbol name in `cli.py` when patching (`grep -n "def.*load" src/experiment_bot/cli.py` — the TaskCard is loaded around line 45; use whatever function `main` calls, e.g. patch at its import site the same way existing tests in `tests/test_cli.py` do).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "behavior" -q`
Expected: FAIL with `ImportError: cannot import name '_available_keys_from_taskcard'`

- [ ] **Step 3: Implement**

In `cli.py`, add the import and the helper:

```python
from experiment_bot.behavior.provider import (
    BehaviorSession, load_program, resolve_program,
)
from experiment_bot.core.executor import _WITHHOLD_SENTINELS  # reuse the sentinel set


def _available_keys_from_taskcard(taskcard) -> tuple[str, ...]:
    keys: set[str] = set()
    km = (taskcard.task_specific or {}).get("key_map") or {}
    keys.update(v for v in km.values() if isinstance(v, str))
    for stim in taskcard.stimuli or []:
        k = ((stim.get("response") or {}).get("key")) if isinstance(stim, dict) else None
        if isinstance(k, str):
            keys.add(k)
    return tuple(sorted(k for k in keys
                        if k and k.lower() not in _WITHHOLD_SENTINELS))
```

(If `_WITHHOLD_SENTINELS` lives elsewhere or is spelled differently — check `grep -n "_WITHHOLD_SENTINELS" src/experiment_bot/core/executor.py` — import from the actual location.)

Add the option after `--no-calibration`:

```python
@click.option("--behavior-program", default=None,
              help="SP21 naive arm: path (or <label>/<hash-prefix> under "
                   "naive_programs/) of a generated participant program. "
                   "Replaces the behavioral layer; navigation/detection/"
                   "capture come from the TaskCard as usual.")
```

In the body, after `seed` is finalized and the TaskCard is loaded, before the executor is built:

```python
    provider = None
    if behavior_program:
        prog_path = resolve_program(behavior_program)
        provider = BehaviorSession(
            load_program(prog_path), seed=seed,
            available_keys=_available_keys_from_taskcard(taskcard),
            program_path=prog_path,
        )
        click.echo(f"Naive arm: program {prog_path} (sha {provider.program_sha256[:8]})")
```

and pass `behavior_provider=provider` to `TaskExecutor(...)`. Also skip the `sample_session_params` stamping when `provider` is set (the behavioral layer is the program's):

```python
    if behavior_program is None:
        sampled = sample_session_params(taskcard.to_dict(), seed=seed)
        for cond, params in sampled.items():
            if cond in taskcard.response_distributions:
                taskcard.response_distributions[cond].value.update(params)
    else:
        sampled = {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q`
Expected: all pass (existing + 2 new)

- [ ] **Step 5: Full suite, then commit**

```bash
uv run pytest -q   # expected: 888 passed, 7 skipped
git add src/experiment_bot/cli.py tests/test_cli.py
git commit -m "feat(cli): SP21 --behavior-program flag wires BehaviorSession into the executor

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Simulation gate (`behavior/simgate.py` + `experiment-bot-naive-sim`)

**Files:**
- Create: `src/experiment_bot/behavior/simgate.py`
- Create: `src/experiment_bot/behavior/sim_cli.py`
- Modify: `pyproject.toml` (`[project.scripts]`: add `experiment-bot-naive-sim = "experiment_bot.behavior.sim_cli:main"`)
- Test: `tests/test_simgate.py`

**Interfaces:**
- Consumes: `load_program`, `BehaviorSession`, `ProtocolViolation`, `program_sha256` (Task 1).
- Produces (used by Task 6): `run_gate(program_path: Path, conditions: list[str], key_map: dict[str, str], has_interrupt: bool, n_trials: int = 1000, seeds: tuple[int, ...] = (1, 2)) -> GateReport` where `GateReport` is a dataclass with `.passed: bool`, `.failures: list[str]`, `.stats: dict`, `.to_dict()`; and `scan_imports(program_path: Path) -> list[str]` returning disallowed imports. Allowed imports: `{"math","random","itertools","functools","collections","dataclasses","statistics","typing","numpy"}` (module constant `ALLOWED_IMPORTS`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_simgate.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_simgate.py -q`
Expected: collection error `ModuleNotFoundError ... simgate`

- [ ] **Step 3: Implement `simgate.py`**

```python
# src/experiment_bot/behavior/simgate.py
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
           report: GateReport) -> list[tuple]:
    """One synthetic session; returns [(key, rt), ...]. Failures -> report."""
    keys = tuple(sorted(set(key_map.values()))) or ("z",)
    session = BehaviorSession(load_program(program_path), seed=seed,
                              available_keys=keys, program_path=program_path)
    out = []
    for i in range(n_trials):
        cond = conditions[i % len(conditions)]
        correct = key_map.get(cond, keys[0])
        try:
            r = session.respond(cond, correct, i)
            if has_interrupt and cond == conditions[-1]:
                # Deterministic synthetic SSD schedule: 100..400ms cycle.
                d = session.on_interrupt(ssd_ms=100.0 + (i % 4) * 100.0)
                if d is not None:
                    r = d
            session.record_outcome(cond, correct=(r.key == correct),
                                   rt_ms=r.rt_ms, interrupted=False)
            out.append((r.key, round(r.rt_ms, 6)))
        except Exception as e:  # noqa: BLE001 — the gate reports every failure mode
            report.fail(f"trial {i} ({cond}): {type(e).__name__}: {e}")
            return out
    return out


def run_gate(program_path: Path, conditions: list[str], key_map: dict[str, str],
             has_interrupt: bool, n_trials: int = 1000,
             seeds: tuple[int, ...] = (1, 2)) -> GateReport:
    report = GateReport(program_sha256=program_sha256(program_path))
    bad_imports = scan_imports(program_path)
    if bad_imports:
        report.fail(f"disallowed imports: {bad_imports}")
        return report
    t1 = _trace(program_path, seeds[0], conditions, key_map, has_interrupt,
                n_trials, report)
    if not report.passed:
        return report
    t1_again = _trace(program_path, seeds[0], conditions, key_map, has_interrupt,
                      n_trials, report)
    if t1 != t1_again:
        report.fail("non-deterministic: same seed produced different traces")
    t2 = _trace(program_path, seeds[1], conditions, key_map, has_interrupt,
                n_trials, report)
    if report.passed and t1 == t2:
        report.fail("seeds not distinct: different seeds produced identical traces")
    report.stats = {"n_trials": len(t1), "seeds": list(seeds),
                    "n_conditions": len(conditions)}
    return report
```

- [ ] **Step 4: Implement `sim_cli.py` and register the script**

```python
# src/experiment_bot/behavior/sim_cli.py
"""experiment-bot-naive-sim: run the SP21 mechanical gate on a program."""
from __future__ import annotations

import json
from pathlib import Path

import click

from experiment_bot.behavior.simgate import run_gate


@click.command()
@click.argument("program", type=click.Path(exists=True, path_type=Path))
@click.option("--conditions", required=True,
              help="Comma-separated condition labels (structural facts)")
@click.option("--key-map", "key_map_json", required=True,
              help='JSON condition->key map, e.g. \'{"go": "z"}\'')
@click.option("--has-interrupt", is_flag=True, default=False)
@click.option("--trials", default=1000, show_default=True)
def main(program: Path, conditions: str, key_map_json: str,
         has_interrupt: bool, trials: int):
    """Mechanical simulation gate; writes <sha>.simgate.json next to PROGRAM."""
    report = run_gate(program, conditions=conditions.split(","),
                      key_map=json.loads(key_map_json),
                      has_interrupt=has_interrupt, n_trials=trials)
    out = program.parent / f"{report.program_sha256}.simgate.json"
    out.write_text(json.dumps(report.to_dict(), indent=2))
    click.echo(f"{'PASS' if report.passed else 'FAIL'} -> {out}")
    if not report.passed:
        for f in report.failures:
            click.echo(f"  - {f}")
        raise SystemExit(1)
```

In `pyproject.toml` `[project.scripts]` add:

```toml
experiment-bot-naive-sim = "experiment_bot.behavior.sim_cli:main"
```

- [ ] **Step 5: Run tests, full suite, commit**

```bash
uv run pytest tests/test_simgate.py -q      # expected: 5 passed
uv run pytest -q                            # expected: 893 passed, 7 skipped
git add src/experiment_bot/behavior/simgate.py src/experiment_bot/behavior/sim_cli.py pyproject.toml tests/test_simgate.py
git commit -m "feat(behavior): SP21 mechanical simulation gate + naive-sim CLI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Generation prompt template + neutrality invariants

**Files:**
- Create: `src/experiment_bot/behavior/prompts/naive_gen.md`
- Test: `tests/test_naive_prompt_invariants.py`

**Interfaces:**
- Produces (used by Task 6): a template with placeholders `{PAGE_SOURCE}`, `{CONDITIONS}`, `{KEY_MAP}`, `{INTERRUPT_NOTE}` — loaded via `Path(...).read_text()` and `.format(...)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_naive_prompt_invariants.py
"""SP21 neutrality guardrails: the naive generation prompt must contain no
expert behavioral scaffolding. These invariants ARE the experiment's
scientific core — a leak here invalidates the naive arm."""
from pathlib import Path

TEMPLATE = Path("src/experiment_bot/behavior/prompts/naive_gen.md")

BANNED_TERMS = [
    # mechanism / registry vocabulary
    "autocorrelation", "fatigue_drift", "condition_repetition", "pink_noise",
    "lag1_pair_modulation", "post_event_slowing", "practice_effect",
    "vigilance_decrement",
    # distribution families
    "ex_gaussian", "ex-gaussian", "lognormal", "shifted_wald", "shifted wald",
    # phenomenon names
    "post-error slowing", "post_error", "congruency sequence", "gratton",
    "ssrt", "stop-signal reaction time", "conflict adaptation",
    "sequential effect",
]


def test_template_exists_with_placeholders():
    text = TEMPLATE.read_text()
    for ph in ("{PAGE_SOURCE}", "{CONDITIONS}", "{KEY_MAP}", "{INTERRUPT_NOTE}"):
        assert ph in text


def test_no_banned_behavioral_terms():
    text = TEMPLATE.read_text().lower()
    for term in BANNED_TERMS:
        assert term not in text, f"banned term in naive prompt: {term!r}"


def test_no_registry_mechanism_names():
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    text = TEMPLATE.read_text().lower()
    for name in EFFECT_REGISTRY:
        assert name.lower() not in text


def test_no_numeric_behavioral_priors():
    """The template's static text may contain numbers ONLY in the protocol
    constraints (rt bounds, seed) — never as ms/accuracy suggestions."""
    import re
    text = TEMPLATE.read_text()
    # Strip fenced code blocks (the protocol signatures may carry types).
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(ms|milliseconds|%)", text.lower()):
        raise AssertionError(f"numeric behavioral prior in template: {m.group(0)!r}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_naive_prompt_invariants.py -q`
Expected: FAIL (`FileNotFoundError` — template missing)

- [ ] **Step 3: Write the template**

````markdown
<!-- src/experiment_bot/behavior/prompts/naive_gen.md -->
You are writing a computational model of a human research participant.

Below is the source code of a web-based task. Read it and write ONE
self-contained Python program that simulates a typical healthy adult
completing this task. Your program's recorded data should be
indistinguishable from a real participant's platform-recorded data — in
whatever respects you judge matter. You decide every aspect of the
behavioral model: what varies, across what, and by how much. Each seed is
a distinct participant, so participants must differ from each other the
way real people differ.

## Contract (exact)

Your program is a single Python file that defines:

```python
def make_participant(seed: int):
    """Return a participant object. Same seed => identical behavior."""
```

The participant object must define:

```python
def respond(self, ctx):
    """Called once per trial. Return (key, rt_ms).

    key: one of ctx.available_keys, or None to make no response.
    rt_ms: response time in milliseconds (float > 0).

    ctx fields: condition (str), correct_key (str | None),
    available_keys (tuple[str, ...]), trial_index (int),
    prev_condition, prev_correct, prev_rt_ms, prev_interrupted
    (previous-trial outcome; None on the first trial).
    """
```

{INTERRUPT_NOTE}

## Hard constraints

- Imports: Python standard library (math, random, itertools, functools,
  collections, dataclasses, statistics, typing) and numpy ONLY.
- Deterministic per seed: seed all randomness from the `seed` argument.
- No file, network, or clock access.
- Return plain tuples; do not import anything from the experiment harness.

## Mechanical facts about this task

- Condition labels your model will see: {CONDITIONS}
- Key map (condition -> correct key): {KEY_MAP}

## Task source

{PAGE_SOURCE}

Reply with ONLY the Python program in a single fenced code block.
````

Where `{INTERRUPT_NOTE}` is filled by Task 6 with either `""` or this block (kept out of the static template so non-interrupt paradigms never see it):

```python
def on_interrupt(self, ctx, ssd_ms, intended):
    """Called when a mid-trial signal tells the participant to withhold
    the response they were preparing. ssd_ms: ms from trial start to the
    signal. intended: the (key, rt_ms) your respond() returned. Return
    None to withhold, or (key, rt_ms) to respond anyway."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_naive_prompt_invariants.py -q`
Expected: 4 passed

- [ ] **Step 5: Full suite, commit**

```bash
uv run pytest -q   # expected: 897 passed, 7 skipped
git add src/experiment_bot/behavior/prompts/ tests/test_naive_prompt_invariants.py
git commit -m "feat(behavior): SP21 domain-neutral generation prompt + neutrality invariants

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Generation CLI (`experiment-bot-naive-gen`)

**Files:**
- Create: `src/experiment_bot/behavior/gen_cli.py`
- Modify: `pyproject.toml` (`experiment-bot-naive-gen = "experiment_bot.behavior.gen_cli:main"`)
- Test: `tests/test_naive_gen.py`

**Interfaces:**
- Consumes: `scrape_experiment_source(url, hint)` (returns a `SourceBundle`; use its combined text — check `grep -n "class SourceBundle" -A 15 src/experiment_bot/core/scraper.py` for the exact field, e.g. `.combined_source` or similar, and use that); `build_default_client(model)` → `LLMClient` with `async complete(system, user, max_tokens, output_format) -> LLMResponse(.text)`; TaskCard loading (same helper `cli.py` uses); `run_gate` (Task 4); template (Task 5).
- Produces: `naive_programs/<label>/<sha>.py`, `<sha>.transcript.json`, `<sha>.simgate.json`; pure helpers `extract_python_block(text) -> str`, `mechanical_facts(taskcard) -> dict` (keys: `conditions`, `key_map`, `has_interrupt`), and `async generate(url, label, client, taskcards_dir="taskcards", out_root="naive_programs", max_retries=2) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_naive_gen.py
"""SP21 Task 6: generation CLI — archival, extraction, retry-on-gate-fail."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.behavior.gen_cli import (
    extract_python_block, generate, mechanical_facts,
)

TOY_TEXT = Path("tests/fixtures/toy_participant.py").read_text()


def test_extract_python_block():
    assert extract_python_block(f"prose\n```python\n{TOY_TEXT}```\nmore") == TOY_TEXT
    with pytest.raises(ValueError):
        extract_python_block("no code here")


def test_mechanical_facts():
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "z", "stop": "withhold"}}
    tc.stimuli = [{"response": {"condition": "go", "key": "z"}},
                  {"response": {"condition": "stop", "key": None}}]
    tc.runtime.trial_interrupt.detection_condition = "stop"
    facts = mechanical_facts(tc)
    assert set(facts["conditions"]) == {"go", "stop"}
    assert facts["key_map"] == {"go": "z"}
    assert facts["has_interrupt"] is True


def _fake_client(responses):
    client = MagicMock()
    client.model = "claude-fable-5"
    client.complete = AsyncMock(
        side_effect=[MagicMock(text=r) for r in responses])
    return client


def _fake_scrape(monkeypatch):
    import experiment_bot.behavior.gen_cli as g
    bundle = MagicMock()
    bundle.combined_source = "<html>task</html>"
    monkeypatch.setattr(g, "scrape_experiment_source",
                        AsyncMock(return_value=bundle))


def _fake_taskcard(monkeypatch):
    import experiment_bot.behavior.gen_cli as g
    tc = MagicMock()
    tc.task_specific = {"key_map": {"go": "z"}}
    tc.stimuli = [{"response": {"condition": "go", "key": "z"}}]
    tc.runtime.trial_interrupt.detection_condition = None
    monkeypatch.setattr(g, "_load_structural_taskcard",
                        MagicMock(return_value=tc))


def test_generate_archives_program_and_transcript(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    client = _fake_client([f"```python\n{TOY_TEXT}```"])
    path = asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    assert path.exists() and path.suffix == ".py"
    sha = path.stem
    transcript = json.loads((tmp_path / "toy" / f"{sha}.transcript.json").read_text())
    assert transcript["model"] == "claude-fable-5"
    assert "task source" in transcript["prompt"].lower() or transcript["prompt"]
    assert (tmp_path / "toy" / f"{sha}.simgate.json").exists()


def test_generate_retries_on_gate_failure_then_fails(tmp_path, monkeypatch):
    _fake_scrape(monkeypatch); _fake_taskcard(monkeypatch)
    crash = "def make_participant(seed):\n    raise ValueError('boom')\n"
    client = _fake_client([f"```python\n{crash}```"] * 3)
    with pytest.raises(RuntimeError, match="gate"):
        asyncio.run(generate("http://x", "toy", client, out_root=tmp_path))
    assert client.complete.await_count == 3  # initial + 2 retries, all archived
    assert len(list((tmp_path / "toy").glob("*.transcript.json"))) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_naive_gen.py -q`
Expected: collection error `ModuleNotFoundError ... gen_cli`

- [ ] **Step 3: Implement `gen_cli.py`**

```python
# src/experiment_bot/behavior/gen_cli.py
"""experiment-bot-naive-gen: SP21 naive-arm program generation.

Pre-registered discipline: the first program that passes the mechanical
simulation gate IS the program. Retries (max 2) happen only on gate
failure, every attempt is archived. Never regenerate on behavioral taste.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from experiment_bot.behavior.simgate import run_gate
from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.llm.factory import build_default_client

_TEMPLATE = Path(__file__).parent / "prompts" / "naive_gen.md"

_INTERRUPT_NOTE = '''The task also has trials where a mid-trial signal tells
the participant to withhold the response they were preparing. Your
participant must also define:

```python
def on_interrupt(self, ctx, ssd_ms, intended):
    """ssd_ms: ms from trial start to the signal. intended: the
    (key, rt_ms) your respond() returned. Return None to withhold,
    or (key, rt_ms) to respond anyway."""
```'''


def _load_structural_taskcard(label: str, taskcards_dir: str):
    # Same newest-by-mtime loader the run CLI uses (import at call time to
    # avoid a cycle) — check src/experiment_bot/cli.py for the exact helper.
    from experiment_bot.taskcard.loader import load_taskcard_for_label
    return load_taskcard_for_label(label, taskcards_dir)


def extract_python_block(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if not m:
        raise ValueError("LLM reply contains no fenced Python block")
    return m.group(1)


def mechanical_facts(taskcard) -> dict:
    conditions: list[str] = []
    for stim in taskcard.stimuli or []:
        cond = ((stim.get("response") or {}).get("condition")) if isinstance(stim, dict) else None
        if cond and cond not in conditions:
            conditions.append(cond)
    km = {k: v for k, v in ((taskcard.task_specific or {}).get("key_map") or {}).items()
          if isinstance(v, str) and v.lower() not in {"withhold", "none", "null", ""}}
    ti = getattr(taskcard.runtime, "trial_interrupt", None)
    has_interrupt = bool(ti and getattr(ti, "detection_condition", None))
    return {"conditions": conditions, "key_map": km, "has_interrupt": has_interrupt}


async def generate(url: str, label: str, client, taskcards_dir: str = "taskcards",
                   out_root: Path = Path("naive_programs"),
                   max_retries: int = 2) -> Path:
    bundle = await scrape_experiment_source(url=url, hint="")
    taskcard = _load_structural_taskcard(label, taskcards_dir)
    facts = mechanical_facts(taskcard)
    prompt = _TEMPLATE.read_text().format(
        PAGE_SOURCE=bundle.combined_source,
        CONDITIONS=", ".join(facts["conditions"]),
        KEY_MAP=json.dumps(facts["key_map"]),
        INTERRUPT_NOTE=_INTERRUPT_NOTE if facts["has_interrupt"] else "",
    )
    out_dir = Path(out_root) / label
    out_dir.mkdir(parents=True, exist_ok=True)

    last_failures: list[str] = []
    for attempt in range(1 + max_retries):
        user = prompt if attempt == 0 else (
            prompt + "\n\n## Previous attempt failed the MECHANICAL gate\n"
            + "\n".join(f"- {f}" for f in last_failures)
            + "\nFix ONLY these mechanical problems.")
        reply = await client.complete(system="", user=user, max_tokens=16384)
        code = extract_python_block(reply.text)
        sha = hashlib.sha256(code.encode()).hexdigest()
        prog = out_dir / f"{sha}.py"
        prog.write_text(code)
        (out_dir / f"{sha}.transcript.json").write_text(json.dumps({
            "model": client.model, "attempt": attempt, "url": url,
            "label": label, "prompt": user, "response": reply.text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        report = run_gate(prog, conditions=facts["conditions"],
                          key_map=facts["key_map"],
                          has_interrupt=facts["has_interrupt"])
        (out_dir / f"{sha}.simgate.json").write_text(
            json.dumps(report.to_dict(), indent=2))
        if report.passed:
            return prog
        last_failures = report.failures
    raise RuntimeError(
        f"naive program for {label!r} failed the mechanical gate after "
        f"{1 + max_retries} attempts: {last_failures}")


@click.command()
@click.argument("url")
@click.option("--label", required=True)
@click.option("--model", default="claude-fable-5", show_default=True)
@click.option("--taskcards-dir", default="taskcards", show_default=True)
def main(url: str, label: str, model: str, taskcards_dir: str):
    """Generate the SP21 naive-arm participant program for LABEL."""
    client = build_default_client(model)
    path = asyncio.run(generate(url, label, client, taskcards_dir=taskcards_dir))
    click.echo(f"PASS -> {path}")
```

Note for the implementer: verify the two look-up points flagged in the code — the `SourceBundle` text field name and the TaskCard loader helper name — with grep before running; adjust the two call sites (not the tests, which mock both).

- [ ] **Step 4: Run tests, register script, full suite, commit**

Add to `pyproject.toml`: `experiment-bot-naive-gen = "experiment_bot.behavior.gen_cli:main"`.

```bash
uv run pytest tests/test_naive_gen.py -q    # expected: 4 passed
uv run pytest -q                            # expected: 901 passed, 7 skipped
git add src/experiment_bot/behavior/gen_cli.py pyproject.toml tests/test_naive_gen.py
git commit -m "feat(behavior): SP21 generation CLI — archive, gate, bounded mechanical retries

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Pre-registration + collection script

**Files:**
- Create: `docs/preregistration-naive.md`
- Create: `scripts/naive_run.sh`
- Test: none (docs + script; the script's session loop reuses the tested CLI)

**Interfaces:**
- Consumes: `experiment-bot-naive-gen`, `experiment-bot ... --behavior-program`, `scripts/frozen_run.sh` (expert-v2 re-collection = `scripts/frozen_run.sh 30 output_expert_v2`).

- [ ] **Step 1: Write `docs/preregistration-naive.md`**

Transcribe the spec's "Experiment protocol" section verbatim into the same format as `docs/preregistration.md` (goal, design table with the four paradigm URLs + pinned structural-card hashes 45751cfe / e29f22de / b16c7891 / 6fc729c3, arms, N=30, seed scheme SEED_BASE 730000 + offsets naive: stroop 5000 / stop_signal 6000 / cognitionrun 7000 / stopit 8000, measures = the frozen battery unchanged, exclusions incl. the ≥3-live-failures paradigm-failure rule, no-behavioral-iteration rule, primary/exploratory split). State explicitly: "This document is committed BEFORE any generation call; generation transcripts are data."

- [ ] **Step 2: Write `scripts/naive_run.sh`** (mirror `scripts/frozen_run.sh`'s stream pattern)

```bash
#!/usr/bin/env bash
# SP21 naive-arm collection: generate (once, gated) + N seeded sessions per
# paradigm. Idempotent by seed. Pre-registration: docs/preregistration-naive.md
set -uo pipefail
cd "$(dirname "$0")/.."
N="${1:-30}"
export EXPERIMENT_BOT_OUTPUT_DIR="$(pwd)/${2:-output_naive}"
mkdir -p "$EXPERIMENT_BOT_OUTPUT_DIR"
SEED_BASE=730000

gen_if_missing() {  # label url
  local label="$1" url="$2"
  if ! ls "naive_programs/$label/"*.py >/dev/null 2>&1; then
    uv run experiment-bot-naive-gen "$url" --label "$label" || return 1
  fi
}

run_stream() {  # label url structural_hash seed_offset
  local label="$1" url="$2" hash="$3" offset="$4" log="/tmp/naive_${1}.log"
  : > "$log"
  local prog
  prog=$(ls "naive_programs/$label/"*.py | head -1)
  for i in $(seq 1 "$N"); do
    local seed=$(( SEED_BASE + offset + i ))
    echo "[$label] session $i/$N seed=$seed $(date +%H:%M:%S)" >> "$log"
    uv run experiment-bot "$url" --label "$label" --headless --no-calibration \
      --taskcard-sha256 "$hash" --seed "$seed" \
      --behavior-program "$prog" >> "$log" 2>&1 \
      && echo "[$label] $i ok" >> "$log" || echo "[$label] $i FAIL rc=$?" >> "$log"
  done
  echo "[$label] DONE" >> "$log"
}

gen_if_missing expfactory_stroop      "https://deploy.expfactory.org/preview/10/" &
gen_if_missing expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  &
gen_if_missing cognitionrun_stroop    "https://strooptest.cognition.run/"         &
gen_if_missing stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" &
wait

run_stream expfactory_stroop      "https://deploy.expfactory.org/preview/10/" 45751cfe 5000 &
run_stream expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  e29f22de 6000 &
run_stream cognitionrun_stroop    "https://strooptest.cognition.run/"         b16c7891 7000 &
run_stream stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 6fc729c3 8000 &
wait
echo "== NAIVE ARM DONE =="
```

`chmod +x scripts/naive_run.sh`. (Expfactory preview URLs are ephemeral — re-verify before the live run, per `reference_dev_paradigm_urls`.)

- [ ] **Step 3: Full suite, commit**

```bash
uv run pytest -q   # expected: 901 passed, 7 skipped (unchanged)
git add docs/preregistration-naive.md scripts/naive_run.sh
git commit -m "docs+scripts: SP21 naive-arm pre-registration and collection script

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Out of scope for this plan (live phases, run after implementation lands)

1. Verify the four dev URLs are live (redeploy expfactory previews if expired).
2. Expert-v2 re-collection: `scripts/frozen_run.sh 30 output_expert_v2`.
3. Naive generation + collection: `scripts/naive_run.sh 30` — **read the four generated programs before the live sessions** (archival review, not behavioral veto).
4. Analysis: `experiment-bot-per-subject --label all --output-dir output_naive ...` and the same against `output_expert_v2`; three-way write-up per pre-reg.

These are operational runs under the pre-registration, not code tasks; they follow the ×1-before-×5 verification discipline (one live session per paradigm before the full stream).

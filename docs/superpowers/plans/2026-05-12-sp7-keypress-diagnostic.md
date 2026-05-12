# SP7 — Keypress diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Investigation-only SP. Add a generic page-level keypress listener and per-trial drain to the executor; re-run Flanker; analyze the captured keypress data alongside bot logs and platform CSV to name the layer responsible for the per-trial response_key mismatch surfaced in SP6.

**Architecture:** Two touch-points in `src/experiment_bot/core/executor.py`: a session-start JS injection that installs `document.addEventListener('keydown', ...)` writing to `window.__bot_keydown_log`; a per-trial drain that reads-and-clears that log and adds two new fields to each trial entry. Plus one new paradigm-agnostic analysis script `scripts/keypress_audit.py` that uses the existing `PLATFORM_ADAPTERS` dispatch to compare bot's logged keys with the page's received keys with the platform's recorded responses.

**Tech Stack:** Python 3.12 / uv; pytest + pytest-asyncio + AsyncMock; Playwright; same executor as SP6.

Reference: spec at `docs/superpowers/specs/2026-05-12-sp7-keypress-diagnostic-design.md`. SP6 background at `docs/sp6-results.md`. User feedback: instrumentation and analysis must be paradigm-agnostic (saved at `~/.claude/projects/.../memory/feedback_avoid_paradigm_overfitting.md`).

**Held-out policy reminder:** SP7 is investigation-only. No behavioral fix ships here. If Task 8's analysis makes the fix obvious, the fix lives in SP8.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/experiment_bot/core/executor.py` | Listener injection + per-trial drain + extended log entry | Modified (Tasks 1, 2, 3) |
| `tests/test_executor_keypress_diagnostic.py` | Unit tests | Created (Tasks 1, 2, 3) |
| `scripts/keypress_audit.py` | Generic 4-way alignment analysis | Created (Task 4) |
| `output/flanker_rdoc/<timestamp>/` × 5 | Re-run sessions | Generated (Task 6; gitignored) |
| `docs/sp7-results.md` | Investigation report | Created (Task 8) |
| `CLAUDE.md` | Sub-project history | Modified (Task 9) |

`OutputWriter.log_trial` already accepts an arbitrary dict (`writer.py:32`), so no writer changes needed.

---

## Task 0: Set up SP7 worktree

**Files:**
- Worktree: `.worktrees/sp7` on branch `sp7/keypress-diagnostic`, branched off tag `sp6-complete`

Steps 1-3 below have already been executed by the controller. Subsequent tasks assume the worktree exists at `.worktrees/sp7` and the engineer is operating inside it.

- [x] **Step 1: `git worktree add .worktrees/sp7 -b sp7/keypress-diagnostic sp6-complete`** (controller)
- [x] **Step 2: Cherry-pick SP7 spec + this plan onto sp7 branch** (controller)
- [x] **Step 3: `uv sync` and verify clean baseline (517 passed)** (controller)

- [ ] **Step 4: Verify the worktree's clean state**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp7
git status
git log --oneline -5
```

Expected: clean working tree on `sp7/keypress-diagnostic`; log shows two cherry-picked docs commits on top of `sp6-complete`.

- [ ] **Step 5: Verify tests pass**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `517 passed, 3 skipped` (matches sp6-complete state).

---

## Task 1: Add session-start keydown listener injection

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (insert helper + call point after `_navigator.execute_all`)
- Create: `tests/test_executor_keypress_diagnostic.py`

Add a helper method `_install_keydown_listener(page)` that evaluates the listener-installation JS. Call it from `run()` immediately after `await self._navigator.execute_all(page, self._config.navigation)` (around `executor.py:306`).

- [ ] **Step 1: Read the surrounding context**

```bash
sed -n '295,315p' src/experiment_bot/core/executor.py
```

Note the line where `_navigator.execute_all` is called. The new injection happens right after that call, before the trial-polling loop begins.

- [ ] **Step 2: Write failing tests**

Create `tests/test_executor_keypress_diagnostic.py`:

```python
"""Unit tests for SP7 keypress diagnostic instrumentation.

The executor injects a generic page-level keydown listener at session
start and drains it once per trial, adding two new fields to each
trial log entry: `resolved_key_pre_error` (the bot's raw resolution
before `_pick_wrong_key`) and `page_received_keys` (the events the
page's listener captured).

The listener and drain are paradigm-agnostic (document.addEventListener
on 'keydown', no platform-specific assumptions). Stub-based tests
verify the executor evaluates the right JS without invoking a real
Playwright page.
"""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from experiment_bot.core.executor import TaskExecutor


def _stub_executor(poll_interval_ms: int = 10) -> TaskExecutor:
    stub = TaskExecutor.__new__(TaskExecutor)
    timing = SimpleNamespace(poll_interval_ms=poll_interval_ms)
    runtime = SimpleNamespace(timing=timing)
    stub._config = SimpleNamespace(runtime=runtime)
    stub._stimulus_detection_js_cache = {}
    return stub


@pytest.mark.asyncio
async def test_install_keydown_listener_evaluates_correct_js():
    stub = _stub_executor()
    page = AsyncMock()
    await stub._install_keydown_listener(page)
    assert page.evaluate.call_count == 1
    js = page.evaluate.call_args.args[0]
    # Listener installation JS must:
    # - Initialize the storage array.
    # - Attach a 'keydown' listener.
    # - Capture key, code, and time per event.
    # - Use capture-phase (third arg true) so the listener sees events
    #   before any application-level handler.
    assert "window.__bot_keydown_log" in js
    assert "addEventListener('keydown'" in js
    assert "e.key" in js and "e.code" in js
    assert "Date.now()" in js
    assert ", true)" in js  # capture-phase flag


@pytest.mark.asyncio
async def test_install_keydown_listener_resets_log():
    """A second injection re-initializes window.__bot_keydown_log (idempotent)."""
    stub = _stub_executor()
    page = AsyncMock()
    await stub._install_keydown_listener(page)
    await stub._install_keydown_listener(page)
    # Both injections must reset the log: every call starts with `window.__bot_keydown_log = []`.
    for call in page.evaluate.call_args_list:
        js = call.args[0]
        assert "window.__bot_keydown_log = []" in js
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v 2>&1 | tail -10
```

Expected: both tests FAIL with `AttributeError: 'TaskExecutor' object has no attribute '_install_keydown_listener'`.

- [ ] **Step 4: Implement the helper and the call site**

Edit `src/experiment_bot/core/executor.py`. Add the helper method (place it near `_stimulus_detection_js` or other private helpers):

```python
    async def _install_keydown_listener(self, page) -> None:
        """Inject a paradigm-agnostic keydown listener at session start.

        The listener writes to `window.__bot_keydown_log` (an array of
        {key, code, time} dicts). The per-trial drain reads and clears
        this array, surfacing the keys the PAGE's listener actually
        received — useful for diagnosing layer-by-layer mismatches
        between bot.keyboard.press, Playwright dispatch, page handler,
        and platform recording.

        Capture-phase listener so we see the event before any
        application-level handler can modify or stop propagation.
        """
        await page.evaluate(
            "window.__bot_keydown_log = [];"
            " document.addEventListener('keydown', (e) => {"
            "   window.__bot_keydown_log.push({"
            "     key: e.key, code: e.code, time: Date.now()"
            "   });"
            " }, true);"
        )
```

In `run()` (around line 306), find the line `await self._navigator.execute_all(page, self._config.navigation)` (the FIRST occurrence — before the trial-polling loop) and add immediately after:

```python
                await self._install_keydown_listener(page)
```

Make sure the indentation matches the surrounding lines (this is inside a `try`/`async with` block).

- [ ] **Step 5: Run tests to confirm pass**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v 2>&1 | tail -10
```

Expected: both tests PASS.

- [ ] **Step 6: Confirm full suite passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 519 passed, 3 skipped (517 + 2 new).

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_keypress_diagnostic.py
git commit -m "feat(executor): install paradigm-agnostic keydown listener at session start

Installs document.addEventListener('keydown', ...) in capture phase,
writing every event's {key, code, time} into window.__bot_keydown_log.
Generic — works on any HTML page regardless of paradigm or platform
framework. Used by the per-trial drain (next commit) to record what
the page's listener actually received."
```

---

## Task 2: Add per-trial drain helper

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `tests/test_executor_keypress_diagnostic.py`

Add a helper `_drain_keydown_log(page) -> list | None` that reads and clears the log. Returns the list, or None on `page.evaluate` failure.

- [ ] **Step 1: Append failing tests**

Append to `tests/test_executor_keypress_diagnostic.py`:

```python
@pytest.mark.asyncio
async def test_drain_keydown_log_returns_captured_keys():
    stub = _stub_executor()
    page = AsyncMock()
    captured = [{"key": ",", "code": "Comma", "time": 12345}]
    page.evaluate = AsyncMock(return_value=captured)
    result = await stub._drain_keydown_log(page)
    assert result == captured
    page.evaluate.assert_called_once()
    js = page.evaluate.call_args.args[0]
    # Drain JS must:
    # - Read window.__bot_keydown_log (or default to []).
    # - Clear the array after reading (so next trial doesn't double-count).
    assert "window.__bot_keydown_log" in js
    assert "= []" in js  # the reset


@pytest.mark.asyncio
async def test_drain_keydown_log_returns_empty_when_no_events():
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    result = await stub._drain_keydown_log(page)
    assert result == []


@pytest.mark.asyncio
async def test_drain_keydown_log_returns_none_on_evaluate_failure():
    """If page.evaluate raises (page tearing down), drain returns None
    rather than propagating the exception. Trial logging must continue."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    result = await stub._drain_keydown_log(page)
    assert result is None
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v 2>&1 | tail -10
```

Expected: 3 new tests FAIL with `AttributeError: ... no attribute '_drain_keydown_log'`.

- [ ] **Step 3: Implement the drain helper**

Add to `src/experiment_bot/core/executor.py` near `_install_keydown_listener`:

```python
    async def _drain_keydown_log(self, page) -> list | None:
        """Read-and-clear the page-side keydown log. Returns the list
        of {key, code, time} dicts captured since the last drain, or
        None if `page.evaluate` raises (e.g., page navigation tore
        down the context).

        Reset pattern: read existing log, then assign a fresh empty
        array so subsequent trials don't double-count earlier events.
        """
        try:
            return await page.evaluate(
                "(() => {"
                "  const log = window.__bot_keydown_log || [];"
                "  window.__bot_keydown_log = [];"
                "  return log;"
                "})()"
            )
        except Exception:
            return None
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v 2>&1 | tail -10
```

Expected: 5 tests PASS (2 from Task 1 + 3 new).

- [ ] **Step 5: Confirm full suite passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 522 passed, 3 skipped.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_keypress_diagnostic.py
git commit -m "feat(executor): per-trial keydown-log drain helper

Reads window.__bot_keydown_log and resets it to []. Returns the
captured events (possibly empty), or None if page.evaluate raises
(page teardown during navigation). The reset pattern prevents
subsequent trials from double-counting earlier keypresses."
```

---

## Task 3: Wire drain into trial loop + extend log_trial

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (the trial-response block around L780-800)
- Modify: `tests/test_executor_keypress_diagnostic.py`

Add `resolved_key_pre_error` and `page_received_keys` to the trial's log entry.

- [ ] **Step 1: Read the current trial-response block**

```bash
grep -nE "_pick_wrong_key|response_key.*resolved_key|page\.keyboard\.press" src/experiment_bot/core/executor.py | head -10
```

The relevant block is around L788-800 (the `if is_error: resolved_key = self._pick_wrong_key(...)` and the keyboard press + log_trial call). Read those lines:

```bash
sed -n '785,815p' src/experiment_bot/core/executor.py
```

You should see:

```python
        if is_error:
            resolved_key = self._pick_wrong_key(resolved_key)
        await page.keyboard.press(resolved_key)

        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": resolved_key,
            ...
        })
```

- [ ] **Step 2: Write failing integration test**

Append to `tests/test_executor_keypress_diagnostic.py`:

```python
@pytest.mark.asyncio
async def test_log_trial_includes_new_keypress_fields():
    """After Task 3 wiring: the trial log entry must include
    resolved_key_pre_error and page_received_keys."""
    from unittest.mock import MagicMock
    stub = _stub_executor()
    # Stub _writer to capture log_trial calls.
    log_calls = []
    stub._writer = MagicMock()
    stub._writer.log_trial = lambda payload: log_calls.append(payload)
    # Stub page with a drainable log.
    page = AsyncMock()
    captured_keys = [{"key": ",", "code": "Comma", "time": 1000}]
    page.evaluate = AsyncMock(return_value=captured_keys)

    # Call the drain + log function directly. The implementation
    # provides a helper like _log_trial_with_keypress_diag that wraps
    # the existing log_trial call.
    payload = {
        "trial": 1,
        "stimulus_id": "go",
        "condition": "congruent",
        "response_key": ",",  # post-_pick_wrong_key
    }
    # The wrapper should accept the existing payload + an extra
    # resolved_key_pre_error arg + the page, and write augmented payload.
    await stub._log_trial_with_keypress_diag(
        page=page,
        base_payload=payload,
        resolved_key_pre_error=".",
    )
    assert len(log_calls) == 1
    written = log_calls[0]
    # Existing fields preserved
    assert written["trial"] == 1
    assert written["response_key"] == ","
    # New fields added
    assert written["resolved_key_pre_error"] == "."
    assert written["page_received_keys"] == captured_keys


@pytest.mark.asyncio
async def test_log_trial_with_keypress_diag_handles_drain_failure():
    """If drain fails, page_received_keys=None but trial still logs."""
    from unittest.mock import MagicMock
    stub = _stub_executor()
    log_calls = []
    stub._writer = MagicMock()
    stub._writer.log_trial = lambda payload: log_calls.append(payload)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))

    payload = {"trial": 1, "response_key": ","}
    await stub._log_trial_with_keypress_diag(
        page=page,
        base_payload=payload,
        resolved_key_pre_error=".",
    )
    assert log_calls[0]["page_received_keys"] is None
    assert log_calls[0]["trial"] == 1
    assert log_calls[0]["response_key"] == ","
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v 2>&1 | tail -15
```

Expected: 2 new tests FAIL with `AttributeError: ... no attribute '_log_trial_with_keypress_diag'`.

- [ ] **Step 4: Implement the wrapper helper**

Add to `src/experiment_bot/core/executor.py` near `_drain_keydown_log`:

```python
    async def _log_trial_with_keypress_diag(
        self,
        *,
        page,
        base_payload: dict,
        resolved_key_pre_error: str | None,
    ) -> None:
        """Drain the page's keydown log and write an augmented trial
        entry. Adds two fields to `base_payload`:

        - resolved_key_pre_error: the bot's response_key_js result
          before `_pick_wrong_key` flipped it for an intended-error
          trial. When intended_error=False, this equals
          base_payload['response_key'].
        - page_received_keys: list of {key, code, time} the page's
          listener captured since the last drain. None if drain
          failed (page teardown).

        Both fields are paradigm-agnostic — they describe the
        runtime layer between bot and platform, not paradigm content.
        """
        page_received_keys = await self._drain_keydown_log(page)
        payload = dict(base_payload)
        payload["resolved_key_pre_error"] = resolved_key_pre_error
        payload["page_received_keys"] = page_received_keys
        self._writer.log_trial(payload)
```

- [ ] **Step 5: Wire the wrapper into `_execute_trial`**

Find the trial-response block. The existing structure (around L785-810) is approximately:

```python
        if is_error:
            resolved_key = self._pick_wrong_key(resolved_key)
        await page.keyboard.press(resolved_key)

        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": resolved_key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
            "intended_error": is_error,
            "rt_distribution": rt_condition,
            "cue": cue,
        })
```

Replace it with:

```python
        resolved_key_pre_error = resolved_key  # capture pre-flip
        if is_error:
            resolved_key = self._pick_wrong_key(resolved_key)
        await page.keyboard.press(resolved_key)

        await self._log_trial_with_keypress_diag(
            page=page,
            base_payload={
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": resolved_key,
                "sampled_rt_ms": round(rt_ms, 1),
                "actual_rt_ms": round(actual_rt, 1),
                "omission": False,
                "intended_error": is_error,
                "rt_distribution": rt_condition,
                "cue": cue,
            },
            resolved_key_pre_error=resolved_key_pre_error,
        )
```

Note: `resolved_key_pre_error` is captured **before** `_pick_wrong_key` may overwrite `resolved_key`.

- [ ] **Step 6: Run tests to confirm pass**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v 2>&1 | tail -15
```

Expected: 7 tests PASS (5 from Tasks 1-2 + 2 new).

- [ ] **Step 7: Full suite must still pass**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 524 passed, 3 skipped.

If existing trial-related tests break, the most likely cause is that `_execute_trial`'s `log_trial` call shape changed. Inspect failures and either:
- Update the test to use the new wrapper helper if the test was asserting log_trial-call structure (rare).
- Confirm the test passes via the wrapper which now uses `log_trial` under the hood (most likely).

- [ ] **Step 8: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_keypress_diagnostic.py
git commit -m "feat(executor): wire keypress diagnostic into trial log

Captures resolved_key BEFORE _pick_wrong_key may flip it
(resolved_key_pre_error) and reads-and-clears the page's keydown
log after the press (page_received_keys). Adds both as new fields
on each trial's log entry. Existing fields and trial flow unchanged
otherwise.

Paradigm-agnostic — applies to any paradigm regardless of platform
framework. Used by scripts/keypress_audit.py (next commit) to name
the layer responsible for SP6's per-trial response_key mismatch."
```

---

## Task 4: Create `scripts/keypress_audit.py`

**Files:**
- Create: `scripts/keypress_audit.py`

Paradigm-agnostic analysis script. Uses `PLATFORM_ADAPTERS` dispatch so it works for any paradigm with a registered adapter.

- [ ] **Step 1: Verify the scripts directory exists or create it**

```bash
mkdir -p scripts
```

- [ ] **Step 2: Write the script**

Create `scripts/keypress_audit.py`:

```python
#!/usr/bin/env python3
"""SP7 keypress audit — paradigm-agnostic 4-way alignment analysis.

Compares, per trial:
  - bot_intended_correct_key (bot's resolved_key_pre_error)
  - bot_pressed_key          (bot's response_key, after _pick_wrong_key)
  - page_received_key        (first event in page_received_keys)
  - platform_recorded_resp   (platform CSV 'response' column)
  - platform_expected_resp   (platform CSV 'correct_response' column)

Uses PLATFORM_ADAPTERS dispatch so it works for any registered
paradigm (Flanker, n-back, stop-signal, stroop, future paradigms).

Usage:
  uv run python scripts/keypress_audit.py --label <task-name> [--output-dir output]
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from experiment_bot.validation.platform_adapters import PLATFORM_ADAPTERS


def _bot_stimulus_entries(bot_log: list[dict]) -> list[dict]:
    """Filter bot_log to actual stimulus-response entries."""
    return [
        t for t in bot_log
        if t.get("intended_error") in (True, False)
        and t.get("response_key") is not None
    ]


def _first_key(events) -> str | None:
    """Return the first {key} from a page_received_keys list, or None."""
    if not events:
        return None
    try:
        return events[0].get("key")
    except (AttributeError, IndexError, TypeError):
        return None


def _audit_session(ses_dir: Path, label: str) -> dict:
    """Run the 4-way audit on a single session. Returns counts."""
    bot_log = json.loads((ses_dir / "bot_log.json").read_text())
    csv_path = ses_dir / "experiment_data.csv"
    if not csv_path.exists():
        # Some platforms only emit JSON.
        return {"error": f"no experiment_data.csv in {ses_dir}"}
    plat_rows = list(csv.DictReader(open(csv_path)))
    # Use the registered adapter to filter platform rows to test trials
    # (the adapter returns canonical {condition, rt, correct, omission}
    # but we want the full CSV rows here for the comparison — so we
    # filter by the same trial_id == 'test_trial' convention manually
    # OR rely on the order: adapter trials are in CSV order, so we can
    # cross-reference).
    adapter = PLATFORM_ADAPTERS.get(label)
    if not adapter:
        return {"error": f"no adapter registered for label {label!r}"}
    canonical_trials = adapter(ses_dir)
    # Filter CSV rows that the adapter would have selected. Convention:
    # for expfactory-family adapters, trial_id == 'test_trial'.
    test_rows = [r for r in plat_rows if r.get("trial_id") == "test_trial"]
    bot = _bot_stimulus_entries(bot_log)

    n = min(len(bot), len(test_rows))
    counts = Counter()
    for i in range(n):
        b = bot[i]
        p = test_rows[i]
        bot_intended = b.get("resolved_key_pre_error")
        bot_pressed = b.get("response_key")
        page_received = _first_key(b.get("page_received_keys"))
        plat_recorded = p.get("response")
        plat_expected = p.get("correct_response")

        # Pairwise agreement
        counts["bot_pressed == page_received"] += (bot_pressed == page_received)
        counts["page_received == platform_recorded"] += (page_received == plat_recorded)
        counts["bot_pressed == platform_recorded"] += (bot_pressed == plat_recorded)
        counts["bot_intended == platform_expected"] += (bot_intended == plat_expected)

    return {
        "n_trials": n,
        "n_bot_log_entries": len(bot),
        "n_platform_trials": len(test_rows),
        "agreements": dict(counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True,
                        help="Paradigm label (matches output/<label>/ and PLATFORM_ADAPTERS key)")
    parser.add_argument("--output-dir", default="output",
                        help="Top-level output directory (default: output)")
    args = parser.parse_args()

    label_dir = Path(args.output_dir) / args.label
    if not label_dir.exists():
        raise SystemExit(f"no output directory: {label_dir}")

    print(f"=== SP7 keypress audit: {args.label} ===")
    print()
    total = Counter()
    total_n = 0
    for ses in sorted(label_dir.iterdir()):
        if not ses.is_dir():
            continue
        result = _audit_session(ses, args.label)
        if "error" in result:
            print(f"  {ses.name}: ERROR — {result['error']}")
            continue
        n = result["n_trials"]
        total_n += n
        a = result["agreements"]
        print(f"  {ses.name}: n={n} (bot_log={result['n_bot_log_entries']}, plat={result['n_platform_trials']})")
        for key, val in a.items():
            pct = 100 * val / n if n else 0
            print(f"    {key}: {val}/{n} = {pct:.1f}%")
            total[key] += val
        print()

    print(f"AGGREGATE across {total_n} trials:")
    for key, val in total.items():
        pct = 100 * val / total_n if total_n else 0
        print(f"  {key}: {val}/{total_n} = {pct:.1f}%")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Make the script executable + verify imports work**

```bash
chmod +x scripts/keypress_audit.py
uv run python -c "
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('keypress_audit', Path('scripts/keypress_audit.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('script imports cleanly')
"
```

Expected: prints `script imports cleanly`.

- [ ] **Step 4: Smoke-run with --label that has no output dir**

```bash
uv run python scripts/keypress_audit.py --label expfactory_flanker 2>&1 | head -5
```

Expected: error message like `no output directory: output/expfactory_flanker` (the sessions haven't been re-run yet under SP7 instrumentation; the script correctly bails).

If output/flanker_rdoc/ from a previous SP run is present (gitignored, so likely not), the script will run but report `page_received_keys=None` everywhere since pre-SP7 sessions don't have that field. That's fine — informational output, not a failure.

- [ ] **Step 5: Commit**

```bash
git add scripts/keypress_audit.py
git commit -m "feat(scripts): paradigm-agnostic keypress audit script

scripts/keypress_audit.py compares per-trial:
- bot's intended correct key (resolved_key_pre_error)
- bot's pressed key (response_key, after _pick_wrong_key)
- page's received key (first event in page_received_keys)
- platform's recorded response
- platform's expected response

Uses PLATFORM_ADAPTERS dispatch so it applies to any registered
paradigm (Flanker, n-back, stop-signal, stroop, future paradigms).
No paradigm-specific column names or condition labels hardcoded."
```

---

## Task 5: Full-suite regression check

**Files:**
- None modified

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest 2>&1 | tail -10
```

Expected: 524 passed, 3 skipped, 0 failures.

- [ ] **Step 2: Confirm `git status` is clean**

```bash
git status
```

Expected: nothing to commit, working tree clean.

- [ ] **Step 3: No commit needed (verification only).**

---

## Task 6: Re-run 5 Flanker smoke sessions

**Files:**
- Working: `output/flanker_rdoc/<timestamp>/` × 5 (gitignored)
- Working: `.reasoner-logs/sp7_flanker_sessions.log`

The sessions exercise the new instrumentation; the bot_log entries will now include `resolved_key_pre_error` and `page_received_keys`.

- [ ] **Step 1: Run 5 sessions**

```bash
mkdir -p .reasoner-logs
for seed in 7001 7002 7003 7004 7005; do
  echo "=== Flanker session seed=$seed ==="
  uv run experiment-bot "https://deploy.expfactory.org/preview/3/" \
    --label expfactory_flanker --headless --seed "$seed" \
    >> .reasoner-logs/sp7_flanker_sessions.log 2>&1
  echo "  exit=$?"
done
```

Wall time: ~25-75 min.

- [ ] **Step 2: Confirm 5 session directories exist**

```bash
find output/flanker_rdoc -mindepth 1 -maxdepth 1 -type d | wc -l
```

Expected: `5`.

- [ ] **Step 3: Sanity-check that bot_log entries have the new fields**

```bash
uv run python << 'PY'
import json
from pathlib import Path
ses = sorted(Path('output/flanker_rdoc').iterdir())[-1]  # most recent
bot_log = json.loads((ses / 'bot_log.json').read_text())
# Find the first stimulus-response entry
sample = next((t for t in bot_log if t.get('intended_error') in (True, False)), None)
if sample is None:
    print('ERROR: no stimulus-response entries')
else:
    print(f'session: {ses.name}')
    print(f'  has resolved_key_pre_error: {"resolved_key_pre_error" in sample}')
    print(f'  has page_received_keys: {"page_received_keys" in sample}')
    print(f'  sample resolved_key_pre_error: {sample.get("resolved_key_pre_error")!r}')
    print(f'  sample page_received_keys: {sample.get("page_received_keys")}')
PY
```

Expected output:
```
has resolved_key_pre_error: True
has page_received_keys: True
sample resolved_key_pre_error: ',' (or some single key)
sample page_received_keys: [{'key': ',', 'code': 'Comma', 'time': ...}, ...]
```

If `page_received_keys` is empty list (`[]`) or None for every trial, the listener may not be capturing events — investigate before continuing (the listener injection might be failing silently).

- [ ] **Step 4: No commit yet** (output/ is gitignored).

---

## Task 7: Run the keypress audit

**Files:**
- Working: stdout (captured for Task 8's report)

- [ ] **Step 1: Run the audit script**

```bash
uv run python scripts/keypress_audit.py --label flanker_rdoc --output-dir output 2>&1 | tee .reasoner-logs/sp7_keypress_audit.txt
```

Expected output structure (numbers will vary):

```
=== SP7 keypress audit: flanker_rdoc ===

  2026-05-12_HH-MM-SS: n=120 (bot_log=125, plat=120)
    bot_pressed == page_received: 120/120 = 100.0%
    page_received == platform_recorded: 60/120 = 50.0%
    bot_pressed == platform_recorded: 60/120 = 50.0%
    bot_intended == platform_expected: 60/120 = 50.0%
  ...

AGGREGATE across N trials:
  bot_pressed == page_received: <percentage>
  page_received == platform_recorded: <percentage>
  bot_pressed == platform_recorded: <percentage>
  bot_intended == platform_expected: <percentage>
```

Interpretation guide for Task 8's analysis:

- **bot_pressed == page_received ≈ 100%**: Playwright is faithfully delivering the bot's intended keypress to the page's keydown handler. → root cause is downstream (platform recording).
- **bot_pressed == page_received < 90%**: Playwright is delivering a different key than what `keyboard.press(...)` was called with. → root cause is between bot and Playwright (key encoding, layout).
- **page_received == platform_recorded ≈ 100%**: The platform records what the page received. → root cause is upstream (bot's resolved_key).
- **page_received == platform_recorded < 90%**: The platform's recording mechanism doesn't reflect the page's keydown events. → root cause is in the platform's response capture (different mechanism than keydown).
- **bot_intended == platform_expected ≈ 50%**: The bot's response_key_js evaluation is essentially random relative to the platform's expected key. → root cause is at the response_key_js layer (Stage 1 extraction or runtime evaluation timing).

- [ ] **Step 2: No commit yet** (audit output feeds Task 8's report).

---

## Task 8: Write `docs/sp7-results.md`

**Files:**
- Create: `docs/sp7-results.md`

Name the responsible layer based on the audit data.

- [ ] **Step 1: Write the report**

Create `docs/sp7-results.md` using this template. Fill in the placeholders with the actual numbers from Task 7's audit output:

```markdown
# SP7 — Keypress diagnostic results

**Date:** 2026-05-12 (or actual run date)
**Spec:** `docs/superpowers/specs/2026-05-12-sp7-keypress-diagnostic-design.md`
**Plan:** `docs/superpowers/plans/2026-05-12-sp7-keypress-diagnostic.md`
**Branch:** `sp7/keypress-diagnostic` (off `sp6-complete`)
**Tag (after this report lands):** `sp7-complete`

## Goal

Investigation-only SP. SP6 closed the over-firing trial-detection bug, but per-trial alignment between `bot.intended_error` and `platform.correct_trial=0` remained poor (intersection 0 vs chance 2.4 in SP6). Further inspection revealed the bot's logged `response_key` doesn't match the platform's recorded `response` on most trials. SP7 instruments page-level keypress capture to name the responsible layer.

## Procedure

5 Flanker sessions (seeds 7001-7005) on the SP7 worktree with `_install_keydown_listener` injecting a generic capture-phase keydown listener at session start, and `_drain_keydown_log` reading and clearing the log per trial. Each trial entry in bot_log now includes:
- `resolved_key_pre_error`: bot's response_key_js result before `_pick_wrong_key`
- `page_received_keys`: events the page's listener captured for this trial

Generic `scripts/keypress_audit.py` aligned bot's entries with platform's test trials 1:1 (post-SP6 alignment is clean) and produced a 4-way agreement table.

## Headline numbers (aggregate across 5 sessions, ~600 trials)

| Comparison | Agreement | Reading |
|---|---|---|
| `bot_pressed == page_received` | <pct>% | <Playwright faithful?> |
| `page_received == platform_recorded` | <pct>% | <platform recording faithful?> |
| `bot_pressed == platform_recorded` | <pct>% | end-to-end |
| `bot_intended == platform_expected` | <pct>% | <bot's response_key_js correct?> |

## Responsible layer

[Fill in based on data. Pick the most likely letter from the success criterion:]

- **(a) Bot resolves the wrong key** to begin with. Evidence: `bot_intended == platform_expected` is ~50% (essentially random), suggesting `response_key_js` evaluation is unreliable. Fix at Stage 1 extraction quality or runtime evaluation timing.
- **(b) `_pick_wrong_key` picks the wrong wrong-key.** Unlikely in 2-key paradigms; would show as `bot_pressed != opposite(bot_intended)` on intended_error=True trials.
- **(c) Playwright dispatches a different key than passed.** Evidence: `bot_pressed != page_received` on many trials. Fix at the bot↔Playwright layer (e.g., explicit key naming, key event configuration).
- **(d) Platform records from a non-keydown source.** Evidence: `page_received == platform_recorded` < 90%. Fix at the bot's polling/wait-for-response logic.

[Name the layer with the strongest evidence. If multiple apply, list each with its proportion.]

## Implications

[Fill in based on layer:]

- If (a): Stage 1's `response_key_js` extraction needs to handle dynamic-key paradigms more reliably. SP8 could add Stage 1 prompt examples for response_key_js OR add a runtime fallback that reads platform-expected response if available.
- If (c): The `page.keyboard.press(key)` invocation needs a different key-spec format (Playwright supports `keyboard.press('Comma')` vs raw character; try the explicit name).
- If (d): The bot's response timing needs investigation — the keydown happens after the platform's response window has closed (event captured by listener but not by platform).

## SP8 scope candidate

[One paragraph naming the next fix's scope, grounded in the data above. Honor the user-feedback constraint: any fix must generalize across paradigms, not target Flanker specifically.]

## Internal CI gate status

Test suite at sp7-complete: 524 passed, 3 skipped (was 517 at sp6-complete; +7 new tests covering the listener install, drain, and log-trial wrapper).

✅ Internal gate: PASS.

## Status

[Fill in based on whether the audit named the layer cleanly. Tag `sp7-complete` on the commit landing this report.]
```

Replace each `<...>` and `[Fill in: ...]` with the actual numbers and prose from Task 7's audit output. Be precise about which letter the data supports.

- [ ] **Step 2: Sanity-check no placeholders remain**

```bash
grep -nE "<pct>|<Playwright|<platform|<bot|\[Fill in|\[Name the layer|\[One paragraph" docs/sp7-results.md
```

Expected: no output. If any remain, fill them in from the audit data.

- [ ] **Step 3: Commit**

```bash
git add docs/sp7-results.md
git commit -m "docs(sp7): keypress diagnostic results

Names the layer responsible for SP6's per-trial response_key
mismatch (bot-logged key vs platform-recorded response) based on
the 4-way agreement audit across 5 Flanker sessions. Recommends
SP8 scope grounded in the data."
```

---

## Task 9: Tag, push, update CLAUDE.md

**Files:**
- Tag: `sp7-complete`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify clean state**

```bash
git status
uv run pytest 2>&1 | tail -3
```

Expected: clean working tree; 524 passed, 3 skipped.

- [ ] **Step 2: Tag**

```bash
git tag -a sp7-complete -m "$(cat <<'EOF'
SP7 (keypress diagnostic) — milestone tag

Investigation-only SP. Added paradigm-agnostic page-level keydown
listener (capture-phase) at session start, per-trial drain reading
window.__bot_keydown_log, and two new bot_log fields:
resolved_key_pre_error and page_received_keys.

Generic analysis script (scripts/keypress_audit.py) uses
PLATFORM_ADAPTERS dispatch and produces a 4-way agreement table
applicable to any paradigm.

Internal: 7 new tests; suite at 524 passed (was 517).

External: 5 Flanker re-run sessions; 4-way audit names the layer
responsible for SP6's per-trial response_key mismatch. See
docs/sp7-results.md for the layer attribution and SP8 scope
recommendation.

Per user feedback: instrumentation and analysis are
paradigm-agnostic. The Flanker re-run is the test vehicle but the
mechanism applies to any paradigm-platform.
EOF
)"
```

- [ ] **Step 3: Push**

```bash
git push -u origin sp7/keypress-diagnostic
git push origin sp7-complete
```

- [ ] **Step 4: Update CLAUDE.md sub-project history**

Edit `CLAUDE.md`. Find the SP7 candidate entry that SP6 added (it currently says "(candidate)"). Replace with:

```markdown
- **SP7**: Keypress diagnostic (investigation-only). Added a
  paradigm-agnostic page-level keydown listener and per-trial drain
  to the executor. Generic `scripts/keypress_audit.py` produces a
  4-way agreement table (bot intended → bot pressed → page received
  → platform recorded). Internal: 524 passed (was 517); +7 tests.
  External: see `docs/sp7-results.md` for the named layer and SP8
  scope recommendation. Tag `sp7-complete`. ✓ Complete.
- **SP8** (candidate): scope determined by SP7's named layer.
```

- [ ] **Step 5: Commit and push CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): mark SP7 complete; SP8 candidate scoped by SP7's findings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Self-review checklist

- **Spec § Goal**: Tasks 1, 2, 3 add executor instrumentation; Task 4 adds analysis script; Tasks 6, 7 generate data; Task 8 names the layer.
- **Spec § Success criterion (internal)**: 7 new tests across Tasks 1, 2, 3. Suite goes 517 → 524.
- **Spec § Success criterion (external)**: Tasks 6, 7, 8 produce the audit and report.
- **Spec § Architecture (2 touch-points + 1 script)**: Tasks 1, 2, 3 cover the executor changes. Task 4 adds the script.
- **Spec § Data flow**: matched in Task 3 wiring + Task 7 audit.
- **Spec § Out of scope**: no behavioral fix; no paradigm-specific instrumentation; no `_extract_json` cleanup. ✓
- **Spec § Sub-project boundary check**: deliverables match; one bounded change set; clear "fix scoped after layer named" rule.

---

## Notes for the implementing engineer

- Held-out policy is binding: SP7 is investigation-only. Even if Task 7's data makes the fix obvious, do NOT ship it in SP7. The point of SP-discipline is that fixes are explicit, scoped, and reviewed in their own cycles.
- The instrumentation is **paradigm-agnostic**. Do NOT add Flanker-specific selectors, condition labels, or assumptions to either the executor changes or the analysis script. Per user feedback: any framework-level change must generalize across paradigms.
- If Task 6's sanity check (Step 3) shows `page_received_keys=None` or `[]` for every trial, the listener injection is failing silently. Most likely causes: the page navigates after injection (re-injection needed) or capture-phase listener is being shadowed by a `stopPropagation` handler. Investigate before continuing.
- Task 3's wiring assumes `_execute_trial` (or equivalent) is the method containing the keyboard press + log_trial call. Verify by grepping for `_pick_wrong_key`; the surrounding function is the right target.
- The analysis script's adapter-dispatch approach means new paradigms just need their adapter registered in `PLATFORM_ADAPTERS` to be analyzable — no script changes needed.

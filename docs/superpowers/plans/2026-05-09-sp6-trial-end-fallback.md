# SP6 — Executor trial-end fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the over-firing trial-detection bug from SP5: when `runtime.timing.response_window_js` is None, the executor falls back to polling the matched stimulus's own detection JS (inverted) until the stimulus stops matching. Prevents the polling loop from re-detecting the same stimulus and double-firing the trial handler.

**Architecture:** Single-file change in `src/experiment_bot/core/executor.py` — extend `_wait_for_trial_end` to accept a fallback JS expression, add `_stimulus_detection_js` helper that builds the fallback from a stimulus's detection method/selector with per-stimulus-id caching, and update the post-trial call site to pass the fallback. Stop_signal unchanged (its `response_window_js` takes precedence).

**Tech Stack:** Python 3.12 / uv; pytest + pytest-asyncio + AsyncMock; same executor as SP5.

Reference: spec at `docs/superpowers/specs/2026-05-09-sp6-trial-end-fallback-design.md`. SP5 root-cause investigation in `docs/sp5-heldout-measurement-results.md`.

**Held-out policy reminder:** Tasks 5-7 re-run Flanker as descriptive evidence. Per spec, the held-out result does not gate SP6 completion. If new misalignment shows up post-fix, that's the next SP's input.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/experiment_bot/core/executor.py` | Trial-end wait logic + new helper | Modified (Tasks 1, 2, 3) |
| `tests/test_executor_trial_end.py` | Unit tests for both helpers | Created (Tasks 1, 2) |
| `output/flanker_rdoc/` | 5 re-run sessions | Generated (Task 5; gitignored) |
| `validation/sp6_heldout/<label>_<timestamp>.json` | Re-validation report | Created (Task 6) |
| `docs/sp6-results.md` | Descriptive measurement report | Created (Task 8) |
| `CLAUDE.md` | Sub-project history | Modified (Task 9) |

---

## Task 0: Set up SP6 worktree

**Files:**
- Worktree: `.worktrees/sp6` on branch `sp6/trial-end-fallback`, branched off tag `sp5-complete`

The sp6 branch additionally cherry-picks the SP6 spec and this plan from `sp5/heldout-measurement`.

Steps 1-3 below have already been executed by the controller. Subsequent tasks assume the worktree exists at `.worktrees/sp6` and the engineer is operating inside it.

- [x] **Step 1: `git worktree add .worktrees/sp6 -b sp6/trial-end-fallback sp5-complete`** (controller)
- [x] **Step 2: Cherry-pick SP6 spec + this plan onto sp6 branch** (controller)
- [x] **Step 3: `uv sync` and verify clean baseline (505 passed)** (controller)

- [ ] **Step 4: Verify worktree's clean state**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp6
git status
git log --oneline -5
```

Expected: clean working tree on `sp6/trial-end-fallback`; recent log shows the two cherry-picked docs commits on top of `sp5-complete`.

- [ ] **Step 5: Verify tests pass**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `505 passed, 3 skipped` (matches sp5-complete state).

---

## Task 1: Extend `_wait_for_trial_end` to accept `fallback_js`

**Files:**
- Modify: `src/experiment_bot/core/executor.py:541-555`
- Create: `tests/test_executor_trial_end.py`

Add a keyword-only `fallback_js` parameter. Use it when `response_window_js` is falsy. When both are None, return immediately. Existing callers remain compatible (positional call with response_window_js).

- [ ] **Step 1: Read the current `_wait_for_trial_end`**

```bash
sed -n '541,560p' src/experiment_bot/core/executor.py
```

Confirm the existing function signature and body match the spec's "currently at L541-555" snippet.

- [ ] **Step 2: Write failing tests**

Create `tests/test_executor_trial_end.py` with these tests for `_wait_for_trial_end` only (the `_stimulus_detection_js` helper tests come in Task 2). The helper is called as a method on `TaskExecutor`; tests construct a minimal stub object that holds the helper and a mocked `_config.runtime.timing.poll_interval_ms`.

```python
"""Unit tests for executor trial-end fallback helpers (SP6).

`_wait_for_trial_end` previously skipped the wait entirely when
`response_window_js` was None. SP6 adds a `fallback_js` parameter so
the executor can poll the stimulus's own detection JS until it stops
matching. This prevents the polling loop from re-detecting the same
stimulus and double-firing the trial handler — the SP5-observed
over-firing bug.
"""
from __future__ import annotations
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.core.executor import TaskExecutor


def _stub_executor(poll_interval_ms: int = 10) -> TaskExecutor:
    """Build a stub TaskExecutor whose only initialized state is the
    `_config.runtime.timing.poll_interval_ms` field used by
    `_wait_for_trial_end` and the cache field used by
    `_stimulus_detection_js`."""
    stub = TaskExecutor.__new__(TaskExecutor)
    timing = SimpleNamespace(poll_interval_ms=poll_interval_ms)
    runtime = SimpleNamespace(timing=timing)
    stub._config = SimpleNamespace(runtime=runtime)
    stub._stimulus_detection_js_cache = {}
    return stub


@pytest.mark.asyncio
async def test_wait_returns_immediately_when_both_none():
    stub = _stub_executor()
    page = AsyncMock()
    await stub._wait_for_trial_end(page, None, fallback_js=None, timeout_s=1.0)
    page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_wait_uses_response_window_js_when_present():
    """response_window_js takes precedence over fallback_js when set."""
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=[True, True, False])
    await stub._wait_for_trial_end(
        page, "preferred_js", fallback_js="fallback_should_be_ignored",
        timeout_s=1.0,
    )
    # Three evaluate calls; all use preferred_js.
    assert page.evaluate.call_count == 3
    for call in page.evaluate.call_args_list:
        assert call.args[0] == "preferred_js"


@pytest.mark.asyncio
async def test_wait_falls_back_to_stimulus_js_when_response_window_none():
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=[True, False])
    await stub._wait_for_trial_end(
        page, None, fallback_js="!!(stim_detect)", timeout_s=1.0,
    )
    assert page.evaluate.call_count == 2
    for call in page.evaluate.call_args_list:
        assert call.args[0] == "!!(stim_detect)"


@pytest.mark.asyncio
async def test_wait_returns_on_timeout():
    """If JS keeps returning truthy, function exits within timeout."""
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    import time as _time
    t0 = _time.monotonic()
    await stub._wait_for_trial_end(
        page, "always_true_js", fallback_js=None, timeout_s=0.05,
    )
    elapsed = _time.monotonic() - t0
    assert elapsed < 0.5, f"timeout not honored: elapsed={elapsed}s"


@pytest.mark.asyncio
async def test_wait_returns_on_evaluate_exception():
    """If page.evaluate raises (page navigated away), function returns gracefully."""
    stub = _stub_executor(poll_interval_ms=1)
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    # Should not raise:
    await stub._wait_for_trial_end(
        page, "any_js", fallback_js=None, timeout_s=1.0,
    )
    page.evaluate.assert_called_once()
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/test_executor_trial_end.py -v 2>&1 | tail -15
```

Expected: 4 of 5 tests FAIL (specifically `test_wait_returns_immediately_when_both_none` and the three `test_wait_falls_back_*` / precedence tests fail because the current signature doesn't accept `fallback_js`). One test (`test_wait_returns_on_timeout`) might pass even pre-fix because the existing function does have a timeout. Doesn't matter — we just need the others to drive the change.

- [ ] **Step 4: Modify `_wait_for_trial_end`**

Edit `src/experiment_bot/core/executor.py`. Find the existing function (around L541-555) and replace it with:

```python
    async def _wait_for_trial_end(
        self,
        page: Page,
        response_window_js: str | None,
        *,
        fallback_js: str | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        """Wait for the trial response window to close.

        Prefer `response_window_js` if present (Stage 1 extraction got
        it). Otherwise fall back to `fallback_js` (typically the matched
        stimulus's own detection JS — wait for it to stop matching).
        When both are None, return immediately (no-op behavior preserved
        for paradigms with neither signal).
        """
        js = response_window_js or fallback_js
        if not js:
            return
        poll_s = self._config.runtime.timing.poll_interval_ms / 1000.0
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                still_active = await page.evaluate(js)
                if not still_active:
                    return
            except Exception:
                # Page context may be torn down by navigation — treat as trial ended
                return
            await asyncio.sleep(poll_s)
```

Note: this signature is backwards-compatible with the existing call site (positional `response_window_js`); the new `fallback_js` is keyword-only with default None. Existing call site at L535-540 still works without modification.

- [ ] **Step 5: Run tests to confirm pass**

```bash
uv run pytest tests/test_executor_trial_end.py -v 2>&1 | tail -15
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Confirm full suite passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 510 passed, 3 skipped (505 + 5 new).

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_trial_end.py
git commit -m "feat(executor): _wait_for_trial_end accepts fallback_js kwarg

When response_window_js is None, the executor can fall back to a
provided fallback_js expression (typically the matched stimulus's own
detection JS). When both are None, returns immediately (preserves the
no-op behavior for paradigms with no trial-end signal).

Backwards compatible: existing call site uses positional response_window_js
unchanged. The new fallback_js is keyword-only with default None."
```

---

## Task 2: Add `_stimulus_detection_js` helper

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `tests/test_executor_trial_end.py`

Add a helper that builds the fallback JS from a stimulus's `detection.method` and `detection.selector`. Cache per `stim.id` so the build cost is paid once per stimulus per session.

- [ ] **Step 1: Locate where to add the helper and the cache field**

```bash
grep -n "_stimulus_detection_js\|_stimulus_detection_js_cache\|_build_interrupt_check_js\|self\._key_map\s*=" src/experiment_bot/core/executor.py | head
```

The cache field `_stimulus_detection_js_cache: dict[str, str | None] = {}` should be initialized in `TaskExecutor.__init__` near the other instance fields. The helper itself sits near `_build_interrupt_check_js` (around L555-580 — same file area, similar role).

- [ ] **Step 2: Append unit tests for the helper**

Append to `tests/test_executor_trial_end.py`:

```python
def _stim(method: str, selector: str, stim_id: str = "test_stim"):
    """Build a stimulus stub with .id, .detection.method, .detection.selector."""
    detection = SimpleNamespace(method=method, selector=selector)
    return SimpleNamespace(id=stim_id, detection=detection)


def test_stimulus_detection_js_dom_query():
    stub = _stub_executor()
    stim = _stim("dom_query", ".foo")
    js = stub._stimulus_detection_js(stim)
    assert js == "document.querySelector('.foo') !== null"


def test_stimulus_detection_js_js_eval():
    stub = _stub_executor()
    stim = _stim("js_eval", "window.x === 1")
    js = stub._stimulus_detection_js(stim)
    assert js == "!!(window.x === 1)"


def test_stimulus_detection_js_canvas_state():
    stub = _stub_executor()
    stim = _stim("canvas_state", "ctx.getImageData(0,0,1,1)[0] > 100")
    js = stub._stimulus_detection_js(stim)
    assert js == "!!(ctx.getImageData(0,0,1,1)[0] > 100)"


def test_stimulus_detection_js_quotes_safely():
    """A dom_query selector containing a single quote must be escaped
    so the resulting JS is valid (mirrors _build_interrupt_check_js's
    pattern of replacing `'` with `\\'` before string interpolation)."""
    stub = _stub_executor()
    stim = _stim("dom_query", "div[data-name='foo']")
    js = stub._stimulus_detection_js(stim)
    assert js == "document.querySelector('div[data-name=\\'foo\\']') !== null"


def test_stimulus_detection_js_caches():
    """Same stimulus → result cached; second call returns identical
    string and does not re-build."""
    stub = _stub_executor()
    stim = _stim("js_eval", "expr", stim_id="cache_me")
    js1 = stub._stimulus_detection_js(stim)
    # Mutate the underlying selector after first call; cached result must NOT change.
    stim.detection.selector = "MUTATED"
    js2 = stub._stimulus_detection_js(stim)
    assert js2 == js1


def test_stimulus_detection_js_returns_none_for_empty_selector():
    stub = _stub_executor()
    stim = _stim("js_eval", "")
    assert stub._stimulus_detection_js(stim) is None


def test_stimulus_detection_js_returns_none_for_unknown_method():
    stub = _stub_executor()
    stim = _stim("unknown_method", "anything")
    assert stub._stimulus_detection_js(stim) is None
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/test_executor_trial_end.py -v 2>&1 | tail -20
```

Expected: 7 new tests FAIL with `AttributeError: 'TaskExecutor' object has no attribute '_stimulus_detection_js'`.

- [ ] **Step 4: Implement the helper**

Add to `src/experiment_bot/core/executor.py` near `_build_interrupt_check_js` (the spec's recommended location is "in the same file area, similar role"):

```python
    def _stimulus_detection_js(self, stim) -> str | None:
        """Return a JS expression that returns truthy while ``stim`` is
        currently on screen. Used as a fallback for `_wait_for_trial_end`
        when the paradigm's `runtime.timing.response_window_js` is
        missing (Stage 1 didn't extract it).

        Caches per-stimulus-id so the build cost is paid once.
        """
        cache_key = stim.id
        if cache_key in self._stimulus_detection_js_cache:
            return self._stimulus_detection_js_cache[cache_key]
        sel = stim.detection.selector
        if not sel:
            result = None
        elif stim.detection.method == "dom_query":
            sel_q = sel.replace("'", "\\'")
            result = f"document.querySelector('{sel_q}') !== null"
        elif stim.detection.method in ("js_eval", "canvas_state"):
            result = f"!!({sel})"
        else:
            result = None
        self._stimulus_detection_js_cache[cache_key] = result
        return result
```

Initialize the cache field in `TaskExecutor.__init__`. Find the `__init__` method (around L60-110 by inspection) and add this line near the other instance-state initializations (alongside `self._key_map = ...` or `self._seen_response_keys = set()` — pick a nearby field):

```python
        self._stimulus_detection_js_cache: dict[str, str | None] = {}
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
uv run pytest tests/test_executor_trial_end.py -v 2>&1 | tail -20
```

Expected: all 12 tests PASS (5 from Task 1 + 7 new).

- [ ] **Step 6: Confirm full suite passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 517 passed, 3 skipped (510 + 7 new).

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_trial_end.py
git commit -m "feat(executor): _stimulus_detection_js helper builds fallback JS

Used as the fallback for _wait_for_trial_end when a paradigm's
response_window_js is missing. Builds the JS expression from the
matched stimulus's detection.method + detection.selector, with
per-stimulus-id caching so the build cost is paid once per session.

Mirrors the safe-quoting pattern from _build_interrupt_check_js.
js_eval and canvas_state both wrap with !!(...); dom_query produces
document.querySelector(escaped_selector) !== null. Empty selector
or unknown method → None (helper degrades gracefully)."
```

---

## Task 3: Wire fallback into the post-trial call site

**Files:**
- Modify: `src/experiment_bot/core/executor.py:533-540`

Change the post-trial call to use both helpers from Tasks 1 and 2.

- [ ] **Step 1: Read the current call site**

```bash
sed -n '530,545p' src/experiment_bot/core/executor.py
```

Confirm the existing block matches:

```python
            # After responding, wait for the response window to close (next trial's
            # fixation) to avoid re-detecting the same stimulus and pressing into
            # the wrong trial.
            if timing.response_window_js:
                await self._wait_for_trial_end(
                    page,
                    timing.response_window_js,
                    timeout_s=timing.trial_end_timeout_s,
                )
```

- [ ] **Step 2: Replace the block**

Replace lines 530-540 (or whatever the exact range is — locate with `grep -n "After responding"`) with:

```python
            # After responding, wait for the response window to close (next trial's
            # fixation) to avoid re-detecting the same stimulus and pressing into
            # the wrong trial. Prefer the paradigm's response_window_js when
            # extracted by Stage 1; fall back to the matched stimulus's own
            # detection JS so paradigms without a response_window_js still avoid
            # over-firing (SP5 root-caused this gap for Flanker, n-back, stroop).
            fallback = self._stimulus_detection_js(match.stimulus)
            if timing.response_window_js or fallback:
                await self._wait_for_trial_end(
                    page,
                    timing.response_window_js,
                    fallback_js=fallback,
                    timeout_s=timing.trial_end_timeout_s,
                )
```

The outer `if` retains the no-op path for the truly-no-signal case (both None). When `response_window_js` is set, it takes precedence inside the helper — current behavior unchanged for stop_signal.

- [ ] **Step 3: Confirm `match.stimulus` is the right attribute**

Quickly verify `match.stimulus` is the attribute name used elsewhere in the executor for the matched stimulus:

```bash
grep -n "match\.stimulus" src/experiment_bot/core/executor.py | head -5
```

If `match` exposes the matched stimulus under a different name (e.g., `match.stim` or `match.matched`), use that name instead. The spec assumes `match.stimulus`; verify and adjust.

- [ ] **Step 4: Run full suite to ensure no regression in existing tests**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 517 passed, 3 skipped (no change from Task 2; the call-site edit doesn't add new tests but shouldn't break existing ones).

If any existing test fails, the most likely cause is `match.stimulus` being the wrong attribute name. Inspect the failure, fix the attribute reference, re-run.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py
git commit -m "feat(executor): trial-end wait falls back to stimulus detection JS

The post-trial call site now passes the matched stimulus's detection
JS as fallback_js. When the paradigm's response_window_js is set
(e.g., expfactory_stop_signal), it takes precedence — unchanged.
When response_window_js is None (Flanker, n-back, stroop), the
fallback fires and waits for the stimulus to disappear, preventing
the polling loop from re-detecting the same stimulus and double-
firing the trial handler. SP5 root-caused this as the source of
2-3x over-firing on the affected paradigms."
```

---

## Task 4: Full-suite regression check

**Files:**
- None modified

Verification step before kicking off the long-running held-out re-run.

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest 2>&1 | tail -10
```

Expected: 517 passed, 3 skipped, no failures.

- [ ] **Step 2: Confirm `git status` is clean**

```bash
git status
```

Expected: nothing to commit, working tree clean.

- [ ] **Step 3: No commit needed (verification only).**

---

## Task 5: Re-run 5 Flanker smoke sessions

**Files:**
- Working: `output/flanker_rdoc/<timestamp>/` × 5 (gitignored)
- Working: `.reasoner-logs/sp6_flanker_sessions.log`

- [ ] **Step 1: Run 5 sessions sequentially**

```bash
mkdir -p .reasoner-logs
for seed in 6001 6002 6003 6004 6005; do
  echo "=== Flanker session seed=$seed ==="
  uv run experiment-bot "https://deploy.expfactory.org/preview/3/" \
    --label expfactory_flanker --headless --seed "$seed" \
    >> .reasoner-logs/sp6_flanker_sessions.log 2>&1
  echo "  exit=$?"
done
```

Wall time: ~25-75 min total (5 × 5-15 min). Each session is roughly 5-10 min for Flanker.

- [ ] **Step 2: Confirm 5 session directories exist**

```bash
find output/flanker_rdoc -mindepth 1 -maxdepth 1 -type d | wc -l
```

Expected: `5`.

- [ ] **Step 3: Sanity-check: bot stimulus-response entries should drop to ≈ platform test trials**

```bash
uv run python << 'PY'
"""Compare bot stimulus-response entries to platform test trials.
SP5 baseline: bot logged 240-280 entries vs 120 platform test trials
per Flanker session (2× over-firing). SP6 target: <140 (within 20% of 120)."""
import json, csv
from pathlib import Path

print(f'{"session":>30} {"bot_entries":>13} {"plat_trials":>13} {"ratio":>8}')
for ses in sorted(Path('output/flanker_rdoc').iterdir()):
    if not ses.is_dir(): continue
    bot_log = json.load(open(ses / 'bot_log.json'))
    bot_n = sum(1 for t in bot_log
                if t.get('intended_error') in (True, False)
                and t.get('condition') in {'congruent','incongruent'})
    csv_rows = list(csv.DictReader(open(ses / 'experiment_data.csv')))
    plat_n = sum(1 for r in csv_rows if r.get('trial_id') == 'test_trial')
    ratio = bot_n / plat_n if plat_n else float('inf')
    flag = '' if ratio < 1.2 else ' ⚠'
    print(f"{ses.name:>30} {bot_n:>13} {plat_n:>13} {ratio:>7.2f}x{flag}")
PY
```

Expected: ratio close to 1.0 across all 5 sessions. If still ≥ 1.5×, the fallback isn't firing as intended — investigate before continuing (likely `match.stimulus` attribute name issue or stim.detection.selector being different from what the polling loop checks).

- [ ] **Step 4: No commit yet** (output/ is gitignored; observations come together in Task 8's report).

---

## Task 6: Re-validate Flanker against `norms/conflict.json`

**Files:**
- Output: `validation/sp6_heldout/flanker_rdoc_<timestamp>.json`

- [ ] **Step 1: Make the output dir**

```bash
mkdir -p validation/sp6_heldout
touch validation/sp6_heldout/.gitkeep
```

- [ ] **Step 2: Run validation**

```bash
uv run experiment-bot-validate \
  --paradigm-class conflict \
  --label flanker_rdoc \
  --output-dir output \
  --reports-dir validation/sp6_heldout \
  -v 2>&1 | tail -20
```

- [ ] **Step 3: Inspect the report**

```bash
uv run python << 'PY'
import json
from pathlib import Path
f = sorted(Path('validation/sp6_heldout').glob('flanker*.json'))[-1]
d = json.load(open(f))
print(f'overall_pass: {d["overall_pass"]}')
for pillar, info in d['pillar_results'].items():
    marker = '✅' if info['pass'] else '❌'
    print(f'\n{marker} {pillar}:')
    for m, mr in info['metrics'].items():
        ps = '✓' if mr['pass'] is True else ('✗' if mr['pass'] is False else '·')
        bv = mr['bot_value']
        bv_s = f'{bv:.2f}' if isinstance(bv, (int, float)) else str(bv)
        print(f'  {ps} {m}: {bv_s} vs {mr["published_range"]}')
PY
```

Compare to SP5's report (`validation/sp5_heldout/flanker_rdoc_*.json`). Expected differences:
- `rt_distribution` should still pass (the over-firing didn't affect aggregate RT).
- `post_error_slowing` should move from -7.23ms toward the configured +25-55ms range (or at least toward zero — depends on how clean the fix is).
- `cse_magnitude` may or may not become computable (depends on whether the alignment fix unblocks the metric's expected data shape).

- [ ] **Step 4: Commit the validation report**

```bash
git add validation/sp6_heldout/
git commit -m "chore(sp6): Flanker re-validation report after trial-end fallback

5-session re-run of Flanker (seeds 6001-6005) on the SP6 worktree
with the trial-end fallback in place. Compared to SP5's run as
descriptive evidence of the fix's effect on alignment and sequential
metrics."
```

---

## Task 7: Compute alignment metrics (bot_log vs platform CSV)

**Files:**
- Working: stdout

Quantify the per-trial alignment improvement between SP5 and SP6 — the headline number for Task 8's report.

- [ ] **Step 1: Compute SP6 alignment**

```bash
uv run python << 'PY'
"""SP6 vs SP5 alignment comparison: bot.intended_error vs platform.correct_trial=0
intersection vs chance prediction."""
import json, csv
from pathlib import Path

def session_alignment(ses_dir, bot_conditions, csv_filter):
    bot_all = json.load(open(ses_dir / 'bot_log.json'))
    csv_rows = list(csv.DictReader(open(ses_dir / 'experiment_data.csv')))
    plat = [r for r in csv_rows if csv_filter(r)]
    bot = [t for t in bot_all if t.get('intended_error') in (True, False)
           and t.get('condition') in bot_conditions]
    n = min(len(bot), len(plat))
    bot, plat = bot[:n], plat[:n]
    intended_err = [bool(t.get('intended_error')) for t in bot]
    plat_err = [r.get('correct_trial') == '0' for r in plat]
    n_intended = sum(intended_err); n_plat = sum(plat_err)
    intersection = sum(1 for ie, pe in zip(intended_err, plat_err) if ie and pe)
    return n, n_intended, n_plat, intersection, len(bot_all)

print(f'{"session":>30} {"bot_log":>9} {"bot_resp":>9} {"plat":>5} {"int_err":>9} {"plat_err":>10} {"intsect":>9}')
total = [0, 0, 0, 0]
for ses in sorted(Path('output/flanker_rdoc').iterdir()):
    if not ses.is_dir(): continue
    n, ni, np, x, log_n = session_alignment(ses, {'congruent','incongruent'},
                                              lambda r: r.get('trial_id')=='test_trial')
    print(f"{ses.name:>30} {log_n:>9} {n:>9} {n:>5} {ni:>9} {np:>10} {x:>9}")
    for i, v in enumerate([n, ni, np, x]): total[i] += v

print()
print(f'AGGREGATE: n={total[0]} intended_err={total[1]} plat_err={total[2]} intersection={total[3]}')
chance = total[1] * total[2] / total[0] if total[0] else 0
print(f'  expected intersection if independent: {chance:.1f}')
print(f'  observed / chance ratio: {total[3]/chance:.2f}x' if chance else 'no chance baseline')
print()
print('Reading: ratio > 1.5x suggests intended_error and platform_error are correlated (fix working).')
print('         ratio ~ 1.0x suggests still independent (fix not having expected effect).')
PY
```

Save the printed output for Task 8's report.

- [ ] **Step 2: No commit yet** — data goes into Task 8's report.

---

## Task 8: Write `docs/sp6-results.md`

**Files:**
- Create: `docs/sp6-results.md`

Descriptive report on the SP6 fix's impact, mirroring the structure of `docs/sp5-heldout-measurement-results.md`.

- [ ] **Step 1: Gather data**

The report draws from:
- Task 5's bot vs platform ratio output (over-firing reduction).
- Task 6's validation report (sequential metrics before/after).
- Task 7's alignment intersection vs chance.
- SP5's report `docs/sp5-heldout-measurement-results.md` for the before-numbers.

- [ ] **Step 2: Write the report**

Create `docs/sp6-results.md` with this template (replace placeholders with actual numbers):

```markdown
# SP6 — Executor trial-end fallback results

**Date:** 2026-05-09 (or actual run date)
**Spec:** `docs/superpowers/specs/2026-05-09-sp6-trial-end-fallback-design.md`
**Plan:** `docs/superpowers/plans/2026-05-09-sp6-trial-end-fallback.md`
**Branch:** `sp6/trial-end-fallback` (off `sp5-complete`)
**Tag (after this report lands):** `sp6-complete`

## Goal

Close the over-firing trial-detection bug surfaced in SP5: when
`runtime.timing.response_window_js` is None, the executor falls back
to polling the matched stimulus's own detection JS until the stimulus
stops matching. Re-run the SP5 Flanker measurement; report alignment
and sequential-metrics improvement descriptively.

## Procedure

5 Flanker sessions (seeds 6001-6005) on the SP6 worktree (`sp6/trial-end-fallback`)
re-ran with the trial-end fallback in place. Same Flanker URL as SP5;
same TaskCard (`taskcards/expfactory_flanker/2e7fe980.json`); same
adapter (`read_expfactory_flanker`); same norms file
(`norms/conflict.json`).

## Headline numbers

### Over-firing reduction

| Session | bot stimulus-response entries (SP5 vs SP6) | platform test trials | SP5 ratio | SP6 ratio |
|---|---|---|---|---|
| 1 | <SP5_n_1> → <SP6_n_1> | 120 | <SP5_ratio_1>x | <SP6_ratio_1>x |
| 2 | <SP5_n_2> → <SP6_n_2> | 120 | <SP5_ratio_2>x | <SP6_ratio_2>x |
| 3 | <SP5_n_3> → <SP6_n_3> | 120 | <SP5_ratio_3>x | <SP6_ratio_3>x |
| 4 | <SP5_n_4> → <SP6_n_4> | 120 | <SP5_ratio_4>x | <SP6_ratio_4>x |
| 5 | <SP5_n_5> → <SP6_n_5> | 120 | <SP5_ratio_5>x | <SP6_ratio_5>x |
| **Aggregate** | <total_SP5> → <total_SP6> | 600 | ~2.0x | <SP6_aggregate_ratio>x |

### intended_error vs platform_error alignment

| Run | n_intended_error | n_platform_error | intersection | chance prediction | observed/chance |
|---|---|---|---|---|---|
| SP5 | 37 | 46 | 2 | 2.8 | 0.71x (independent) |
| SP6 | <int> | <plat> | <intsect> | <chance> | <ratio>x |

### Validator sequential metrics (Flanker, conflict-class)

| Metric | SP5 value | SP6 value | Range | Pass? |
|---|---|---|---|---|
| post_error_slowing | -7.23ms | <SP6_value>ms | [10, 50] | <SP5: ✗> → <SP6: ?> |
| lag1_autocorr | 0.01 | <SP6_value> | None (descriptive) | · → · |
| cse_magnitude | None | <SP6_value> | [-45, -10] | · → ? |
| rt_distribution.mu | 493ms | <SP6_value> | [400, 550] | ✓ → ? |
| rt_distribution.sigma | 55 | <SP6_value> | [25, 60] | ✓ → ? |
| rt_distribution.tau | 115 | <SP6_value> | [70, 160] | ✓ → ? |

## Reading

[Fill in based on actual outcome:]

- If over-firing ratio drops to ~1.0x and intersection ratio rises significantly above chance: the executor fallback works as designed. The intended_error → platform_error path is now coherent. Sequential metrics like PES should now correctly reflect the bot's configured behavior.
- If over-firing ratio remains > 1.5x: the fallback isn't firing as expected. Likely cause: the stimulus's detection JS evaluates as truthy even after the trial advances (the page keeps `window.delay === 1` during ITI for n-back, for example, even after the response). In that case, an additional fix is needed — perhaps tracking which stimulus was just responded to and demanding the detection drop *and* a different stimulus be detected.
- rt_distribution metrics shouldn't change much (the aggregate RT didn't depend on per-trial alignment).

## n-back cross-validation (optional)

If time allows, also re-run 5 n-back sessions (seeds 6101-6105) and compute the same alignment metrics. n-back's SP5 over-firing was ~3x (worse than Flanker's 2x) so the fix's effect should be even more visible.

## Status

[Fill in]:
- Internal CI gate: PASS (517 passed, 3 skipped at sp6-complete; was 505 at sp5-complete; +12 new tests).
- External descriptive evidence: <summary of headline outcome>.

The framework's generalizability claim (G1) is [further strengthened / unchanged / weakened] by this run. Tag `sp6-complete` on the commit landing this report.
```

Replace the `<...>` placeholders with the real numbers from Tasks 5, 6, 7. Replace `[Fill in based on actual outcome:]` and `[Fill in]` sections with prose specific to the run.

- [ ] **Step 3: Sanity-check no placeholders remain**

```bash
grep -nE "<SP[0-9]_|<int>|<plat>|<intsect>|<chance>|<ratio>|<total_|<SP6_|<summary|\[Fill in" docs/sp6-results.md
```

Expected: no output. If any remain, fill them in with the actual data from earlier tasks.

- [ ] **Step 4: Commit**

```bash
git add docs/sp6-results.md
git commit -m "docs(sp6): trial-end-fallback re-run results

Descriptive report on the over-firing reduction, intended_error vs
platform_error alignment, and validator sequential metrics
before/after the SP6 fix on Flanker."
```

---

## Task 9: Tag, push, update CLAUDE.md

**Files:**
- Tag: `sp6-complete`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify clean state**

```bash
git status
uv run pytest 2>&1 | tail -3
```

Expected: clean working tree, all tests passing.

- [ ] **Step 2: Tag the milestone**

```bash
git tag -a sp6-complete -m "$(cat <<'EOF'
SP6 (executor trial-end fallback) — milestone tag

Closes the over-firing trial-detection bug surfaced in SP5. Single-
file change in core/executor.py: _wait_for_trial_end accepts a
fallback_js kwarg; new _stimulus_detection_js helper builds the
fallback from the matched stimulus's detection method/selector with
per-stimulus-id caching; post-trial call site passes the fallback.

Stop_signal unchanged (its response_window_js takes precedence in
the helper). Flanker, n-back, stroop now wait for their stimulus's
own detection JS to stop matching before resuming polling.

Internal: 12 new tests in tests/test_executor_trial_end.py covering
both helpers' correctness, timeout, exception paths, JS quoting, and
caching.

External: Flanker re-validation. See docs/sp6-results.md.
EOF
)"
```

- [ ] **Step 3: Push branch + tag**

```bash
git push -u origin sp6/trial-end-fallback
git push origin sp6-complete
```

- [ ] **Step 4: Update CLAUDE.md sub-project history**

Edit `CLAUDE.md`. Find the SP5 entry (added by SP5's CLAUDE.md update). After it, add an SP6 entry. The SP6 entry replaces the SP6 (planned) line that SP5 added.

Find this in CLAUDE.md:

```markdown
- **SP6** (planned): investigate Flanker PES sign-flip — likely
  related to lag1_pair_modulation runtime-vs-TaskCard label mismatch
  (Item 3 in `docs/sp2-validation-followups.md`). Highest-priority
  fidelity-gap from SP5.
```

Replace with:

```markdown
- **SP6**: Executor trial-end fallback. SP5's "Flanker PES sign-flip"
  finding root-caused to a deeper bug: `runtime.timing.response_window_js`
  was None for Flanker / n-back / stroop, causing the executor's
  polling loop to re-detect the same stimulus and double-fire trial
  handlers (2-3× over-firing). Single-file fix in core/executor.py
  adds a fallback to the matched stimulus's own detection JS.
  Internal: 517 passed (was 505); +12 tests. External: see
  `docs/sp6-results.md` for alignment improvement on Flanker (and
  n-back if cross-validated). Tag `sp6-complete`. ✓ Complete.
- **SP7** (candidate): if SP6 leaves residual misalignment (e.g.,
  paradigms whose stimulus detection stays truthy through ITI),
  investigate per-stimulus identity tracking. Otherwise: re-run
  stroop / cognitionrun_stroop / stopit_stop_signal sequential-
  metric validation under the post-SP6 framework.
```

- [ ] **Step 5: Commit and push CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): mark SP6 complete; SP7 candidate noted

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Self-review checklist

- **Spec § Goal**: Tasks 1, 2, 3 ship the executor fallback; Tasks 5-8 measure it on Flanker.
- **Spec § Success criterion (internal)**: 12 new tests in tests/test_executor_trial_end.py cover all 8 spec'd cases plus extras (none-method, empty-selector). Suite goes 505 → 517.
- **Spec § Success criterion (external)**: Tasks 5, 6, 7 produce alignment + validation data; Task 8 reports it.
- **Spec § Architecture (3 touch-points)**: Tasks 1 (helper #1), 2 (helper #2), 3 (call site). All in core/executor.py.
- **Spec § Test strategy**: unit tests in Tasks 1+2; held-out re-run in Task 5; alignment analysis in Task 7. All accounted for.
- **Spec § Out of scope**: no tasks for Stage 1 prompt update, validator changes, or stroop/dev-paradigm re-run.
- **Spec § Sub-project boundary check**: deliverables match; one bounded change set; clear "next SP for new modes" rule.

---

## Notes for the implementing engineer

- Held-out policy is binding: if Task 5's ratio doesn't drop, document and stop. Do NOT iterate on prompts or schemas in SP6.
- The `match.stimulus` attribute name in Task 3 is the spec's assumption. If the executor uses a different name (`match.stim`, `match.matched`, etc.), use that — verify via grep before editing.
- `_stimulus_detection_js_cache` initialization in `__init__` matters. If you forget it, `_stimulus_detection_js` raises `AttributeError` on first call. The unit tests catch this (the stub explicitly initializes the cache).
- The helper degrades gracefully when method or selector is unrecognized (returns None). The call site treats None fallback the same as no fallback (existing no-op path).

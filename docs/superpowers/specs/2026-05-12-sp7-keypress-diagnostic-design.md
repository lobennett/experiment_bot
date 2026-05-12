# SP7 — Keypress diagnostic (investigation-only)

## Origin

SP6 (`docs/sp6-results.md`) closed the over-firing trial-detection bug. Bot stimulus-response entries dropped from 2.05× to 1.02× platform trial count. PES moved from −7.23ms (broken) to +35.43ms (in configured range). But a residual finding remains: **per-trial alignment between `bot.intended_error` and `platform.correct_trial == 0` is still poor** — intersection 0 across all 5 sessions vs chance prediction 2.4. Aggregate accuracy aligns (~93% platform-correct), but the specific trials don't.

Investigation in the SP7 brainstorm narrowed the gap further:
- The bot's logged `response_key` (what `_pick_wrong_key` produced and what `page.keyboard.press(...)` received) does **not** match the platform's recorded `response` column on most trials. The bot says it pressed `","`; the platform says `"."` was the response.
- Off-by-one alignment tests across multiple offsets all produced ~50% match — consistent with random / independent keys, not a simple structural shift.

The root cause sits somewhere along the layer chain:

```
bot.response_key_js evaluation
    → bot's resolved_key (after _pick_wrong_key for intended-error trials)
    → page.keyboard.press(resolved_key)
    → page's own keydown handler
    → platform's response-recording logic
    → platform's CSV "response" column
```

The bot logs the resolved_key (third arrow). The platform records the final result (sixth arrow). We don't know which arrow corrupts the key. SP7 names the layer by capturing what the page's keyboard handler actually receives.

## Goal

Add page-level keydown instrumentation to the executor and re-run Flanker (5 sessions) under the post-SP6 framework. Analyze the captured keypress data alongside the bot's logged keys and the platform's recorded responses. Produce `docs/sp7-results.md` that names the responsible layer precisely enough to scope a follow-on fix SP.

No bot-behavior changes; pure instrumentation. The instrumentation and analysis must be **paradigm-agnostic** — applicable to any paradigm-platform (expfactory, cognition.run, jsPsych, anything DOM-based) without paradigm-specific selectors, condition labels, or assumptions.

## Success criterion

Two-tier success:

**Internal (CI-checkable, gates SP7 completion):** unit tests covering:
1. Executor's session-start hook evaluates the keydown-listener installation JS.
2. Per-trial drain reads from `window.__bot_keydown_log` via `.splice(0)`.
3. Trial log includes `resolved_key_pre_error` and `page_received_keys` fields.
4. Empty `page_received_keys` list (no key events captured) is logged without exception.
5. `page.evaluate` failure (e.g., navigation) doesn't lose the trial — `page_received_keys=None` and other fields still log.

**External (descriptive, scientific evidence):** Flanker held-out re-run + analysis script output. `docs/sp7-results.md` answers: for trials where bot.response_key ≠ platform.response, which layer corrupts the key? Layers to attribute (in order of decreasing innocence):

- **(a) Bot resolves the wrong key** to begin with (`response_key_js` evaluation returns a wrong key for the trial). → fix at Stage 1 (extraction quality) or at runtime evaluation timing.
- **(b) Bot resolves correctly but `_pick_wrong_key` picks the wrong wrong-key** (unlikely with 2-key paradigms but worth checking).
- **(c) Playwright `keyboard.press(K)` dispatches a different key than K** to the page's keydown handler. → fix at the bot↔Playwright layer.
- **(d) Page's keydown handler receives the bot's pressed key, but the platform's response-recording logic attributes a different key** (e.g., the platform reads from a different source like a polling-of-window-state mechanism that misses the actual keydown event). → fix at the bot's polling cadence or wait-for-response logic.

SP7 names which letter applies, supported by the diagnostic data. If multiple apply (some trials in different layers), the report says so with proportions.

Held-out outcome is the scientific contribution. Naming the layer correctly gates SP7. The fix lives in the follow-on SP.

## Architecture

Two touch-points in `src/experiment_bot/core/executor.py` plus a new analysis script.

### Per-session listener injection

Insertion point: immediately after the initial navigation completes — between `await self._navigator.execute_all(page, self._config.navigation)` (around `core/executor.py:306`) and the trial polling loop entry. Installing here (rather than right after `page.goto`) avoids capturing the instruction-screen keypresses the bot fires during navigation, which would be noise relative to trial-time keys.

The executor evaluates this JS:

```javascript
window.__bot_keydown_log = [];
document.addEventListener('keydown', (e) => {
    window.__bot_keydown_log.push({
        key: e.key,
        code: e.code,
        time: Date.now()
    });
}, true);  // capture phase: catch the event before any other handler
```

This is fully paradigm-agnostic — works on any HTML page regardless of which experiment framework is used. The capture-phase flag (`true` as the third arg) means we see the event before any application-level handler can modify or stop propagation.

The injection happens once per session. If the page navigates (full page reload), `window.__bot_keydown_log` is reset; the executor re-injects.

### Per-trial drain + extended trial log

Just after `await page.keyboard.press(resolved_key)` and before logging the trial, drain the keydown log:

```python
try:
    page_received_keys = await page.evaluate(
        "(() => { const log = window.__bot_keydown_log || []; "
        "  window.__bot_keydown_log = []; "
        "  return log; })()"
    )
except Exception:
    page_received_keys = None  # page may be torn down by navigation
```

The drain pattern (`window.__bot_keydown_log = []` after read) ensures subsequent trials don't double-count earlier presses.

Extend the existing `_writer.log_trial({...})` call to include two new fields:
- `resolved_key_pre_error`: the raw response_key_js result before `_pick_wrong_key` applied. When `intended_error=False`, this equals `response_key`. When `True`, this is the bot's "what I would have pressed if I weren't intending to err" — useful for distinguishing layer (a) from later layers.
- `page_received_keys`: the drained list (possibly empty, possibly None on failure).

These fields are paradigm-agnostic: they describe the bot's runtime layer, not paradigm content.

### Generic analysis script: `scripts/keypress_audit.py`

New top-level script (not paradigm-coupled):

```python
# Usage:
#   uv run python scripts/keypress_audit.py \
#     --label <task-name> --output-dir output
```

For each session directory under `output/<label>/`, the script:
1. Loads `bot_log.json` (with the new fields).
2. Loads `experiment_data.csv` via the registered platform adapter (`PLATFORM_ADAPTERS[label]`).
3. Aligns bot stim-response entries (those with `intended_error in {True, False}` and `condition` in the platform's known conditions) with platform test_trial rows 1:1.
4. For each trial, computes:
   - `bot_intended_correct_key`: `resolved_key_pre_error` (the bot's view of the right answer)
   - `bot_pressed_key`: `response_key` (after `_pick_wrong_key` for intended-error trials)
   - `page_received_key`: first key from `page_received_keys` (or `<empty>` if list is empty)
   - `platform_recorded_response`: platform CSV `response` column
   - `platform_expected_response`: platform CSV `correct_response` column
5. Aggregates a 4-way agreement table:
   - **bot pressed == page received**: did Playwright deliver the press faithfully?
   - **page received == platform recorded**: did the platform record what the page received?
   - **bot pressed == platform recorded**: end-to-end consistency.
6. Outputs per-session and aggregate counts.

The script uses `PLATFORM_ADAPTERS[label]` for the platform-side parsing, so it works for **any registered paradigm** (Flanker, n-back, stop-signal, stroop, future paradigms). No condition labels or selectors hardcoded.

## Data flow

```
Session start:
    Executor injects keydown listener via page.evaluate(...)
    window.__bot_keydown_log = [], document.addEventListener('keydown', ...)
    │
    ▼
Per trial:
    Polling detects stimulus → bot resolves response_key_js → bot decides intent
    │
    ▼
    resolved_key_pre_error = response_key_js result
    if intended_error: resolved_key = _pick_wrong_key(resolved_key_pre_error)
    else:              resolved_key = resolved_key_pre_error
    │
    ▼
    await page.keyboard.press(resolved_key)
    (page's own keydown handler fires; bot's capture-phase listener
     records to window.__bot_keydown_log)
    │
    ▼
    page_received_keys = await page.evaluate(drain JS)
    │
    ▼
    log_trial({
        ...existing fields...,
        resolved_key_pre_error,
        response_key,          # = resolved_key (post-_pick_wrong_key)
        page_received_keys,    # list of {key, code, time} since last drain
    })
    │
    ▼
    _wait_for_trial_end (SP6 fallback) — unchanged
```

One extra `page.evaluate` per trial (the drain). Tiny overhead.

## Test strategy

### `tests/test_executor_keypress_diagnostic.py` (new)

Unit tests using `AsyncMock` and the `_stub_executor` pattern from `tests/test_executor_trial_end.py`:

- `test_inject_keydown_listener_evaluates_correct_js`: stub `page.evaluate`; call the executor's session-start hook (whatever method holds the injection); assert one call whose JS string contains `addEventListener('keydown'`, `window.__bot_keydown_log`, and the capture-phase `true` arg.
- `test_drain_keydown_log_uses_correct_js`: stub `page.evaluate` to return a fixed list; call the executor's drain helper; assert the JS string includes `window.__bot_keydown_log` and `= []` (the reset).
- `test_log_trial_includes_keypress_fields`: stub a trial with `intended_error=True`, `resolved_key_pre_error="."`, `response_key=","`, `page_received_keys=[{"key":",","code":"Comma","time":0}]`; assert the writer's log payload includes both new fields.
- `test_log_trial_handles_empty_keypress_log`: `page.evaluate` returns `[]`; trial logs with `page_received_keys=[]`; no exception.
- `test_log_trial_handles_evaluate_failure`: `page.evaluate` raises; `page_received_keys` is `None`; trial still logs with all other fields intact.

### Generic analysis script tested via dry-run

The analysis script's correctness is verified by running it on the existing SP6 sessions (committed in the worktree's `output/` — wait, those are gitignored). Manual verification: after the re-run in Task 5, run the script on Flanker sessions; visually verify the output shape matches expectations.

Optionally, add `tests/test_keypress_audit_script.py` with a fixture-based test (a fake `output/flanker_rdoc/<timestamp>/` with stub bot_log.json + experiment_data.csv, verify aggregate counts).

### Held-out re-run

5 Flanker sessions (seeds 7001-7005). Same URL, same TaskCard, same procedure. ~25-75 min wall-clock. Generates the data the analysis script consumes.

## Deliverables

- Worktree `.worktrees/sp7` on branch `sp7/keypress-diagnostic`, branched off tag `sp6-complete`. Spec + plan cherry-picked.
- Code changes in `src/experiment_bot/core/executor.py` only (listener injection at session start; per-trial drain; extended trial log).
- New tests in `tests/test_executor_keypress_diagnostic.py` (5 tests covering injection, drain, and the three log-trial paths).
- New `scripts/keypress_audit.py` — paradigm-agnostic analysis tool using `PLATFORM_ADAPTERS` dispatch.
- 5 Flanker re-run sessions in `output/flanker_rdoc/` (gitignored).
- `docs/sp7-results.md` — names the responsible layer (a/b/c/d from the success criterion). Recommends concrete SP8 scope.
- Tag `sp7-complete`. Push branch + tag.
- `CLAUDE.md` sub-project history updated.

## Out of scope

- **Any behavioral fix.** SP7 is investigation-only. The fix is a follow-on SP scoped after the layer is named.
- **Paradigm-specific instrumentation.** No expfactory or jsPsych-specific selectors, condition labels, or assumptions. The listener is `document.addEventListener('keydown', ...)`; the analysis script uses the existing `PLATFORM_ADAPTERS` dispatch.
- **Investigating the 5 extra bot stim-response entries beyond 120 platform trials.** Possibly related, but the keypress audit will surface whether they matter; if not, a separate SP.
- **Re-running other paradigms (n-back, stroop, etc.).** The analysis script is generic so this is trivially possible later; SP7 uses Flanker only to keep scope focused.
- **OS-level keyboard layout investigation.** If SP7 surfaces this as the layer, the follow-on fix SP can address it; SP7 only names the layer.
- **Cleanups from prior SPs.** `_extract_json` ownership, Tier 2/3 SP4 backlog items, `cse_magnitude` metric gap. Each their own SP.

## Sub-project boundary check

This spec is appropriately scoped to a single implementation plan:

- One concrete deliverable (executor instrumentation + analysis script + investigation report).
- One bounded set of code changes (one file: `core/executor.py`, plus a new test file and a new script).
- One pre-defined success criterion (internal CI gate + descriptive layer-naming report).
- A clear hand-off rule for findings (named layer → follow-on SP8 with that layer's fix in scope).

The investigation-only framing keeps SP7 disciplined: no fixes ship here, even if the data makes the fix obvious mid-investigation. The point of held-out testing is that fixes are explicit, scoped, and reviewed in their own sub-projects.

# SP9c — Layer (d) investigation and fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the page→platform keypress gap (SP7 layer d, ~26-64% pressed→recorded across paradigms). Add paradigm-agnostic keydown + keypress + keyup instrumentation, diagnose which suspect explains the gap on jsPsych pages, then ship a Web-Platform-only fix at the trial-keypress site.

**Architecture:** Three phases. (A) Extend existing keydown-listener install in `core/executor.py` to also capture keypress and keyup events, per-trial drain extended. (B) Read jsPsych keyboard-response-plugin source + run one stroop session with new instrumentation; document findings. (C) Implement a new `_press_trial_key(page, key)` helper that uses `page.dispatch_event` with constructed `KeyboardEvent` (most likely suspect: listener type mismatch), only at the trial-keypress call site. The fix mechanism is Web Platform APIs only — no jsPsych-specific selectors. Multi-platform validation on 2 jsPsych platforms.

**Tech Stack:** Python 3.12 / uv; pytest + pytest-asyncio; Playwright (async API); Web Platform `KeyboardEvent` constructor for the fix mechanism.

Reference: spec at `docs/superpowers/specs/2026-05-13-sp9c-layer-d-investigation-design.md`. Parent results at `docs/sp9a-results.md`. SP7 layer-d evidence at `docs/sp7-results.md`. User memory file at `~/.claude/projects/-Users-lobennett-grants-r01-rdoc-projects-experiment-bot/memory/project_jspsych_keypress_layer_d.md` carries the full quantitative description of the gap.

**Adaptive note:** Phase C's exact code (Task 8) assumes Phase B reveals **suspect 1 (listener type mismatch)** — the highest-prior candidate. If Phase B reveals a different suspect (choices filter mismatch, response-window timing, or multiple-presses-per-trial), Task 7 explicitly pauses for user input and Task 8 gets revised per the spec's Phase C fix-shape table. The plan does not branch on speculation; it commits to the most-likely path and acknowledges the user-checkpoint gate.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/experiment_bot/core/executor.py` | Executor — keypress instrumentation + delivery | Modified (Tasks 1, 2, 8) |
| `tests/test_executor_keypress_diagnostic.py` | SP7 instrumentation tests | Modified (Tasks 1, 2) |
| `tests/test_executor_trial_keypress.py` | New helper tests | Created (Task 8) |
| `docs/sp9c-investigation.md` | Phase B findings | Created (Tasks 4, 6) |
| `docs/sp9c-results.md` | Phase C empirical results | Created (Task 10) |
| `output/<paradigm>/<timestamp>/` × 5 | Smoke + validation sessions | Generated (Tasks 5, 9; gitignored) |
| `CLAUDE.md` | Sub-project history | Modified (Task 11) |
| `docs/reviewer-1-charter.md` | "Last reviewed at" + threat model | Modified (Task 11) |

---

## Paradigm reference

SP9c uses these TaskCards (already committed to the sp8 branch at `b06122e`):

| Label | URL | TaskCard hash | Phase |
|---|---|---|---|
| `expfactory_stroop` | `https://deploy.expfactory.org/preview/10/` | `f099a88b` | Phase B testbed (Task 5); Phase C validation (Task 9) |
| `stopit_stop_signal` | `https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html` | `39e97714` | Phase C validation (Task 9) |

Cognition.run validation is out of scope (no TaskCard available, deferred per spec §4).

---

## Task 0: Set up SP9c worktree

**Files:**
- Worktree: `.worktrees/sp9c` on branch `sp9c/layer-d-investigation`, branched off `sp9b-complete`

Steps 1-3 are executed by the controller before subagent dispatch. Subsequent tasks assume the engineer is operating inside `.worktrees/sp9c`.

- [ ] **Step 1: Create worktree from sp9b-complete**

```bash
git worktree add /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c -b sp9c/layer-d-investigation sp9b-complete
```

- [ ] **Step 2: Cherry-pick SP9c spec + this plan onto the new branch**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c
git cherry-pick abcf91a  # SP9c spec
git cherry-pick <plan-commit>  # this plan (commit lands after plan is written)
```

- [ ] **Step 3: Sync deps + verify clean baseline**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c
uv sync
uv run pytest -q
```

Expected: 564 passed, 3 skipped (matches `sp9b-complete` baseline).

---

## Task 1: Extend `_install_keydown_listener` to also install keypress + keyup listeners

**Files:**
- Modify: `src/experiment_bot/core/executor.py:660-680` (the existing `_install_keydown_listener` method)
- Modify: `tests/test_executor_keypress_diagnostic.py`

The current implementation installs ONE listener (keydown). Phase A extends it to install all three event types on `document` (capture phase). Each event type writes to its own `window.__bot_<type>_log` array.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_executor_keypress_diagnostic.py`:

```python
@pytest.mark.asyncio
async def test_install_keydown_listener_also_installs_keypress_and_keyup_listeners():
    """SP9c: layer-d diagnostic needs all three event types to identify
    listener-type mismatches. The install hook must initialize three log
    arrays and attach three capture-phase listeners."""
    stub = _stub_executor()
    page = AsyncMock()
    await stub._install_keydown_listener(page)
    js = page.evaluate.call_args.args[0]
    # Three log arrays
    assert "window.__bot_keydown_log" in js
    assert "window.__bot_keypress_log" in js
    assert "window.__bot_keyup_log" in js
    # Three listeners
    assert "addEventListener('keydown'" in js
    assert "addEventListener('keypress'" in js
    assert "addEventListener('keyup'" in js
    # All three use capture phase (third arg true)
    assert js.count(", true)") >= 3
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py::test_install_keydown_listener_also_installs_keypress_and_keyup_listeners -v
```

Expected: FAIL with `assert 'window.__bot_keypress_log' in js` (or similar).

- [ ] **Step 3: Update `_install_keydown_listener`**

In `src/experiment_bot/core/executor.py`, find the existing method (around line 660-680):

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

Replace with:

```python
    async def _install_keydown_listener(self, page) -> None:
        """Inject paradigm-agnostic keyboard-event listeners at session start.

        Installs three capture-phase listeners on `document`:
        - keydown -> window.__bot_keydown_log (SP7 instrumentation)
        - keypress -> window.__bot_keypress_log (SP9c instrumentation)
        - keyup -> window.__bot_keyup_log (SP9c instrumentation)

        Each log is an array of {key, code, time} dicts. Per-trial drain
        reads and clears all three, surfacing the keys the PAGE's
        listeners actually received — useful for diagnosing layer-by-
        layer mismatches between bot.keyboard.press, Playwright
        dispatch, page handler, and platform recording.

        Capture-phase listeners so we see events before any
        application-level handler can modify or stop propagation. The
        method name preserves the SP7 API for backward compatibility.
        """
        await page.evaluate(
            "window.__bot_keydown_log = [];"
            " window.__bot_keypress_log = [];"
            " window.__bot_keyup_log = [];"
            " document.addEventListener('keydown', (e) => {"
            "   window.__bot_keydown_log.push({"
            "     key: e.key, code: e.code, time: Date.now()"
            "   });"
            " }, true);"
            " document.addEventListener('keypress', (e) => {"
            "   window.__bot_keypress_log.push({"
            "     key: e.key, code: e.code, time: Date.now()"
            "   });"
            " }, true);"
            " document.addEventListener('keyup', (e) => {"
            "   window.__bot_keyup_log.push({"
            "     key: e.key, code: e.code, time: Date.now()"
            "   });"
            " }, true);"
        )
```

- [ ] **Step 4: Run all keypress diagnostic tests**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v
```

Expected: All existing tests pass + new test passes.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_keypress_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(executor): install keypress + keyup listeners alongside keydown

Phase A of SP9c — paradigm-agnostic instrumentation for the layer-(d)
investigation. Existing keydown listener (SP7) is unchanged in shape;
two new capture-phase listeners are added on `document` for keypress
and keyup, each writing to its own window.__bot_*_log array.

The three event arrays let the per-trial diagnostic distinguish:
- "page received keydown but no keypress" → suspect 1 (jsPsych may
  listen for keypress, not keydown)
- "page received keydown and keypress but not at trial time" →
  suspect 3 (response-window timing)

Method name preserved for backward compatibility with SP7 callers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Extend per-trial drain to capture all three event arrays

**Files:**
- Modify: `src/experiment_bot/core/executor.py:682-727` (the existing `_drain_keydown_log` and `_log_trial_with_keypress_diag` methods)
- Modify: `tests/test_executor_keypress_diagnostic.py`

The current drain reads `window.__bot_keydown_log` and writes `page_received_keys` to the trial payload. Phase A extends both: read all three arrays and write three trial fields. Backward compatibility — `page_received_keys` stays for SP7 audit-script compatibility.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_executor_keypress_diagnostic.py`:

```python
@pytest.mark.asyncio
async def test_drain_keydown_log_returns_all_three_event_arrays():
    """SP9c: drain reads and clears keydown, keypress, and keyup arrays
    in one round-trip. Returns a dict with three keys."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={
        "keydown": [{"key": ",", "code": "Comma", "time": 100}],
        "keypress": [],
        "keyup": [{"key": ",", "code": "Comma", "time": 110}],
    })
    got = await stub._drain_keydown_log(page)
    assert got == {
        "keydown": [{"key": ",", "code": "Comma", "time": 100}],
        "keypress": [],
        "keyup": [{"key": ",", "code": "Comma", "time": 110}],
    }
    # JS must read all three arrays and reset them
    js = page.evaluate.call_args.args[0]
    assert "__bot_keydown_log" in js
    assert "__bot_keypress_log" in js
    assert "__bot_keyup_log" in js


@pytest.mark.asyncio
async def test_drain_keydown_log_returns_none_on_failure():
    """SP9c: drain returns None when page.evaluate raises (page teardown)."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    got = await stub._drain_keydown_log(page)
    assert got is None


@pytest.mark.asyncio
async def test_log_trial_writes_keypress_received_and_keyup_received_fields():
    """SP9c: the per-trial logger writes three diagnostic fields:
    page_received_keys (SP7, backward-compatible), keypress_received,
    keyup_received."""
    stub = _stub_executor()
    stub._writer = MagicMock()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={
        "keydown": [{"key": ",", "code": "Comma", "time": 100}],
        "keypress": [{"key": ",", "code": "Comma", "time": 105}],
        "keyup": [{"key": ",", "code": "Comma", "time": 110}],
    })
    await stub._log_trial_with_keypress_diag(
        page=page,
        base_payload={"trial": 1, "response_key": ","},
        resolved_key_pre_error=",",
    )
    args = stub._writer.log_trial.call_args.args
    assert len(args) == 1
    payload = args[0]
    assert payload["trial"] == 1
    assert payload["response_key"] == ","
    assert payload["resolved_key_pre_error"] == ","
    assert payload["page_received_keys"] == [{"key": ",", "code": "Comma", "time": 100}]
    assert payload["keypress_received"] == [{"key": ",", "code": "Comma", "time": 105}]
    assert payload["keyup_received"] == [{"key": ",", "code": "Comma", "time": 110}]


@pytest.mark.asyncio
async def test_log_trial_handles_drain_failure_gracefully():
    """When drain returns None, all three fields are None."""
    stub = _stub_executor()
    stub._writer = MagicMock()
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    await stub._log_trial_with_keypress_diag(
        page=page,
        base_payload={"trial": 1, "response_key": ","},
        resolved_key_pre_error=",",
    )
    payload = stub._writer.log_trial.call_args.args[0]
    assert payload["page_received_keys"] is None
    assert payload["keypress_received"] is None
    assert payload["keyup_received"] is None
```

(`MagicMock` may already be imported; if not, add `from unittest.mock import MagicMock` near the top.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v
```

Expected: The four new tests FAIL — the drain returns a list (not dict), the log helper writes only one field (`page_received_keys`).

- [ ] **Step 3: Update `_drain_keydown_log`**

In `src/experiment_bot/core/executor.py`, find the existing method (around line 682-700):

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

Replace with:

```python
    async def _drain_keydown_log(self, page) -> dict | None:
        """Read-and-clear all three page-side event logs. Returns a dict
        with three keys (`keydown`, `keypress`, `keyup`), each a list of
        {key, code, time} dicts captured since the last drain, or None
        if `page.evaluate` raises (e.g., page navigation tore down the
        context).

        Reset pattern: read all three existing logs, then assign fresh
        empty arrays so subsequent trials don't double-count earlier
        events.

        Note: method name preserved from SP7 for backward compatibility
        with callers; SP9c extends the return shape from list to dict.
        """
        try:
            return await page.evaluate(
                "(() => {"
                "  const keydown = window.__bot_keydown_log || [];"
                "  const keypress = window.__bot_keypress_log || [];"
                "  const keyup = window.__bot_keyup_log || [];"
                "  window.__bot_keydown_log = [];"
                "  window.__bot_keypress_log = [];"
                "  window.__bot_keyup_log = [];"
                "  return { keydown, keypress, keyup };"
                "})()"
            )
        except Exception:
            return None
```

- [ ] **Step 4: Update `_log_trial_with_keypress_diag`**

In `src/experiment_bot/core/executor.py`, find the existing method (around line 702-727):

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

Replace with:

```python
    async def _log_trial_with_keypress_diag(
        self,
        *,
        page,
        base_payload: dict,
        resolved_key_pre_error: str | None,
    ) -> None:
        """Drain the page's three event logs and write an augmented trial
        entry. Adds four fields to `base_payload`:

        - resolved_key_pre_error: the bot's response_key_js result
          before `_pick_wrong_key` flipped it for an intended-error
          trial. When intended_error=False, this equals
          base_payload['response_key'].
        - page_received_keys: list of {key, code, time} the page's
          keydown listener captured since the last drain (SP7 name).
        - keypress_received: same shape, for keypress events (SP9c).
        - keyup_received: same shape, for keyup events (SP9c).

        When the drain fails (page teardown), all three event-log
        fields are None.

        All fields are paradigm-agnostic — they describe the runtime
        layer between bot and platform, not paradigm content.
        """
        drained = await self._drain_keydown_log(page)
        payload = dict(base_payload)
        payload["resolved_key_pre_error"] = resolved_key_pre_error
        if drained is None:
            payload["page_received_keys"] = None
            payload["keypress_received"] = None
            payload["keyup_received"] = None
        else:
            payload["page_received_keys"] = drained.get("keydown", [])
            payload["keypress_received"] = drained.get("keypress", [])
            payload["keyup_received"] = drained.get("keyup", [])
        self._writer.log_trial(payload)
```

- [ ] **Step 5: Run tests to verify they pass + full suite for regressions**

```bash
uv run pytest tests/test_executor_keypress_diagnostic.py -v
uv run pytest -q
```

Expected: All four new tests PASS. Full suite at 568 passed (was 564 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_keypress_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(executor): per-trial drain captures keypress + keyup arrays

Phase A of SP9c continues. The drain helper now returns a dict with
three event-type keys instead of a single list; the log helper
unpacks them into three trial payload fields (page_received_keys
keeps the SP7 name for backward compatibility; keypress_received
and keyup_received are new).

Drain-failure path returns None for all three fields — preserves the
existing "page torn down" graceful degradation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Verify the new instrumentation lands in real bot_log files (sanity check, no test)

This is a 5-minute manual confirmation — no code, just verify a smoke run produces the new fields. No commit at this task; the verification feeds into Task 5.

- [ ] **Step 1: Run a quick smoke session against the SessionAgent-disabled config to isolate Phase A**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c
set -a && source /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.env && set +a
export EXPERIMENT_BOT_LLM_CLIENT=api
uv run experiment-bot --label expfactory_n_back --seed 9501 https://deploy.expfactory.org/preview/5/ 2>&1 | tail -5
```

(Use n-back rather than stroop — faster, less variance.)

- [ ] **Step 2: Inspect the latest bot_log for the three new fields**

```bash
uv run python -c "
import json, glob
log_path = sorted(glob.glob('output/n_back_rdoc/2026-05-*/bot_log.json'))[-1]
log = json.load(open(log_path))
sample = next((t for t in log if t.get('page_received_keys')), log[0])
print('Sample trial fields:', sorted(sample.keys()))
print('page_received_keys present:', 'page_received_keys' in sample)
print('keypress_received present:', 'keypress_received' in sample)
print('keyup_received present:', 'keyup_received' in sample)
print('Sample event counts:', {
    'keydown': len(sample.get('page_received_keys') or []),
    'keypress': len(sample.get('keypress_received') or []),
    'keyup': len(sample.get('keyup_received') or []),
})
"
```

Expected: all three fields present. Event counts may be empty or non-empty; the point is the FIELDS exist in the schema.

If fields aren't present → revisit Task 2 (likely a field-name typo or the drain dict missing keys).

---

## Task 4: Phase B.1 — Read jsPsych keyboard-response-plugin source; document in `docs/sp9c-investigation.md`

**Files:**
- Create: `docs/sp9c-investigation.md`

This is a research task — fetch jsPsych source from GitHub and document the listener mechanics. The output is a doc commit, no code.

- [ ] **Step 1: WebFetch the jsPsych keyboard-response-plugin source**

Run two WebFetch calls:

```
URL 1: https://raw.githubusercontent.com/jspsych/jsPsych/main/packages/plugin-html-keyboard-response/src/index.ts
URL 2: https://raw.githubusercontent.com/jspsych/jsPsych/main/packages/plugin-keyboard-response/src/index.ts
```

Prompt for each: "Read this jsPsych plugin source. What DOM event does it listen for (keydown / keypress / keyup)? What is the listener attachment target (document / window / specific element)? How does it filter by `choices`? When does the listener attach and detach (relative to trial start/end)? Return findings as a structured summary."

If those URLs 404, try variants — `master` branch, `packages/plugin-keyboard-response/src/index.js`, or the jsPsych core `keyboard-listener.ts` file. Fall back to the jsPsych docs page at `https://www.jspsych.org/latest/plugins/html-keyboard-response/` for a behavioral description.

- [ ] **Step 2: Also probe the deployed expfactory stroop page directly to see which listener attaches**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c
uv run python <<'EOF'
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://deploy.expfactory.org/preview/10/", wait_until="networkidle")
        # Wait long enough for jsPsych to initialize
        await asyncio.sleep(3)
        # Check what listeners are attached to document
        listeners = await page.evaluate("""
          (() => {
            // Most browsers don't expose attached listeners directly.
            // Workaround: instrument addEventListener and force jsPsych
            // to re-register by triggering navigation OR just check
            // that our listeners can see what jsPsych emits later.
            // For now, log version and trial-config-relevant globals.
            return {
              jsPsychVersion: (window.jsPsych && window.jsPsych.version) ? window.jsPsych.version() : null,
              hasJsPsychKeyboardListener: typeof window.jsPsych?._currentTrial !== 'undefined',
              winKeys: Object.keys(window).filter(k => /jspsych|trial|response|keyboard/i.test(k)).slice(0, 30),
            }
          })()
        """)
        print("Page probe:", listeners)
        await asyncio.sleep(1)
        await browser.close()

asyncio.run(main())
EOF
```

(Expected: an empty-ish probe — the deeper info comes from the source read.)

- [ ] **Step 3: Write `docs/sp9c-investigation.md` Phase B.1 section**

Create the file with a header section AND the source-read findings. Template:

```markdown
# SP9c — Layer (d) investigation

**Date:** 2026-05-13
**Spec:** `docs/superpowers/specs/2026-05-13-sp9c-layer-d-investigation-design.md`
**Plan:** `docs/superpowers/plans/2026-05-13-sp9c-layer-d-investigation.md`

## Phase B.1 — jsPsych keyboard-response-plugin source mechanics

### Listener type
[from source read — keydown / keypress / keyup, plus any chained logic]

### Listener target
[document / window / specific element]

### Choices filter shape
[how raw event is matched against the `choices` array — `.key`? `.code`? `.toLowerCase()`?]

### Response-window lifecycle
[when listener attaches (trial start? after stimulus onset?), when it detaches (response received? trial timeout?)]

### Implications for SP7 suspect taxonomy
- Suspect 1 (listener type mismatch): [present / absent based on listener type finding]
- Suspect 2 (choices filter mismatch): [present / absent based on filter shape finding]
- Suspect 3 (response-window timing): [present / absent based on lifecycle finding]

---

(Phase B.3 findings to follow after Task 6 lands.)
```

Fill in the bracketed sections from the source-read output.

- [ ] **Step 4: Commit**

```bash
git add docs/sp9c-investigation.md
git commit -m "$(cat <<'EOF'
docs(sp9c): Phase B.1 — jsPsych keyboard-response-plugin mechanics

Fetched plugin source from jsPsych GitHub repo and documented the
listener type, target element, choices filter shape, and response-
window lifecycle. This narrows the SP7 suspect taxonomy before the
Phase B.3 empirical diagnostic.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Phase B.2 — Run one stroop session with the new instrumentation

**Files:**
- Generated: `output/expfactory_stroop/<timestamp>/` (gitignored)

No code change. Run the smoke session, then sanity-check the bot_log for the three event arrays before moving to analysis.

- [ ] **Step 1: Confirm SP8 stroop TaskCard is present**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c
ls taskcards/expfactory_stroop/
```

Expected output includes `f099a88b.json`. If only `d63c4d2d.json` is present (pre-SP8), copy the SP8 TaskCard:

```bash
cp /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp8/taskcards/expfactory_stroop/f099a88b.json taskcards/expfactory_stroop/
```

- [ ] **Step 2: Run the diagnostic session**

```bash
set -a && source /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.env && set +a
export EXPERIMENT_BOT_LLM_CLIENT=api
uv run experiment-bot --label expfactory_stroop --seed 9601 https://deploy.expfactory.org/preview/10/ 2>&1 | tail -5
```

Expected: session completes successfully with ~120-130 trials.

- [ ] **Step 3: Confirm the new fields landed in this session's bot_log**

```bash
uv run python -c "
import json, glob
log_path = sorted(glob.glob('output/expfactory_stroop/2026-05-*/bot_log.json'))[-1]
log = json.load(open(log_path))
trial = next((t for t in log if t.get('condition') in ('congruent', 'incongruent')), None)
print('Session:', log_path)
print('keys in trial:', sorted(trial.keys()))
print('event counts (first sample trial):', {
    'keydown': len(trial.get('page_received_keys') or []),
    'keypress': len(trial.get('keypress_received') or []),
    'keyup': len(trial.get('keyup_received') or []),
})
"
```

Expected: counts where keydown > 0 (since the bot pressed at least one key) and counts for keypress / keyup are whatever jsPsych emits.

No commit at this task — the session output is gitignored. The data feeds Task 6.

---

## Task 6: Phase B.3+B.4 — Analyze per-trial data, append findings to `docs/sp9c-investigation.md`

**Files:**
- Modify: `docs/sp9c-investigation.md` (append Phase B.3 section)

For every trial where `bot_pressed != platform_recorded`, what did the three event arrays contain? The analysis identifies which suspect explains the gap.

- [ ] **Step 1: Run a per-trial diagnostic script**

```bash
uv run python <<'EOF'
import json, glob
from pathlib import Path
from collections import Counter

# Find the SP9c stroop session (most recent)
candidates = sorted(Path("output/expfactory_stroop").glob("2026-05-13_*/bot_log.json"))
ses_dir = candidates[-1].parent
bot_log = json.loads((ses_dir / "bot_log.json").read_text())
plat = json.loads((ses_dir / "experiment_data.json").read_text())
test_rows = [r for r in plat if r.get("trial_id") == "test_trial"]

bot_trials = [t for t in bot_log if t.get("condition") in ("congruent", "incongruent")]
n = min(len(bot_trials), len(test_rows))

# Tally
mismatches = []
for i in range(n):
    b = bot_trials[i]
    p = test_rows[i]
    bot_pressed = b.get("response_key")
    plat_recorded = p.get("response")
    if bot_pressed != plat_recorded:
        mismatches.append({
            "trial": i,
            "bot_pressed": bot_pressed,
            "plat_recorded": plat_recorded,
            "keydown_count": len(b.get("page_received_keys") or []),
            "keypress_count": len(b.get("keypress_received") or []),
            "keyup_count": len(b.get("keyup_received") or []),
            "keydown_first": (b.get("page_received_keys") or [{}])[0].get("key") if b.get("page_received_keys") else None,
            "keypress_first": (b.get("keypress_received") or [{}])[0].get("key") if b.get("keypress_received") else None,
        })

print(f"Total trials: {n}, mismatches: {len(mismatches)} ({100*len(mismatches)/n:.1f}%)")
print()
print("Suspect-tally across mismatches:")
suspect_1 = sum(1 for m in mismatches if m["keydown_count"] > 0 and m["keypress_count"] == 0)
suspect_4 = sum(1 for m in mismatches if m["keydown_count"] > 1)
print(f"  Suspect 1 (keydown present, no keypress): {suspect_1} / {len(mismatches)}")
print(f"  Suspect 4 (multiple keydowns this trial): {suspect_4} / {len(mismatches)}")
print()
print("First 10 mismatch trials:")
for m in mismatches[:10]:
    print(f"  trial {m['trial']:>3}: bot={m['bot_pressed']} plat={m['plat_recorded']} | "
          f"kd={m['keydown_count']}({m['keydown_first']!r}) kp={m['keypress_count']}({m['keypress_first']!r}) ku={m['keyup_count']}")
EOF
```

- [ ] **Step 2: Open the previous SP9a stroop sessions for comparison context**

```bash
# Look at the SP9a stroop sessions for reference — those used the SAME TaskCard
ls -t output/expfactory_stroop/2026-05-13_18-3*/run_metadata.json | head
```

(No script needed — just have the directories findable in case Step 3's analysis needs to cross-reference.)

- [ ] **Step 3: Append Phase B.3 findings to `docs/sp9c-investigation.md`**

Below the Phase B.1 section, append:

```markdown
## Phase B.3 — Per-trial empirical findings

### Session

- Path: `output/expfactory_stroop/<timestamp>/`
- Seed: 9601
- N trials: <from script output>
- Mismatch count (`bot_pressed != platform_recorded`): <X / N>

### Suspect tally across mismatches

| Suspect | Pattern | Count | % of mismatches |
|---|---|---|---|
| 1 (listener type) | keydown present, keypress absent | <from script> | <pct> |
| 2 (choices filter) | events present but key format differs from plugin choices | <hand-counted from sample> | <pct> |
| 3 (response-window) | events present but timestamp outside trial's response window | <hand-counted from sample> | <pct> |
| 4 (multiple presses) | >1 keydown event in this trial's array | <from script> | <pct> |

### Dominant suspect

[Identify the suspect that explains the largest fraction of mismatches. State it explicitly: "Suspect N dominates with <X>% of mismatches."]

### Implication for Phase C fix

[State the Phase C fix shape based on the dominant suspect, referring to the spec §3 Phase C fix-shape table.]
```

- [ ] **Step 4: Commit**

```bash
git add docs/sp9c-investigation.md
git commit -m "$(cat <<'EOF'
docs(sp9c): Phase B.3 — per-trial findings identify dominant suspect

Analyzed bot_log + experiment_data for one stroop session under the
SP9c instrumentation. Counted suspects across mismatches and named
the dominant cause of the layer-(d) gap. Phase C's fix shape follows
from this finding per the spec's fix-shape table.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: User checkpoint — present findings before Phase C implementation

This task is a **decision gate**. The implementer presents the Phase B findings (the dominant suspect and the proposed fix shape) to the user and waits for go-ahead before proceeding to Task 8.

- [ ] **Step 1: Summarize the Phase B findings concisely (3-5 bullets)**

Output to the user:

```
Phase B findings (from docs/sp9c-investigation.md):
- Dominant suspect: <N — name>
- Mismatch rate this session: <X / N> trials (<pct>%)
- Phase C proposed fix shape per spec table: <description>
- Confidence in finding: <high/medium/low> (based on sample size and pattern strength)
- Open questions for user input: <e.g., scope, additional suspects to test>
```

- [ ] **Step 2: Wait for user input**

If user agrees → proceed to Task 8 (which assumes suspect 1 — see adaptive note in plan header; if a different suspect dominates, revise Task 8's code per spec §3 Phase C fix-shape table BEFORE proceeding).

If user requests changes → revise scope (split into smaller SP, defer some suspects, etc.). May require re-invoking the writing-plans skill for the revised Phase C scope.

No commit at this task — it's a gate, not a deliverable.

---

## Task 8: Phase C — Implement `_press_trial_key` helper (assuming suspect 1: listener type mismatch)

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (add new method + change one call site)
- Create: `tests/test_executor_trial_keypress.py`

**Adaptive note:** This task's code assumes Phase B revealed **suspect 1 (jsPsych listens on `keypress` or some path that `page.keyboard.press` doesn't fully trigger)**. If Phase B revealed a different dominant suspect, replace this task's code with the corresponding entry from spec §3 Phase C fix-shape table before executing. Re-run Task 7 as needed to confirm scope.

The new helper uses `page.dispatch_event` to fire all three keyboard events (`keydown`, `keypress`, `keyup`) with a fully-constructed `KeyboardEvent`. Existing `page.keyboard.press` stays at non-trial-keypress call sites (navigation, attention checks, feedback).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_executor_trial_keypress.py`:

```python
"""Unit tests for SP9c's _press_trial_key helper.

The helper dispatches keydown + keypress + keyup events directly to
document via page.dispatch_event with a fully-constructed
KeyboardEvent. Paradigm-agnostic — uses only Web Platform APIs.
"""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from experiment_bot.core.executor import TaskExecutor


def _stub_executor() -> TaskExecutor:
    return TaskExecutor.__new__(TaskExecutor)


@pytest.mark.asyncio
async def test_press_trial_key_dispatches_three_events():
    """The helper must call page.dispatch_event with keydown, keypress,
    and keyup events for the given key."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    await stub._press_trial_key(page, ",")
    # Each dispatch goes through page.evaluate with a JS snippet that
    # constructs and dispatches three events.
    js = page.evaluate.call_args.args[0]
    assert "KeyboardEvent" in js
    assert "'keydown'" in js
    assert "'keypress'" in js
    assert "'keyup'" in js
    assert "dispatchEvent" in js


@pytest.mark.asyncio
async def test_press_trial_key_passes_key_into_event_constructor():
    """The key string is embedded in the JS so the KeyboardEvent has the
    right `key` property."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    await stub._press_trial_key(page, ",")
    js = page.evaluate.call_args.args[0]
    # The key value should appear in the constructed event payload
    assert "','" in js or '","' in js


@pytest.mark.asyncio
async def test_press_trial_key_handles_special_keys():
    """Non-printable keys (ArrowLeft, Space) work the same as char keys."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    await stub._press_trial_key(page, "ArrowLeft")
    js = page.evaluate.call_args.args[0]
    assert "ArrowLeft" in js


@pytest.mark.asyncio
async def test_press_trial_key_swallows_dispatch_errors():
    """If page.evaluate raises (page teardown mid-trial), the helper
    must not propagate — the executor's existing error handling treats
    these as benign."""
    stub = _stub_executor()
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page closed"))
    # Should not raise
    await stub._press_trial_key(page, ",")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_executor_trial_keypress.py -v
```

Expected: all four tests FAIL — `_press_trial_key` does not exist.

- [ ] **Step 3: Add `_press_trial_key` to TaskExecutor**

In `src/experiment_bot/core/executor.py`, find the `_install_keydown_listener` method (around line 660). Add the new method ABOVE it:

```python
    async def _press_trial_key(self, page, key: str) -> None:
        """SP9c: deliver a trial-time keypress by dispatching three
        Web Platform KeyboardEvents (keydown + keypress + keyup) directly
        to `document`.

        This bypasses Playwright's `keyboard.press` synthetic events
        which, per SP7 layer-(d) findings, don't always trigger
        platform listeners (e.g., jsPsych's keyboard-response-plugin).
        By constructing KeyboardEvents and dispatching them ourselves,
        we control the event shape and target precisely.

        Paradigm-agnostic — uses Web Platform APIs only. The bot's
        own document-level listeners (installed by
        _install_keydown_listener) capture these events as expected
        for diagnostic purposes.

        Errors are swallowed: if `page.evaluate` raises (page torn
        down mid-trial), the executor's existing trial-handling will
        observe the missing keypress via the bot_log / platform data
        and proceed accordingly.
        """
        # Escape backslashes and quotes in `key` defensively. Most keys
        # are single chars or simple names ("ArrowLeft"), so escaping
        # is usually a no-op, but handle the edge case.
        safe_key = key.replace("\\", "\\\\").replace("'", "\\'")
        js = (
            "(() => {"
            "  const init = {"
            f"    key: '{safe_key}',"
            f"    code: '{safe_key}',"
            "    bubbles: true,"
            "    cancelable: true,"
            "    composed: true,"
            "  };"
            "  document.dispatchEvent(new KeyboardEvent('keydown', init));"
            "  document.dispatchEvent(new KeyboardEvent('keypress', init));"
            "  document.dispatchEvent(new KeyboardEvent('keyup', init));"
            "})()"
        )
        try:
            await page.evaluate(js)
        except Exception as e:
            logger.warning("_press_trial_key failed (page may be torn down): %s", e)
```

- [ ] **Step 4: Find the trial-keypress call site and replace `page.keyboard.press` there**

In `src/experiment_bot/core/executor.py`, find the trial-keypress call at line ~986:

```python
        await page.keyboard.press(resolved_key)
```

This call lives inside the trial-handling code (after stimulus detection, before trial-end wait). Inspect 5-10 lines of surrounding context to confirm it's the trial keypress and NOT a navigation/attention-check press. The neighboring code should reference `match.condition`, `resolved_key`, and `_wait_for_trial_end`.

Replace just that one line with:

```python
        await self._press_trial_key(page, resolved_key)
```

Leave other `page.keyboard.press` call sites (navigation, attention checks, etc.) unchanged.

- [ ] **Step 5: Run new tests + full suite for regressions**

```bash
uv run pytest tests/test_executor_trial_keypress.py -v
uv run pytest -q
```

Expected: all four new tests PASS. Full suite at 572 passed (568 from Task 2 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor_trial_keypress.py
git commit -m "$(cat <<'EOF'
feat(executor): _press_trial_key uses dispatch_event with KeyboardEvent

Phase C of SP9c. Replaces page.keyboard.press at the trial-keypress
call site with a new helper that constructs and dispatches three
KeyboardEvents (keydown + keypress + keyup) directly to document.
This bypasses Playwright's synthetic-event path which (per Phase B
findings) doesn't reliably trigger the platform's
keyboard-response-plugin listener.

Web Platform APIs only — no jsPsych-specific selectors. Existing
page.keyboard.press stays at non-trial-keypress call sites
(navigation, attention checks, feedback).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Phase C empirical validation — 2 paradigms × 2 seeds = 4 sessions, audit

**Files:**
- Generated: `output/<paradigm>/<timestamp>/` × 4 (gitignored)

Run validation sessions on two jsPsych platforms and hand-roll alignment audits comparing before (SP9a baseline) vs after (SP9c fix).

- [ ] **Step 1: Run 2 stroop sessions**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp9c
set -a && source /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.env && set +a
export EXPERIMENT_BOT_LLM_CLIENT=api
echo "=== stroop seed 9701 ===" && uv run experiment-bot --label expfactory_stroop --seed 9701 https://deploy.expfactory.org/preview/10/ 2>&1 | tail -3
echo "=== stroop seed 9702 ===" && uv run experiment-bot --label expfactory_stroop --seed 9702 https://deploy.expfactory.org/preview/10/ 2>&1 | tail -3
```

- [ ] **Step 2: Run 2 stop-it sessions**

```bash
# Confirm sp8 stopit TaskCard is present
ls taskcards/stopit_stop_signal/
# Should include 39e97714.json. If missing, copy from sp8 worktree.
echo "=== stopit seed 9801 ===" && uv run experiment-bot --label stopit_stop_signal --seed 9801 https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html 2>&1 | tail -3
echo "=== stopit seed 9802 ===" && uv run experiment-bot --label stopit_stop_signal --seed 9802 https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html 2>&1 | tail -3
```

- [ ] **Step 3: Audit each session**

```bash
uv run python <<'EOF'
import json, csv
from pathlib import Path
from collections import Counter

def audit(ses_dir: Path, label: str, condition_set: set):
    bot_log = json.loads((ses_dir / "bot_log.json").read_text())
    # Try JSON first, then CSV
    json_path = ses_dir / "experiment_data.json"
    csv_path = ses_dir / "experiment_data.csv"
    if json_path.exists():
        plat = json.loads(json_path.read_text())
    elif csv_path.exists():
        with csv_path.open() as f:
            plat = list(csv.DictReader(f))
    else:
        return None
    test_rows = [r for r in plat if r.get("trial_id") in ("test_trial", "stop_signal_trial")]
    bot_trials = [t for t in bot_log if t.get("condition") in condition_set]
    n = min(len(bot_trials), len(test_rows))
    c = Counter()
    for i in range(n):
        b = bot_trials[i]
        p = test_rows[i]
        c["pressed==recorded"] += (b.get("response_key") == p.get("response"))
        c["intended==expected"] += (b.get("resolved_key_pre_error") == p.get("correct_response"))
    return {"n": n, "pressed_recorded_pct": 100*c["pressed==recorded"]/n if n else 0, "intended_expected_pct": 100*c["intended==expected"]/n if n else 0}

# Find SP9c session dirs (seeds 9701, 9702, 9801, 9802 — most recent four)
results = []
for label, conds in [
    ("expfactory_stroop", {"congruent", "incongruent"}),
    ("stopit_stop_signal", {"go", "stop", "stop_signal", "go_signal"}),
]:
    dirs = sorted(Path(f"output/{label}").glob("2026-05-13_*"))[-2:]
    for d in dirs:
        r = audit(d, label, conds)
        if r:
            results.append((label, d.name, r))

print(f"{'paradigm':<22} | {'session':<22} | {'n':<4} | pressed==recorded | intended==expected")
print("-" * 95)
for label, ses, r in results:
    print(f"{label:<22} | {ses:<22} | {r['n']:<4} | {r['pressed_recorded_pct']:>15.1f}% | {r['intended_expected_pct']:>15.1f}%")
EOF
```

The script output is the input data for the results report (Task 10). No commit at this task.

---

## Task 10: Phase C results report

**Files:**
- Create: `docs/sp9c-results.md`

- [ ] **Step 1: Draft the results report**

Create `docs/sp9c-results.md` using this structure:

```markdown
# SP9c — Layer (d) investigation and fix: results

**Date:** 2026-05-13
**Spec:** `docs/superpowers/specs/2026-05-13-sp9c-layer-d-investigation-design.md`
**Plan:** `docs/superpowers/plans/2026-05-13-sp9c-layer-d-investigation.md`
**Investigation:** `docs/sp9c-investigation.md`
**Branch:** `sp9c/layer-d-investigation` (off `sp9b-complete`)
**Tag (after this report lands):** `sp9c-complete`

## Goal

Close the page→platform keypress gap (SP7 layer d) by identifying which of three SP7-named suspects dominates jsPsych's layer-(d) gap, then implementing a Web-Platform-only fix at the trial-keypress site.

## Phase B finding (summary)

[From docs/sp9c-investigation.md — dominant suspect, % of mismatches, fix shape.]

## Phase C fix

[Description of the helper landed in Task 8 and which call site it replaced.]

## Empirical results

| Paradigm | n trials | `pressed==recorded` (SP9c) | SP9a baseline | Delta |
|---|---|---|---|---|
| stroop seed 9701 | <n> | <pct> | 47.5% (seed 9201) | <delta> |
| stroop seed 9702 | <n> | <pct> | 50.0% (seed 9202) | <delta> |
| stopit seed 9801 | <n> | <pct> | (no SP9a baseline) | n/a |
| stopit seed 9802 | <n> | <pct> | (no SP9a baseline) | n/a |
| **Aggregate stroop (SP9c)** | <sum> | <pct> | **48.6% (SP9a, 360 trials)** | <delta> |

## Reading

[Whether the fix lifted pressed==recorded across both paradigms, only one, or neither. Honest framing — if mixed, say so.]

## Comparison to SP9a

[How Phase C's improvement (or lack of it) interacts with SP9a's SessionAgent and SP8's response_key_js prompt. Cross-paradigm picture.]

## Framework gaps remaining (SP9d candidates)

[List items still open: cognition.run platform, stop-signal condition-name mismatch, per-stimulus mapping for conflict tasks, etc.]

## Status

✅/⚠/❌ **SP9c internal CI gate:** [PASS/MIXED/FAIL with test count.]
✅/⚠/❌ **SP9c external descriptive evidence:** [PASS/MIXED/FAIL with one-sentence summary.]

**Recommended next step:** [SP9d candidate or other.]

Tag `sp9c-complete` on the commit landing this report.
```

Fill in all bracketed sections from Task 9's audit script output and Phase B's investigation document.

- [ ] **Step 2: Commit**

```bash
git add docs/sp9c-results.md
git commit -m "$(cat <<'EOF'
docs(sp9c): empirical results for layer-d fix

[1-3 sentence headline summary: did the fix close the page→platform
gap on the two jsPsych testbeds, and by how much?]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Documentation + tag + push

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/reviewer-1-charter.md`

- [ ] **Step 1: Append SP9c entry to CLAUDE.md sub-project history**

In `CLAUDE.md`, find the SP9b entry. Add the SP9c entry directly after it (using the same shape as SP9a/SP9b entries):

```
- **SP9c**: Layer (d) investigation and fix. New paradigm-agnostic
  instrumentation in `core/executor.py` — `_install_keydown_listener`
  now installs `keydown` + `keypress` + `keyup` capture-phase listeners
  on document; per-trial drain captures all three event arrays into
  `bot_log.json`. Phase B diagnostic on one stroop session identified
  [dominant suspect] as the cause of the layer-(d) gap. Phase C fix:
  new `_press_trial_key` helper uses `page.dispatch_event` with
  fully-constructed `KeyboardEvent`s at the trial-keypress call site;
  navigation / attention-check / feedback keypresses keep
  `page.keyboard.press`. Internal: [N] passed (was 564). External:
  stroop `pressed==recorded` <SP9a%> → <SP9c%>, stop-it
  `pressed==recorded` <pct>. Cognition.run validation deferred (no
  TaskCard available). See `docs/sp9c-investigation.md` for
  diagnostic and `docs/sp9c-results.md` for empirical comparison.
  Tag `sp9c-complete`. ✓ Complete.
```

Fill in [bracketed] values from Tasks 6, 9, 10.

- [ ] **Step 2: Bump reviewer-1-charter.md "Last reviewed at" line**

In `docs/reviewer-1-charter.md`, find the line:

```
**Last reviewed at:** sp9b-complete (SP9b: Stage 4 openalex defensive fix; next SP9 candidate: jsPsych platform-recording gap, SP7 layer d)
```

Replace with:

```
**Last reviewed at:** sp9c-complete (SP9c closed the layer-d gap via dispatch_event-based trial keypress; next SP9 candidate: TaskCard key_map schema standardization)
```

If Phase C's fix changes how the bot delivers keys at the trial site (it does), add a probe candidate to the charter's threat model section: "Does the bot's keypress mechanism produce events indistinguishable from real user input (no synthetic-event-detection heuristic could flag it)?"

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md docs/reviewer-1-charter.md
git commit -m "$(cat <<'EOF'
docs(claude.md,reviewer-1): mark SP9c complete

SP9c closed the layer-(d) page→platform keypress gap on jsPsych
testbeds via dispatch_event-based trial keypress. Reviewer-1 charter
updated with a probe candidate covering the new keypress delivery
mechanism.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Tag and push**

```bash
git tag sp9c-complete
git push origin sp9c/layer-d-investigation
git push origin sp9c-complete
```

Expected: branch and tag both land on origin. Verify with `git ls-remote origin sp9c-complete`.

---

## Self-review notes

**Spec coverage:**
- Section 1 (motivation): plan header references it ✓
- Section 2 (hypothesis + 3 suspects): Tasks 4-6 directly test the suspects ✓
- Section 3 (approach: Phase A/B/C): Tasks 1-2 are Phase A, Tasks 4-6 are Phase B, Tasks 8-9 are Phase C ✓
- Section 4 (out of scope): no task touches Stage 6, key_map schema, cognition.run regen, per-stimulus mapping, SessionAgent modification, wholesale `page.keyboard.press` replacement ✓
- Section 5 (deliverables): all files present in task table; tag in Task 11 ✓
- Section 6 (open questions): Task 7 explicitly addresses Q1 (rename vs keep `page_received_keys`) and Q2 (multi-suspect handling) as user-input gates; Q3 (cognition.run) is explicitly deferred and named in Task 11's CLAUDE.md entry ✓

**Placeholder scan:** Task 8's adaptive note + Task 7's checkpoint are NOT placeholders — they're explicit decision gates with concrete pre-condition behavior. Tasks 6 and 10 have `<...>` brackets in the results-report template, but each bracketed section explicitly says what data fills it (from Task 5 script output, etc.). Test count `[N]` in Task 11 is determined empirically from the final `uv run pytest -q`.

**Type consistency:**
- `_install_keydown_listener` keeps SP7's name but installs three listeners (documented in docstring).
- `_drain_keydown_log` returns `dict | None` (changed from `list | None` — documented in docstring; matches Task 2 tests).
- `_log_trial_with_keypress_diag` writes 4 fields total: `resolved_key_pre_error`, `page_received_keys`, `keypress_received`, `keyup_received`. Matches Task 2 tests.
- `_press_trial_key(page, key)` signature is consistent between Task 8 implementation and Task 8 tests.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-sp9c-layer-d-investigation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, spec-compliance review between tasks (skipping code-quality review per saved feedback memory), fast iteration in this session. Phase B (Task 4) requires WebFetch which only the controller can dispatch; Tasks 5/9 require browser sessions which the user usually wants to watch.

**2. Inline Execution** — execute tasks here using `superpowers:executing-plans`, batch execution with checkpoints for your review.

Which approach?

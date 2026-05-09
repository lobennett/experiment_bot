# SP6 — Executor trial-end fallback (close over-firing detection)

## Origin

SP5 (`docs/sp5-heldout-measurement-results.md`) measured held-out behavioral fidelity for Flanker and n-back. Aggregate accuracy and rt_distribution metrics looked good, but Flanker's `post_error_slowing` came out -7.23ms (facilitation) vs configured +10–50ms (slowing). Investigation initially framed as a Flanker-specific PES bug pivoted to a deeper finding:

The bot's logged stimulus-response entries are 2–3× the platform's recorded test trials per session (Flanker: 240–280 vs 120; n-back: 320–350 vs 120). The bot's `intended_error` flag and the platform's `correct_trial == 0` are statistically independent (intersection equals chance prediction across all 10 sessions). Per-trial alignment is broken, even though aggregate accuracy lands within configured ranges (~92–95%).

Root cause: `core/executor.py:533-540` skips `_wait_for_trial_end` when `runtime.timing.response_window_js` is None. The polling loop loops back, re-detects the same stimulus still on screen, and fires another trial-detection + keypress. Across SP5's TaskCards:

| Paradigm | response_window_js | Per-trial alignment |
|---|---|---|
| `expfactory_stop_signal` | set | ✓ (the only paradigm with reliable sequential metrics) |
| `expfactory_flanker` | None | ✗ over-fires ~2× |
| `expfactory_n_back` | None | ✗ over-fires ~3× |
| `expfactory_stroop` | None | ✗ probably over-fires (unmeasured) |

The fix is at the executor layer (held-out compatible — no Stage 1 prompt edits) and is paradigm-agnostic.

## Goal

When `runtime.timing.response_window_js` is None (or missing), the executor falls back to polling the matched stimulus's own detection JS (inverted) — waits for the stimulus to no longer be detected before resuming the polling loop. This prevents the polling loop from re-detecting the same stimulus and double-firing the trial handler.

## Success criterion

Two-tier success:

**Internal (CI-checkable, gates SP6 completion):** unit tests covering:

1. `_wait_for_trial_end` with both `response_window_js` and `fallback_js` None returns immediately.
2. `_wait_for_trial_end` polls `response_window_js` when present and exits when it returns falsy.
3. `_wait_for_trial_end` polls `fallback_js` when `response_window_js` is None and exits when fallback returns falsy.
4. `_wait_for_trial_end` exits cleanly on timeout when JS keeps returning truthy.
5. `_wait_for_trial_end` exits cleanly when `page.evaluate` raises (e.g., page navigation).
6. `_stimulus_detection_js` builder produces correct JS for `dom_query`, `js_eval`, and `canvas_state` methods.
7. `_stimulus_detection_js` quotes selectors safely (no JS-injection from selector content).
8. `_stimulus_detection_js` caches per-stimulus-id (re-build cost paid once).

**External (descriptive, scientific evidence):** re-run SP5's Flanker measurement on the SP6 worktree:

- Bot stimulus-response entries should drop to ≈ platform test trials (target: within 10–20% tolerance, vs 2–3× currently).
- intended_error vs platform_error intersection should significantly exceed chance.
- `post_error_slowing` validator metric should re-land in or near the configured +25–55ms range.

Held-out outcome is the scientific evidence; it does not gate SP6 completion. If the re-run still shows residual misalignment, root cause is downstream of the trial-end logic and seeds the next SP.

## Architecture

Three small touch-points, all in `src/experiment_bot/core/executor.py`.

### Modified `_wait_for_trial_end`

Currently at L541-555:

```python
async def _wait_for_trial_end(
    self, page: Page, response_window_js: str, timeout_s: float = 5.0
) -> None:
    """Wait for the response window to close, indicating the current trial ended."""
    poll_s = self._config.runtime.timing.poll_interval_ms / 1000.0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            ready = await page.evaluate(response_window_js)
            if not ready:
                return
        except Exception:
            return
        await asyncio.sleep(poll_s)
```

Replace with:

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

    Prefer `response_window_js` if present (Stage 1 extraction got it).
    Otherwise fall back to `fallback_js` (the matched stimulus's own
    detection JS — wait for it to stop matching). When both are None,
    return immediately (current no-op behavior preserved for paradigms
    with neither signal).
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
            return
        await asyncio.sleep(poll_s)
```

Signature is backwards-compatible: existing callers pass positional `response_window_js`; the new `fallback_js` is keyword-only with default None.

### New `_stimulus_detection_js` helper

Builds a JS expression from a stimulus's `detection.method` and `detection.selector`. Mirrors the patterns at `_build_interrupt_check_js` (L568-571). Caches per-`stimulus_id` so the JS is rebuilt once per session, not per trial.

```python
def _stimulus_detection_js(self, stim: StimulusConfig) -> str | None:
    """Return a JS expression that returns truthy while ``stim`` is on
    screen. Used as a fallback for `_wait_for_trial_end` when the
    paradigm's `runtime.timing.response_window_js` is missing.

    Caches per-stimulus_id so the build cost is paid once.
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

The cache `_stimulus_detection_js_cache: dict[str, str | None]` is initialized to `{}` in `__init__`.

### Modified call site

The current call site at L533-540:

```python
if timing.response_window_js:
    await self._wait_for_trial_end(
        page,
        timing.response_window_js,
        timeout_s=timing.trial_end_timeout_s,
    )
```

Replace with:

```python
fallback = self._stimulus_detection_js(match.stimulus)
if timing.response_window_js or fallback:
    await self._wait_for_trial_end(
        page,
        timing.response_window_js,
        fallback_js=fallback,
        timeout_s=timing.trial_end_timeout_s,
    )
```

The outer `if` is preserved so the wait is skipped only when *neither* signal is available (the truly-no-signal case behaves identically to today). When `response_window_js` is set (e.g., expfactory_stop_signal), the helper uses it preferentially — current behavior unchanged.

## Data flow

```
Stimulus polling loop detects matched stimulus
    │
    ▼
Trial counter increments; bot decides intended_error,
 resolves response key, presses key, logs trial
    │
    ▼
Post-trial:
  preferred = timing.response_window_js
  fallback  = _stimulus_detection_js(match.stimulus)
    │
    ▼
_wait_for_trial_end(page, preferred, fallback_js=fallback, timeout_s)
    │
    ▼
poll page.evaluate(preferred or fallback) at poll_interval_ms cadence
    │
    ├── returns falsy ──▶ trial ended, resume polling for next stimulus
    │
    └── timeout (5s default) ──▶ proceed anyway (silently — already done in current code)
```

## Test strategy

### `tests/test_executor_trial_end.py` (new)

Unit tests using AsyncMock for the page object and a stub `TaskExecutor` (or just import-and-call the helpers directly if they can be invoked without a fully-initialized executor).

**`_wait_for_trial_end` cases:**

- `test_wait_returns_immediately_when_both_none`: with both args None, returns without invoking `page.evaluate` at all.
- `test_wait_uses_response_window_js_when_present`: `response_window_js="window.foo"`, `fallback_js="ignored"`, page.evaluate returns True, True, False; verify exits after 3rd call; verify the JS sent was "window.foo" each time (not "ignored").
- `test_wait_falls_back_to_stimulus_js_when_response_window_none`: `response_window_js=None`, `fallback_js="!!(stim)"`, page.evaluate returns True, False; verify exits after 2nd call; verify fallback JS was used.
- `test_wait_returns_on_timeout`: page.evaluate always returns True, `timeout_s=0.05`; verify function returns within (e.g.) 0.5s.
- `test_wait_returns_on_evaluate_exception`: page.evaluate raises; verify graceful return.

**`_stimulus_detection_js` cases:**

- `test_stimulus_detection_js_dom_query`: stim with `method="dom_query"`, `selector=".foo"` → returns `"document.querySelector('.foo') !== null"`.
- `test_stimulus_detection_js_js_eval`: stim with `method="js_eval"`, `selector="window.x === 1"` → returns `"!!(window.x === 1)"`.
- `test_stimulus_detection_js_canvas_state`: stim with `method="canvas_state"` → uses the `!!(...)` wrap.
- `test_stimulus_detection_js_quotes_safely`: stim with `dom_query` selector containing `'` → output uses the escaped form (e.g., `'\\''`).
- `test_stimulus_detection_js_caches`: call helper twice with the same stim object; verify the result is identical and the second call doesn't re-construct (e.g., monkeypatch `replace` and assert it's called once total across both invocations).
- `test_stimulus_detection_js_returns_none_for_empty_selector`: stim with `selector=""` → returns None.

### Held-out re-run (manual, descriptive)

Re-run 5 Flanker sessions on the SP6 worktree (seeds 6001-6005) and compute:

- `bot_count / platform_count` ratio per session (target: 1.0 ± 0.2).
- `intended_error ∩ platform_error` intersection vs chance prediction (`E[I] = n_intended × n_plat / n_trials`).
- Re-validate against `norms/conflict.json`; report new PES, lag1_autocorr, cse_magnitude.

Optionally re-run n-back the same way to cross-validate (n-back's gap was even more dramatic — 3× over-firing).

Document outcome in `docs/sp6-results.md`.

## Deliverables

- Worktree `.worktrees/sp6` on branch `sp6/trial-end-fallback`, branched off tag `sp5-complete`. Spec + plan cherry-picked from `sp5/heldout-measurement`.
- Code changes in `src/experiment_bot/core/executor.py` only.
- Tests in `tests/test_executor_trial_end.py` (new file).
- 5 Flanker re-run sessions in `output/flanker_rdoc/` (gitignored; reported descriptively).
- Re-validation report in `validation/sp6_heldout/` (committed).
- `docs/sp6-results.md` — descriptive measurement.
- Tag `sp6-complete`. Push branch + tag to origin.
- `CLAUDE.md` sub-project history updated.

## Out of scope

- **Stage 1 prompt update** to make `response_window_js` extraction more reliable. The executor fallback makes this less urgent. Future SP if the fallback's timeout bound fires in real runs.
- **Validator reading `bot_log.json`** for sequential metrics in addition to platform CSV. Cleaner architecture but a separate concern.
- **Re-running stroop / cognitionrun_stroop / stopit_stop_signal** to confirm no dev-paradigm regression. Worth doing post-SP6 if Flanker re-run is clean. Out of scope to keep this SP focused.
- **Investigating why aggregate accuracy still hits ~92% despite over-firing.** Statistical: most over-fired trials' keys are intended-correct. Documented as observation, not a fix target.
- **Multi-trial PES decay weights** (item 4 in `docs/sp2-validation-followups.md`). Untouched.
- **Tier 2/3 SP4 backlog items** at `docs/sp4-stage2-robustness.md`. Each their own SP.

## Sub-project boundary check

This spec is appropriately scoped to a single implementation plan:

- One concrete deliverable (executor fallback + Flanker re-validation).
- One bounded set of code changes (one file: `core/executor.py`).
- One pre-defined success criterion (internal CI gate + descriptive Flanker re-run alignment).
- A clear hand-off rule for findings (residual gaps after fallback → next SP).

If the held-out re-run reveals new mechanisms (e.g., the stimulus detection itself stays truthy even after the trial advances on some paradigms), the resulting SP7 would be its own brainstorm/spec/plan cycle.

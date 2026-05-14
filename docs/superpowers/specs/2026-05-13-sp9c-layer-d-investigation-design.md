# SP9c — Layer (d) investigation and fix: closing the page→platform keypress gap

**Date:** 2026-05-13
**Parent tag:** `sp9b-complete`
**Worktree:** `.worktrees/sp9c` off `sp9b-complete`
**Target tag:** `sp9c-complete`

## 1. Motivation

Across SP6 → SP7 → SP8 → SP9a, the bot's per-trial alignment with the platform's recorded response has been gated by two compounding layers (SP7's taxonomy):

- **Layer (a)** — bot's `response_key_js` resolution. SP8 partially closed this for paradigms with `window.correctResponse` (n-back 49.8% → 72.1%); SP9a tried runtime LLM and confirmed the limitation is architectural (single-key-per-condition doesn't fit conflict tasks).
- **Layer (d)** — page-level keydown events vs platform-recorded responses. Across every paradigm and every SP since SP7, `page_received == platform_recorded` has held at **26-64%**. Even when the bot delivers a keydown event to the page (`bot_pressed == page_received` ~93%), the platform's CSV `response` column reflects something else on roughly half the trials. SP9a's user observation during stroop runs (the platform kept showing "incorrect"/"please respond" feedback even when the bot was clearly pressing) is direct evidence.

Layer (d) is the single highest-leverage open item in the framework because:

1. **It affects every paradigm.** Unlike layer (a) which is paradigm-conditional (works for paradigms with `window.correctResponse`, fails for conflict tasks), layer (d) is present in every platform tested.
2. **Fixing it has compound benefits.** Once `page_received == platform_recorded` lifts toward 90%, the bot's intent-vs-recorded alignment improves correspondingly without any other change. Sequential metrics (PES, lag-1 autocorrelations) that depend on per-trial fidelity become trustworthy.
3. **The likely fix is small.** SP7 identified three candidate causes (listener type, choices filter, response-window timing). Each has a small, focused fix shape — not architectural rewrite.
4. **The user has already flagged it from direct observation.** This isn't a numbers-on-a-page concern; it's a visible bug the user noticed in stroop sessions.

## 2. Hypothesis and three suspects

The general problem statement is **paradigm-agnostic**: the bot's keypress sometimes doesn't make it from the page's keydown event to the platform's response field. The three candidate causes (from SP7's investigation) are also paradigm-agnostic:

1. **Listener type mismatch.** Bot fires `keydown` + `keyup` (via `page.keyboard.press`). If the platform's listener uses `keypress` instead of `keydown`, the bot's events don't trigger it. (Browsers fire `keypress` for character-producing keys, but its behavior across `key`/`code`/`charCode` is platform-dependent and `keypress` is officially deprecated — modern frameworks should use `keydown`, but some libraries still listen for the legacy event.)
2. **Choices/allowlist filter.** Most platforms constrain valid keys per trial (jsPsych's `choices`, similar in other libraries). The filter compares the event's `.key` or `.code` against a list. If the bot's key format doesn't match exactly (case, English-word vs single-char, key vs code), the filter rejects.
3. **Response-window timing.** The platform's listener attaches at stimulus onset and detaches at trial end. The bot polls for stimulus detection and then fires a press; if the bot's press lands *before* the listener attaches (rare but possible at trial transitions) or *after* the response window closes, it's silently dropped.

A fourth less-likely cause:

4. **Multiple presses per trial.** Bot fires more than one press per trial (residual SP6 over-firing or feedback-screen confusion). Platform's listener fires on the FIRST valid keypress and records that one; the audit script reads from `page_received_keys[0]` which may be a different event. SP6 reduced over-firing to ~1.02× but not 1.00×.

## 3. Approach

Three phases. **The investigation IS the work** — the fix shape depends on what we learn in Phase B. The spec commits to Phases A and B; Phase C is a small focused commit whose contents are decided by Phase B's findings.

### Phase A — Generic, paradigm-agnostic instrumentation

Extend `_install_keydown_listener` in `src/experiment_bot/core/executor.py` to ALSO install `keypress` and `keyup` listeners on `document` (capture phase, mirroring the existing keydown listener). All three event arrays live at `window.__bot_keydown_log` / `window.__bot_keypress_log` / `window.__bot_keyup_log`.

Per-trial drain extended: each trial entry in `bot_log.json` gains three new fields:
- `keydown_received: list[dict]` (existing `page_received_keys`, renamed for symmetry — or kept as the old name with two new siblings; decided by implementer)
- `keypress_received: list[dict]`
- `keyup_received: list[dict]`

Each event dict carries `{key, code, time}` — `time` is `Date.now()` so we can correlate with stimulus-onset detection timestamps.

The instrumentation is **paradigm-agnostic** — no jsPsych selectors, no platform globals. It works on any HTML page.

### Phase B — Diagnostic

**Step B.1 — Read jsPsych source.** WebFetch `https://github.com/jspsych/jsPsych/blob/main/packages/plugin-html-keyboard-response/src/index.ts` (or equivalent path). Identify exactly which event the plugin listens for, how it filters by `choices`, and when the listener attaches/detaches relative to stimulus onset.

**Step B.2 — Run one stroop session with Phase A instrumentation enabled.** Stroop is the right testbed because SP9a already showed it has a clear layer-(d) gap (48.6% pressed→recorded). Reuse `expfactory_stroop/f099a88b.json` (SP8 TaskCard, now committed on sp8 branch).

**Step B.3 — Hand-roll per-trial analysis.** For every trial where `bot_pressed != platform_recorded`, what did the three event arrays contain? Look for patterns:
- Is `keypress_received` always empty while `keydown_received` is present? → Suspect 1 (listener type).
- Are the events present but the key format doesn't match what the plugin's `choices` would accept? → Suspect 2 (choices filter).
- Are events present but their `time` is outside the response window for the trial? → Suspect 3 (response-window timing).
- Are multiple events present and the platform picked a different one than the audit reads? → Suspect 4 (multiple presses).

**Step B.4 — Document findings in `docs/sp9c-investigation.md`.** This is a deliverable in its own right — even if Phase C's fix is small, the investigation document tells future SP work how layer (d) actually fails. The doc lands on a commit by itself.

### Phase C — Fix + multi-platform validation

The fix shape is one of these, depending on Phase B's findings:

| Phase B finding | Phase C fix |
|---|---|
| Suspect 1 (listener type) | New `_press_trial_key(page, key)` helper that uses `page.dispatch_event('document', 'keydown', {key, code, ...})` PLUS `'keypress'` PLUS `'keyup'` events with the right `KeyboardEvent` properties. Existing `page.keyboard.press` stays at non-trial-keypress call sites (navigation, attention checks, etc.). |
| Suspect 2 (choices filter) | Generic key-format normalization extended — the existing SP9a `_KEY_ALIASES` adds whatever formats Phase B identifies. Per-trial: the bot resolves its key, looks up the platform's `choices` (if accessible via the new instrumentation) or the configured key set, and normalizes. |
| Suspect 3 (response-window) | Bot's press is delayed until stimulus onset is confirmed (already happens via the polling loop). The fix is to read the platform's response-window-start timestamp (if exposed) and confirm the bot's press lands inside. If late presses are rare, the fix may be unnecessary; if frequent, the bot's polling cadence needs to be tighter. |
| Suspect 4 (multiple presses) | Bot drains `window.__bot_*_log` arrays BEFORE each trial's intentional press so only one event is in the array per trial. Plus tighter accounting of when residual SP6-style over-firing happens. |

**Fix discipline:**
- Only changes the trial-keypress call site (executor.py:986 region). Navigation / attention-check / feedback-screen keypresses keep `page.keyboard.press`.
- Uses Web Platform APIs only — `page.dispatch_event`, `KeyboardEvent` properties — no platform-specific globals.
- Tests: unit tests for the new helper(s) verify event shape and call count; integration test verifies the executor uses the new helper at the trial site.

**Multi-platform validation:**
- 2 sessions × 2 jsPsych platforms (expfactory_stroop + stopit_stop_signal). Different jsPsych versions/plugins; sanity check that the fix isn't accidentally jsPsych-version-specific.
- Cognition.run validation is best-effort. If a TaskCard becomes available (SP8 couldn't produce one — Stage 6 pilot exhausted), validate. Otherwise document as "deferred; jsPsych validation sufficient for the SP9c claim."
- Audit each session's `pressed==recorded` and `intended==expected` before vs after the fix. The before number for stroop is SP9a's 48.6%; SP9c's "after" target is somewhere meaningfully higher (e.g., 80%+ on stroop). Honest reporting: if the fix only moves one paradigm meaningfully, say so and frame the result accordingly.

### Decision points (user input expected)

- **After Phase B.4 lands:** present findings and propose the Phase C fix. User can redirect scope here (e.g., "I want to address suspects 1+2 together," or "let's defer suspect 3 to a future SP").
- **If Phase C empirical run shows mixed results:** present comparison, decide whether to iterate within SP9c or write a MIXED results report and ship.

## 4. Out of scope

- **Stage 6 pilot timing fragility** (SP8 backlog) — separate concern.
- **TaskCard `task_specific.key_map` schema standardization** (SP9a-surfaced) — separate concern.
- **`cognitionrun_stroop` TaskCard regeneration** — SP8 couldn't produce one. SP9c validates on whatever TaskCards exist; cognition.run is best-effort, not blocking.
- **Per-stimulus / stim-property mapping abstraction** (SP9a stroop layer-(a) limitation) — separate concern; lower priority once layer (d) is closed.
- **Modifying SP9a's SessionAgent.** SP9c is complementary. If SP9c lifts pressed→recorded, SessionAgent's directives may *post-hoc* look more useful, but no SessionAgent code changes.
- **Replacing `page.keyboard.press` at every call site.** Only at the trial-keypress site. Navigation-key presses (Enter on instructions, fullscreen button) and attention-check presses keep `page.keyboard.press` because they don't need the precision and the platforms accept them fine there.
- **New paradigm support.** Investigation uses the existing TaskCards (5 paradigms; cognition.run if-available).
- **Refactoring the keypress audit script.** SP9a noted the `--label` ↔ `PLATFORM_ADAPTERS` mismatch and the `.csv` vs `.json` handling gap. SP9c will hand-roll alignment audits and document the audit-script refactor as separate backlog.

## 5. Deliverables

### Workspace

Branch `.worktrees/sp9c` off `sp9b-complete` → branch name `sp9c/layer-d-investigation`.

### Files

**New:**
- `tests/test_executor_trial_keypress.py` — unit tests for the Phase C helper (created when Phase C lands).
- `docs/sp9c-investigation.md` — Phase B.4 findings document.
- `docs/sp9c-results.md` — Phase C multi-platform empirical results.

**Modified:**
- `src/experiment_bot/core/executor.py` — Phase A (extended listener install + per-trial drain) + Phase C (new `_press_trial_key` helper at the trial-keypress site).
- `tests/test_executor_keypress_diagnostic.py` — extend with `keypress`/`keyup` listener install tests.
- `CLAUDE.md` — append SP9c to sub-project history.
- `docs/reviewer-1-charter.md` — bump "Last reviewed at." Add probe candidate if Phase C's fix changes how the bot delivers keys.

### Run metadata

Every Phase A+ session writes the three event arrays into `bot_log.json` per trial. Backward-compatible — old `page_received_keys` field stays for compatibility; new fields land alongside.

### Tag

`sp9c-complete` on the commit landing `docs/sp9c-results.md`.

## 6. Open questions deferred to plan

1. Should `page_received_keys` (SP7 name) be renamed to `keydown_received` for symmetry with the two new fields, or kept as-is for backward compatibility? Decide during Phase A; either is defensible.
2. If Phase B reveals multiple suspects firing simultaneously, do we fix them in one SP9c commit or split into SP9c (one suspect) + SP9d (the others)? Decide based on fix complexity per suspect.
3. Cognition.run validation: WebFetch the cognition.run TaskCard / Stage 6 pilot logs to understand the SP8 exhaustion, OR accept "jsPsych-only validation, cognition.run deferred"? Lean toward the latter unless the cost of revival is small.

# SP9c — Layer (d) investigation

**Date:** 2026-05-13
**Spec:** `docs/superpowers/specs/2026-05-13-sp9c-layer-d-investigation-design.md`
**Plan:** `docs/superpowers/plans/2026-05-13-sp9c-layer-d-investigation.md`

## Phase B.1 — jsPsych keyboard-response-plugin source mechanics

### Listener type

**`keydown` (plus `keyup` for held-key tracking).** NOT keypress.

From `packages/jspsych/src/modules/plugin-api/KeyboardListenerAPI.ts`:

```javascript
rootElement.addEventListener("keydown", this.rootKeydownListener);
rootElement.addEventListener("keyup", this.rootKeyupListener);
```

**SP7 Suspect 1 (listener type mismatch — bot fires keydown, jsPsych listens for keypress) is RULED OUT.** jsPsych listens for keydown, which is what `page.keyboard.press` already fires.

### Listener target

**`rootElement` from `getRootElement()` — typically the `#jspsych-display-element` div, NOT `document`.** Attached in **bubble phase** (no third `true` arg).

```javascript
const rootElement = this.getRootElement();
if (rootElement) {
  rootElement.addEventListener("keydown", this.rootKeydownListener);
```

**This is the likely actual layer-(d) cause.** The bot's `page.keyboard.press(key)` dispatches keyboard events on `document.activeElement` (or `document` if no focus). Events bubble UP from the dispatch target through ancestors to `document`. They do NOT propagate DOWN into descendants. So if `rootElement` (a child of `body`) is below the dispatch target in the DOM, jsPsych's bubble-phase listener never fires.

For a real user: pressing `,` while focused inside `#jspsych-display-element` produces a keydown on the focused descendant → event bubbles UP through `#jspsych-display-element` → jsPsych's listener fires. For Playwright's `keyboard.press`: the synthetic event lands wherever the activeElement happens to be. If activeElement is NOT inside `#jspsych-display-element`, the event bubbles up but never reaches jsPsych's listener.

Smoke data from `output/n_back_rdoc/2026-05-15_*/bot_log.json` (140 trials, SP9c Phase A instrumentation): 170 keydown events on `document`, 170 keyup events on `document`, but only **11 keypress events** (~6.5% of keydowns). The keypress shortfall is a separate Playwright quirk (synthetic events for character-producing keys don't always fire keypress) — interesting but not the layer-(d) cause, since jsPsych doesn't listen for keypress.

### Choices filter shape

**Compares `e.key` against `valid_responses` using `Array.includes`.** Case-normalization is configurable via constructor's `areResponsesCaseSensitive` flag (default: case-insensitive, lowercases both sides).

```javascript
if (!this.areResponsesCaseSensitive && typeof valid_responses !== "string") {
  valid_responses = valid_responses.map((r) => r.toLowerCase());
}
// ...
const key = this.toLowerCaseIfInsensitive(e.key);
return validResponses.includes(key);
```

No `.code` / `.keyCode` matching. No aliasing beyond case.

**Implication for SP9a's English-word key fix:** SP9a's executor `_KEY_ALIASES` already converts `"comma"` → `","`. For paradigms where bot emits `.key="comma"` and choices=`[","]`, the bot's key would be rejected — but SP9a normalizes before emit, so this is closed already.

### Held-keys filter

```javascript
if (!allowHeldKey && this.heldKeys.has(key)) {
  return false;
}
```

If a keydown arrives for a key that's currently "held" (keydown received without subsequent keyup), it's rejected. `heldKeys` is updated on every keydown (add) and keyup (remove) globally.

**Implication:** if the bot fires multiple keydowns for the same key WITHOUT a keyup in between, the second keydown is rejected. SP6 reduced over-firing to ~1.02× but not 1.00×, so this MAY explain a small residual fraction of mismatches.

### Response-window lifecycle

Listener attaches per-trial at stimulus display (immediately after `display_element.innerHTML = ...`). Detaches when (a) a valid keydown is captured (if `response_ends_trial: true`), or (b) `trial_duration` elapses via `setTimeout(end_trial, trial_duration)`.

Bot's polling cadence (`poll_interval_ms`) is fast enough that presses landing after stimulus detection are inside the response window for most paradigms. Late-press rejection is possible but probably small.

### Implications for SP7 suspect taxonomy

| Suspect | Original framing | Phase B.1 verdict |
|---|---|---|
| 1 (listener type) | jsPsych uses `keypress` not `keydown` | **RULED OUT** — jsPsych uses keydown |
| 1' (NEW — listener target) | bot's events don't reach jsPsych's rootElement listener | **LIKELY DOMINANT** — bot dispatches on document/activeElement; jsPsych listens on `#jspsych-display-element` in bubble phase |
| 2 (choices filter) | bot's key format doesn't match `choices` array | Mostly closed by SP9a; case-normalization in jsPsych may still bite for non-stroop paradigms |
| 3 (response window) | bot's press lands outside window | Possible but small effect; bot polls aggressively after stim detection |
| 4 (held keys) | residual over-firing rejected by held-key filter | Possible; SP6 measured 1.02× over-firing — small residual |

### Proposed Phase C fix (subject to Phase B.3 data confirmation)

The Phase C fix shape: at the trial-keypress site, dispatch `KeyboardEvent`s explicitly on a target inside `#jspsych-display-element` (or generically: `document.activeElement || document.body`, after ensuring activeElement is inside the display root). The event has `bubbles: true` so it propagates up to jsPsych's listener.

For paradigm-agnosticism: don't hardcode `#jspsych-display-element`. Use `document.activeElement || document.body` as the dispatch target with `bubbles: true` — this works for any platform whose listener is at any ancestor of activeElement.

If Phase B.3 trial-level data confirms suspect 1' (events present in `keydown_received` but no platform record), Phase C ships that fix. Otherwise the data will redirect us.

---

## Phase B.3 — Per-trial empirical findings

### Session

- Path: `output/expfactory_stroop/2026-05-15_13-44-18/`
- Seed: 9601
- TaskCard: `expfactory_stroop/f099a88b.json` (SP8 regenerated, copied from sp8 worktree)
- N trials: 120

### Per-trial alignment (this session)

- `bot_pressed == platform_recorded`: **50.0%** (60/120) — matches SP9a stroop baseline (48.6% across 3 sessions)
- `bot_intended == platform_expected`: 34.2% (41/120)

### Aggregate event-type tally across 120 trials

| Event type | Count |
|---|---|
| keydown captured on document | 129 |
| keypress captured on document | **4** |
| keyup captured on document | 129 |

The bot fires ~1 keypress per trial (some over-firing residual from SP6 — 129/120 = 1.08×). Keypress events are essentially absent (4 vs 129 keydowns = ~3%). **But jsPsych listens for `keydown`, not `keypress` — so the keypress shortfall is not the layer-(d) cause.**

### Suspect tally across 60 mismatches

| Suspect | Pattern | Count | % of mismatches |
|---|---|---|---|
| No events at all in this trial's bot_log | `keydown_received == []` | 2 | 3% |
| **Bot's intended key landed on document's keydown listener** | `keydown_received[0].key == bot_pressed` | **55** | **92%** |
| Multiple keydowns this trial | `len(keydown_received) > 1` | 3 | 5% |

### Dominant suspect

**Suspect 1' (listener target mismatch) dominates with 92% of mismatches.**

In 55 of 60 mismatch trials, the bot's intended key was successfully captured by the document-level keydown listener (Phase A instrumentation). The event clearly reached the page's `document` and propagated through any capture-phase listener. But the platform's CSV `response` column reflects a different key on those trials — meaning jsPsych's bubble-phase listener on `#jspsych-display-element` (per Phase B.1) never received the event.

This rules out:
- Suspect 1 (listener type) — RULED OUT in Phase B.1
- Suspect 2 (choices filter) — bot sends `,` and `.` which match jsPsych's `choices` exactly
- Suspect 3 (response window) — events present in 92% of mismatches, just not landing on the right target
- Suspect 4 (held keys / over-firing) — only 5% of mismatches have multiple keydowns

The mechanism: `page.keyboard.press(key)` dispatches synthetic keyboard events on `document.activeElement` (or `document` if no element has focus). Events bubble UP from the dispatch target. jsPsych's `rootElement.addEventListener("keydown", ...)` uses **bubble phase** without the third `true` capture-arg, so the listener only fires for events that originate in `rootElement`'s subtree (i.e., descendants of `#jspsych-display-element`). If the bot's event lands on `document.activeElement` and that activeElement is NOT inside `#jspsych-display-element`, the event bubbles up to document and the rootElement listener never sees it.

### Trial-level evidence (sample mismatch trials)

| trial | bot pressed | plat recorded | keydown received | keypress received | keyup received |
|---|---|---|---|---|---|
| 0 | `,` | `.` | 1 (`,`) | 0 | 1 |
| 5 | `,` | `.` | 1 (`,`) | 0 | 1 |
| 10 | `.` | `,` | 1 (`.`) | 0 | 1 |
| 17 | `,` | `.` | 1 (`,`) | 0 | 1 |
| 23 | `.` | `,` | 1 (`.`) | 0 | 1 |

The pattern is consistent: the bot pressed correctly per its intended logic, the page-level document listener captured the event, but the platform recorded the opposite (or a different) key. This is the layer-(d) gap from SP7 quantified per-trial.

### Implication for Phase C fix

The fix is to dispatch the keyboard event such that it propagates through `#jspsych-display-element` to reach jsPsych's listener.

**Paradigm-agnostic implementation:** Use `page.evaluate` to (a) find a target inside the display root and (b) dispatch a `KeyboardEvent` on it with `bubbles: true`. Two candidate targets:
1. `document.activeElement` if it's a descendant of any element (best-effort)
2. `document.body.querySelector(":focus, [tabindex], input, button")` — find any focusable descendant
3. As a fallback: focus `document.body` first, then dispatch — Playwright's `keyboard.press` will then deliver to activeElement

Simplest path that addresses suspect 1':
- Before pressing, set focus on `document.body` (always inside any rootElement hierarchy is impossible since body IS the parent — but if we focus on whatever's CURRENTLY in the display root via `document.body.querySelector('[tabindex], #jspsych-display-element *, [class*="jspsych"] *')` or similar, the synthetic event will bubble up through rootElement).

A cleaner alternative: in `page.evaluate`, construct a `KeyboardEvent` and dispatch it directly on `document.body.querySelector('#jspsych-display-element') || document.body`. Falling back to `document.body` for non-jsPsych platforms keeps it paradigm-agnostic, but on jsPsych pages the event lands directly on the rootElement and is captured there (since the listener fires for events that ORIGINATE on rootElement, even before bubbling).

Wait — bubble-phase listeners fire when the event PROPAGATES THROUGH the element during bubbling. An event ORIGINATING on rootElement starts there, bubbles up; the bubble-phase listener attached to rootElement WILL fire (the event passes through rootElement on its way up). So dispatching directly on rootElement is sufficient.

**Concrete proposed fix:** new `_press_trial_key(page, key)` helper that does:

```javascript
(() => {
  const target = document.querySelector('#jspsych-display-element') || document.activeElement || document.body;
  const init = { key: '<KEY>', code: '<KEY>', bubbles: true, cancelable: true, composed: true };
  target.dispatchEvent(new KeyboardEvent('keydown', init));
  target.dispatchEvent(new KeyboardEvent('keyup', init));
})()
```

The `#jspsych-display-element` selector is a known jsPsych ID and a reasonable specific-then-fallback path. For non-jsPsych platforms (cognition.run, custom), the event still dispatches on `activeElement` or `body` with `bubbles: true`, matching the SP9a fallback behavior. This is more general than the spec's original "dispatch on document" because it specifically anchors on the listener target jsPsych uses.

**Concern:** the selector `#jspsych-display-element` IS jsPsych-specific. To stay paradigm-agnostic, we could use a more general approach: dispatch on the deepest visible interactive descendant. But that's complex and brittle. The hardcoded selector with a generic fallback is honest about the dominant case (jsPsych) while not breaking other platforms.

**Recommendation for user-checkpoint (Task 7):** ship the hardcoded `#jspsych-display-element` selector with the documented generic fallback, with a note in the helper docstring that this is the cleanest fix for the dominant testbed (jsPsych) and works no-worse than the existing `page.keyboard.press` for other platforms.

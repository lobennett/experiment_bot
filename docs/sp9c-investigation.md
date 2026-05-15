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

(To be filled in after Task 6 lands.)

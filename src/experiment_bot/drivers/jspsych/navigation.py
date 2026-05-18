"""SP10 jsPsych navigation helpers.

Per-plugin dispatch. Each known jsPsych plugin type has a specific
advance strategy informed by the vendored anchor files in
`vendor/jspsych/7.3.1/`:

- instructions: click `#jspsych-instructions-next` (Playwright's
  high-level `page.click` simulates a real user click; the plugin's
  one-shot `addEventListener("click", btnListener)` reliably fires).
  Also dispatch ArrowRight (the plugin's `key_forward` default) at
  the display root as a belt-and-suspenders backup.
- fullscreen: click `#jspsych-fullscreen-btn`. The plugin needs an
  actual user gesture to trigger the browser's fullscreen API.
- html-button-response, survey-html-form, etc.: click the visible
  forward-text button (regex: next/continue/start/begin/submit/yes).
- preload, html-display, anything unrecognized: dispatch Space +
  Enter + ArrowRight at the display root and hope one fires.

Paradigm-agnostic from the bot library's perspective (it just calls
navigate); jsPsych-specific from the driver's perspective (which is
correct per CLAUDE.md G2).
"""
from __future__ import annotations

import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


_DISPLAY_SELECTOR = "#jspsych-display-element"


# Reads the current plugin type + button IDs visible in the DOM.
_DECIDE_JS = """
(() => {
  if (!window.jsPsych) return { type_name: null, reason: 'no_jspsych' };
  let trial = null;
  try {
    trial = window.jsPsych.getCurrentTrial && window.jsPsych.getCurrentTrial();
  } catch (e) {}
  if (!trial) return { type_name: null, reason: 'no_current_trial' };
  let type_name = null;
  try {
    type_name = (trial.type && trial.type.info && trial.type.info.name) ||
                (trial.type && trial.type.name) ||
                (typeof trial.type === 'string' ? trial.type : 'unknown');
  } catch (e) { type_name = 'unknown'; }
  // Inventory of known jsPsych button IDs present in the display.
  const root = document.querySelector('#jspsych-display-element') || document.body;
  const present = {};
  for (const id of [
    'jspsych-instructions-next', 'jspsych-instructions-back',
    'jspsych-fullscreen-btn',
  ]) {
    present[id] = !!root.querySelector('#' + id);
  }
  // First visible button label (for forward-text matching fallback).
  let first_btn_label = null;
  let last_btn_label = null;
  try {
    const btns = Array.from(root.querySelectorAll('button')).filter(b => {
      const r = b.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && !b.disabled;
    });
    if (btns.length > 0) {
      first_btn_label = (btns[0].textContent || '').slice(0, 64);
      last_btn_label = (btns[btns.length - 1].textContent || '').slice(0, 64);
    }
  } catch (e) {}
  return { type_name, present, first_btn_label, last_btn_label };
})()
"""


# Dispatch generic keys (Space, Enter, ArrowRight) at the display root.
_DISPATCH_KEYS_JS = """
(() => {
  const root = document.querySelector('#jspsych-display-element') ||
               document.body;
  const dispatched = [];
  for (const [key, code] of [
    [' ', 'Space'], ['Enter', 'Enter'], ['ArrowRight', 'ArrowRight'],
  ]) {
    try {
      const init = { key, code, bubbles: true, cancelable: true };
      root.dispatchEvent(new KeyboardEvent('keydown', init));
      root.dispatchEvent(new KeyboardEvent('keyup', init));
      dispatched.push(code);
    } catch (e) {}
  }
  return { dispatched_keys: dispatched };
})()
"""


# Find the best forward-text button in the display and return its
# locator hint (the button text, since IDs may not exist for all
# plugins). Used by the html-button-response fallback path.
_FORWARD_BUTTON_TEXT_JS = """
(() => {
  const root = document.querySelector('#jspsych-display-element') ||
               document.body;
  const btns = Array.from(root.querySelectorAll('button')).filter(b => {
    const r = b.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !b.disabled;
  });
  if (btns.length === 0) return null;
  const forwardRe = /next|continue|start|begin|submit|ok|yes|finish/i;
  const backRe = /previous|back|cancel/i;
  // 1. button whose text matches forward
  let chosen = btns.find(b => forwardRe.test(b.textContent || ''));
  if (chosen) return (chosen.textContent || '').trim().slice(0, 64);
  // 2. last button (rightmost in DOM order) if it's not a back button
  const last = btns[btns.length - 1];
  if (!backRe.test(last.textContent || '')) return (last.textContent || '').trim().slice(0, 64);
  // 3. second-to-last
  if (btns.length > 1) {
    const sec = btns[btns.length - 2];
    return (sec.textContent || '').trim().slice(0, 64);
  }
  return (last.textContent || '').trim().slice(0, 64);
})()
"""


async def _click_by_id(page: Page, button_id: str) -> bool:
    """Use Playwright's high-level page.click to trigger a real-user
    click on the given button ID. Returns True on success."""
    selector = f"#{button_id}"
    try:
        # Short timeout so we don't hang here if the button vanished
        # between the decide-JS read and now.
        await page.click(selector, timeout=2000)
        return True
    except Exception as e:
        logger.debug("page.click(%s) failed: %s", selector, e)
        return False


async def _click_by_text(page: Page, text: str) -> bool:
    """Click a button whose textContent matches `text` via Playwright's
    locator. Used when no known plugin ID is present."""
    try:
        # Use a robust :has-text selector restricted to the display root.
        locator = page.locator(
            f"{_DISPLAY_SELECTOR} button:has-text({_escape_for_css(text)!r}):visible"
        )
        await locator.first.click(timeout=2000)
        return True
    except Exception as e:
        logger.debug("text-based click %r failed: %s", text, e)
        return False


def _escape_for_css(text: str) -> str:
    """Conservative escape for use in a Playwright :has-text(...)
    selector argument. Replaces backslashes and quotes."""
    return text.replace("\\", "\\\\").replace('"', "")


async def navigate_page(page: Page) -> dict:
    """Advance jsPsych through one non-trial step using per-plugin
    knowledge. Returns telemetry dict."""
    try:
        info = await page.evaluate(_DECIDE_JS)
    except Exception as e:
        logger.warning("navigate_page decide JS raised: %s", e)
        return {"action": "no_op", "type_name": "unknown", "details": {"error": str(e)}}

    type_name = info.get("type_name") or "unknown"
    present = info.get("present") or {}
    details = {"type_name": type_name, "present": present}

    # 1. instructions plugin — try multiple advance paths:
    #    a. Playwright's page.click on #jspsych-instructions-next
    #       (real-user-style click; should fire the plugin's
    #       addEventListener-bound btnListener).
    #    b. Playwright's page.keyboard.press("ArrowRight") (real
    #       keyboard input, not synthetic dispatchEvent — covers cases
    #       where the plugin's keyboard listener doesn't pick up our
    #       dispatchEvent for some reason).
    #    c. Generic dispatch of Space/Enter/ArrowRight at root.
    if "instructions" in type_name:
        if present.get("jspsych-instructions-next"):
            ok = await _click_by_id(page, "jspsych-instructions-next")
            details["clicked_id"] = "jspsych-instructions-next" if ok else None
        # Real Playwright keyboard press — uses Chromium's real input
        # event pipeline. Bypasses synthetic-event quirks.
        try:
            await page.keyboard.press("ArrowRight")
            details["pressed_real_key"] = "ArrowRight"
        except Exception as e:
            details["press_error"] = str(e)
        # Belt-and-suspenders: also dispatch generic keys at root.
        try:
            await page.evaluate(_DISPATCH_KEYS_JS)
            details["dispatched_keys"] = ["Space", "Enter", "ArrowRight"]
        except Exception:
            pass
        return {"action": "instructions_next", "type_name": type_name, "details": details}

    # 2. fullscreen plugin — click the fullscreen button.
    if "fullscreen" in type_name:
        if present.get("jspsych-fullscreen-btn"):
            ok = await _click_by_id(page, "jspsych-fullscreen-btn")
            details["clicked_id"] = "jspsych-fullscreen-btn" if ok else None
            return {"action": "fullscreen_button", "type_name": type_name, "details": details}

    # 3. html-button-response (and similar button-driven plugins) —
    #    click the visible forward-text button via locator.
    if "button-response" in type_name or "survey" in type_name:
        try:
            text = await page.evaluate(_FORWARD_BUTTON_TEXT_JS)
        except Exception:
            text = None
        if text:
            ok = await _click_by_text(page, text)
            details["clicked_text"] = text if ok else None
            if ok:
                return {"action": "clicked_button", "type_name": type_name, "details": details}

    # 4. Generic fallback: dispatch Space + Enter + ArrowRight at the
    #    display root. Also try clicking ANY visible forward-text
    #    button if one exists (covers unrecognized plugins with a
    #    "Continue" button).
    try:
        text = await page.evaluate(_FORWARD_BUTTON_TEXT_JS)
    except Exception:
        text = None
    if text:
        ok = await _click_by_text(page, text)
        details["fallback_clicked_text"] = text if ok else None
    try:
        await page.evaluate(_DISPATCH_KEYS_JS)
        details["dispatched_keys"] = ["Space", "Enter", "ArrowRight"]
    except Exception:
        pass
    return {"action": "fallback_advance", "type_name": type_name, "details": details}

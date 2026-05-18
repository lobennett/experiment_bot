"""SP10 jsPsych navigation helpers.

Per-plugin dispatch. Each known jsPsych plugin type has a specific
advance strategy informed by the vendored anchor files in
`vendor/jspsych/7.3.1/`:

- instructions: wait an adult silent-reading-pace interval (250 WPM)
  PER UNIQUE PAGE so jsPsych doesn't reject the advance as "too fast"
  (some experiments loop instructions back to page 1 if completed
  faster than a human could read). Then click
  `#jspsych-instructions-next` (Playwright's high-level `page.click`
  + a real `page.keyboard.press("ArrowRight")` + generic dispatch).
- fullscreen: click `#jspsych-fullscreen-btn`. The plugin needs an
  actual user gesture to trigger the browser's fullscreen API.
- html-button-response with non-trivial text: same reading-pace wait
  before clicking the forward-text button.
- preload, html-display, anything unrecognized: dispatch Space +
  Enter + ArrowRight at the display root.

Paradigm-agnostic from the bot library's perspective (it just calls
navigate); jsPsych-specific from the driver's perspective (which is
correct per CLAUDE.md G2).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


_DISPLAY_SELECTOR = "#jspsych-display-element"


# Adult silent reading rate. 250 WPM is conservative — slightly slower
# than the often-cited 300 WPM average, leaving room for processing
# time on instruction-heavy text.
_READING_RATE_WPS = 250.0 / 60.0  # ≈ 4.17 words/second

# Minimum wait per unique instruction page. Even a short "Press Next
# to continue" needs a couple seconds of human-eye dwell.
_MIN_READING_S = 3.0

# Maximum wait per page. Caps the total smoke time on absurdly long
# instruction text; real participants would skim past it too.
_MAX_READING_S = 30.0


# Module-level cache of page-text hashes we've already paced. Re-visits
# to the same page (e.g. after a back-button mishit) don't re-wait —
# we already "read" it. Keyed by sha1(innerText) so identical page
# content de-duplicates cleanly.
_seen_page_hashes: set[str] = set()


_READ_DISPLAY_TEXT_JS = """
(() => {
  const root = document.querySelector('#jspsych-display-element');
  if (!root) return '';
  return (root.innerText || root.textContent || '').trim();
})()
"""


def _estimate_reading_seconds(text: str) -> float:
    """Estimate adult silent-reading time for `text` in seconds."""
    if not text:
        return _MIN_READING_S
    words = len(text.split())
    seconds = max(_MIN_READING_S, words / _READING_RATE_WPS)
    return min(_MAX_READING_S, seconds)


async def _wait_for_reading(page: Page, details: dict) -> None:
    """Pace the bot's advance to adult silent-reading speed for the
    current page's visible text. Idempotent per unique text — second
    visit to identical page content is a fast no-op.

    Some jsPsych experiments (expfactory's stroop preview is one)
    detect superhuman-fast progression through the instructions and
    loop back to page 1. Waiting a human-like duration per page is
    the simplest and most general fix.
    """
    try:
        text = await page.evaluate(_READ_DISPLAY_TEXT_JS)
    except Exception as e:
        details["reading_wait_error"] = str(e)
        return
    details["reading_text_len"] = len(text) if isinstance(text, str) else 0
    if not text:
        # Empty display text — fall back to a minimum dwell so we don't
        # blast through hidden/transitional screens. Real users always
        # take SOME time even on a blank-looking page.
        details["reading_wait_s"] = _MIN_READING_S
        details["reading_wait_reason"] = "empty_text_min_dwell"
        await asyncio.sleep(_MIN_READING_S)
        return
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()
    if key in _seen_page_hashes:
        details["reading_wait"] = "already_seen"
        return
    _seen_page_hashes.add(key)
    secs = _estimate_reading_seconds(text)
    details["reading_word_count"] = len(text.split())
    details["reading_wait_s"] = round(secs, 2)
    await asyncio.sleep(secs)


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

    # 1. instructions plugin — pace advance to adult silent-reading
    #    speed (some experiments loop the timeline if you progress too
    #    fast). Then try multiple advance paths:
    #    a. Playwright's page.click on #jspsych-instructions-next.
    #    b. Real page.keyboard.press("ArrowRight").
    #    c. Generic dispatch of Space/Enter/ArrowRight at root.
    if "instructions" in type_name:
        # Wait an adult-reading-pace interval BEFORE advancing. Per-page
        # idempotent via the seen-hash cache.
        await _wait_for_reading(page, details)
        if present.get("jspsych-instructions-next"):
            ok = await _click_by_id(page, "jspsych-instructions-next")
            details["clicked_id"] = "jspsych-instructions-next" if ok else None
        try:
            await page.keyboard.press("ArrowRight")
            details["pressed_real_key"] = "ArrowRight"
        except Exception as e:
            details["press_error"] = str(e)
        try:
            await page.evaluate(_DISPATCH_KEYS_JS)
            details["dispatched_keys"] = ["Space", "Enter", "ArrowRight"]
        except Exception:
            pass
        return {"action": "instructions_next", "type_name": type_name, "details": details}

    # 2. fullscreen plugin — click the fullscreen button if visible;
    #    otherwise (we've already clicked, and jsPsych is in its 1-sec
    #    delay_after window) wait quietly. Dispatching keys/clicks
    #    during the delay_after window can push the page into an
    #    unintended state.
    if "fullscreen" in type_name:
        if present.get("jspsych-fullscreen-btn"):
            ok = await _click_by_id(page, "jspsych-fullscreen-btn")
            details["clicked_id"] = "jspsych-fullscreen-btn" if ok else None
            return {"action": "fullscreen_button", "type_name": type_name, "details": details}
        # Button not present → post-click delay_after window. Wait
        # silently for jsPsych to transition.
        await asyncio.sleep(0.5)
        return {"action": "fullscreen_wait", "type_name": type_name, "details": details}

    # 2b. inter-trial gap (no current trial) — wait quietly. jsPsych
    #     transitions take a few hundred ms; dispatching keys during
    #     this window can be interpreted as a response to whatever
    #     trial fires next.
    if type_name == "unknown" and not present:
        await asyncio.sleep(0.3)
        return {"action": "inter_trial_wait", "type_name": type_name, "details": details}

    # 3. html-button-response (and similar button-driven plugins) —
    #    dwell at reading pace, then click the visible forward-text
    #    button via locator.
    if "button-response" in type_name or "survey" in type_name:
        await _wait_for_reading(page, details)
        try:
            text = await page.evaluate(_FORWARD_BUTTON_TEXT_JS)
        except Exception:
            text = None
        if text:
            ok = await _click_by_text(page, text)
            details["clicked_text"] = text if ok else None
            if ok:
                return {"action": "clicked_button", "type_name": type_name, "details": details}

    # 4. Generic fallback: dwell briefly at reading pace, then dispatch
    #    Space + Enter + ArrowRight at the display root. Also try
    #    clicking ANY visible forward-text button if one exists
    #    (covers unrecognized plugins with a "Continue" button).
    await _wait_for_reading(page, details)
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

"""SP10 jsPsych navigation helpers.

These functions advance jsPsych through non-trial phases (instructions,
button-response, feedback, etc.) by dispatching the appropriate input
to the page. Paradigm-agnostic: no stroop/n-back/etc. assumptions.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# Dispatch a KeyboardEvent('keydown' + 'keyup') for Space to the
# jsPsych display element (or document.body if not present). bubbles=true
# so jsPsych's root listener catches it.
_DISPATCH_SPACE_JS = """
(() => {
  const target = document.querySelector('#jspsych-display-element') ||
                 document.body;
  const init = { key: ' ', code: 'Space', bubbles: true, cancelable: true };
  target.dispatchEvent(new KeyboardEvent('keydown', init));
  target.dispatchEvent(new KeyboardEvent('keyup', init));
  return { action: 'dispatched_space', target_id: target.id || null };
})()
"""


# Click the first <button> inside the display element. Used when
# jsPsych is showing html-button-response.
_CLICK_FIRST_BUTTON_JS = """
(() => {
  const root = document.querySelector('#jspsych-display-element') ||
               document.body;
  const btn = root.querySelector('button');
  if (!btn) return { action: 'no_op', reason: 'no_button' };
  btn.click();
  return { action: 'clicked_button',
           button_label: (btn.textContent || '').slice(0, 64) };
})()
"""


# Decide what to do based on the current jsPsych plugin type.
_DECIDE_NAVIGATE_JS = """
(() => {
  if (!window.jsPsych) return { action: 'no_op', reason: 'no_jspsych' };
  let trial = null;
  try {
    trial = window.jsPsych.getCurrentTrial && window.jsPsych.getCurrentTrial();
  } catch (e) {}
  if (!trial) return { action: 'noop_no_trial' };
  let type_name = null;
  try {
    type_name = (trial.type && trial.type.info && trial.type.info.name) ||
                (trial.type && trial.type.name) ||
                (typeof trial.type === 'string' ? trial.type : 'unknown');
  } catch (e) { type_name = 'unknown'; }
  return { action: 'recommend', type_name };
})()
"""


async def navigate_page(page: Page) -> dict:
    """Advance the page through one non-trial step.

    Strategy:
    1. Read current plugin type via _DECIDE_NAVIGATE_JS.
    2. If it's a button-response variant, click the first button.
    3. Otherwise (instructions, html-display, between-trials,
       hook-not-armed), dispatch Space.

    Returns telemetry: {action, type_name, details}.
    """
    try:
        info = await page.evaluate(_DECIDE_NAVIGATE_JS)
    except Exception as e:
        logger.warning("navigate_page decide JS raised: %s", e)
        info = {"action": "no_op", "reason": "decide_raised"}
    type_name = info.get("type_name") or "unknown"
    if info.get("action") == "recommend" and "button-response" in type_name:
        try:
            res = await page.evaluate(_CLICK_FIRST_BUTTON_JS)
            return {
                "action": res.get("action", "clicked_button"),
                "type_name": type_name,
                "details": res,
            }
        except Exception as e:
            logger.warning("navigate_page click JS raised: %s", e)
    # Default: dispatch Space.
    try:
        res = await page.evaluate(_DISPATCH_SPACE_JS)
        return {
            "action": res.get("action", "dispatched_space"),
            "type_name": type_name,
            "details": res,
        }
    except Exception as e:
        logger.warning("navigate_page dispatch JS raised: %s", e)
        return {"action": "no_op", "type_name": type_name, "details": {"error": str(e)}}

"""SP10 jsPsych response-delivery utilities.

The driver's setup() installs a hook on pluginAPI.getKeyboardResponse
(see driver.py's _INSTALL_HOOK_JS). This module holds the deliver()
helper that invokes the captured callback with a synthetic (key, rt).
"""
from __future__ import annotations

import json
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


_DELIVER_JS_TEMPLATE = """
(() => {
  const hook = window.__bot_hook;
  if (!hook || !hook.current) {
    return { ok: false, reason: 'no_active_listener' };
  }
  const info = { rt: %(rt)s, key: %(key_js)s };
  try {
    hook.current.callback_function(info);
    hook.history.push({
      key: info.key, rt: info.rt, delivered_at: performance.now(),
    });
    hook.current = null;
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: 'callback_raised', error: String(e) };
  }
})()
"""


async def deliver(page: Page, key: str, rt_ms: float) -> dict:
    """Invoke the captured jsPsych callback with (key, rt).

    Returns the JS-side outcome dict: `{ok: bool, reason?: str, error?: str}`.
    """
    js = _DELIVER_JS_TEMPLATE % {
        "rt": rt_ms,
        "key_js": json.dumps(key),
    }
    try:
        return await page.evaluate(js)
    except Exception as e:
        logger.warning("deliver() page.evaluate raised: %s", e)
        return {"ok": False, "reason": "evaluate_raised", "error": str(e)}

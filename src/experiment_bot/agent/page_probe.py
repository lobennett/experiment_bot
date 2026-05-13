"""Read-only probes of a live Playwright page.

All helpers are paradigm-agnostic: they read whatever the page exposes
and return it. SessionAgent calls them to build the LLM prompt; the
LLM does the paradigm-specific interpretation.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)

_DOM_TRUNCATION_LIMIT = 20480

_WINDOW_GLOBALS_JS = """
(() => {
  const out = {};
  const re = /response|correct|key|stim/i;
  for (const k of Object.keys(window)) {
    if (!re.test(k)) continue;
    try {
      const v = window[k];
      let s;
      if (v === null) s = "null";
      else if (typeof v === "object") s = JSON.stringify(v);
      else s = String(v);
      out[k] = s.length > 200 ? s.slice(0, 200) + "...[trunc]" : s;
    } catch (e) {
      out[k] = "<error reading: " + String(e) + ">";
    }
  }
  return out;
})()
"""


async def snapshot_window_globals(page: Page) -> dict:
    """Return a dict of window.* keys matching /response|correct|key|stim/i.

    Values are stringified and truncated to 200 chars. Returns {} on
    evaluation failure (page torn down, JS error, etc.).
    """
    try:
        return await page.evaluate(_WINDOW_GLOBALS_JS)
    except Exception as e:
        logger.warning("snapshot_window_globals failed: %s", e)
        return {}


async def snapshot_dom_summary(page: Page) -> str:
    """Return up to 20KB of page.content().

    No structural parsing — just a truncated raw HTML string. The LLM
    handles the rest.
    """
    try:
        content = await page.content()
    except Exception as e:
        logger.warning("snapshot_dom_summary failed: %s", e)
        return ""
    if len(content) > _DOM_TRUNCATION_LIMIT:
        return content[:_DOM_TRUNCATION_LIMIT]
    return content


async def capture_screenshot(page: Page) -> bytes:
    """Return a viewport-only PNG. Returns b'' on failure."""
    try:
        return await page.screenshot(type="png", full_page=False)
    except Exception as e:
        logger.warning("capture_screenshot failed: %s", e)
        return b""

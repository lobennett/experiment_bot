"""SP10 jsPsych data export — fetches the session's trial data.

jsPsych 7.x exposes window.jsPsych.data.get().json() returning the
canonical trial data as a JSON string. The driver wraps this in an
ExperimentData carrying (trials, format, raw, metadata) for the
executor and Oracle.
"""
from __future__ import annotations

import json
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


_FETCH_JS = """
(() => {
  if (!window.jsPsych || !window.jsPsych.data) return null;
  try {
    const dc = window.jsPsych.data.get();
    return dc && typeof dc.json === 'function' ? dc.json() : null;
  } catch (e) {
    return null;
  }
})()
"""


async def fetch_data_json(page: Page) -> str | None:
    """Return the jsPsych data.get().json() result as a string, or None
    on failure."""
    try:
        return await page.evaluate(_FETCH_JS)
    except Exception as e:
        logger.warning("fetch_data_json: page.evaluate raised: %s", e)
        return None

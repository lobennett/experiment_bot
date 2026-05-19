"""PlaywrightGateDismisser — pre-trial gate dismissal for live sessions.

Implements :class:`~experiment_bot.calibration.runner.GateDismisser`
for real Playwright sessions. Generic per G1 — no paradigm-specific
selectors. Strategy:

  1. Look for visible buttons (anything matching ``button``, ``input
     [type=button]``, or ``[role=button]``) whose visible text matches
     a small set of canonical advance-words (start, begin, continue,
     next, ok, ready, go). Click the first match.
  2. If no button is found or clicked, fall back to keyboard advance:
     fire Space, then Enter (both forward keys in jsPsych's
     instructions and instruction-loop plugins, and in plain HTML
     forms with submit buttons).
  3. Return True if either path executes successfully; False otherwise.

The dismisser does NOT verify that the gate is actually dismissed
afterwards — the calibration runner queries the trial-marker
post-dismiss to decide whether to proceed. False from this method just
means "no advance action could be issued"; calibration may still
proceed if the page wasn't gated.
"""
from __future__ import annotations

from .runner import GateDismisser

# Visible-text keywords that should match a "advance" button. Lowercased
# substring match. Generic — these words are paradigm-agnostic and appear
# across most experiment frameworks' welcome / start screens.
_ADVANCE_KEYWORDS: tuple[str, ...] = (
    "start", "begin", "continue", "next",
    "ok", "ready", "go",
)


class PlaywrightGateDismisser(GateDismisser):
    """Visible-button + keyboard-advance gate dismissal.

    Parameters:
      ``page`` — Playwright Page.
      ``advance_keywords`` — Override the default keyword list. Useful
        for non-English locales.
      ``keyboard_fallback_keys`` — Keys to press as a final fallback if
        no button is found. Default: ``("Space", "Enter")``.
    """

    def __init__(
        self,
        page,
        *,
        advance_keywords: tuple[str, ...] = _ADVANCE_KEYWORDS,
        keyboard_fallback_keys: tuple[str, ...] = ("Space", "Enter"),
    ):
        self._page = page
        self._keywords = tuple(k.lower() for k in advance_keywords)
        self._fallback_keys = tuple(keyboard_fallback_keys)

    async def _try_button_click(self) -> bool:
        """Find and click a visible advance button. Returns True if a
        click succeeded."""
        try:
            handles = await self._page.query_selector_all(
                "button, input[type=button], input[type=submit], [role=button]"
            )
        except Exception:
            return False
        for handle in handles:
            try:
                bbox = await handle.bounding_box()
            except Exception:
                bbox = None
            if not bbox or bbox.get("width", 0) < 1 or bbox.get("height", 0) < 1:
                continue
            try:
                text = (await handle.text_content() or "").strip().lower()
            except Exception:
                text = ""
            try:
                value = (await handle.get_attribute("value") or "").strip().lower()
            except Exception:
                value = ""
            combined = f"{text} {value}".strip()
            if not combined:
                continue
            if any(kw in combined for kw in self._keywords):
                try:
                    await handle.click()
                    return True
                except Exception:
                    continue
        return False

    async def _try_keyboard_advance(self) -> bool:
        any_ok = False
        for key in self._fallback_keys:
            try:
                await self._page.keyboard.press(key)
                any_ok = True
            except Exception:
                continue
        return any_ok

    async def dismiss(self) -> bool:
        clicked = await self._try_button_click()
        if clicked:
            return True
        return await self._try_keyboard_advance()

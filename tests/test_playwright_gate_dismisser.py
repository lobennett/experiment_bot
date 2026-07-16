"""PlaywrightGateDismisser unit tests."""
from __future__ import annotations

import asyncio
from typing import Any

from experiment_bot.calibration.playwright_gate_dismisser import (
    PlaywrightGateDismisser,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeButton:
    def __init__(
        self,
        text: str = "",
        value: str = "",
        bbox: dict | None = None,
        click_raises: bool = False,
    ):
        self._text = text
        self._value = value
        self._bbox = bbox if bbox is not None else {"width": 50, "height": 20}
        self._click_raises = click_raises
        self.clicked = False

    async def bounding_box(self):
        return self._bbox

    async def text_content(self):
        return self._text

    async def get_attribute(self, name: str):
        return self._value if name == "value" else None

    async def click(self):
        if self._click_raises:
            raise RuntimeError("click failed")
        self.clicked = True


class _FakeKeyboard:
    def __init__(self):
        self.presses: list[str] = []

    async def press(self, key: str):
        self.presses.append(key)


class _FakePage:
    def __init__(self, buttons: list[_FakeButton] | None = None):
        self._buttons = list(buttons or [])
        self.keyboard = _FakeKeyboard()

    async def query_selector_all(self, sel: str):
        return list(self._buttons)


def test_dismisses_via_start_button_click():
    """A visible button with 'Start' text gets clicked."""
    start_btn = _FakeButton(text="Start experiment")
    page = _FakePage(buttons=[start_btn])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert ok is True
    assert start_btn.clicked is True
    # Keyboard fallback shouldn't fire when button click succeeded.
    assert page.keyboard.presses == []


def test_dismisses_via_continue_button_click():
    """'Continue' is in the default keyword list."""
    btn = _FakeButton(text="Continue")
    page = _FakePage(buttons=[btn])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert ok is True
    assert btn.clicked is True


def test_skips_buttons_with_no_bounding_box():
    """Hidden buttons (zero-width or no bbox) should be skipped."""
    hidden = _FakeButton(text="Start", bbox={"width": 0, "height": 0})
    visible = _FakeButton(text="Start")
    page = _FakePage(buttons=[hidden, visible])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert ok is True
    assert hidden.clicked is False
    assert visible.clicked is True


def test_falls_back_to_keyboard_when_no_button():
    """If no advance-keyword button is present, fall back to Space+Enter."""
    page = _FakePage(buttons=[])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert ok is True
    assert "Space" in page.keyboard.presses
    assert "Enter" in page.keyboard.presses


def test_falls_back_to_keyboard_when_button_text_doesnt_match():
    """A button labeled 'Quit' should NOT be clicked — falls back to
    keyboard."""
    btn = _FakeButton(text="Quit")
    page = _FakePage(buttons=[btn])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert ok is True
    assert btn.clicked is False
    assert "Space" in page.keyboard.presses


def test_falls_back_to_keyboard_when_button_click_raises():
    """If the matched button's click() raises, the dismisser must
    still try keyboard fallback rather than crashing."""
    btn = _FakeButton(text="Start", click_raises=True)
    page = _FakePage(buttons=[btn])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert ok is True
    assert "Space" in page.keyboard.presses


def test_custom_advance_keywords_respect_locale():
    """Non-English locale support: caller passes its own keyword list."""
    btn = _FakeButton(text="Empezar")  # Spanish "Start"
    page = _FakePage(buttons=[btn])
    dismisser = PlaywrightGateDismisser(
        page, advance_keywords=("empezar", "comenzar")
    )
    ok = _run(dismisser.dismiss())
    assert btn.clicked is True
    assert ok is True


def test_matches_via_value_attribute_for_input_buttons():
    """input[type=submit] uses value attribute for label, not text."""
    btn = _FakeButton(text="", value="Start now")
    page = _FakePage(buttons=[btn])
    dismisser = PlaywrightGateDismisser(page)
    ok = _run(dismisser.dismiss())
    assert btn.clicked is True
    assert ok is True

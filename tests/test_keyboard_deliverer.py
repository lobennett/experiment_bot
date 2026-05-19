"""SP11 Phase 4b — PlaywrightKeyboardDeliverer unit tests.

Same four-step protocol as CDPDeliverer; uses ``page.keyboard.press``
instead of CDP. Mocked-Playwright tests only.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from experiment_bot.calibration.keyboard_deliverer import (
    PlaywrightKeyboardDeliverer,
    playwright_key_for,
)


def _run(coro):
    return asyncio.run(coro)


def test_playwright_key_for_translates_space_character():
    """Bare space ' ' must become 'Space' for Playwright API."""
    assert playwright_key_for(" ") == "Space"


def test_playwright_key_for_passes_through_named_keys():
    """Other names pass through unchanged."""
    for k in ("Space", "Enter", "ArrowRight", ",", ".", "/", "a", "5"):
        assert playwright_key_for(k) == k


# -----------------------------------------------------------------
# Mocks
# -----------------------------------------------------------------


class _FakeKeyboard:
    def __init__(self):
        self.presses: list[str] = []

    async def press(self, key: str):
        self.presses.append(key)


class _FakePage:
    def __init__(
        self,
        *,
        marker_sequence: list[Any] | None = None,
        records: list[dict] | None = None,
    ):
        self._markers = list(marker_sequence or [])
        self._idx = 0
        self._records = list(records or [])
        self.keyboard = _FakeKeyboard()

    async def evaluate(self, js: str):
        if "current_trial_global" in js:
            if self._idx < len(self._markers):
                v = self._markers[self._idx]
                self._idx += 1
                return v
            return self._markers[-1] if self._markers else None
        if "data.get" in js or "values" in js:
            return list(self._records)
        if "focus" in js or "activeElement" in js:
            return None
        return None


# -----------------------------------------------------------------
# Four-step protocol on keyboard channel
# -----------------------------------------------------------------


def test_keyboard_deliverer_fires_via_keyboard_press():
    """Step 4 uses page.keyboard.press, not CDP. Channel must tag as
    keyboard_press_fallback."""
    page = _FakePage(
        marker_sequence=[5, 5, 6],
        records=[{"trial_index": 5, "response": ",", "rt": 250}],
    )
    deliverer = PlaywrightKeyboardDeliverer(page, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([","], [1.0]))
    assert page.keyboard.presses == [","]
    assert events[0].metadata["delivery"]["channel"] == "keyboard_press_fallback"


def test_keyboard_deliverer_translates_space_to_Space_for_press():
    """Per playwright_key_for, ' ' becomes 'Space' when calling
    page.keyboard.press."""
    page = _FakePage(
        marker_sequence=[5, 5, 6],
        records=[{"trial_index": 5, "response": " ", "rt": 250}],
    )
    deliverer = PlaywrightKeyboardDeliverer(page, default_dwell_ms=1.0)
    _run(deliverer.deliver_sequence([" "], [1.0]))
    assert page.keyboard.presses == ["Space"]


def test_keyboard_deliverer_skips_on_no_trial_marker():
    """Step 1: skip if no trial marker (same as CDPDeliverer)."""
    page = _FakePage(marker_sequence=[None])
    deliverer = PlaywrightKeyboardDeliverer(page, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([","], [1.0]))
    assert events[0].metadata["skipped"] is True
    assert events[0].metadata["skip_reason"] == "no_trial_marker_available"
    assert page.keyboard.presses == []


def test_keyboard_deliverer_skips_on_advance_during_dwell():
    """Step 3: skip if trial marker advanced during dwell."""
    page = _FakePage(marker_sequence=[5, 6])
    deliverer = PlaywrightKeyboardDeliverer(page, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([","], [1.0]))
    assert events[0].metadata["skipped"] is True
    assert events[0].metadata["skip_reason"] == "trial_advanced_during_dwell"
    assert page.keyboard.presses == []


def test_keyboard_deliverer_pairs_records_by_trial_marker():
    """Same trial-marker-based pairing as CDP."""
    page = _FakePage(
        marker_sequence=[10, 10, 11,  # fire 1 OK
                         11, 11, 12],  # fire 2 OK
        records=[
            {"trial_index": 10, "response": ",", "rt": 200},
            {"trial_index": 11, "response": ".", "rt": 250},
        ],
    )
    deliverer = PlaywrightKeyboardDeliverer(page, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([",", "."], [1.0, 1.0]))
    assert events[0].is_correctly_recorded
    assert events[1].is_correctly_recorded
    assert events[0].metadata["trial_marker_at_fire"] == 10
    assert events[1].metadata["trial_marker_at_fire"] == 11

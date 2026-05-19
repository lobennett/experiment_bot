"""SP11 Phase 4b — CDPDeliverer unit tests.

Tests the four-step per-trial protocol and the CDP field map. Uses
mocked Playwright Page + CDP session — no live browser. Live-browser
smoke tests live in ``test_phase4b_paradigm_smokes.py`` (RUN_LIVE
env-gated).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from experiment_bot.calibration.cdp_deliverer import (
    CDPDeliverer,
    KEY_TO_CDP_FIELDS,
    cdp_fields_for,
)
from experiment_bot.calibration.deliverer import KeypressEvent


def _run(coro):
    return asyncio.run(coro)


# -----------------------------------------------------------------
# CDP field map
# -----------------------------------------------------------------


def test_cdp_field_map_covers_stroop_response_keys():
    """Phase 4a established Comma=188, Period=190, Slash=191. Phase
    4b's map must keep them and surface them under those exact keyCodes
    so downstream paradigms get the same fidelity as the spike."""
    assert KEY_TO_CDP_FIELDS[","]["windowsVirtualKeyCode"] == 188
    assert KEY_TO_CDP_FIELDS[","]["code"] == "Comma"
    assert KEY_TO_CDP_FIELDS["."]["windowsVirtualKeyCode"] == 190
    assert KEY_TO_CDP_FIELDS["."]["code"] == "Period"
    assert KEY_TO_CDP_FIELDS["/"]["windowsVirtualKeyCode"] == 191
    assert KEY_TO_CDP_FIELDS["/"]["code"] == "Slash"


def test_cdp_field_map_covers_nback_digits():
    """Phase 4b user note 3: CDP field map needs all paradigm keys
    including digit keys for n-back. KeyCodes 48-57 for '0' through
    '9'."""
    for i in range(10):
        d = str(i)
        assert d in KEY_TO_CDP_FIELDS, f"digit {d} missing from map"
        assert KEY_TO_CDP_FIELDS[d]["windowsVirtualKeyCode"] == 48 + i
        assert KEY_TO_CDP_FIELDS[d]["code"] == f"Digit{d}"


def test_cdp_field_map_covers_navigation():
    """Navigation keys: Space, Enter, ArrowRight, ArrowLeft. Required
    for instruction advance + pre-trial gate dismissal."""
    for key in ("Space", "Enter", "ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"):
        assert key in KEY_TO_CDP_FIELDS, f"navigation key {key!r} missing"
    # The bare space character ' ' must also map (Stroop's space-advance).
    assert " " in KEY_TO_CDP_FIELDS


def test_cdp_fields_for_letter_fallback_derives_keycode():
    """Per Phase 4b user note 3, unmapped letters must still fire via
    fallback. 'a' should derive code='KeyA', keyCode=65."""
    out = cdp_fields_for("a")
    assert out["code"] == "KeyA"
    assert out["windowsVirtualKeyCode"] == ord("A") == 65
    assert out["text"] == "a"
    # Capital letter
    out = cdp_fields_for("Z")
    assert out["code"] == "KeyZ"
    assert out["windowsVirtualKeyCode"] == ord("Z") == 90


def test_cdp_fields_for_unknown_multi_char_key_passes_through():
    """A multi-char key like 'PageDown' that's not in the explicit map
    should pass through with keyCode=0 (jsPsych reads from key field)."""
    out = cdp_fields_for("PageDown")
    assert out["key"] == "PageDown"
    assert out["code"] == "PageDown"
    assert out["windowsVirtualKeyCode"] == 0
    assert "text" not in out  # multi-char keys don't carry text


def test_cdp_fields_for_returns_independent_dict():
    """Mutating the returned dict must not poison the shared map."""
    out = cdp_fields_for(",")
    out["windowsVirtualKeyCode"] = 999
    assert KEY_TO_CDP_FIELDS[","]["windowsVirtualKeyCode"] == 188


# -----------------------------------------------------------------
# Mocks
# -----------------------------------------------------------------


class _FakeCDP:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def send(self, method: str, params: dict):
        self.calls.append((method, params))


class _FakePage:
    """Minimal mock of Playwright's Page for evaluate(). Each call to
    evaluate() returns the next value from ``script_returns`` indexed by
    a pattern match on the JS source."""

    def __init__(
        self,
        *,
        marker_sequence: list[Any] | None = None,
        records: list[dict] | None = None,
        focus_calls_collector: list | None = None,
    ):
        self._markers = list(marker_sequence or [])
        self._marker_idx = 0
        self._records = list(records or [])
        self._focus_calls = focus_calls_collector
        self.evaluate_log: list[str] = []

    async def evaluate(self, js: str):
        self.evaluate_log.append(js)
        if "current_trial_global" in js:
            if self._marker_idx < len(self._markers):
                v = self._markers[self._marker_idx]
                self._marker_idx += 1
                return v
            return self._markers[-1] if self._markers else None
        if "data.get" in js or "values" in js:
            return list(self._records)
        if "focus" in js or "activeElement" in js:
            if self._focus_calls is not None:
                self._focus_calls.append(js)
            return None
        return None


# -----------------------------------------------------------------
# Four-step protocol
# -----------------------------------------------------------------


def test_deliver_at_trial_start_fires_keydown_keyup_pair():
    """Step 4: rawKeyDown + keyUp via CDP."""
    cdp = _FakeCDP()
    page = _FakePage(
        marker_sequence=[5, 5, 6],  # start=5, after_dwell=5, after_advance=6
        records=[{"trial_index": 5, "response": ",", "rt": 250}],
    )
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    rec = _run(deliverer.deliver_at_trial_start(","))
    assert rec.skipped is False
    types_sent = [params["type"] for (m, params) in cdp.calls if m == "Input.dispatchKeyEvent"]
    assert types_sent == ["rawKeyDown", "keyUp"], (
        f"Expected rawKeyDown+keyUp pair, got {types_sent}"
    )
    # All CDP calls used the comma's correct fields
    for _, params in cdp.calls:
        assert params["windowsVirtualKeyCode"] == 188
        assert params["code"] == "Comma"


def test_deliver_at_trial_start_skips_if_no_trial_marker():
    """Step 1: if trial marker is None (pre-test-phase), skip and
    return skipped=True. The bot must not fire into a non-trial state."""
    cdp = _FakeCDP()
    page = _FakePage(marker_sequence=[None])
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    rec = _run(deliverer.deliver_at_trial_start(","))
    assert rec.skipped is True
    assert rec.skip_reason == "no_trial_marker_available"
    assert len(cdp.calls) == 0  # no fire


def test_deliver_at_trial_start_skips_if_trial_advances_during_dwell():
    """Step 3: if trial advances during dwell, the bot's response would
    land on the WRONG trial. Skip + return skipped=True. This is the
    off-by-one diagnosed in the Phase 4a spike."""
    cdp = _FakeCDP()
    page = _FakePage(
        marker_sequence=[5, 6],  # start=5, after_dwell=6 (advanced!)
    )
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    rec = _run(deliverer.deliver_at_trial_start(","))
    assert rec.skipped is True
    assert rec.skip_reason == "trial_advanced_during_dwell"
    assert rec.trial_marker_at_fire == 5
    assert len(cdp.calls) == 0


def test_deliver_at_trial_start_observes_real_dwell():
    """Step 2: dwell_ms parameter controls dwell duration. The
    observed dwell should be approximately the configured value
    (within timer precision)."""
    cdp = _FakeCDP()
    page = _FakePage(marker_sequence=[5, 5, 6])
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=50.0)
    rec = _run(deliverer.deliver_at_trial_start(","))
    assert rec.skipped is False
    # Observed dwell should be at least the configured value (sleep is
    # a lower bound, not exact). Cap at +200ms to avoid CI flakiness.
    assert rec.observed_dwell_ms >= 50.0
    assert rec.observed_dwell_ms < 250.0


def test_deliver_at_trial_start_uses_dwell_override():
    """Override dwell_ms per fire (Phase 4b user note 2 — stop-signal
    may need shorter dwell than Stroop)."""
    cdp = _FakeCDP()
    page = _FakePage(marker_sequence=[5, 5, 6])
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=200.0)
    rec = _run(deliverer.deliver_at_trial_start(",", dwell_ms=10.0))
    assert rec.intended_dwell_ms == 10.0
    assert rec.observed_dwell_ms < 100.0  # under default 200ms


def test_deliver_at_trial_start_runs_focus_when_provided():
    """Phase 4b user note 5: focus management before each press. If
    ``listener_focus_js`` is set, it should be evaluated before fire."""
    cdp = _FakeCDP()
    focus_calls: list[str] = []
    page = _FakePage(
        marker_sequence=[5, 5, 6],
        focus_calls_collector=focus_calls,
    )
    deliverer = CDPDeliverer(
        page, cdp,
        default_dwell_ms=1.0,
        listener_focus_js="() => document.body.focus()",
    )
    _run(deliverer.deliver_at_trial_start(","))
    assert len(focus_calls) >= 1
    assert "focus" in focus_calls[0]


def test_deliver_at_trial_start_no_focus_when_not_configured():
    """Without listener_focus_js, no focus call is issued."""
    cdp = _FakeCDP()
    focus_calls: list[str] = []
    page = _FakePage(
        marker_sequence=[5, 5, 6],
        focus_calls_collector=focus_calls,
    )
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    _run(deliverer.deliver_at_trial_start(","))
    assert len(focus_calls) == 0


def test_deliver_at_trial_start_skips_on_marker_mismatch():
    """expected_trial_marker enforces fire-on-specific-trial — if the
    page is on a different trial than the caller expected, skip."""
    cdp = _FakeCDP()
    page = _FakePage(marker_sequence=[7])
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    rec = _run(deliverer.deliver_at_trial_start(",", expected_trial_marker=5))
    assert rec.skipped is True
    assert rec.skip_reason == "trial_marker_mismatch"
    assert len(cdp.calls) == 0


# -----------------------------------------------------------------
# deliver_sequence + pairing
# -----------------------------------------------------------------


def test_deliver_sequence_pairs_by_trial_marker_not_index():
    """Pairing must match trial_marker_at_fire to record.trial_index.
    The Phase 4a spike's 100% fidelity result depended on this — naive
    sequential pairing gave 26% / 2% / 0% on the same runs."""
    cdp = _FakeCDP()
    # Marker sequence:
    #   fire 1: start=10, after_dwell=10, after_fire-advance=11
    #   fire 2: start=11, after_dwell=11, after_fire-advance=12
    page = _FakePage(
        marker_sequence=[10, 10, 11, 11, 11, 12],
        records=[
            {"trial_index": 10, "response": ",", "rt": 200},
            {"trial_index": 11, "response": ".", "rt": 250},
        ],
    )
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([",", "."], [1.0, 1.0]))
    assert len(events) == 2
    # Both should be correctly-recorded since record.trial_index ==
    # trial_marker_at_fire and record.response == key.
    assert events[0].is_correctly_recorded is True
    assert events[0].metadata["trial_marker_at_fire"] == 10
    assert events[1].is_correctly_recorded is True
    assert events[1].metadata["trial_marker_at_fire"] == 11


def test_deliver_sequence_tags_delivery_channel_cdp():
    """Phase 4b user note 6: every event must carry
    ``delivery.channel`` so bot_log can break out by channel."""
    cdp = _FakeCDP()
    page = _FakePage(
        marker_sequence=[10, 10, 11],
        records=[{"trial_index": 10, "response": ",", "rt": 200}],
    )
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([","], [1.0]))
    assert events[0].metadata["delivery"]["channel"] == "cdp_dispatchKeyEvent"


def test_deliver_sequence_rejects_mismatched_lengths():
    """API contract: keys and intervals must be same length."""
    cdp = _FakeCDP()
    page = _FakePage(marker_sequence=[5])
    deliverer = CDPDeliverer(page, cdp)
    with pytest.raises(ValueError, match="same length"):
        _run(deliverer.deliver_sequence([",", "."], [200.0]))


def test_deliver_sequence_emits_skipped_event_with_no_platform_record():
    """When a fire is skipped (trial advanced during dwell etc.), the
    KeypressEvent should still be returned but with
    platform_recorded_key=None."""
    cdp = _FakeCDP()
    # Marker advances during dwell on first fire; second fire OK.
    page = _FakePage(
        marker_sequence=[10, 11,  # fire 1: start=10, after_dwell=11 → SKIP
                         12, 12, 13],  # fire 2: start=12, after_dwell=12, advance=13
        records=[
            {"trial_index": 12, "response": ".", "rt": 250},
        ],
    )
    deliverer = CDPDeliverer(page, cdp, default_dwell_ms=1.0)
    events = _run(deliverer.deliver_sequence([",", "."], [1.0, 1.0]))
    assert events[0].platform_recorded_key is None
    assert events[0].metadata["skipped"] is True
    assert events[1].platform_recorded_key == "."
    assert events[1].metadata["skipped"] is False

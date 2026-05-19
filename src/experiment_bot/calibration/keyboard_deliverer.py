"""PlaywrightKeyboardDeliverer — non-CDP keypress delivery channel.

Fallback for non-Chromium engines (Firefox, WebKit) or sessions that
explicitly don't open a CDP session. Uses ``page.keyboard.press`` via
Playwright instead of ``Input.dispatchKeyEvent`` via CDP. Same four-step
per-trial protocol as :class:`CDPDeliverer` so the calibration estimator
sees identical event shape regardless of channel.

Per Phase 4b user note 3, this deliverer maps human-readable key
strings to the Playwright keyboard API's expected names — e.g., space
character " " becomes "Space" for Playwright. The CDP deliverer's
``KEY_TO_CDP_FIELDS`` lives in ``cdp_deliverer.py``; this module ships
a similar but smaller mapping for Playwright's API.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .cdp_deliverer import (
    DEFAULT_RECORD_MARKER_FIELD,
    DEFAULT_RECORDS_JS,
    DEFAULT_TRIAL_MARKER_JS,
    _FireRecord,
)
from .deliverer import KeypressDeliverer, KeypressEvent


# Playwright keyboard.press accepts most key names directly. The space
# character must be passed as "Space"; printable chars pass through.
def playwright_key_for(key: str) -> str:
    """Translate the deliverer's canonical key string to the form
    ``page.keyboard.press`` expects.

      - " " → "Space"
      - "Space", "Enter", "ArrowRight", letters, digits, punctuation:
        pass through unchanged.
    """
    if key == " ":
        return "Space"
    return key


class PlaywrightKeyboardDeliverer(KeypressDeliverer):
    """Implements :class:`KeypressDeliverer` via Playwright's
    ``page.keyboard.press``. Same four-step per-trial protocol as
    :class:`CDPDeliverer`; only the fire mechanism differs.

    Use when:
      - Running against Firefox / WebKit (no CDP available).
      - Diagnostic A/B comparison vs CDP — bot_log breaks
        ``delivery.channel`` down for §7 of the Phase 8 report.
    """

    DEFAULT_DWELL_MS: float = 200.0
    DEFAULT_TRIAL_ADVANCE_TIMEOUT_S: float = 30.0
    DELIVERY_CHANNEL: str = "keyboard_press_fallback"

    def __init__(
        self,
        page,
        *,
        default_dwell_ms: float = DEFAULT_DWELL_MS,
        trial_marker_js: str = DEFAULT_TRIAL_MARKER_JS,
        records_js: str = DEFAULT_RECORDS_JS,
        record_marker_field: str = DEFAULT_RECORD_MARKER_FIELD,
        listener_focus_js: str | None = None,
        trial_advance_timeout_s: float = DEFAULT_TRIAL_ADVANCE_TIMEOUT_S,
    ):
        self._page = page
        self._default_dwell_ms = float(default_dwell_ms)
        self._trial_marker_js = trial_marker_js
        self._records_js = records_js
        self._record_marker_field = record_marker_field
        self._listener_focus_js = listener_focus_js
        self._trial_advance_timeout_s = float(trial_advance_timeout_s)

    async def _read_trial_marker(self):
        try:
            return await self._page.evaluate(self._trial_marker_js)
        except Exception:
            return None

    async def _read_records(self) -> list[dict]:
        try:
            recs = await self._page.evaluate(self._records_js)
            return list(recs or [])
        except Exception:
            return []

    async def _focus_listener_target(self) -> None:
        if self._listener_focus_js is None:
            return
        try:
            await self._page.evaluate(self._listener_focus_js)
        except Exception:
            pass

    async def _fire_press(self, key: str) -> str:
        pw_key = playwright_key_for(key)
        await self._page.keyboard.press(pw_key)
        return pw_key

    async def deliver_at_trial_start(
        self,
        key: str,
        *,
        dwell_ms: float | None = None,
        expected_trial_marker: Any = None,
    ) -> _FireRecord:
        dwell = self._default_dwell_ms if dwell_ms is None else float(dwell_ms)

        # Step 1: Detect
        start_marker = await self._read_trial_marker()
        if start_marker is None:
            return _FireRecord(
                key=key, intended_dwell_ms=dwell, observed_dwell_ms=0.0,
                trial_marker_at_fire=None, skipped=True,
                skip_reason="no_trial_marker_available",
                fired_at_monotonic=None,
                cdp_fields={"playwright_key": playwright_key_for(key)},
            )
        if expected_trial_marker is not None and start_marker != expected_trial_marker:
            return _FireRecord(
                key=key, intended_dwell_ms=dwell, observed_dwell_ms=0.0,
                trial_marker_at_fire=start_marker, skipped=True,
                skip_reason="trial_marker_mismatch",
                fired_at_monotonic=None,
                cdp_fields={"playwright_key": playwright_key_for(key)},
            )

        # Step 2: Dwell
        dwell_start = time.monotonic()
        await asyncio.sleep(dwell / 1000.0)
        dwell_observed_ms = (time.monotonic() - dwell_start) * 1000.0

        # Step 3: Verify
        after_dwell_marker = await self._read_trial_marker()
        if after_dwell_marker is None or after_dwell_marker != start_marker:
            return _FireRecord(
                key=key, intended_dwell_ms=dwell, observed_dwell_ms=dwell_observed_ms,
                trial_marker_at_fire=start_marker, skipped=True,
                skip_reason="trial_advanced_during_dwell",
                fired_at_monotonic=None,
                cdp_fields={"playwright_key": playwright_key_for(key)},
            )

        # Step 4: Focus + Fire
        await self._focus_listener_target()
        fired_at = time.monotonic()
        pw_key = await self._fire_press(key)

        # Step 5: Wait for advance
        poll_interval_s = 0.05
        waited_s = 0.0
        while waited_s < self._trial_advance_timeout_s:
            cur = await self._read_trial_marker()
            if cur is not None and cur != start_marker:
                break
            await asyncio.sleep(poll_interval_s)
            waited_s += poll_interval_s

        return _FireRecord(
            key=key, intended_dwell_ms=dwell,
            observed_dwell_ms=dwell_observed_ms,
            trial_marker_at_fire=start_marker,
            skipped=False,
            skip_reason=None,
            fired_at_monotonic=fired_at,
            cdp_fields={"playwright_key": pw_key},
        )

    async def deliver_sequence(
        self,
        keys: list[str],
        target_intervals_ms: list[float],
    ) -> list[KeypressEvent]:
        if len(keys) != len(target_intervals_ms):
            raise ValueError(
                f"keys and target_intervals_ms must be same length: "
                f"got {len(keys)} and {len(target_intervals_ms)}"
            )

        fire_records: list[_FireRecord] = []
        for k, dwell_ms in zip(keys, target_intervals_ms):
            rec = await self.deliver_at_trial_start(k, dwell_ms=dwell_ms)
            fire_records.append(rec)

        platform_records = await self._read_records()
        recs_by_marker: dict[Any, dict] = {}
        for r in platform_records:
            marker = r.get(self._record_marker_field)
            if marker is not None and marker not in recs_by_marker:
                recs_by_marker[marker] = r

        events: list[KeypressEvent] = []
        for rec in fire_records:
            platform_key: str | None = None
            platform_rt: float | None = None
            if not rec.skipped and rec.trial_marker_at_fire is not None:
                platform_row = recs_by_marker.get(rec.trial_marker_at_fire)
                if platform_row is not None:
                    raw_resp = platform_row.get("response")
                    if raw_resp is not None:
                        platform_key = str(raw_resp)
                    raw_rt = platform_row.get("rt")
                    if raw_rt is not None:
                        try:
                            platform_rt = float(raw_rt)
                        except (TypeError, ValueError):
                            platform_rt = None
            events.append(KeypressEvent(
                key=rec.key,
                bot_intended_rt_ms=rec.observed_dwell_ms,
                platform_recorded_key=platform_key,
                platform_recorded_rt_ms=platform_rt,
                metadata={
                    "delivery": {"channel": self.DELIVERY_CHANNEL},
                    "trial_marker_at_fire": rec.trial_marker_at_fire,
                    "intended_dwell_ms": rec.intended_dwell_ms,
                    "observed_dwell_ms": rec.observed_dwell_ms,
                    "skipped": rec.skipped,
                    "skip_reason": rec.skip_reason,
                    "playwright_key": rec.cdp_fields.get("playwright_key"),
                },
            ))
        return events

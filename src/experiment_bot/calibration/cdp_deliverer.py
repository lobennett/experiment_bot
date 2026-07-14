"""CDPDeliverer — Chromium Input.dispatchKeyEvent path.

Phase 4b's canonical keypress delivery channel. Implements the four-step
per-trial protocol validated in the Phase 4a feasibility spike
(``scripts/probe_cdp_delivery.py``, 100% fidelity on expfactory Stroop):

    1. Detect    — read the current trial marker
    2. Dwell     — wait dwell_ms (paradigm-tunable; default 200)
    3. Verify    — confirm trial marker hasn't advanced during dwell
    4. Fire      — Input.dispatchKeyEvent rawKeyDown + keyUp
    5. Wait      — poll trial marker until it advances (trial completed)

The fire mechanism is Chromium-specific (CDP). The trial-marker probe
and platform-record readback are JS strings passed to
``page.evaluate``, with paradigm-platform-aware defaults for jsPsych
(``window.jsPsych.getProgress().current_trial_global`` for the marker,
``window.jsPsych.data.get().values()`` for the records). Non-jsPsych
platforms substitute by passing different ``trial_marker_js`` /
``records_js`` strings at construction. Per G1, the deliverer itself
contains no paradigm logic.

Pairing of bot fires to platform records is by trial-marker match
(robust to interstitial trials, fixations, and ITIs — the off-by-one
diagnosed in the Phase 4a spike came from index-based pairing). The
record's ``trial_index`` field (jsPsych default) is what pairs to the
bot's ``trial_marker_at_fire``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .deliverer import KeypressDeliverer, KeypressEvent

logger = logging.getLogger(__name__)


# CDP keyboard fields per key. Each entry is the kwargs dict for both
# Input.dispatchKeyEvent calls (rawKeyDown + keyUp). The ``text`` field
# is only set for character keys (jsPsych's keyboard plugin reads it
# from KeyboardEvent.key, but raw character output sometimes matters).
KEY_TO_CDP_FIELDS: dict[str, dict[str, Any]] = {
    # Punctuation: Stroop / stop-signal response keys
    ",":  {"key": ",",  "code": "Comma",  "windowsVirtualKeyCode": 188, "text": ","},
    ".":  {"key": ".",  "code": "Period", "windowsVirtualKeyCode": 190, "text": "."},
    "/":  {"key": "/",  "code": "Slash",  "windowsVirtualKeyCode": 191, "text": "/"},
    # Digits 0-9: n-back / generic numeric responses
    "0":  {"key": "0",  "code": "Digit0", "windowsVirtualKeyCode": 48,  "text": "0"},
    "1":  {"key": "1",  "code": "Digit1", "windowsVirtualKeyCode": 49,  "text": "1"},
    "2":  {"key": "2",  "code": "Digit2", "windowsVirtualKeyCode": 50,  "text": "2"},
    "3":  {"key": "3",  "code": "Digit3", "windowsVirtualKeyCode": 51,  "text": "3"},
    "4":  {"key": "4",  "code": "Digit4", "windowsVirtualKeyCode": 52,  "text": "4"},
    "5":  {"key": "5",  "code": "Digit5", "windowsVirtualKeyCode": 53,  "text": "5"},
    "6":  {"key": "6",  "code": "Digit6", "windowsVirtualKeyCode": 54,  "text": "6"},
    "7":  {"key": "7",  "code": "Digit7", "windowsVirtualKeyCode": 55,  "text": "7"},
    "8":  {"key": "8",  "code": "Digit8", "windowsVirtualKeyCode": 56,  "text": "8"},
    "9":  {"key": "9",  "code": "Digit9", "windowsVirtualKeyCode": 57,  "text": "9"},
    # Navigation
    " ":          {"key": " ",          "code": "Space",      "windowsVirtualKeyCode": 32,  "text": " "},
    "Space":      {"key": " ",          "code": "Space",      "windowsVirtualKeyCode": 32,  "text": " "},
    "Enter":      {"key": "Enter",      "code": "Enter",      "windowsVirtualKeyCode": 13},
    "ArrowRight": {"key": "ArrowRight", "code": "ArrowRight", "windowsVirtualKeyCode": 39},
    "ArrowLeft":  {"key": "ArrowLeft",  "code": "ArrowLeft",  "windowsVirtualKeyCode": 37},
    "ArrowUp":    {"key": "ArrowUp",    "code": "ArrowUp",    "windowsVirtualKeyCode": 38},
    "ArrowDown":  {"key": "ArrowDown",  "code": "ArrowDown",  "windowsVirtualKeyCode": 40},
    "Escape":     {"key": "Escape",     "code": "Escape",     "windowsVirtualKeyCode": 27},
    "Tab":        {"key": "Tab",        "code": "Tab",        "windowsVirtualKeyCode": 9},
    "Backspace":  {"key": "Backspace",  "code": "Backspace",  "windowsVirtualKeyCode": 8},
}

# Default jsPsych probes — three out of four SP11 dev paradigms use
# jsPsych 7.3.1 + cognition.run uses the same engine (Phase 3.1 finding).
# stopit uses jsPsych 6.0.5 but exposes the same getProgress() API.
DEFAULT_TRIAL_MARKER_JS = (
    "() => (window.jsPsych && window.jsPsych.getProgress && "
    "window.jsPsych.getProgress().current_trial_global) || null"
)
DEFAULT_RECORDS_JS = (
    "() => (window.jsPsych && window.jsPsych.data && "
    "window.jsPsych.data.get().values()) || []"
)
DEFAULT_RECORD_MARKER_FIELD = "trial_index"


def cdp_fields_for(key: str) -> dict[str, Any]:
    """Return CDP Input.dispatchKeyEvent kwargs for ``key``.

    Falls back for unmapped keys:
      - Single letter A-Z / a-z: derive ``code='Key{X}'``, ``keyCode=ord(X)``.
      - Single character outside the map: pass through with ``ord``-based
        ``keyCode``, ``code`` equal to the literal character.
      - Multi-character key without a map entry: pass through as ``key``
        and ``code`` with ``keyCode=0`` (jsPsych typically reads from
        the ``key`` field, so this still works for special keys).

    Per Phase 4b user note 3, unmapped keys must still fire — the
    fallback prevents silent failures on platforms with unusual keys.
    """
    if key in KEY_TO_CDP_FIELDS:
        # Copy so caller mutations don't poison the shared dict
        return dict(KEY_TO_CDP_FIELDS[key])
    # Single ASCII letter
    if len(key) == 1 and key.isalpha() and key.isascii():
        upper = key.upper()
        return {
            "key": key,
            "code": f"Key{upper}",
            "windowsVirtualKeyCode": ord(upper),
            "text": key,
        }
    # Single ASCII character outside the explicit map
    if len(key) == 1:
        return {
            "key": key,
            "code": key,
            "windowsVirtualKeyCode": ord(key) if ord(key) < 128 else 0,
            "text": key,
        }
    # Multi-char key name
    return {"key": key, "code": key, "windowsVirtualKeyCode": 0}


@dataclass
class _FireRecord:
    """Internal per-fire bookkeeping before pairing with platform records."""
    key: str
    intended_dwell_ms: float
    observed_dwell_ms: float
    trial_marker_at_fire: Any
    skipped: bool
    skip_reason: str | None
    fired_at_monotonic: float | None
    cdp_fields: dict[str, Any]
    # Whether the trial marker advanced as a result of this fire (or during
    # dwell). Drives deliver_sequence's feasibility gate. Defaults False so
    # existing _FireRecord(...) constructions stay valid.
    advanced: bool = False


class CDPDeliverer(KeypressDeliverer):
    """Implements :class:`KeypressDeliverer` via CDP Input.dispatchKeyEvent.

    Constructor parameters:

      ``page`` — Playwright ``Page`` for evaluate() reads.
      ``cdp_session`` — Playwright CDP session
        (typically from ``context.new_cdp_session(page)``).
      ``default_dwell_ms`` — default dwell in step 2 (default 200.0).
        Phase 4b user note 2: stop-signal's 1000ms response window may
        make 200ms too aggressive on go trials; callers can override
        per-paradigm via ``dwell_ms`` argument to
        :meth:`deliver_at_trial_start` or by setting this value at
        construction.
      ``trial_marker_js`` — JS arrow returning the current trial's
        monotonic identifier. Default: jsPsych
        ``getProgress().current_trial_global``.
      ``records_js`` — JS arrow returning an array of platform records.
        Default: jsPsych ``data.get().values()``.
      ``record_marker_field`` — Field on each platform record that
        equals the trial marker. Default: ``"trial_index"`` (jsPsych).
      ``trial_advance_timeout_s`` — Per-fire upper bound on step 5 wait
        before giving up. Default: 30.0.

    CDP is the only supported delivery channel. If a CDP session can't
    be acquired (Firefox / WebKit / mocked tests), the executor falls
    through to ``page.keyboard.press``.
    """

    DEFAULT_DWELL_MS: float = 200.0
    # Per-fire upper bound on waiting for the trial to advance after a keypress.
    # A real jsPsych trial-advance after a response is sub-second; 8s is a
    # generous margin. (Lowered from 30s: combined with the feasibility gate
    # below, it bounds calibration on a non-pairing platform to seconds.)
    DEFAULT_TRIAL_ADVANCE_TIMEOUT_S: float = 8.0
    # Feasibility gate: abort the calibration sequence after this many
    # consecutive fires that fail to advance the trial marker (the platform is
    # not pairing the calibration keypresses — wrong advance key, non-trial
    # screen). Prevents the ~15-min stall observed on cognition.run.
    MAX_CONSECUTIVE_NO_ADVANCE: int = 3
    DELIVERY_CHANNEL: str = "cdp_dispatchKeyEvent"

    def __init__(
        self,
        page,
        cdp_session,
        *,
        default_dwell_ms: float = DEFAULT_DWELL_MS,
        trial_marker_js: str = DEFAULT_TRIAL_MARKER_JS,
        records_js: str = DEFAULT_RECORDS_JS,
        record_marker_field: str = DEFAULT_RECORD_MARKER_FIELD,
        trial_advance_timeout_s: float = DEFAULT_TRIAL_ADVANCE_TIMEOUT_S,
    ):
        self._page = page
        self._cdp = cdp_session
        self._default_dwell_ms = float(default_dwell_ms)
        self._trial_marker_js = trial_marker_js
        self._records_js = records_js
        self._record_marker_field = record_marker_field
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

    async def _fire_cdp_pair(self, key: str) -> dict[str, Any]:
        """Issue rawKeyDown + keyUp via CDP. Returns the field set used
        (for delivery.channel logging downstream)."""
        fields = cdp_fields_for(key)
        await self._cdp.send(
            "Input.dispatchKeyEvent", {"type": "rawKeyDown", **fields},
        )
        # Brief between-event sleep — same as the Phase 4a spike used.
        await asyncio.sleep(0.05)
        await self._cdp.send(
            "Input.dispatchKeyEvent", {"type": "keyUp", **fields},
        )
        return fields

    async def fire_key(self, key: str) -> dict[str, Any]:
        """Dispatch ONE keypress immediately, with no trial-marker protocol.

        `deliver_at_trial_start` is a one-key-PER-trial design: it dwells,
        verifies the trial hasn't advanced, fires, then WAITS for the trial
        marker to advance (pairing one fire to one trial). That wait is wrong
        for a multi-action response delivered WITHIN a single trial (e.g. a
        serial reproduction: navigate + select, several keys, one trial): the
        marker does not advance until the whole trial ends, so each intra-trial
        key would block the ~trial_advance_timeout. This method just fires the
        rawKeyDown+keyUp pair; inter-action timing is owned by the caller
        (`TaskExecutor._deliver_sequence` sleeps each action's gap). Returns
        the same metadata shape as `TaskExecutor._fire_response_key`.
        """
        marker = await self._read_trial_marker()
        fields = await self._fire_cdp_pair(key)
        return {
            "channel": self.DELIVERY_CHANNEL,
            "trial_marker_at_fire": marker,
            "skipped": False,
            "skip_reason": None,
            "cdp_fields": fields,
        }

    async def deliver_at_trial_start(
        self,
        key: str,
        *,
        dwell_ms: float | None = None,
        expected_trial_marker: Any = None,
    ) -> _FireRecord:
        """Four-step per-trial protocol.

        Parameters:
          ``key`` — key to fire (must be a string).
          ``dwell_ms`` — override default dwell for this fire. Per Phase
            4b user note 2, stop-signal may need a shorter/longer dwell
            than Stroop's 200ms; pass the paradigm-specific value here.
          ``expected_trial_marker`` — if provided, only fire if the
            current trial marker matches. Used by sequence delivery to
            confirm we're on the right trial after the previous fire's
            wait-for-advance.

        Returns a :class:`_FireRecord` capturing dwell, trial marker at
        fire, skip status, and the CDP fields used. Callers (most
        commonly :meth:`deliver_sequence`) pair these records to
        platform readouts.
        """
        dwell = self._default_dwell_ms if dwell_ms is None else float(dwell_ms)

        # Step 1: Detect — read the current trial marker
        start_marker = await self._read_trial_marker()
        if start_marker is None:
            return _FireRecord(
                key=key, intended_dwell_ms=dwell, observed_dwell_ms=0.0,
                trial_marker_at_fire=None, skipped=True,
                skip_reason="no_trial_marker_available",
                fired_at_monotonic=None,
                cdp_fields=cdp_fields_for(key),
            )
        if expected_trial_marker is not None and start_marker != expected_trial_marker:
            return _FireRecord(
                key=key, intended_dwell_ms=dwell, observed_dwell_ms=0.0,
                trial_marker_at_fire=start_marker, skipped=True,
                skip_reason="trial_marker_mismatch",
                fired_at_monotonic=None,
                cdp_fields=cdp_fields_for(key),
            )

        # Step 2: Dwell
        dwell_start = time.monotonic()
        await asyncio.sleep(dwell / 1000.0)
        dwell_observed_ms = (time.monotonic() - dwell_start) * 1000.0

        # Step 3: Verify the trial hasn't advanced during dwell
        after_dwell_marker = await self._read_trial_marker()
        if after_dwell_marker is None or after_dwell_marker != start_marker:
            return _FireRecord(
                key=key, intended_dwell_ms=dwell, observed_dwell_ms=dwell_observed_ms,
                trial_marker_at_fire=start_marker, skipped=True,
                skip_reason="trial_advanced_during_dwell",
                fired_at_monotonic=None,
                cdp_fields=cdp_fields_for(key),
                advanced=True,  # the trial DID advance (just faster than dwell)
            )

        # Step 4: Fire
        fired_at = time.monotonic()
        fields = await self._fire_cdp_pair(key)

        # Step 5: Wait for trial advance
        poll_interval_s = 0.05
        waited_s = 0.0
        advanced = False
        while waited_s < self._trial_advance_timeout_s:
            cur = await self._read_trial_marker()
            if cur is not None and cur != start_marker:
                advanced = True
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
            cdp_fields=fields,
            advanced=advanced,
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
        consecutive_no_advance = 0
        for k, dwell_ms in zip(keys, target_intervals_ms):
            rec = await self.deliver_at_trial_start(k, dwell_ms=dwell_ms)
            fire_records.append(rec)
            # Feasibility gate: if the trial marker keeps not advancing, the
            # platform isn't pairing the calibration keypresses — abort rather
            # than pay the per-fire timeout on every remaining key.
            if rec.advanced:
                consecutive_no_advance = 0
            else:
                consecutive_no_advance += 1
            if consecutive_no_advance >= self.MAX_CONSECUTIVE_NO_ADVANCE:
                logger.info(
                    "Calibration feasibility gate: %d consecutive fires did not "
                    "advance the trial marker; aborting after %d/%d keys "
                    "(platform not pairing keypresses).",
                    consecutive_no_advance, len(fire_records), len(keys),
                )
                break

        # Read back platform records once at the end
        platform_records = await self._read_records()
        # Index records by their marker field for O(N) pairing
        recs_by_marker: dict[Any, dict] = {}
        for r in platform_records:
            marker = r.get(self._record_marker_field)
            if marker is not None and marker not in recs_by_marker:
                recs_by_marker[marker] = r

        events: list[KeypressEvent] = []
        for rec in fire_records:
            platform_key: str | None = None
            platform_rt: float | None = None
            platform_row = None
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
                    "cdp_fields": rec.cdp_fields,
                },
            ))
        return events

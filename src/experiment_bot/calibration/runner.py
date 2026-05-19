"""SP11 Phase 3.6 — calibration runner.

Glue between the platform's pre-trial gate (welcome screen, click-to-
start button), the :class:`KeypressDeliverer` abstraction, and the
:func:`estimate_calibration` model selector.

The runner is itself delivery-channel-agnostic. It takes:
  - a :class:`KeypressDeliverer` (Phase 3 mock or Phase 4 real)
  - a :class:`GateDismisser` (Phase 3 mock or Phase 4 real)

Both abstractions let the runner be tested in pure Python without
browser state. Phase 4 provides the Playwright-backed implementations.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from experiment_bot.calibration.deliverer import KeypressDeliverer, KeypressEvent
from experiment_bot.calibration.estimator import (
    CalibrationResult, estimate_calibration,
)

logger = logging.getLogger(__name__)


# Default calibration sequence: 30 keypresses at intervals derived
# from a uniform-random ex-Gaussian RT distribution clipped to a
# realistic range. The exact intervals don't matter for offset
# estimation (estimator filters on key-match, not RT closeness); the
# spread does matter for the regression fallback.
_DEFAULT_KEYS = ["Space"] * 30
_DEFAULT_INTERVALS_MS = [
    200.0, 400.0, 600.0, 800.0, 1000.0,
    250.0, 450.0, 650.0, 850.0, 950.0,
    220.0, 420.0, 620.0, 820.0, 980.0,
    280.0, 480.0, 680.0, 880.0, 1020.0,
    240.0, 440.0, 640.0, 840.0, 960.0,
    260.0, 460.0, 660.0, 860.0, 1040.0,
]


class GateDismisser(ABC):
    """Abstract interface for dismissing a pre-trial gate (welcome
    screen, click-to-start button, etc.).

    Phase 3 provides:
      - :class:`NoGateDismisser` — no-op, for platforms with no gate.
      - :class:`MockGateDismisser` — test stub.

    Phase 4 provides:
      - ``PlaywrightGateDismisser`` — clicks visible Start/Begin
        buttons; falls back to keyboard advance (Space + Enter) for
        kbd-only welcome screens (per the Phase 3.1 cognition.run
        probe finding).
    """

    @abstractmethod
    async def dismiss(self) -> bool:
        """Try to dismiss any pre-trial gate. Return True if a gate
        was found and dismissed (or no gate was present), False if a
        gate is present but can't be dismissed via this strategy."""
        raise NotImplementedError


class NoGateDismisser(GateDismisser):
    """For platforms that don't gate keyboard input (calibration can
    start immediately)."""

    async def dismiss(self) -> bool:
        return True


class MockGateDismisser(GateDismisser):
    """Test stub. ``succeeds`` controls whether dismiss() returns True
    or False on the first call; subsequent calls return ``succeeds``."""

    def __init__(self, *, succeeds: bool = True):
        self.succeeds = succeeds
        self.dismiss_calls = 0

    async def dismiss(self) -> bool:
        self.dismiss_calls += 1
        return self.succeeds


@dataclass
class CalibrationRun:
    """Per-session calibration result + diagnostic counts.

    Phase 4b adds ``events`` (the raw KeypressEvent list) and
    ``delivery_channel_counts`` (a summary dict of how many events
    fired through each channel — e.g., ``{"cdp_dispatchKeyEvent": 30}``).
    Callers that write bot_log.json use these to populate the per-trial
    ``delivery.channel`` field (Phase 4b user note 5).
    """
    result: CalibrationResult
    gate_dismissed: bool
    sequence_length: int
    events: list[KeypressEvent] = field(default_factory=list)
    delivery_channel_counts: dict[str, int] = field(default_factory=dict)


def _summarize_delivery_channels(events: list[KeypressEvent]) -> dict[str, int]:
    """Tally delivery.channel values across events. Missing channel
    (e.g., MockDeliverer doesn't set one) maps to ``"unknown"``."""
    counts: dict[str, int] = {}
    for ev in events:
        chan = ((ev.metadata or {}).get("delivery") or {}).get("channel") or "unknown"
        counts[chan] = counts.get(chan, 0) + 1
    return counts


async def run_calibration(
    deliverer: KeypressDeliverer,
    gate_dismisser: GateDismisser | None = None,
    keys: list[str] | None = None,
    target_intervals_ms: list[float] | None = None,
) -> CalibrationRun:
    """Orchestrate calibration: dismiss gate → fire sequence → estimate.

    If ``gate_dismisser`` is None, treats the platform as no-gate.
    If ``keys`` / ``target_intervals_ms`` are None, uses the default
    30-keypress Space sequence.
    """
    dismisser = gate_dismisser or NoGateDismisser()
    dismissed = await dismisser.dismiss()
    if not dismissed:
        logger.warning(
            "Gate dismissal returned False; proceeding to fire calibration "
            "keys anyway, but expect platform to drop them."
        )
    seq_keys = keys if keys is not None else list(_DEFAULT_KEYS)
    seq_intervals = (
        target_intervals_ms if target_intervals_ms is not None
        else list(_DEFAULT_INTERVALS_MS)
    )
    events = await deliverer.deliver_sequence(seq_keys, seq_intervals)
    result = estimate_calibration(events)
    return CalibrationRun(
        result=result,
        gate_dismissed=dismissed,
        sequence_length=len(seq_keys),
        events=list(events),
        delivery_channel_counts=_summarize_delivery_channels(list(events)),
    )

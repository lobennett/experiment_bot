from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class StuckDetector:
    """Tracks trial heartbeats to detect when the executor is stuck."""

    def __init__(self, timeout_seconds: float = 10.0):
        self._timeout = timeout_seconds
        self._last_heartbeat: float = time.monotonic()

    def heartbeat(self) -> None:
        """Call this whenever a stimulus is successfully detected."""
        self._last_heartbeat = time.monotonic()

    @property
    def seconds_since_heartbeat(self) -> float:
        return time.monotonic() - self._last_heartbeat

    @property
    def is_stuck(self) -> bool:
        return self.seconds_since_heartbeat > self._timeout

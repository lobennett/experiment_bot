from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class StuckDetector:
    """Monitors for inactivity and triggers a fallback when stuck."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        fallback_fn: Callable[[Page, bytes], Awaitable[dict[str, Any]]] | None = None,
    ):
        self._timeout = timeout_seconds
        self._fallback_fn = fallback_fn
        self._last_heartbeat: float = 0.0
        self._running = False
        self._event = asyncio.Event()

    def heartbeat(self) -> None:
        """Call this whenever a stimulus is successfully detected."""
        self._event.set()

    def stop(self) -> None:
        self._running = False
        self._event.set()  # Unblock the wait

    async def watch(self, page: Page) -> dict[str, Any] | None:
        """Watch for stuck state. Returns fallback guidance if triggered, else None."""
        self._running = True
        while self._running:
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=self._timeout)
            except asyncio.TimeoutError:
                if not self._running:
                    return None
                logger.warning(f"Stuck detected (no heartbeat for {self._timeout}s)")
                if self._fallback_fn:
                    try:
                        screenshot = await page.screenshot(type="png")
                        guidance = await self._fallback_fn(page, screenshot)
                        logger.info(f"Fallback guidance: {guidance}")
                        return guidance
                    except Exception as e:
                        logger.error(f"Fallback failed: {e}")
                return None
        return None

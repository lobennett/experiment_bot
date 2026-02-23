from __future__ import annotations

import asyncio
import logging
import random

from playwright.async_api import Page

from experiment_bot.core.config import NavigationConfig, NavigationPhase

logger = logging.getLogger(__name__)


class InstructionNavigator:
    def __init__(self, reading_delay_range: tuple[float, float] = (3.0, 8.0)):
        self._reading_delay_range = reading_delay_range

    async def execute_all(self, page: Page, nav_config: NavigationConfig) -> None:
        for phase in nav_config.phases:
            await self.execute_phase(page, phase)

    async def execute_phase(self, page: Page, phase: NavigationPhase) -> None:
        logger.info(f"Executing navigation phase: {phase.phase} ({phase.action})")

        if phase.action == "click":
            await self._do_click(page, phase.target)
        elif phase.action == "press":
            await self._do_press(page, phase.key)
        elif phase.action == "wait":
            await self._do_wait(phase.duration_ms)
        elif phase.action == "sequence":
            for step in phase.steps:
                sub_phase = NavigationPhase.from_dict(step)
                await self.execute_phase(page, sub_phase)
        elif phase.action == "repeat":
            max_iterations = 20
            for _ in range(max_iterations):
                try:
                    for step in phase.steps:
                        sub_phase = NavigationPhase.from_dict(step)
                        await self.execute_phase(page, sub_phase)
                except Exception:
                    break

    async def _do_click(self, page: Page, target: str) -> None:
        await self._inject_reading_delay()
        locator = page.locator(target).first
        try:
            await locator.wait_for(state="visible", timeout=10000)
            await locator.click()
        except Exception as e:
            logger.warning(f"Click target not found: {target} ({e})")
            raise

    async def _do_press(self, page: Page, key: str) -> None:
        await self._inject_reading_delay()
        await page.keyboard.press(key)

    async def _do_wait(self, duration_ms: int) -> None:
        await asyncio.sleep(duration_ms / 1000.0)

    async def _inject_reading_delay(self) -> None:
        lo, hi = self._reading_delay_range
        if hi > 0:
            delay = random.uniform(lo, hi)
            await asyncio.sleep(delay)

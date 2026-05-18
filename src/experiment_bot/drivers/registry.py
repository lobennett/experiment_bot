"""SP10 driver registry — picks the right driver at session start."""
from __future__ import annotations

import logging

from playwright.async_api import Page

from experiment_bot.drivers.base import (
    PlatformDriver, UnsupportedVersionError,
)
from experiment_bot.drivers.diagnostic import DiagnosticDriver

logger = logging.getLogger(__name__)


# Order matters: specific drivers first. DiagnosticDriver is NOT in this
# list — the bot library invokes it directly on no-match or version-
# mismatch.
REGISTERED_DRIVERS: list[type[PlatformDriver]] = [
    # JsPsychDriver added in Task 12
    # CognitionRunDriver added when needed
]


async def identify_driver(page: Page) -> PlatformDriver:
    """Pick the first registered driver whose `can_handle` returns True.

    On UnsupportedVersionError during driver.create(): switch to
    DiagnosticDriver.for_version_mismatch.

    On no driver matching at all: DiagnosticDriver.for_unknown_platform.
    """
    for driver_cls in REGISTERED_DRIVERS:
        try:
            matches = await driver_cls.can_handle(page)
        except Exception as e:
            logger.warning(
                "%s.can_handle raised; skipping: %s", driver_cls.__name__, e,
            )
            continue
        if not matches:
            continue
        try:
            return await driver_cls.create(page)
        except UnsupportedVersionError as e:
            return await DiagnosticDriver.for_version_mismatch(page, e)
    return await DiagnosticDriver.for_unknown_platform(page)

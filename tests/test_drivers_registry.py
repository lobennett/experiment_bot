"""SP10: identify_driver picks the first matching registered driver,
falls back to DiagnosticDriver on no match or unsupported version."""
from __future__ import annotations
from unittest.mock import AsyncMock

import pytest

from experiment_bot.drivers.base import (
    DriverError, PlatformDriver, UnsupportedVersionError,
)
from experiment_bot.drivers.registry import identify_driver


class _MockDriver:
    """Test double for a registered driver."""
    _can_handle_value: bool = False
    _create_raises: Exception | None = None

    def __init__(self, name: str):
        self._name = name

    @classmethod
    async def can_handle(cls, page) -> bool:
        return cls._can_handle_value

    @classmethod
    async def create(cls, page):
        if cls._create_raises is not None:
            raise cls._create_raises
        return cls(name=cls.__name__)


class _AcceptingDriver(_MockDriver):
    _can_handle_value = True


class _RejectingDriver(_MockDriver):
    _can_handle_value = False


class _UnsupportedVersionDriver(_MockDriver):
    _can_handle_value = True
    _create_raises = UnsupportedVersionError(
        detected_version="9.0",
        supported_versions=("7.3", "8.0"),
        missing_anchors=["vendor/x/9.0/"],
    )


@pytest.mark.asyncio
async def test_identify_driver_picks_first_match(monkeypatch):
    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_RejectingDriver, _AcceptingDriver],
    )
    driver = await identify_driver(page)
    assert driver._name == "_AcceptingDriver"


@pytest.mark.asyncio
async def test_identify_driver_falls_back_to_diagnostic_on_no_match(monkeypatch):
    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_RejectingDriver],
    )
    page.url = "http://example.com/test"
    page.title = AsyncMock(return_value="Unknown")
    page.evaluate = AsyncMock(return_value={"jspsych_keys": [], "ids": [], "classes": []})
    page.screenshot = AsyncMock(return_value=b"")
    driver = await identify_driver(page)
    # DiagnosticDriver instance
    assert driver.__class__.__name__ == "DiagnosticDriver"


@pytest.mark.asyncio
async def test_identify_driver_falls_back_on_unsupported_version(monkeypatch):
    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_UnsupportedVersionDriver],
    )
    page.url = "http://example.com/test"
    page.title = AsyncMock(return_value="Unknown")
    page.evaluate = AsyncMock(return_value={"jspsych_keys": [], "ids": [], "classes": []})
    page.screenshot = AsyncMock(return_value=b"")
    driver = await identify_driver(page)
    assert driver.__class__.__name__ == "DiagnosticDriver"
    assert getattr(driver, "_mode", None) == "version_mismatch"


@pytest.mark.asyncio
async def test_identify_driver_skips_drivers_whose_can_handle_raises(monkeypatch):
    class _ExplodingDriver(_MockDriver):
        @classmethod
        async def can_handle(cls, page):
            raise RuntimeError("boom")

    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_ExplodingDriver, _AcceptingDriver],
    )
    driver = await identify_driver(page)
    assert driver._name == "_AcceptingDriver"

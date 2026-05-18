"""SP10: JsPsychDriver tests with stubbed Playwright page."""
from __future__ import annotations
from unittest.mock import AsyncMock

import pytest

from experiment_bot.drivers.base import UnsupportedVersionError
from experiment_bot.drivers.jspsych import JsPsychDriver


@pytest.mark.asyncio
async def test_can_handle_returns_true_when_window_jspsych_present():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    assert await JsPsychDriver.can_handle(page) is True


@pytest.mark.asyncio
async def test_can_handle_returns_false_when_window_jspsych_absent():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    assert await JsPsychDriver.can_handle(page) is False


@pytest.mark.asyncio
async def test_can_handle_returns_false_on_evaluate_error():
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page torn down"))
    assert await JsPsychDriver.can_handle(page) is False


@pytest.mark.asyncio
async def test_create_succeeds_for_supported_version():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="7.3.1")
    driver = await JsPsychDriver.create(page)
    assert driver._version == "7.3.1"


@pytest.mark.asyncio
async def test_create_raises_for_unsupported_version():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="6.3.1")
    with pytest.raises(UnsupportedVersionError) as excinfo:
        await JsPsychDriver.create(page)
    assert excinfo.value.detected_version == "6.3.1"
    assert "7.3.1" in excinfo.value.supported_versions


@pytest.mark.asyncio
async def test_create_raises_for_null_version():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    with pytest.raises(UnsupportedVersionError):
        await JsPsychDriver.create(page)


@pytest.mark.asyncio
async def test_setup_invokes_install_hook_js():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    driver = JsPsychDriver(version="7.3.1")
    await driver.setup(page)
    # setup should call page.evaluate at least once (to install the hook)
    assert page.evaluate.await_count >= 1

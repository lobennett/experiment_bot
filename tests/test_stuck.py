import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.navigation.stuck import StuckDetector


@pytest.mark.asyncio
async def test_stuck_detector_fires_after_timeout():
    """Detector calls the fallback after the timeout elapses."""
    fallback_called = asyncio.Event()
    guidance = {"action": "press", "key": "space"}

    async def mock_fallback(page, screenshot):
        fallback_called.set()
        return guidance

    detector = StuckDetector(timeout_seconds=0.1, fallback_fn=mock_fallback)
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_png")

    task = asyncio.create_task(detector.watch(mock_page))

    # Don't call heartbeat — should trigger after 0.1s
    await asyncio.sleep(0.3)
    detector.stop()
    await task

    assert fallback_called.is_set()


@pytest.mark.asyncio
async def test_stuck_detector_reset_on_heartbeat():
    """Heartbeat resets the timer, preventing fallback."""
    fallback_called = False

    async def mock_fallback(page, screenshot):
        nonlocal fallback_called
        fallback_called = True
        return {}

    detector = StuckDetector(timeout_seconds=0.2, fallback_fn=mock_fallback)
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_png")

    task = asyncio.create_task(detector.watch(mock_page))

    # Send heartbeats faster than timeout
    for _ in range(5):
        detector.heartbeat()
        await asyncio.sleep(0.05)

    detector.stop()
    await task
    assert not fallback_called

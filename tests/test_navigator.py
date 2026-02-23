import pytest
from unittest.mock import AsyncMock, MagicMock

from experiment_bot.navigation.navigator import InstructionNavigator
from experiment_bot.core.config import NavigationPhase, NavigationConfig


@pytest.mark.asyncio
async def test_execute_click_action():
    phase = NavigationPhase(phase="fullscreen", action="click", target="button.continue")
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))

    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_locator)
    mock_locator.first = mock_locator
    mock_locator.is_visible = AsyncMock(return_value=True)

    await nav.execute_phase(mock_page, phase)
    mock_page.locator.assert_called_with("button.continue")
    mock_locator.click.assert_called_once()


@pytest.mark.asyncio
async def test_execute_press_action():
    phase = NavigationPhase(phase="start", action="press", key="Enter")
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))

    mock_page = AsyncMock()
    await nav.execute_phase(mock_page, phase)
    mock_page.keyboard.press.assert_called_with("Enter")


@pytest.mark.asyncio
async def test_execute_wait_action():
    phase = NavigationPhase(phase="reading", action="wait", duration_ms=100)
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))

    mock_page = AsyncMock()
    await nav.execute_phase(mock_page, phase)

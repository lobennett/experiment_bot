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


@pytest.mark.asyncio
async def test_repeat_breaks_on_first_missing_click_target():
    """Regression: the instruction_pages 'repeat' phase used to keep
    iterating after the Next button disappeared, eating ~10 seconds per
    iteration in click timeouts. _do_click now re-raises on timeout so
    the surrounding repeat loop's exception handler breaks out.

    Without this fix, on expfactory_stop_signal the bot wasted ~170s
    clicking phantom Next buttons while the platform was already
    running trials — losing 35 of 180 trials at the start.
    """
    from playwright.async_api import Error as PlaywrightError
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))
    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_locator)
    mock_locator.first = mock_locator
    # First two clicks succeed; third call raises (button gone).
    waits = [None, None, PlaywrightError("Timeout 1500ms exceeded")]
    mock_locator.wait_for = AsyncMock(side_effect=waits)
    mock_locator.click = AsyncMock()

    repeat_phase = NavigationPhase(
        phase="instruction_pages", action="repeat",
        steps=[
            {"action": "click", "target": "#next-btn"},
        ],
    )
    await nav.execute_phase(mock_page, repeat_phase)
    # Two successful clicks before the missing target broke the loop;
    # without the re-raise, the loop would have iterated max_iterations
    # (default 50) times.
    assert mock_locator.click.call_count == 2


@pytest.mark.asyncio
async def test_do_click_timeout_is_short_for_fast_fail():
    """The click timeout must be short (<= 2s). 10s × N missing-target
    iterations was the original bug — too long causes the bot to fall
    behind the platform's trial pacing and miss real trials."""
    import inspect
    src = inspect.getsource(InstructionNavigator._do_click)
    # Anchor: timeout argument should be a small numeric (1500ms or so).
    # Specifically we should NOT see 10000ms.
    assert "10000" not in src, "click timeout regressed to 10s — bot will miss trials"

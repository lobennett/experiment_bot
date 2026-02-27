import pytest
from unittest.mock import AsyncMock

from experiment_bot.core.phase_detection import detect_phase
from experiment_bot.core.config import PhaseDetectionConfig, TaskPhase


@pytest.mark.asyncio
async def test_detect_phase_complete():
    page = AsyncMock()
    config = PhaseDetectionConfig(
        complete="document.querySelector('#done') !== null",
        test="true",
    )
    # The implementation wraps in (() => { try { return EXPR; } catch(e) { return false; } })()
    # So we match on the complete expression being in the JS string
    async def mock_evaluate(js):
        if "document.querySelector('#done')" in js:
            return True
        return False
    page.evaluate = AsyncMock(side_effect=mock_evaluate)

    result = await detect_phase(page, config)
    assert result == TaskPhase.COMPLETE


@pytest.mark.asyncio
async def test_detect_phase_fallback_to_test():
    page = AsyncMock()
    # All phase expressions return False
    page.evaluate = AsyncMock(return_value=False)

    config = PhaseDetectionConfig(
        complete="false",
        test="true",
    )
    result = await detect_phase(page, config)
    assert result == TaskPhase.TEST


@pytest.mark.asyncio
async def test_detect_phase_no_config():
    page = AsyncMock()
    config = PhaseDetectionConfig()  # All defaults — test="true"
    result = await detect_phase(page, config)
    assert result == TaskPhase.TEST


@pytest.mark.asyncio
async def test_detect_phase_context_destroyed():
    """Context destroyed (page navigated away) should return COMPLETE."""
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("Execution context was destroyed"))

    config = PhaseDetectionConfig(
        complete="document.querySelector('#done') !== null",
        test="true",
    )
    result = await detect_phase(page, config)
    assert result == TaskPhase.COMPLETE


@pytest.mark.asyncio
async def test_detect_phase_feedback():
    page = AsyncMock()
    config = PhaseDetectionConfig(
        complete="false",
        feedback="document.querySelector('.feedback') !== null",
        test="true",
    )
    call_count = 0

    async def mock_evaluate(js):
        nonlocal call_count
        call_count += 1
        if ".feedback" in js:
            return True
        return False

    page.evaluate = AsyncMock(side_effect=mock_evaluate)
    result = await detect_phase(page, config)
    assert result == TaskPhase.FEEDBACK

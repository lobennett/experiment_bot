import pytest
from unittest.mock import AsyncMock
from experiment_bot.platforms.base import Platform
from experiment_bot.core.config import TaskPhase, PhaseDetectionConfig


def test_platform_is_abstract():
    try:
        Platform()
        assert False, "Should raise TypeError"
    except TypeError:
        pass


def test_platform_subclass_must_implement_methods():
    class Incomplete(Platform):
        pass
    try:
        Incomplete()
        assert False, "Should raise TypeError"
    except TypeError:
        pass


@pytest.mark.asyncio
async def test_config_driven_phase_detection_complete():
    """Phase detection uses JS expressions from config when provided."""
    config = PhaseDetectionConfig(
        method="js_eval",
        complete="document.title === 'Done'",
        test="true",
    )
    page = AsyncMock()
    # complete expression returns True
    page.evaluate = AsyncMock(return_value=True)
    result = await Platform.detect_task_phase_from_config(page, config)
    assert result == TaskPhase.COMPLETE


@pytest.mark.asyncio
async def test_config_driven_phase_detection_fallthrough():
    """Returns None when no config expressions match, allowing subclass fallback."""
    config = PhaseDetectionConfig()  # empty, no expressions
    page = AsyncMock()
    result = await Platform.detect_task_phase_from_config(page, config)
    assert result is None


@pytest.mark.asyncio
async def test_config_driven_phase_detection_test_default():
    """When complete/loading don't match, falls through to TEST if test expression set."""
    config = PhaseDetectionConfig(
        complete="false",
        test="true",
    )
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    result = await Platform.detect_task_phase_from_config(page, config)
    assert result == TaskPhase.TEST

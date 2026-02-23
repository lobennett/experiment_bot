import pytest
from unittest.mock import AsyncMock

from experiment_bot.core.stimulus import StimulusLookup, StimulusMatch
from experiment_bot.core.config import (
    TaskConfig,
    StimulusConfig,
    DetectionConfig,
    ResponseConfig,
)


def _make_config_with_stimuli(stimuli: list[StimulusConfig]) -> TaskConfig:
    return TaskConfig.from_dict({
        "task": {"name": "T", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [s.to_dict() for s in stimuli],
        "response_distributions": {},
        "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
        "navigation": {"phases": []},
        "task_specific": {},
    })


@pytest.mark.asyncio
async def test_identify_matching_stimulus():
    stim = StimulusConfig(
        id="go_left",
        description="Left arrow",
        detection=DetectionConfig(method="dom_query", selector=".arrow-left"),
        response=ResponseConfig(key="z", condition="go"),
    )
    config = _make_config_with_stimuli([stim])
    lookup = StimulusLookup(config)

    mock_page = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=AsyncMock())

    match = await lookup.identify(mock_page)
    assert match is not None
    assert match.stimulus_id == "go_left"
    assert match.response_key == "z"
    assert match.condition == "go"


@pytest.mark.asyncio
async def test_identify_no_match():
    stim = StimulusConfig(
        id="go_left",
        description="Left arrow",
        detection=DetectionConfig(method="dom_query", selector=".arrow-left"),
        response=ResponseConfig(key="z", condition="go"),
    )
    config = _make_config_with_stimuli([stim])
    lookup = StimulusLookup(config)

    mock_page = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    match = await lookup.identify(mock_page)
    assert match is None


@pytest.mark.asyncio
async def test_identify_js_eval_method():
    stim = StimulusConfig(
        id="canvas_stim",
        description="Canvas stimulus",
        detection=DetectionConfig(method="js_eval", selector="window.currentStimulus === 'left'"),
        response=ResponseConfig(key="b", condition="go"),
    )
    config = _make_config_with_stimuli([stim])
    lookup = StimulusLookup(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=True)

    match = await lookup.identify(mock_page)
    assert match is not None
    assert match.stimulus_id == "canvas_stim"

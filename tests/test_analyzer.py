import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from experiment_bot.core.analyzer import Analyzer
from experiment_bot.core.config import SourceBundle, TaskConfig


MOCK_CONFIG_JSON = json.dumps({
    "task": {
        "name": "Stop Signal",
        "platform": "expfactory",
        "constructs": ["inhibitory_control"],
        "reference_literature": ["Logan 1994"],
    },
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        }
    ],
    "response_distributions": {
        "go_correct": {
            "distribution": "ex_gaussian",
            "params": {"mu": 450, "sigma": 60, "tau": 80},
        }
    },
    "performance": {
        "go_accuracy": 0.95,
        "stop_accuracy": 0.50,
        "omission_rate": 0.02,
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {},
})


@pytest.mark.asyncio
async def test_analyzer_builds_correct_messages():
    """Analyzer sends system prompt + source code to the API."""
    bundle = SourceBundle(
        platform="expfactory",
        task_id="9",
        source_files={"experiment.js": "console.log('test');"},
        description_text="A stop signal task.",
        metadata={},
    )

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=MOCK_CONFIG_JSON)]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    analyzer = Analyzer(client=mock_client)
    config = await analyzer.analyze(bundle)

    assert isinstance(config, TaskConfig)
    assert config.task.name == "Stop Signal"
    assert len(config.stimuli) == 1

    # Verify the API was called with correct model
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_analyzer_retries_on_invalid_json():
    """Analyzer retries once if Claude returns invalid JSON."""
    bundle = SourceBundle(
        platform="expfactory",
        task_id="9",
        source_files={"experiment.js": "x"},
        description_text="test",
        metadata={},
    )

    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.content = [MagicMock(text="not json")]
    good_response = MagicMock()
    good_response.content = [MagicMock(text=MOCK_CONFIG_JSON)]
    mock_client.messages.create = AsyncMock(side_effect=[bad_response, good_response])

    analyzer = Analyzer(client=mock_client)
    config = await analyzer.analyze(bundle)
    assert config.task.name == "Stop Signal"
    assert mock_client.messages.create.call_count == 2

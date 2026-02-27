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
        url="https://example.com/experiment/9",
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
        url="https://example.com/experiment/9",
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


MOCK_CONFIG_WITH_RUNTIME = json.dumps({
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
    "runtime": {
        "phase_detection": {
            "method": "dom_query",
            "complete": "document.querySelector('#done') !== null",
            "loading": "document.querySelector('#start-btn') !== null",
        },
        "timing": {
            "max_no_stimulus_polls": 300,
            "completion_wait_ms": 20000,
        },
        "advance_behavior": {
            "feedback_selectors": ["button.next"],
            "feedback_fallback_keys": ["Enter"],
        },
        "paradigm": {
            "type": "stop_signal",
            "stop_condition": "stop",
            "stop_failure_rt_key": "stop_failure",
            "stop_rt_cap_fraction": 0.85,
        },
    },
})


@pytest.mark.asyncio
async def test_analyzer_parses_runtime_config():
    """Analyzer correctly parses runtime section from Claude's response."""
    bundle = SourceBundle(
        url="https://example.com/experiment/9",
        source_files={"experiment.js": "console.log('test');"},
        description_text="A stop signal task.",
        metadata={},
    )

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=MOCK_CONFIG_WITH_RUNTIME)]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    analyzer = Analyzer(client=mock_client)
    config = await analyzer.analyze(bundle)

    assert config.runtime.phase_detection.method == "dom_query"
    assert "document.querySelector('#done')" in config.runtime.phase_detection.complete
    assert config.runtime.timing.max_no_stimulus_polls == 300
    assert config.runtime.timing.completion_wait_ms == 20000
    assert config.runtime.advance_behavior.feedback_selectors == ["button.next"]
    assert config.runtime.paradigm.type == "stop_signal"
    assert config.runtime.paradigm.stop_condition == "stop"


@pytest.mark.asyncio
async def test_analyzer_prompt_includes_runtime_schema():
    """The schema sent to Claude includes the runtime section."""
    analyzer = Analyzer(client=MagicMock())
    assert "runtime" in analyzer._schema["properties"]

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from experiment_bot.core.analyzer import Analyzer
from experiment_bot.core.config import SourceBundle, TaskConfig
from experiment_bot.core.pilot import PilotDiagnostics


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
        "accuracy": {"go": 0.95, "stop": 0.50},
        "omission_rate": {"go": 0.02},
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
    assert call_kwargs.kwargs["model"] == "claude-opus-4-7"


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
        "accuracy": {"go": 0.95, "stop": 0.50},
        "omission_rate": {"go": 0.02},
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
        "trial_interrupt": {
            "detection_condition": "stop",
            "failure_rt_key": "stop_failure",
            "failure_rt_cap_fraction": 0.85,
            "inhibit_wait_ms": 1500,
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
    assert config.runtime.trial_interrupt.detection_condition == "stop"
    assert config.runtime.trial_interrupt.failure_rt_key == "stop_failure"


@pytest.mark.asyncio
async def test_analyzer_prompt_includes_runtime_schema():
    """The schema sent to Claude includes the runtime section."""
    analyzer = Analyzer(client=MagicMock())
    assert "runtime" in analyzer._schema["properties"]


@pytest.mark.asyncio
async def test_analyzer_refine_sends_diagnostic_report():
    """refine() sends the diagnostic report and original source to Claude."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"task": {"name": "Test", "constructs": [], "reference_literature": []}, "stimuli": [], "response_distributions": {}, "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85}, "navigation": {"phases": []}}')]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    analyzer = Analyzer(client=mock_client)
    config = TaskConfig.from_dict({
        "task": {"name": "Test", "constructs": [], "reference_literature": []},
        "stimuli": [], "response_distributions": {},
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
        "navigation": {"phases": []}, "task_specific": {},
    })
    diagnostics = PilotDiagnostics(
        trials_completed=5, trials_with_stimulus_match=2,
        conditions_observed=["go"], conditions_missing=["stop"],
        selector_results={"go_stim": {"matches": 10, "polls": 50}},
        phase_results={}, dom_snapshots=[{"trigger": "test", "html": "<div>test</div>"}],
        anomalies=[], trial_log=[],
    )
    bundle = SourceBundle(url="http://test.com", source_files={}, description_text="<html>test</html>", hint="test")

    result = await analyzer.refine(config, diagnostics, bundle)
    assert isinstance(result, TaskConfig)

    # Verify the API was called with diagnostic content
    call_args = mock_client.messages.create.call_args
    user_msg = call_args.kwargs["messages"][0]["content"]
    assert "Pilot Run Diagnostic Report" in user_msg
    assert "<div>test</div>" in user_msg  # DOM snapshot
    assert "<html>test</html>" in user_msg  # original source


def test_analyzer_default_model_is_opus_4_7():
    """Analyzer uses Opus 4.7 as the default model."""
    analyzer = Analyzer(client=None)
    assert analyzer._model == "claude-opus-4-7"

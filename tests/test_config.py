import json
from experiment_bot.core.config import (
    TaskConfig,
    SourceBundle,
    TaskPhase,
    StimulusConfig,
    DetectionConfig,
    ResponseConfig,
    DistributionConfig,
    PerformanceConfig,
    NavigationPhase,
    TaskMetadata,
)


def test_task_phase_enum():
    assert TaskPhase.LOADING.value == "loading"
    assert TaskPhase.INSTRUCTIONS.value == "instructions"
    assert TaskPhase.PRACTICE.value == "practice"
    assert TaskPhase.FEEDBACK.value == "feedback"
    assert TaskPhase.TEST.value == "test"
    assert TaskPhase.ATTENTION_CHECK.value == "attention_check"
    assert TaskPhase.COMPLETE.value == "complete"


def test_source_bundle_creation():
    bundle = SourceBundle(
        platform="expfactory",
        task_id="9",
        source_files={"experiment.js": "var x = 1;"},
        description_text="A stop signal task.",
        metadata={"url": "https://example.com"},
    )
    assert bundle.platform == "expfactory"
    assert bundle.source_files["experiment.js"] == "var x = 1;"


def test_task_config_from_json():
    raw = {
        "task": {
            "name": "Stop Signal Task",
            "platform": "expfactory",
            "constructs": ["inhibitory_control"],
            "reference_literature": ["Logan et al. 1984"],
        },
        "stimuli": [
            {
                "id": "go_left",
                "description": "Left arrow",
                "detection": {
                    "method": "dom_query",
                    "selector": ".arrow-left",
                    "alt_method": "text_content",
                    "pattern": "←",
                },
                "response": {"key": "z", "condition": "go"},
            }
        ],
        "response_distributions": {
            "go_correct": {
                "distribution": "ex_gaussian",
                "params": {"mu": 450, "sigma": 60, "tau": 80},
                "unit": "ms",
            }
        },
        "performance": {
            "go_accuracy": 0.95,
            "stop_accuracy": 0.50,
            "omission_rate": 0.02,
            "practice_accuracy": 0.85,
        },
        "navigation": {
            "phases": [
                {"phase": "fullscreen", "action": "click", "target": "button.continue"}
            ]
        },
        "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
    }
    config = TaskConfig.from_dict(raw)
    assert config.task.name == "Stop Signal Task"
    assert len(config.stimuli) == 1
    assert config.stimuli[0].detection.selector == ".arrow-left"
    assert config.response_distributions["go_correct"].params["mu"] == 450
    assert config.performance.go_accuracy == 0.95
    assert config.navigation.phases[0].action == "click"
    assert config.task_specific["model"] == "independent_race"


def test_task_config_round_trip_json():
    raw = {
        "task": {
            "name": "Test",
            "platform": "test",
            "constructs": [],
            "reference_literature": [],
        },
        "stimuli": [],
        "response_distributions": {},
        "performance": {
            "go_accuracy": 0.9,
            "stop_accuracy": 0.5,
            "omission_rate": 0.01,
            "practice_accuracy": 0.8,
        },
        "navigation": {"phases": []},
        "task_specific": {},
    }
    config = TaskConfig.from_dict(raw)
    serialized = json.loads(json.dumps(config.to_dict()))
    config2 = TaskConfig.from_dict(serialized)
    assert config2.task.name == "Test"


def test_runtime_config_from_dict():
    """RuntimeConfig parses from JSON with all new fields."""
    data = {
        "phase_detection": {
            "method": "js_eval",
            "complete": "typeof psy_experiment_done !== 'undefined' && psy_experiment_done",
            "test": "true",
            "loading": "document.body.textContent.includes('Click to start')"
        },
        "timing": {
            "poll_interval_ms": 20,
            "max_no_stimulus_polls": 2000,
            "stuck_timeout_s": 10.0,
            "completion_wait_ms": 5000,
            "feedback_delay_ms": 2000,
            "omission_wait_ms": 2000,
            "stop_success_wait_ms": 1500,
            "rt_floor_ms": 150,
            "rt_cap_fraction": 0.90,
            "viewport": {"width": 1280, "height": 800}
        },
        "advance_behavior": {
            "pre_keypress_js": "psy_expect_keyboard()",
            "advance_keys": [" "],
            "exit_pager_key": "q",
            "advance_interval_polls": 100,
            "feedback_selectors": ["button"],
            "feedback_fallback_keys": [" ", "Enter"]
        },
        "paradigm": {
            "type": "stop_signal",
            "stop_condition": "stop",
            "stop_failure_rt_key": "stop_failure",
            "stop_rt_cap_fraction": 0.85
        }
    }
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig.from_dict(data)
    assert rc.timing.poll_interval_ms == 20
    assert rc.advance_behavior.exit_pager_key == "q"
    assert rc.paradigm.type == "stop_signal"


def test_task_config_with_runtime():
    """TaskConfig parses and round-trips with runtime section."""
    raw = {
        "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "response_distributions": {},
        "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
        "navigation": {"phases": []},
        "task_specific": {},
        "runtime": {
            "timing": {"poll_interval_ms": 50},
            "paradigm": {"type": "stop_signal"},
        }
    }
    config = TaskConfig.from_dict(raw)
    assert config.runtime.timing.poll_interval_ms == 50
    assert config.runtime.paradigm.type == "stop_signal"
    # Round-trip
    d = config.to_dict()
    assert d["runtime"]["timing"]["poll_interval_ms"] == 50


def test_runtime_config_defaults():
    """RuntimeConfig has sensible defaults when no data provided."""
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig.from_dict({})
    assert rc.timing.poll_interval_ms == 20
    assert rc.timing.max_no_stimulus_polls == 500
    assert rc.advance_behavior.advance_keys == [" "]
    assert rc.paradigm.type == "simple"

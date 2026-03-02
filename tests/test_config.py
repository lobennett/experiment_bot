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
        url="https://example.com/experiment/9",
        source_files={"experiment.js": "var x = 1;"},
        description_text="A stop signal task.",
        metadata={"fetched_resources": 1},
        hint="stop signal task",
    )
    assert bundle.url == "https://example.com/experiment/9"
    assert bundle.source_files["experiment.js"] == "var x = 1;"
    assert bundle.hint == "stop signal task"


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
            "accuracy": {"go": 0.95, "stop": 0.50},
            "omission_rate": {"go": 0.02},
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
    assert config.performance.get_accuracy("go") == 0.95
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
            "accuracy": {"go": 0.9, "stop": 0.5},
            "omission_rate": {"go": 0.01},
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
        "trial_interrupt": {
            "detection_condition": "stop",
            "failure_rt_key": "stop_failure",
            "failure_rt_cap_fraction": 0.85,
            "inhibit_wait_ms": 1500,
        }
    }
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig.from_dict(data)
    assert rc.timing.poll_interval_ms == 20
    assert rc.advance_behavior.exit_pager_key == "q"
    assert rc.trial_interrupt.detection_condition == "stop"


def test_task_config_with_runtime():
    """TaskConfig parses and round-trips with runtime section."""
    raw = {
        "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "response_distributions": {},
        "performance": {"accuracy": {"go": 0.9, "stop": 0.5}, "omission_rate": {"go": 0.01}, "practice_accuracy": 0.8},
        "navigation": {"phases": []},
        "task_specific": {},
        "runtime": {
            "timing": {"poll_interval_ms": 50},
            "trial_interrupt": {"detection_condition": "stop"},
        }
    }
    config = TaskConfig.from_dict(raw)
    assert config.runtime.timing.poll_interval_ms == 50
    assert config.runtime.trial_interrupt.detection_condition == "stop"
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
    assert rc.trial_interrupt.detection_condition == ""


def test_data_capture_config_from_dict():
    d = {
        "method": "js_expression",
        "expression": "jsPsych.data.get().csv()",
        "format": "csv",
    }
    from experiment_bot.core.config import DataCaptureConfig
    cfg = DataCaptureConfig.from_dict(d)
    assert cfg.method == "js_expression"
    assert cfg.expression == "jsPsych.data.get().csv()"
    assert cfg.format == "csv"


def test_data_capture_config_button_click():
    d = {
        "method": "button_click",
        "button_selector": "input[value='show data']",
        "result_selector": "#showdata",
        "format": "tsv",
    }
    from experiment_bot.core.config import DataCaptureConfig
    cfg = DataCaptureConfig.from_dict(d)
    assert cfg.method == "button_click"
    assert cfg.button_selector == "input[value='show data']"


def test_data_capture_config_defaults():
    from experiment_bot.core.config import DataCaptureConfig
    cfg = DataCaptureConfig()
    assert cfg.method == ""
    assert cfg.format == "csv"


def test_attention_check_config_from_dict():
    d = {
        "detection_selector": "#jspsych-attention-check-rdoc-stimulus",
        "text_selector": ".jspsych-display-element",
    }
    from experiment_bot.core.config import AttentionCheckConfig
    cfg = AttentionCheckConfig.from_dict(d)
    assert cfg.detection_selector == "#jspsych-attention-check-rdoc-stimulus"
    assert cfg.text_selector == ".jspsych-display-element"


def test_runtime_config_with_data_capture():
    d = {
        "data_capture": {
            "method": "js_expression",
            "expression": "jsPsych.data.get().csv()",
            "format": "csv",
        },
        "attention_check": {
            "detection_selector": "#attention-check",
        },
    }
    from experiment_bot.core.config import RuntimeConfig
    cfg = RuntimeConfig.from_dict(d)
    assert cfg.data_capture.method == "js_expression"
    assert cfg.attention_check.detection_selector == "#attention-check"


def test_legacy_paradigm_migrates_to_trial_interrupt():
    """Legacy 'paradigm' key in cached configs migrates to trial_interrupt."""
    from experiment_bot.core.config import RuntimeConfig
    legacy = {
        "paradigm": {
            "type": "stop_signal",
            "stop_condition": "stop",
            "stop_failure_rt_key": "stop_failure",
            "stop_rt_cap_fraction": 0.80,
        },
        "timing": {
            "stop_success_wait_ms": 2000,
            "cue_selector_js": "document.querySelector('#cue').textContent",
        },
    }
    rc = RuntimeConfig.from_dict(legacy)
    assert rc.trial_interrupt.detection_condition == "stop"
    assert rc.trial_interrupt.failure_rt_key == "stop_failure"
    assert rc.trial_interrupt.failure_rt_cap_fraction == 0.80
    assert rc.trial_interrupt.inhibit_wait_ms == 2000
    assert rc.timing.trial_context_js == "document.querySelector('#cue').textContent"

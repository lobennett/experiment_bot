import json
from pathlib import Path

import pytest

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
    assert rc.advance_behavior.advance_keys == []
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


def test_runtime_config_to_dict_always_emits_navigation_stimulus_condition():
    """RuntimeConfig.to_dict always includes navigation_stimulus_condition for round-trip stability."""
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig.from_dict({})
    assert rc.navigation_stimulus_condition == ""
    d = rc.to_dict()
    assert "navigation_stimulus_condition" in d
    assert d["navigation_stimulus_condition"] == ""
    # Round-trip preserves empty value
    rc2 = RuntimeConfig.from_dict(d)
    assert rc2.navigation_stimulus_condition == ""


# ---------------------------------------------------------------------------
# Task 5: Agnosticism review — behavioral defaults must be empty/zero by default
# ---------------------------------------------------------------------------


def test_advance_keys_empty_by_default():
    """advance_keys must default to [] — was [' '], now requires Claude to opt in."""
    from experiment_bot.core.config import AdvanceBehaviorConfig
    cfg = AdvanceBehaviorConfig.from_dict({})
    assert cfg.advance_keys == [], (
        "advance_keys should default to [] so the executor does not silently assume "
        "Space advances screens on every task"
    )


def test_feedback_fallback_keys_empty_by_default():
    """feedback_fallback_keys must default to [] — was ['Enter'], now requires Claude to opt in."""
    from experiment_bot.core.config import AdvanceBehaviorConfig
    cfg = AdvanceBehaviorConfig.from_dict({})
    assert cfg.feedback_fallback_keys == [], (
        "feedback_fallback_keys should default to [] so the executor does not silently "
        "assume Enter dismisses feedback on every task"
    )


def test_failure_rt_cap_fraction_zero_by_default():
    """failure_rt_cap_fraction must default to 0.0 — was 0.85, leaked stop-signal assumption."""
    from experiment_bot.core.config import TrialInterruptConfig
    cfg = TrialInterruptConfig.from_dict({})
    assert cfg.failure_rt_cap_fraction == 0.0, (
        "failure_rt_cap_fraction should default to 0.0; non-zero default leaks stop-signal "
        "assumptions into non-interrupt tasks"
    )


def test_inhibit_wait_ms_zero_by_default():
    """inhibit_wait_ms must default to 0 — was 1500, leaked stop-signal assumption."""
    from experiment_bot.core.config import TrialInterruptConfig
    cfg = TrialInterruptConfig.from_dict({})
    assert cfg.inhibit_wait_ms == 0, (
        "inhibit_wait_ms should default to 0; 1500 ms default leaks a specific stop-signal "
        "timing assumption into configs where detection_condition is empty"
    )


# ---------------------------------------------------------------------------
# Task C4: Contract tests — TaskCards must have required fields populated
# ---------------------------------------------------------------------------

_TASKCARD_LABELS = [
    "expfactory_stop_signal",
    "expfactory_stroop",
    "stopit_stop_signal",
    "cognitionrun_stroop",
]


@pytest.mark.parametrize("label", _TASKCARD_LABELS)
def test_taskcard_has_advance_keys(label):
    """advance_keys must be non-empty in every TaskCard (required since Task 5)."""
    from experiment_bot.taskcard.loader import load_latest
    if not list((Path("taskcards") / label).glob("*.json")):
        pytest.skip(f"{label} TaskCard not present")
    tc = load_latest(Path("taskcards"), label=label)
    keys = tc.runtime.advance_behavior.advance_keys
    assert keys, f"{label} has empty advance_keys"


@pytest.mark.parametrize("label", _TASKCARD_LABELS)
def test_taskcard_has_feedback_fallback_keys(label):
    """feedback_fallback_keys must be non-empty in every TaskCard (required since Task 5)."""
    from experiment_bot.taskcard.loader import load_latest
    if not list((Path("taskcards") / label).glob("*.json")):
        pytest.skip(f"{label} TaskCard not present")
    tc = load_latest(Path("taskcards"), label=label)
    keys = tc.runtime.advance_behavior.feedback_fallback_keys
    assert keys, f"{label} has empty feedback_fallback_keys"


@pytest.mark.parametrize("label", [
    "expfactory_stop_signal",
    "stopit_stop_signal",
])
def test_taskcard_failure_rt_cap_fraction_when_stop_signal(label):
    """failure_rt_cap_fraction must be non-zero for stop-signal tasks (required since Task 5)."""
    from experiment_bot.taskcard.loader import load_latest
    if not list((Path("taskcards") / label).glob("*.json")):
        pytest.skip(f"{label} TaskCard not present")
    tc = load_latest(Path("taskcards"), label=label)
    if not tc.runtime.trial_interrupt.detection_condition:
        pytest.skip(f"{label} has no trial interrupt; field not required")
    assert tc.runtime.trial_interrupt.failure_rt_cap_fraction > 0


@pytest.mark.parametrize("label", [
    "expfactory_stop_signal",
    "stopit_stop_signal",
])
def test_taskcard_inhibit_wait_ms_when_stop_signal(label):
    """inhibit_wait_ms must be non-zero for stop-signal tasks (required since Task 5)."""
    from experiment_bot.taskcard.loader import load_latest
    if not list((Path("taskcards") / label).glob("*.json")):
        pytest.skip(f"{label} TaskCard not present")
    tc = load_latest(Path("taskcards"), label=label)
    if not tc.runtime.trial_interrupt.detection_condition:
        pytest.skip(f"{label} has no trial interrupt; field not required")
    assert tc.runtime.trial_interrupt.inhibit_wait_ms > 0

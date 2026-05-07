import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.stimulus import StimulusMatch


SAMPLE_CONFIG = {
    "task": {"name": "Stop Signal", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        },
        {
            "id": "stop_trial",
            "description": "Stop signal",
            "detection": {"method": "dom_query", "selector": ".stop-signal"},
            "response": {"key": None, "condition": "stop"},
        },
    ],
    "response_distributions": {
        "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    },
    "performance": {"accuracy": {"go": 0.95, "stop": 0.50}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
    "runtime": {
        "trial_interrupt": {
            "detection_condition": "stop",
            "failure_rt_key": "stop_failure",
            "failure_rt_cap_fraction": 0.85,
        }
    },
}


def test_executor_init():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config)
    assert executor._config.task.name == "Stop Signal"


def test_should_respond_correctly_on_go():
    """On go trials with high accuracy, bot should usually respond correctly."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, seed=42)
    correct_count = sum(1 for _ in range(100) if executor._should_respond_correctly("go"))
    assert 85 < correct_count < 100


def test_should_omit_rarely():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, seed=42)
    omit_count = sum(1 for _ in range(1000) if executor._should_omit("go"))
    assert 5 < omit_count < 50


@pytest.mark.asyncio
async def test_attention_check_uses_response_js():
    """When response_js is configured, it's used instead of text parsing."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "attention_check": {
            "response_js": "document.querySelector('#ac-key').textContent.trim()",
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="q")
    await executor._handle_attention_check(page)
    page.keyboard.press.assert_called_with("q")


@pytest.mark.asyncio
async def test_attention_check_falls_back_to_enter_without_response_js():
    """Without response_js, attention check presses Enter as fallback."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {"attention_check": {}}
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()
    page = AsyncMock()
    await executor._handle_attention_check(page)
    page.keyboard.press.assert_called_with("Enter")


def test_interrupt_log_conditions_derive_from_config():
    """Interrupt log conditions use detection_condition, not hardcoded names."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    assert '"inhibit_success"' not in source
    assert '"inhibit_failure"' not in source


TASK_SWITCHING_CONFIG = {
    "task": {"name": "Cued Task Switching", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "parity_even",
            "description": "Even number with parity cue",
            "detection": {"method": "js_eval", "selector": "window.currTask === 'parity' && window.currStim.number % 2 === 0"},
            "response": {"key": "dynamic", "condition": "parity_even"},
        },
        {
            "id": "magnitude_high",
            "description": "Number > 5 with magnitude cue",
            "detection": {"method": "js_eval", "selector": "window.currTask === 'magnitude' && window.currStim.number > 5"},
            "response": {"key": "dynamic", "condition": "magnitude_high"},
        },
    ],
    "response_distributions": {
        "task_switch": {"distribution": "ex_gaussian", "params": {"mu": 580, "sigma": 70, "tau": 100}},
    },
    "performance": {"accuracy": {"go": 0.88}, "omission_rate": {"go": 0.03}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {
        "key_map": {
            "parity_even": ".",
            "parity_odd": ",",
            "magnitude_high": ",",
            "magnitude_low": ".",
        },
    },
}


def test_resolve_key_mapping_task_switching():
    """Verify key_map is read directly from task_specific.key_map."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config)
    key_map = executor._resolve_key_mapping(config)

    assert key_map["parity_even"] == "."
    assert key_map["parity_odd"] == ","
    assert key_map["magnitude_high"] == ","
    assert key_map["magnitude_low"] == "."


@pytest.mark.asyncio
async def test_resolve_response_key_dynamic_from_key_map():
    """When response_key='dynamic', falls back to static key_map lookup."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config)

    stimulus_match = StimulusMatch(
        stimulus_id="parity_even",
        response_key="dynamic",
        condition="parity_even"
    )

    # Without page, falls back to key_map
    resolved_key = await executor._resolve_response_key(stimulus_match)
    assert resolved_key == "."


@pytest.mark.asyncio
async def test_resolve_response_key_static():
    """Static response_key='z' returns 'z' unchanged."""
    config = TaskConfig.from_dict(TASK_SWITCHING_CONFIG)
    executor = TaskExecutor(config)

    stimulus_match = StimulusMatch(
        stimulus_id="go_left",
        response_key="z",
        condition="go"
    )

    resolved_key = await executor._resolve_response_key(stimulus_match)
    assert resolved_key == "z"


@pytest.mark.asyncio
async def test_resolve_response_key_via_response_key_js():
    """When response.key is null and response_key_js is set, evaluates JS on page."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["stimuli"] = [{
        "id": "color_red",
        "description": "Red stimulus",
        "detection": {"method": "js_eval", "selector": "true"},
        "response": {
            "key": None,
            "condition": "congruent",
            "response_key_js": "document.querySelector('.stim').dataset.key",
        },
    }]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)

    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=",")

    stimulus_match = StimulusMatch(
        stimulus_id="color_red",
        response_key=None,
        condition="congruent"
    )

    resolved_key = await executor._resolve_response_key(stimulus_match, page)
    assert resolved_key == ","
    assert "," in executor._seen_response_keys


def test_direct_key_map_from_config():
    """Key map uses task_specific.key_map directly when present."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["task_specific"] = {
        "key_map": {
            "go_left": "b",
            "go_right": "n",
            "parity_even": "z",
            "parity_odd": "m",
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)
    assert executor._key_map == config.task_specific["key_map"]


def test_direct_key_map_overrides_legacy():
    """When key_map is present, legacy group_index_mappings are ignored."""
    config_data = dict(TASK_SWITCHING_CONFIG)
    config_data["task_specific"]["key_map"] = {
        "parity_even": "a",
        "parity_odd": "s",
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)
    assert executor._key_map["parity_even"] == "a"
    assert executor._key_map["parity_odd"] == "s"


def test_executor_uses_runtime_timing():
    """Executor reads timing from runtime config, not hardcoded values."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "timing": {
            "poll_interval_ms": 50,
            "max_no_stimulus_polls": 1000,
            "stuck_timeout_s": 15.0,
            "completion_wait_ms": 10000,
            "rt_floor_ms": 200.0,
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)
    assert executor._config.runtime.timing.poll_interval_ms == 50
    assert executor._config.runtime.timing.max_no_stimulus_polls == 1000
    assert executor._config.runtime.timing.stuck_timeout_s == 15.0
    assert executor._config.runtime.timing.rt_floor_ms == 200.0


def test_feedback_uses_config_selectors():
    """_handle_feedback uses config selectors, not hardcoded jsPsych ones."""
    import inspect
    from experiment_bot.core.executor import TaskExecutor
    source = inspect.getsource(TaskExecutor._handle_feedback)
    # Should not contain hardcoded jsPsych selectors
    assert '"#jspsych-instructions-next"' not in source
    assert '".jspsych-btn"' not in source


def test_trial_interrupt_config_controls_inhibition():
    """Interrupt condition names come from trial_interrupt config."""
    config_data = dict(SAMPLE_CONFIG)
    # Override trial_interrupt to use "inhibit" instead of "stop"
    config_data["runtime"] = {
        "trial_interrupt": {
            "detection_condition": "inhibit",
            "failure_rt_key": "inhibit_failure",
            "failure_rt_cap_fraction": 0.80,
        }
    }
    # Add a stimulus with condition="inhibit"
    config_data["stimuli"] = [
        {
            "id": "go_left",
            "description": "Left arrow",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        },
        {
            "id": "inhibit_trial",
            "description": "Inhibition signal",
            "detection": {"method": "js_eval", "selector": "checkInhibit()"},
            "response": {"key": None, "condition": "inhibit"},
        },
    ]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)
    # _build_interrupt_check_js should find "inhibit" condition
    js = executor._build_interrupt_check_js()
    assert js == "!!(checkInhibit())"


def test_should_respond_correctly_uses_per_condition_accuracy():
    """_should_respond_correctly uses per-condition accuracy from the dict."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["performance"] = {
        "accuracy": {"go": 0.95, "inhibit": 0.50},
        "omission_rate": {"go": 0.02},
        "practice_accuracy": 0.85,
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    # "inhibit" should use its own accuracy (0.50)
    results = [executor._should_respond_correctly("inhibit") for _ in range(100)]
    # accuracy is 0.50, so roughly 50% should be True
    assert 30 < sum(results) < 70


def test_executor_no_platform_name_dependency():
    """Executor should not branch on platform name for behavioral logic.

    The _wait_for_completion method may reference platform_name to choose
    the file extension for captured data, which is acceptable.
    """
    import inspect
    from experiment_bot.core.executor import TaskExecutor

    # Check that behavioral methods don't branch on platform name
    for method_name in ("_trial_loop", "_execute_trial", "_handle_feedback",
                         "_handle_attention_check", "_resolve_response_key"):
        method = getattr(TaskExecutor, method_name)
        source = inspect.getsource(method)
        assert 'platform_name == "psytoolkit"' not in source, f"{method_name} branches on psytoolkit"
        assert 'platform_name == "expfactory"' not in source, f"{method_name} branches on expfactory"


def test_executor_sampler_uses_config_floor():
    """ResponseSampler receives floor_ms from runtime config."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {"timing": {"rt_floor_ms": 200.0}}
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    # The sampler should use 200.0 as floor, not the default 150.0
    assert executor._sampler._floor_ms == 200.0


def test_resolve_rt_distribution_key_condition_correct_error():
    """Configs with {condition}_correct distributions resolve via correct/error variants."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, seed=42)
    # SAMPLE_CONFIG has "go_correct" distribution — "go" + "_correct" matches
    assert executor._resolve_rt_distribution_key("go", True) == "go_correct"
    # "go_error" not in dists, so falls back to direct match → "go" not in dists → first available
    assert executor._resolve_rt_distribution_key("go", False) == "go_correct"


def test_sampler_fallback_to_first_distribution():
    """When requested condition doesn't exist, sampler falls back to first available."""
    from experiment_bot.core.distributions import ResponseSampler
    from experiment_bot.core.config import DistributionConfig, TemporalEffectsConfig
    dists = {
        "task_switch": DistributionConfig(distribution="ex_gaussian", params={"mu": 580, "sigma": 70, "tau": 100}),
    }
    sampler = ResponseSampler(dists, temporal_effects=TemporalEffectsConfig(), seed=42)
    rt = sampler.sample_rt_with_fallback("go_correct")
    assert 150 < rt < 2000


@pytest.mark.asyncio
async def test_wait_for_completion_captures_data():
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "data_capture": {
            "method": "js_expression",
            "expression": "jsPsych.data.get().csv()",
            "format": "csv",
        }
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()
    executor._writer.run_dir = "/tmp/fake"
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="rt,response\n450,left\n")
    await executor._wait_for_completion(page)
    executor._writer.save_task_data.assert_called_once_with("rt,response\n450,left\n", "experiment_data.csv")


# --- New tests for condition-driven performance and stimulus-gated detection ---


def test_is_trial_stimulus_with_direct_distribution():
    """_is_trial_stimulus returns True when condition is a direct distribution key."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["response_distributions"] = {
        "congruent": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    match = StimulusMatch(stimulus_id="cong_1", response_key="f", condition="congruent")
    assert executor._is_trial_stimulus(match) is True


def test_is_trial_stimulus_with_correct_error_variant():
    """_is_trial_stimulus returns True when {condition}_correct exists."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, seed=42)
    # SAMPLE_CONFIG has "go_correct" distribution
    match = StimulusMatch(stimulus_id="go_left", response_key="z", condition="go")
    assert executor._is_trial_stimulus(match) is True


def test_is_trial_stimulus_false_for_navigation():
    """_is_trial_stimulus returns False for stimuli without matching distributions."""
    config_data = dict(SAMPLE_CONFIG)
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    match = StimulusMatch(stimulus_id="nav", response_key=None, condition="navigation")
    assert executor._is_trial_stimulus(match) is False


@pytest.mark.asyncio
async def test_feedback_phase_overridden_by_trial_stimulus():
    """When feedback phase is detected but a trial stimulus is present, trial proceeds."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "phase_detection": {"feedback": "true", "complete": "false", "test": "true"},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()

    page = AsyncMock()
    trial_match = StimulusMatch(stimulus_id="go_left", response_key="z", condition="go")
    # identify returns a trial stimulus
    executor._lookup = MagicMock()
    executor._lookup.identify = AsyncMock(side_effect=[
        trial_match,  # probe in feedback check
        trial_match,  # would be reused as probe
        None,  # next poll — no stimulus
        None, None, None,  # enough misses to break
    ])

    # Phase detection returns FEEDBACK then COMPLETE
    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return TaskPhase.FEEDBACK
        return TaskPhase.COMPLETE

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        await executor._trial_loop(page)

    # Should have logged a trial (not just handled feedback)
    assert executor._trial_count == 1


@pytest.mark.asyncio
async def test_feedback_proceeds_when_no_trial_stimulus():
    """When feedback phase is detected and no trial stimulus found, feedback handled normally."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {
        "phase_detection": {"feedback": "true", "complete": "false", "test": "true"},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()

    page = AsyncMock()
    executor._lookup = MagicMock()
    executor._lookup.identify = AsyncMock(return_value=None)

    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return TaskPhase.FEEDBACK
        return TaskPhase.COMPLETE

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        await executor._trial_loop(page)

    # No trials — feedback was handled, then completion
    assert executor._trial_count == 0


def test_direct_condition_distribution_matching():
    """When condition name is a distribution key, it's used directly."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["response_distributions"] = {
        "congruent": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
        "incongruent": {"distribution": "ex_gaussian", "params": {"mu": 500, "sigma": 70, "tau": 90}},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    assert executor._resolve_rt_distribution_key("congruent", True) == "congruent"
    assert executor._resolve_rt_distribution_key("incongruent", True) == "incongruent"


def test_per_condition_accuracy_lookup():
    """get_accuracy returns condition-specific value, falls back to default."""
    from experiment_bot.core.config import PerformanceConfig
    perf = PerformanceConfig(
        accuracy={"congruent": 0.97, "incongruent": 0.88},
        omission_rate={},
    )
    assert perf.get_accuracy("congruent") == 0.97
    assert perf.get_accuracy("incongruent") == 0.88
    # Unknown condition falls back to first value
    assert perf.get_accuracy("neutral") == 0.97


def test_per_condition_accuracy_default_key():
    """get_accuracy uses 'default' key when condition not found."""
    from experiment_bot.core.config import PerformanceConfig
    perf = PerformanceConfig(accuracy={"default": 0.90}, omission_rate={})
    assert perf.get_accuracy("anything") == 0.90


def test_per_condition_omission_lookup():
    """get_omission_rate returns condition-specific value, falls back."""
    from experiment_bot.core.config import PerformanceConfig
    perf = PerformanceConfig(
        accuracy={"go": 0.95},
        omission_rate={"go": 0.02, "stop": 0.0},
    )
    assert perf.get_omission_rate("go") == 0.02
    assert perf.get_omission_rate("stop") == 0.0
    # Unknown falls back to first
    assert perf.get_omission_rate("other") == 0.02


def test_non_trial_stimulus_does_not_reset_consecutive_misses():
    """Non-trial stimuli (fixation, no_response) should not reset consecutive_misses.

    If a fixation stimulus resets the miss counter, the executor can get stuck
    indefinitely polling fixation -> reset -> poll fixation -> reset, never triggering
    advance behavior that would dismiss an instruction screen.
    """
    config_data = dict(SAMPLE_CONFIG)
    # Only "go" distributions — "no_response" has no distribution
    config_data["response_distributions"] = {
        "go": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)

    # A fixation match: null key, no_response condition, no matching distribution
    fixation_match = StimulusMatch(
        stimulus_id="fixation",
        response_key=None,
        condition="no_response",
    )
    assert executor._is_trial_stimulus(fixation_match) is False


def test_build_interrupt_check_js_wraps_dom_query():
    """dom_query selectors are wrapped in document.querySelector() for JS evaluation."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, seed=42)
    js = executor._build_interrupt_check_js()
    assert js is not None
    assert "document.querySelector" in js
    assert ".stop-signal" in js


def test_build_interrupt_check_js_combines_multiple_stimuli():
    """Multiple interrupt stimuli are combined with || into a single JS expression."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["stimuli"] = [
        {"id": "go", "description": "Go", "detection": {"method": "dom_query", "selector": ".go"},
         "response": {"key": "z", "condition": "go"}},
        {"id": "stop_left", "description": "Stop left", "detection": {"method": "dom_query", "selector": "img[src*='stop_left']"},
         "response": {"key": None, "condition": "stop"}},
        {"id": "stop_right", "description": "Stop right", "detection": {"method": "dom_query", "selector": "img[src*='stop_right']"},
         "response": {"key": None, "condition": "stop"}},
    ]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    js = executor._build_interrupt_check_js()
    assert "||" in js
    assert "stop_left" in js
    assert "stop_right" in js


def test_post_interrupt_slowing_state_initialized():
    """Executor starts with _prev_interrupt_detected = False."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, seed=42)
    assert executor._prev_interrupt_detected is False


def test_executor_invokes_post_event_slowing():
    """The executor's trial loop applies post-event slowing via the
    generic mechanism (apply_post_event_slowing). Trigger priority
    (interrupt vs error) is encoded in the TaskCard's triggers list,
    not in inline if/elif logic in the executor."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    assert "apply_post_event_slowing" in source
    assert "te.post_event_slowing" in source
    # Should NOT have hardcoded paradigm-specific names
    assert "te.post_interrupt_slowing" not in source
    assert "te.post_error_slowing" not in source


def test_post_event_slowing_reads_from_config():
    """Post-event slowing magnitudes come from the temporal_effects config."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    assert "post_event_slowing" in source


def test_executor_sampler_receives_temporal_effects():
    """Executor passes temporal_effects to ResponseSampler."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["temporal_effects"] = {
        "autocorrelation": {"enabled": True, "phi": 0.3, "rationale": "test"},
    }
    from experiment_bot.core.config import TaskConfig
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    assert executor._sampler._effects.autocorrelation.phi == 0.3


def test_post_interrupt_skips_condition_repetition():
    """When post-interrupt slowing fires, condition_repetition is suppressed."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    assert "skip_condition_repetition" in source


# ---------------------------------------------------------------------------
# Tests for configurable condition names (Step 3 / Task 4)
# ---------------------------------------------------------------------------


def _config_with_runtime(**runtime_kwargs):
    """Return a config dict with custom runtime fields."""
    data = dict(SAMPLE_CONFIG)
    data["runtime"] = dict(runtime_kwargs)
    return data


def test_navigation_condition_reads_from_config():
    """navigation_stimulus_condition is read from config, not hardcoded 'navigation'."""
    config_data = _config_with_runtime(
        navigation_stimulus_condition="nav_screen",
    )
    config = TaskConfig.from_dict(config_data)
    assert config.runtime.navigation_stimulus_condition == "nav_screen"


def test_navigation_condition_defaults_to_empty_string():
    """When navigation_stimulus_condition is absent, defaults to '' (backward compat)."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    assert config.runtime.navigation_stimulus_condition == ""


def test_attention_check_stimulus_conditions_reads_from_config():
    """attention_check.stimulus_conditions is read from config."""
    config_data = _config_with_runtime(
        attention_check={"stimulus_conditions": ["ac", "ac_response"]},
    )
    config = TaskConfig.from_dict(config_data)
    assert config.runtime.attention_check.stimulus_conditions == ["ac", "ac_response"]


def test_attention_check_stimulus_conditions_defaults():
    """When stimulus_conditions absent, defaults to standard set (backward compat)."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    assert set(config.runtime.attention_check.stimulus_conditions) == {
        "attention_check", "attention_check_response"
    }


@pytest.mark.asyncio
async def test_trial_loop_uses_config_navigation_condition():
    """Trial loop detects navigation using runtime.navigation_stimulus_condition."""
    config_data = _config_with_runtime(
        navigation_stimulus_condition="nav_screen",
        phase_detection={"complete": "false", "test": "true"},
    )
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()

    nav_match = StimulusMatch(stimulus_id="nav", response_key="Enter", condition="nav_screen")

    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return TaskPhase.TEST
        return TaskPhase.COMPLETE

    page = AsyncMock()
    executor._lookup = MagicMock()
    executor._lookup.identify = AsyncMock(side_effect=[nav_match, None])

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        await executor._trial_loop(page)

    # Confirm navigation key was pressed (not a trial)
    assert executor._trial_count == 0
    page.keyboard.press.assert_any_call("Enter")


@pytest.mark.asyncio
async def test_trial_loop_uses_config_attention_check_conditions():
    """Trial loop detects attention checks using runtime.attention_check.stimulus_conditions."""
    config_data = _config_with_runtime(
        attention_check={"stimulus_conditions": ["custom_ac"], "response_js": ""},
        phase_detection={"complete": "false", "test": "true"},
    )
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()

    ac_match = StimulusMatch(stimulus_id="ac1", response_key=None, condition="custom_ac")

    call_count = 0

    async def mock_detect_phase(page, cfg):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return TaskPhase.TEST
        return TaskPhase.COMPLETE

    page = AsyncMock()
    executor._lookup = MagicMock()
    executor._lookup.identify = AsyncMock(side_effect=[ac_match, None])

    handle_ac_calls = []

    async def mock_handle_ac(p):
        handle_ac_calls.append(p)

    executor._handle_attention_check = mock_handle_ac

    with patch("experiment_bot.core.executor.detect_phase", side_effect=mock_detect_phase):
        await executor._trial_loop(page)

    assert len(handle_ac_calls) == 1


# ---------------------------------------------------------------------------
# Tests for timing config fields (Step 11 / Task 4)
# ---------------------------------------------------------------------------


def test_timing_config_has_navigation_delay_ms():
    """TimingConfig has navigation_delay_ms field."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig(navigation_delay_ms=500)
    assert t.navigation_delay_ms == 500


def test_timing_config_navigation_delay_ms_default():
    """navigation_delay_ms defaults to 1000 (matches old hardcoded 1.0s)."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig()
    assert t.navigation_delay_ms == 1000


def test_timing_config_has_attention_check_delay_ms():
    """TimingConfig has attention_check_delay_ms field."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig(attention_check_delay_ms=500)
    assert t.attention_check_delay_ms == 500


def test_timing_config_attention_check_delay_ms_default():
    """attention_check_delay_ms defaults to 1500 (matches old hardcoded 1.5s)."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig()
    assert t.attention_check_delay_ms == 1500


def test_timing_config_has_completion_settle_ms():
    """TimingConfig has completion_settle_ms field."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig(completion_settle_ms=3000)
    assert t.completion_settle_ms == 3000


def test_timing_config_completion_settle_ms_default():
    """completion_settle_ms defaults to 2000 (matches old hardcoded 2.0s)."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig()
    assert t.completion_settle_ms == 2000


def test_timing_config_has_trial_end_timeout_s():
    """TimingConfig has trial_end_timeout_s field."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig(trial_end_timeout_s=10.0)
    assert t.trial_end_timeout_s == 10.0


def test_timing_config_trial_end_timeout_s_default():
    """trial_end_timeout_s defaults to 5.0 (matches old hardcoded default)."""
    from experiment_bot.core.config import TimingConfig
    t = TimingConfig()
    assert t.trial_end_timeout_s == 5.0


def test_timing_config_roundtrips_new_fields():
    """New timing fields survive from_dict/to_dict round-trip."""
    from experiment_bot.core.config import TimingConfig
    d = {
        "navigation_delay_ms": 750,
        "attention_check_delay_ms": 800,
        "completion_settle_ms": 1500,
        "trial_end_timeout_s": 7.5,
    }
    t = TimingConfig.from_dict(d)
    assert t.navigation_delay_ms == 750
    assert t.attention_check_delay_ms == 800
    assert t.completion_settle_ms == 1500
    assert t.trial_end_timeout_s == 7.5
    out = t.to_dict()
    assert out["navigation_delay_ms"] == 750
    assert out["attention_check_delay_ms"] == 800
    assert out["completion_settle_ms"] == 1500
    assert out["trial_end_timeout_s"] == 7.5


def test_executor_navigation_uses_config_delay():
    """_trial_loop uses runtime.timing.navigation_delay_ms for navigation pause."""
    import inspect
    source = inspect.getsource(TaskExecutor._trial_loop)
    # Must not have magic literal 1.0 for navigation sleep
    # (The test verifies the config field is referenced)
    assert "navigation_delay_ms" in source


def test_executor_attention_check_uses_config_delay():
    """_handle_attention_check uses runtime.timing.attention_check_delay_ms."""
    import inspect
    source = inspect.getsource(TaskExecutor._handle_attention_check)
    assert "attention_check_delay_ms" in source


def test_executor_completion_settle_uses_config():
    """_wait_for_completion uses runtime.timing.completion_settle_ms."""
    import inspect
    source = inspect.getsource(TaskExecutor._wait_for_completion)
    assert "completion_settle_ms" in source


def test_executor_trial_end_timeout_uses_config():
    """_wait_for_trial_end uses runtime.timing.trial_end_timeout_s instead of hardcoded 5.0."""
    import inspect
    source = inspect.getsource(TaskExecutor._trial_loop)
    # The call site passes trial_end_timeout_s, not a literal 5.0
    assert "trial_end_timeout_s" in source


# ---------------------------------------------------------------------------
# Tests for _resolve_response_key withhold sentinels (NEW Critical finding)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_response_key_returns_none_for_empty_string():
    """Empty string return from JS is treated as withhold (returns None)."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config)
    match = StimulusMatch(stimulus_id="go_left", response_key=None, condition="go")
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="")
    result = await executor._resolve_response_key(match, page)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_response_key_returns_none_for_none_value():
    """JS returning Python None is treated as withhold."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["stimuli"] = [{
        "id": "go_left",
        "description": "Go stimulus",
        "detection": {"method": "dom_query", "selector": ".go"},
        "response": {"key": None, "condition": "go", "response_key_js": "getKey()"},
    }]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)
    match = StimulusMatch(stimulus_id="go_left", response_key=None, condition="go")
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    result = await executor._resolve_response_key(match, page)
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("sentinel", [
    "none", "None", "NONE", "null", "Null", "NULL",
    "withhold", "Withhold", "WITHHOLD",
    "no_response", "NO_RESPONSE", "No_Response",
    "noresponse", "NORESPONSE",
    "no_key", "NO_KEY",
    "nokey", "NOKEY",
    "suppress", "SUPPRESS",
    "skip", "SKIP",
    "pass", "PASS",
])
async def test_resolve_response_key_returns_none_for_sentinel_strings(sentinel):
    """Sentinel strings (case-insensitive) are treated as withhold / no key press."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["stimuli"] = [{
        "id": "stop_stim",
        "description": "Stop/withhold stimulus",
        "detection": {"method": "dom_query", "selector": ".stop"},
        "response": {"key": None, "condition": "stop", "response_key_js": "getKey()"},
    }]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)
    match = StimulusMatch(stimulus_id="stop_stim", response_key=None, condition="stop")
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=sentinel)
    result = await executor._resolve_response_key(match, page)
    assert result is None, f"Expected None for sentinel {sentinel!r}, got {result!r}"


@pytest.mark.asyncio
async def test_resolve_response_key_sentinel_no_keyboard_press(monkeypatch):
    """When resolved_key is None (sentinel), _execute_trial does not press any key."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["stimuli"] = [{
        "id": "stop_stim",
        "description": "Stop/withhold stimulus",
        "detection": {"method": "dom_query", "selector": ".stop"},
        "response": {"key": None, "condition": "go", "response_key_js": "getKey()"},
    }]
    config_data["response_distributions"] = {
        "go": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    }
    config_data["performance"] = {
        "accuracy": {"go": 1.0},
        "omission_rate": {"go": 0.0},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    executor._writer = MagicMock()

    page = AsyncMock()
    # JS returns "none" — sentinel for withhold
    page.evaluate = AsyncMock(return_value="none")

    match = StimulusMatch(stimulus_id="stop_stim", response_key=None, condition="go")
    await executor._execute_trial(page, match)

    # keyboard.press must NOT have been called
    page.keyboard.press.assert_not_called()
    # trial should still be logged (with response_key=null, withheld=true)
    executor._writer.log_trial.assert_called_once()
    logged = executor._writer.log_trial.call_args[0][0]
    assert logged["response_key"] is None
    assert logged.get("withheld") is True
    assert logged.get("omission") is False


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _minimal_config_dict() -> dict:
    """Return a minimal valid config dict suitable for TaskConfig.from_dict."""
    import copy
    return copy.deepcopy(SAMPLE_CONFIG)


@pytest.mark.live
def test_live_executor_runs_against_regenerated_taskcard():
    """End-to-end smoke against a real Playwright session.

    Skipped by default. Run with `RUN_LIVE_LLM=1 uv run pytest -m live -v`.
    Verifies executor + TaskCard integration on expfactory_stroop.
    """
    import asyncio
    import os
    from pathlib import Path
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.taskcard.loader import load_latest
    from experiment_bot.taskcard.sampling import sample_session_params

    if not os.environ.get("RUN_LIVE_LLM"):
        pytest.skip("Set RUN_LIVE_LLM=1 to run live tests")

    label = "expfactory_stroop"
    if not (Path("taskcards") / label).exists():
        pytest.skip(f"{label} TaskCard not present")

    tc = load_latest(Path("taskcards"), label=label)
    sampled = sample_session_params(tc.to_dict(), seed=42)
    for cond, params in sampled.items():
        if cond in tc.response_distributions:
            tc.response_distributions[cond].value.update(params)

    ex = TaskExecutor(tc, headless=True)
    asyncio.run(ex.run("https://deploy.expfactory.org/preview/10/"))


# ---------------------------------------------------------------------------
# Important Issue 1: cached condition-name attributes
# ---------------------------------------------------------------------------

def test_navigation_condition_name_attribute_is_config_driven(monkeypatch):
    """TaskExecutor caches navigation_stimulus_condition in __init__."""
    cfg_dict = _minimal_config_dict()
    cfg_dict["runtime"]["navigation_stimulus_condition"] = "advance_screen"
    config = TaskConfig.from_dict(cfg_dict)
    executor = TaskExecutor(config)
    assert executor._navigation_condition_name == "advance_screen"


def test_attention_check_conditions_attribute_is_config_driven():
    """TaskExecutor caches attention_check.stimulus_conditions in __init__."""
    cfg_dict = _minimal_config_dict()
    cfg_dict["runtime"]["attention_check"] = {"stimulus_conditions": ["probe", "probe_resp"]}
    config = TaskConfig.from_dict(cfg_dict)
    executor = TaskExecutor(config)
    assert executor._attention_check_conditions == {"probe", "probe_resp"}


# ---------------------------------------------------------------------------
# Minor Issue 4: sentinel test for global task_specific.response_key_js path
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Post-Phase-3 fix: _pick_wrong_key sentinel filtering (second sentinel leak)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sentinel", [
    "withhold", "none", "null", "", "skip", "pass", "noresponse",
    "no_response", "no_key", "nokey", "suppress",
])
def test_pick_wrong_key_filters_sentinels(sentinel):
    """_pick_wrong_key must not return a sentinel value as a 'wrong key'."""
    config = TaskConfig.from_dict(_minimal_config_dict())
    executor = TaskExecutor(config)
    executor._key_map = {"go": "z", "stop": sentinel}
    executor._seen_response_keys = set()
    # correct_key = "z"; the only other candidate is sentinel; must not return sentinel
    result = executor._pick_wrong_key("z")
    assert not TaskExecutor._is_withhold_sentinel(result), f"Got sentinel {result!r}"


@pytest.mark.asyncio
async def test_resolve_response_key_static_key_map_sentinel_returns_none():
    """_resolve_response_key must return None when the static key_map maps to a sentinel."""
    config_data = _minimal_config_dict()
    # Set up key_map with a sentinel for "stop" condition; no response_key_js on the stimulus
    config_data["task_specific"] = {"key_map": {"go": "z", "stop": "withhold"}}
    config_data["stimuli"] = [{
        "id": "stop_stim",
        "description": "Stop/withhold stimulus",
        "detection": {"method": "dom_query", "selector": ".stop"},
        "response": {"key": "dynamic", "condition": "stop"},
    }]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config)

    # No page provided, so JS paths are skipped; falls through to static key_map
    match = StimulusMatch(stimulus_id="stop_stim", response_key="dynamic", condition="stop")
    result = await executor._resolve_response_key(match)
    assert result is None, f"Expected None for sentinel key_map value, got {result!r}"
    # Sentinel must NOT be stored in seen_response_keys
    assert "withhold" not in executor._seen_response_keys


@pytest.mark.asyncio
@pytest.mark.parametrize("sentinel", [
    "", None, "none", "null", "NONE", "Null",
    "withhold", "WITHHOLD",
    "no_response", "noresponse",
    "no_key", "nokey",
    "suppress", "skip", "pass",
])
async def test_resolve_response_key_global_js_sentinel_returns_none(sentinel):
    """Global task_specific.response_key_js returning a sentinel resolves to None."""
    config_data = _minimal_config_dict()
    # Move response_key_js to task_specific (global path) — NOT on the stimulus
    config_data["task_specific"]["response_key_js"] = "getKey()"
    config_data["stimuli"] = [{
        "id": "stop_stim",
        "description": "Stop/withhold stimulus",
        "detection": {"method": "dom_query", "selector": ".stop"},
        "response": {"key": None, "condition": "stop"},
    }]
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)

    match = StimulusMatch(stimulus_id="stop_stim", response_key=None, condition="stop")
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=sentinel)
    result = await executor._resolve_response_key(match, page)
    assert result is None, f"Expected None for sentinel {sentinel!r}, got {result!r}"


def test_executor_constructs_from_taskcard():
    """TaskExecutor accepts a TaskCard (dataclass) as well as legacy TaskConfig."""
    from experiment_bot.taskcard.types import TaskCard
    from experiment_bot.core.executor import TaskExecutor

    base = {
        "schema_version": "2.0",
        "produced_by": {
            "model": "x", "prompt_sha256": "", "scraper_version": "1.0",
            "source_sha256": "", "timestamp": "2026-04-23T12:00:00Z",
            "taskcard_sha256": "",
        },
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "navigation": {"phases": []},
        "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500.0, "sigma": 60.0, "tau": 80.0},
                "rationale": "",
            }
        },
        "temporal_effects": {},
        "between_subject_jitter": {},
        "reasoning_chain": [],
        "pilot_validation": {},
    }
    tc = TaskCard.from_dict(base)
    executor = TaskExecutor(tc)
    assert executor._config.task.name == "stroop"
    # Legacy TaskConfig view still has response_distributions
    assert "default" in executor._config.response_distributions

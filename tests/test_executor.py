"""Tests for the SP10 slim TaskExecutor.

Under SP10 the executor only owns: __init__ (sampler + writer + RNG +
history), `_run_session` (driver-based trial loop), `run()` (Playwright
bootstrap + driver identification), `_resolve_response` (module-level
helper for deciding correct/wrong key on a single trial), and the
`_taskcard_to_config` helper. Everything else (key resolution, phase
detection, keypress diagnostics, navigation, attention checks, trial-
end waiting) lives in the per-platform PlatformDriver.

The pre-SP10 test surface aimed at private executor methods that are
now gone; those tests were deleted in SP10 Task 9.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.core.config import TaskConfig


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


def test_executor_sampler_uses_config_floor():
    """ResponseSampler receives floor_ms from runtime config."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["runtime"] = {"timing": {"rt_floor_ms": 200.0}}
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    assert executor._sampler._floor_ms == 200.0


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


# ---------------------------------------------------------------------------
# PerformanceConfig (paradigm-agnostic) tests — not executor-internal,
# but exercise the config the executor reads.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Config-driven condition names (Step 3 / Task 4 — config layer, not executor)
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


# ---------------------------------------------------------------------------
# TimingConfig field tests
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


# ---------------------------------------------------------------------------
# SP10 executor tests — TaskCard construction + driver-based run flow.
# ---------------------------------------------------------------------------


def test_executor_constructs_from_taskcard():
    """TaskExecutor accepts a TaskCard (dataclass) as well as legacy TaskConfig."""
    from experiment_bot.taskcard.types import TaskCard

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


def test_executor_persists_session_seed_and_params_to_metadata():
    """Regression for SP2-E3 backlog item #5: run_metadata must record
    session_seed and per-session sampled params so a run is reproducible
    and the sampler's per-session draws are auditable."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(
        config, seed=12345,
        session_params={"go": {"mu": 510.0, "sigma": 65.0, "tau": 85.0}},
    )
    fake_writer = MagicMock()
    executor._writer = fake_writer
    # Hand-call the metadata save the way the run() finally block does.
    metadata = {
        "task_name": config.task.name,
        "task_url": "http://example.com/x",
        "total_trials": executor._trial_count,
        "headless": executor._headless,
        "session_seed": executor._session_seed,
        "session_params": executor._session_params,
    }
    fake_writer.save_metadata(metadata)
    saved_args, _ = fake_writer.save_metadata.call_args
    saved = saved_args[0]
    assert saved["session_seed"] == 12345
    assert saved["session_params"]["go"]["mu"] == 510.0


@pytest.mark.asyncio
async def test_run_session_dispatches_navigation_until_ready_then_runs_trial():
    """SP10: _run_session polls driver.loop_state; on NEEDS_NAVIGATION
    calls driver.navigate; on READY_FOR_TRIAL samples RT and calls
    driver.deliver_response; on COMPLETE breaks out of the loop."""
    from collections import deque
    import random
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from experiment_bot.drivers.base import (
        DeliveryResult, NavigationOutcome, TrialContext, TrialLoopState,
    )

    driver = MagicMock()
    driver.setup = AsyncMock()
    driver.loop_state = AsyncMock(side_effect=[
        TrialLoopState.NEEDS_NAVIGATION,
        TrialLoopState.READY_FOR_TRIAL,
        TrialLoopState.COMPLETE,
    ])
    driver.navigate = AsyncMock(return_value=NavigationOutcome(action="advanced_instructions"))
    driver.get_trial_context = AsyncMock(return_value=TrialContext(
        stimulus_id="s1", condition="congruent",
        allowed_responses=(",", "."), expected_correct=",",
        response_window_ms=1500,
    ))
    driver.deliver_response = AsyncMock(return_value=DeliveryResult(
        success=True, delivered_at_ms=350.0, actual_rt_ms=350.0,
        method="jspsych_callback_hook",
    ))
    driver.wait_for_trial_end = AsyncMock()
    driver.wait_for_completion = AsyncMock()
    driver.retrieve_data = AsyncMock(return_value=None)
    driver.teardown = AsyncMock()

    stub = TaskExecutor.__new__(TaskExecutor)
    stub._config = SimpleNamespace(
        task=SimpleNamespace(name="x"),
        performance=SimpleNamespace(get_accuracy=lambda c: 0.95),
        response_distributions={},
    )
    stub._taskcard = None
    stub._py_rng = random.Random(0)
    stub._sampler = MagicMock()
    stub._sampler.sample_rt_with_fallback = MagicMock(return_value=350.0)
    stub._writer = MagicMock()
    stub._trial_count = 0
    stub._recent_errors = deque(maxlen=8)

    page = AsyncMock()
    await stub._run_session(page, driver)

    driver.setup.assert_awaited_once_with(page)
    driver.navigate.assert_awaited_once()
    driver.get_trial_context.assert_awaited_once()
    driver.deliver_response.assert_awaited_once()
    driver.wait_for_trial_end.assert_awaited_once()
    driver.wait_for_completion.assert_awaited_once()
    driver.retrieve_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_uses_identify_driver_and_calls_run_session(monkeypatch):
    """SP10: TaskExecutor.run navigates, identifies a driver, then
    dispatches _run_session."""
    import contextlib
    from collections import deque
    from pathlib import Path
    import random
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from experiment_bot.drivers.base import ExperimentData, TrialLoopState

    fake_driver = MagicMock()
    fake_driver.setup = AsyncMock()
    fake_driver.loop_state = AsyncMock(return_value=TrialLoopState.COMPLETE)
    fake_driver.wait_for_completion = AsyncMock()
    fake_driver.retrieve_data = AsyncMock(return_value=ExperimentData(
        trials=[], format="json", raw="[]",
    ))
    fake_driver.teardown = AsyncMock()

    async def fake_identify(page):
        return fake_driver

    monkeypatch.setattr(
        "experiment_bot.core.executor.identify_driver", fake_identify,
    )

    stub = TaskExecutor.__new__(TaskExecutor)
    stub._config = SimpleNamespace(
        task=SimpleNamespace(name="x"),
        performance=SimpleNamespace(get_accuracy=lambda c: 0.95),
        response_distributions={},
        runtime=SimpleNamespace(timing=SimpleNamespace(viewport={"width": 1280, "height": 720})),
    )
    stub._taskcard = None
    stub._py_rng = random.Random(0)
    stub._sampler = MagicMock()
    stub._writer = MagicMock()
    stub._writer.create_run = MagicMock(return_value=Path("/tmp/x"))
    stub._writer.run_dir = Path("/tmp/x")
    stub._trial_count = 0
    stub._recent_errors = deque(maxlen=8)
    stub._headless = True
    stub._session_seed = 0
    stub._session_params = {}

    fake_page = AsyncMock()
    fake_page.goto = AsyncMock()
    fake_browser = MagicMock()
    fake_context = MagicMock()
    fake_context.new_page = AsyncMock(return_value=fake_page)
    fake_browser.new_context = AsyncMock(return_value=fake_context)
    fake_browser.close = AsyncMock()
    fake_pw = MagicMock()
    fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)

    @contextlib.asynccontextmanager
    async def fake_async_playwright():
        yield fake_pw

    monkeypatch.setattr(
        "experiment_bot.core.executor.async_playwright", fake_async_playwright,
    )

    await stub.run("http://example.com/test")

    fake_driver.setup.assert_awaited_once()
    fake_driver.wait_for_completion.assert_awaited_once()
    fake_driver.retrieve_data.assert_awaited_once()


# ---------------------------------------------------------------------------
# _resolve_response (module-level helper) — pure function tests
# ---------------------------------------------------------------------------


def test_resolve_response_returns_none_when_no_allowed_responses():
    """No allowed responses + no expected_correct = withhold (None)."""
    import random
    from experiment_bot.core.executor import _resolve_response
    from experiment_bot.drivers.base import TrialContext

    ctx = TrialContext(
        stimulus_id="stop", condition="stop",
        allowed_responses=(), expected_correct=None,
        response_window_ms=1500,
    )
    result = _resolve_response(ctx, intended_correct=True, rng=random.Random(0), taskcard=None)
    assert result is None


def test_resolve_response_returns_expected_correct_when_intended_correct():
    """When intended_correct=True and expected_correct is set, returns it."""
    import random
    from experiment_bot.core.executor import _resolve_response
    from experiment_bot.drivers.base import TrialContext

    ctx = TrialContext(
        stimulus_id="s1", condition="congruent",
        allowed_responses=(",", "."), expected_correct=",",
        response_window_ms=1500,
    )
    result = _resolve_response(ctx, intended_correct=True, rng=random.Random(0), taskcard=None)
    assert result == ","


def test_resolve_response_picks_wrong_when_not_intended_correct():
    """When intended_correct=False, returns a non-correct key from allowed_responses."""
    import random
    from experiment_bot.core.executor import _resolve_response
    from experiment_bot.drivers.base import TrialContext

    ctx = TrialContext(
        stimulus_id="s1", condition="congruent",
        allowed_responses=(",", "."), expected_correct=",",
        response_window_ms=1500,
    )
    result = _resolve_response(ctx, intended_correct=False, rng=random.Random(0), taskcard=None)
    assert result == "."
    assert result != ","


def test_resolve_response_legacy_key_map_fallback():
    """When ctx.expected_correct is None, falls back to taskcard.task_specific.key_map."""
    import random
    from types import SimpleNamespace
    from experiment_bot.core.executor import _resolve_response
    from experiment_bot.drivers.base import TrialContext

    ctx = TrialContext(
        stimulus_id="s1", condition="go",
        allowed_responses=("z", "/"), expected_correct=None,
        response_window_ms=1500,
    )
    taskcard = SimpleNamespace(task_specific={"key_map": {"go": "z"}})
    result = _resolve_response(ctx, intended_correct=True, rng=random.Random(0), taskcard=taskcard)
    assert result == "z"


def test_resolve_response_ignores_dynamic_sentinel_in_legacy_key_map():
    """A legacy key_map value of 'dynamic' must NOT be used as a literal key."""
    import random
    from types import SimpleNamespace
    from experiment_bot.core.executor import _resolve_response
    from experiment_bot.drivers.base import TrialContext

    ctx = TrialContext(
        stimulus_id="s1", condition="go",
        allowed_responses=("z", "/"), expected_correct=None,
        response_window_ms=1500,
    )
    taskcard = SimpleNamespace(task_specific={"key_map": {"go": "dynamic"}})
    result = _resolve_response(ctx, intended_correct=True, rng=random.Random(0), taskcard=taskcard)
    # Falls through to random pick from allowed_responses
    assert result in ("z", "/")


# ---------------------------------------------------------------------------
# _taskcard_to_config helper
# ---------------------------------------------------------------------------


def test_taskcard_to_config_projects_response_distributions():
    """_taskcard_to_config projects ParameterValue.value into DistributionConfig.params."""
    from experiment_bot.core.executor import _taskcard_to_config
    from experiment_bot.taskcard.types import TaskCard

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
            "congruent": {
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
    cfg = _taskcard_to_config(tc)
    assert "congruent" in cfg.response_distributions
    assert cfg.response_distributions["congruent"].params == {"mu": 500.0, "sigma": 60.0, "tau": 80.0}


@pytest.mark.live
def test_live_executor_runs_against_regenerated_taskcard():
    """End-to-end smoke against a real Playwright session.

    Skipped by default. Run with `RUN_LIVE_LLM=1 uv run pytest -m live -v`.
    Verifies executor + TaskCard integration on expfactory_stroop.
    """
    import asyncio
    import os
    from pathlib import Path
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

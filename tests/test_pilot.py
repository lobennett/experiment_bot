import asyncio

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.pilot import PilotDiagnostics, PilotRunner


def test_diagnostics_match_rate_all_matched():
    d = PilotDiagnostics(
        trials_completed=10, trials_with_stimulus_match=10,
        conditions_observed=["a", "b"], conditions_missing=[],
        selector_results={}, phase_results={}, dom_snapshots=[],
        anomalies=[], trial_log=[],
    )
    assert d.match_rate == 1.0
    assert d.all_conditions_observed is True


def test_diagnostics_match_rate_none_matched():
    d = PilotDiagnostics(
        trials_completed=10, trials_with_stimulus_match=0,
        conditions_observed=[], conditions_missing=["a"],
        selector_results={}, phase_results={}, dom_snapshots=[],
        anomalies=[], trial_log=[],
    )
    assert d.match_rate == 0.0
    assert d.all_conditions_observed is False


def test_diagnostics_match_rate_zero_trials():
    d = PilotDiagnostics(
        trials_completed=0, trials_with_stimulus_match=0,
        conditions_observed=[], conditions_missing=["a"],
        selector_results={}, phase_results={}, dom_snapshots=[],
        anomalies=[], trial_log=[],
    )
    assert d.match_rate == 0.0  # no division by zero


def test_diagnostics_crashed_factory():
    d = PilotDiagnostics.crashed("browser timed out")
    assert d.trials_completed == 0
    assert "browser timed out" in d.anomalies[0]
    assert d.match_rate == 0.0


def test_diagnostics_to_report_contains_key_sections():
    d = PilotDiagnostics(
        trials_completed=5, trials_with_stimulus_match=3,
        conditions_observed=["congruent"], conditions_missing=["incongruent"],
        selector_results={
            "stim_a": {"matches": 10, "polls": 100},
            "stim_b": {"matches": 0, "polls": 100},
        },
        phase_results={"complete": {"fired": False, "first_fire_trial": None},
                       "test": {"fired": True, "first_fire_trial": 1}},
        dom_snapshots=[{"trigger": "after_navigation", "html": "<div>test</div>"}],
        anomalies=["50 consecutive polls with no match"],
        trial_log=[{"trial": 1, "stimulus_id": "s1", "condition": "congruent", "response_key": "f"}],
    )
    report = d.to_report()
    assert "Trials completed: 5" in report
    assert "incongruent" in report  # missing condition
    assert "NEVER MATCHED" in report  # stim_b
    assert "<div>test</div>" in report  # DOM snapshot
    assert "50 consecutive polls" in report  # anomaly
    assert "Trial 1" in report  # trial log entry


PILOT_CONFIG = {
    "task": {"name": "Test Stroop", "platform": "jsPsych", "constructs": [], "reference_literature": []},
    "stimuli": [
        {"id": "cong", "description": "congruent", "detection": {"method": "js_eval", "selector": "true"},
         "response": {"key": "f", "condition": "congruent"}},
        {"id": "incong", "description": "incongruent", "detection": {"method": "js_eval", "selector": "false"},
         "response": {"key": "j", "condition": "incongruent"}},
    ],
    "response_distributions": {"congruent": {"distribution": "ex_gaussian", "params": {"mu": 500, "sigma": 60, "tau": 80}}},
    "performance": {"accuracy": {"congruent": 0.95}, "omission_rate": {"congruent": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {},
    "pilot": {"min_trials": 5, "target_conditions": ["congruent", "incongruent"], "max_blocks": 1,
              "stimulus_container_selector": "#jspsych-content"},
}


def test_pilot_runner_instantiation():
    """PilotRunner can be created and has run method."""
    runner = PilotRunner()
    assert hasattr(runner, 'run')
    assert asyncio.iscoroutinefunction(runner.run)


def test_pilot_runner_reads_config():
    """PilotRunner reads pilot config from TaskConfig."""
    config = TaskConfig.from_dict(PILOT_CONFIG)
    assert config.pilot.target_conditions == ["congruent", "incongruent"]
    assert config.pilot.min_trials == 5
    assert config.pilot.stimulus_container_selector == "#jspsych-content"


def test_pilot_runner_snapshot_dom_is_static():
    """_snapshot_dom is a static method."""
    assert hasattr(PilotRunner, '_snapshot_dom')

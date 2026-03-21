from experiment_bot.core.pilot import PilotDiagnostics


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

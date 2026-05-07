"""Tests for temporal effect dataclasses and TaskConfig wiring."""
import pytest
from experiment_bot.core.config import (
    TaskConfig,
    TimingConfig,
    PerformanceConfig,
    TemporalEffectsConfig,
    AutocorrelationConfig,
    FatigueDriftConfig,
    ConditionRepetitionConfig,
    PinkNoiseConfig,
    BetweenSubjectJitterConfig,
    PilotConfig,
)


# ---------------------------------------------------------------------------
# TemporalEffectsConfig tests
# ---------------------------------------------------------------------------


def test_temporal_effects_all_disabled_by_default():
    """All registered effects are disabled by default (no effects on tasks
    that don't configure them — see CLAUDE.md G3)."""
    cfg = TemporalEffectsConfig()
    assert cfg.autocorrelation.enabled is False
    assert cfg.fatigue_drift.enabled is False
    assert cfg.condition_repetition.enabled is False
    assert cfg.pink_noise.enabled is False
    assert cfg.lag1_pair_modulation.enabled is False
    assert cfg.post_event_slowing.enabled is False


def test_temporal_effects_from_dict_partial():
    """from_dict handles partial input — missing sub-configs get defaults."""
    d = {
        "autocorrelation": {"enabled": True, "phi": 0.3, "rationale": "AR1"},
    }
    cfg = TemporalEffectsConfig.from_dict(d)
    assert cfg.autocorrelation.enabled is True
    assert cfg.autocorrelation.phi == 0.3
    assert cfg.autocorrelation.rationale == "AR1"
    # Others are default (disabled)
    assert cfg.fatigue_drift.enabled is False
    assert cfg.pink_noise.enabled is False


def test_temporal_effects_round_trip():
    """to_dict -> from_dict preserves all values."""
    from types import SimpleNamespace
    cfg = TemporalEffectsConfig(
        autocorrelation=AutocorrelationConfig(enabled=True, phi=0.25, rationale="AR1"),
        fatigue_drift=FatigueDriftConfig(enabled=True, drift_per_trial_ms=0.15, rationale="drift"),
        condition_repetition=ConditionRepetitionConfig(
            enabled=True, facilitation_ms=8.0, cost_ms=8.0, rationale="cond-rep"
        ),
        pink_noise=PinkNoiseConfig(enabled=True, sd_ms=12.0, hurst=0.75, rationale="1/f"),
        # Generic mechanisms use SimpleNamespace cfg (no typed dataclass).
        lag1_pair_modulation=SimpleNamespace(
            enabled=True, skip_after_error=True,
            modulation_table=[
                {"prev": "incongruent", "curr": "incongruent", "delta_ms": -50.0},
            ],
            rationale="CSE-style",
        ),
        post_event_slowing=SimpleNamespace(
            enabled=True,
            triggers=[
                {"event": "interrupt", "slowing_ms_min": 80.0, "slowing_ms_max": 200.0},
                {"event": "error", "slowing_ms_min": 10.0, "slowing_ms_max": 50.0},
            ],
            rationale="interrupt + PES",
        ),
    )
    d = cfg.to_dict()
    restored = TemporalEffectsConfig.from_dict(d)
    assert restored.autocorrelation.enabled is True
    assert restored.autocorrelation.phi == 0.25
    assert restored.fatigue_drift.drift_per_trial_ms == 0.15
    assert restored.condition_repetition.facilitation_ms == 8.0
    assert restored.condition_repetition.cost_ms == 8.0
    assert restored.pink_noise.sd_ms == 12.0
    assert restored.pink_noise.hurst == 0.75
    # Generic mechanism configs round-trip as SimpleNamespace
    assert restored.lag1_pair_modulation.enabled is True
    assert restored.lag1_pair_modulation.modulation_table[0]["delta_ms"] == -50.0
    assert restored.post_event_slowing.enabled is True
    assert len(restored.post_event_slowing.triggers) == 2


# ---------------------------------------------------------------------------
# Migration of paradigm-named effects on TaskCard load
# (regression: existing TaskCards on disk use old names; the executor's
# _taskcard_to_config feeds the raw `value` dicts to
# TemporalEffectsConfig.from_dict — migration must happen there.)
# ---------------------------------------------------------------------------


def test_from_dict_migrates_congruency_sequence_to_lag1_pair_modulation():
    """Old TaskCard with `congruency_sequence` → executor sees a populated
    `lag1_pair_modulation` so CSE actually fires through the sampler."""
    raw = {
        "congruency_sequence": {
            "enabled": True,
            "high_conflict_condition": "incongruent",
            "low_conflict_condition": "congruent",
            "sequence_facilitation_ms": 25.0,
            "sequence_cost_ms": 18.0,
        }
    }
    cfg = TemporalEffectsConfig.from_dict(raw)
    assert cfg.lag1_pair_modulation.enabled is True
    table = cfg.lag1_pair_modulation.modulation_table
    assert {"prev": "incongruent", "curr": "incongruent",
            "delta_ms": -25.0} in table
    assert {"prev": "congruent", "curr": "incongruent",
            "delta_ms": 18.0} in table


def test_from_dict_migrates_post_error_and_post_interrupt_slowing():
    """Old TaskCard with both legacy slowing entries → unified
    post_event_slowing with interrupt-priority triggers list."""
    raw = {
        "post_error_slowing": {
            "enabled": True,
            "slowing_ms_min": 30.0,
            "slowing_ms_max": 60.0,
        },
        "post_interrupt_slowing": {
            "enabled": True,
            "slowing_ms_min": 80.0,
            "slowing_ms_max": 200.0,
        },
    }
    cfg = TemporalEffectsConfig.from_dict(raw)
    assert cfg.post_event_slowing.enabled is True
    triggers = cfg.post_event_slowing.triggers
    assert triggers[0]["event"] == "interrupt"  # priority order
    assert triggers[1]["event"] == "error"


def test_from_dict_migration_idempotent():
    """Running migration twice (e.g., reasoner already migrated, then
    from_dict re-migrates) doesn't duplicate effects."""
    raw = {
        "congruency_sequence": {
            "enabled": True,
            "high_conflict_condition": "incongruent",
            "low_conflict_condition": "congruent",
            "sequence_facilitation_ms": 25.0,
            "sequence_cost_ms": 18.0,
        }
    }
    cfg1 = TemporalEffectsConfig.from_dict(raw)
    # Round-trip and re-load.
    cfg2 = TemporalEffectsConfig.from_dict(cfg1.to_dict())
    assert cfg2.lag1_pair_modulation.enabled is True
    assert len(cfg2.lag1_pair_modulation.modulation_table) == 2


# ---------------------------------------------------------------------------
# BetweenSubjectJitterConfig tests
# ---------------------------------------------------------------------------


def test_between_subject_jitter_defaults_to_zero():
    """All 5 numeric fields default to 0.0; sigma_tau_range defaults to [1.0, 1.0]."""
    cfg = BetweenSubjectJitterConfig()
    assert cfg.rt_mean_sd_ms == 0.0
    assert cfg.rt_condition_sd_ms == 0.0
    assert cfg.sigma_tau_range == [1.0, 1.0]
    assert cfg.accuracy_sd == 0.0
    assert cfg.omission_sd == 0.0
    assert cfg.rationale == ""


def test_between_subject_jitter_from_dict():
    """from_dict parses all fields correctly."""
    d = {
        "rt_mean_sd_ms": 40.0,
        "rt_condition_sd_ms": 15.0,
        "sigma_tau_range": [0.85, 1.15],
        "accuracy_sd": 0.015,
        "omission_sd": 0.005,
        "rationale": "natural variability",
    }
    cfg = BetweenSubjectJitterConfig.from_dict(d)
    assert cfg.rt_mean_sd_ms == 40.0
    assert cfg.rt_condition_sd_ms == 15.0
    assert cfg.sigma_tau_range == [0.85, 1.15]
    assert cfg.accuracy_sd == 0.015
    assert cfg.omission_sd == 0.005
    assert cfg.rationale == "natural variability"


# ---------------------------------------------------------------------------
# TaskConfig integration tests
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_task_config_has_temporal_effects():
    """TaskConfig has temporal_effects field with default TemporalEffectsConfig."""
    config = TaskConfig.from_dict(MINIMAL_CONFIG)
    assert hasattr(config, "temporal_effects")
    assert isinstance(config.temporal_effects, TemporalEffectsConfig)
    assert config.temporal_effects.autocorrelation.enabled is False


def test_task_config_has_between_subject_jitter():
    """TaskConfig has between_subject_jitter field with default BetweenSubjectJitterConfig."""
    config = TaskConfig.from_dict(MINIMAL_CONFIG)
    assert hasattr(config, "between_subject_jitter")
    assert isinstance(config.between_subject_jitter, BetweenSubjectJitterConfig)
    assert config.between_subject_jitter.rt_mean_sd_ms == 0.0


def test_task_config_temporal_effects_from_dict():
    """TaskConfig.from_dict parses temporal_effects from nested dict."""
    d = dict(MINIMAL_CONFIG)
    d["temporal_effects"] = {
        "autocorrelation": {"enabled": True, "phi": 0.25, "rationale": ""},
        "pink_noise": {"enabled": True, "sd_ms": 12.0, "hurst": 0.75, "rationale": ""},
    }
    config = TaskConfig.from_dict(d)
    assert config.temporal_effects.autocorrelation.enabled is True
    assert config.temporal_effects.autocorrelation.phi == 0.25
    assert config.temporal_effects.pink_noise.enabled is True
    assert config.temporal_effects.pink_noise.sd_ms == 12.0


def test_task_config_round_trip_includes_temporal():
    """to_dict -> from_dict preserves temporal_effects and between_subject_jitter."""
    import json
    d = dict(MINIMAL_CONFIG)
    d["temporal_effects"] = {
        "autocorrelation": {"enabled": True, "phi": 0.3, "rationale": "test"},
    }
    d["between_subject_jitter"] = {
        "rt_mean_sd_ms": 40.0,
        "rt_condition_sd_ms": 15.0,
        "sigma_tau_range": [0.85, 1.15],
        "accuracy_sd": 0.015,
        "omission_sd": 0.005,
        "rationale": "test",
    }
    config = TaskConfig.from_dict(d)
    serialized = json.loads(json.dumps(config.to_dict()))
    config2 = TaskConfig.from_dict(serialized)
    assert config2.temporal_effects.autocorrelation.enabled is True
    assert config2.temporal_effects.autocorrelation.phi == 0.3
    assert config2.between_subject_jitter.rt_mean_sd_ms == 40.0
    assert config2.between_subject_jitter.sigma_tau_range == [0.85, 1.15]


# ---------------------------------------------------------------------------
# Task 2: Verify behavioral defaults are removed
# ---------------------------------------------------------------------------


def test_timing_config_no_behavioral_defaults():
    """TimingConfig does not have autocorrelation_phi or fatigue_drift_per_trial fields."""
    timing = TimingConfig()
    assert not hasattr(timing, "autocorrelation_phi"), (
        "autocorrelation_phi should have been removed from TimingConfig"
    )
    assert not hasattr(timing, "fatigue_drift_per_trial"), (
        "fatigue_drift_per_trial should have been removed from TimingConfig"
    )


def test_performance_config_no_hardcoded_fallback():
    """get_accuracy and get_omission_rate raise ValueError when dict is empty."""
    perf = PerformanceConfig(accuracy={}, omission_rate={})
    with pytest.raises(ValueError, match="No accuracy"):
        perf.get_accuracy("any")
    with pytest.raises(ValueError, match="No omission"):
        perf.get_omission_rate("any")


# ---------------------------------------------------------------------------
# PilotConfig tests
# ---------------------------------------------------------------------------


def test_pilot_config_defaults():
    pc = PilotConfig.from_dict({})
    assert pc.min_trials == 20
    assert pc.target_conditions == []
    assert pc.max_blocks == 3  # bumped from 1: covers practice+early test
    assert pc.stimulus_container_selector == ""


def test_pilot_config_from_dict():
    pc = PilotConfig.from_dict({
        "min_trials": 30,
        "target_conditions": ["congruent", "incongruent"],
        "max_blocks": 2,
        "stimulus_container_selector": "#jspsych-content",
        "rationale": "test",
    })
    assert pc.min_trials == 30
    assert pc.target_conditions == ["congruent", "incongruent"]
    assert pc.stimulus_container_selector == "#jspsych-content"


def test_pilot_config_round_trip():
    original = {"min_trials": 40, "target_conditions": ["go", "stop"],
                "max_blocks": 1, "stimulus_container_selector": "#content",
                "rationale": "need 40 trials for 25% stop ratio"}
    pc = PilotConfig.from_dict(original)
    d = pc.to_dict()
    assert d["min_trials"] == 40
    assert d["target_conditions"] == ["go", "stop"]


def test_task_config_has_pilot():
    config = TaskConfig.from_dict(MINIMAL_CONFIG)
    assert config.pilot.min_trials == 20
    assert config.pilot.target_conditions == []


def test_task_config_pilot_from_dict():
    d = dict(MINIMAL_CONFIG)
    d["pilot"] = {"min_trials": 30, "target_conditions": ["go"], "max_blocks": 1, "rationale": "test"}
    config = TaskConfig.from_dict(d)
    assert config.pilot.min_trials == 30


def test_task_config_round_trip_includes_pilot():
    d = dict(MINIMAL_CONFIG)
    d["pilot"] = {"min_trials": 25, "target_conditions": ["a", "b"], "max_blocks": 2, "rationale": "test"}
    config = TaskConfig.from_dict(d)
    out = config.to_dict()
    assert out["pilot"]["min_trials"] == 25
    assert out["pilot"]["target_conditions"] == ["a", "b"]

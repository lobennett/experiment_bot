"""SP11 Phase 5b — parameter-drift script unit tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


# Load the script as a module (it's a script, not a package member).
_SCRIPT = Path("scripts/check_parameter_drift.py")
spec = importlib.util.spec_from_file_location("check_parameter_drift", _SCRIPT)
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)


def test_relative_drift_basic():
    assert drift._relative_drift(100.0, 110.0) == pytest.approx(10.0)
    assert drift._relative_drift(100.0, 90.0) == pytest.approx(10.0)
    assert drift._relative_drift(100.0, 100.0) == pytest.approx(0.0)


def test_relative_drift_zero_baseline():
    assert drift._relative_drift(0.0, 0.0) == 0.0
    assert drift._relative_drift(0.0, 5.0) == float("inf")


def test_extract_distribution_params_ex_gaussian():
    tc = {
        "response_distributions": {
            "congruent": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 60, "tau": 80},
            },
            "incongruent": {
                "distribution": "ex_gaussian",
                "value": {"mu": 600, "sigma": 70, "tau": 90},
            },
        },
    }
    out = drift._extract_distribution_params(tc)
    assert out["congruent"] == {"mu": 500.0, "sigma": 60.0, "tau": 80.0}
    assert out["incongruent"] == {"mu": 600.0, "sigma": 70.0, "tau": 90.0}


def test_extract_temporal_effects_only_enabled():
    tc = {
        "temporal_effects": {
            "autocorrelation": {"enabled": True, "rho": 0.15, "cite": "x"},
            "fatigue_drift": {"enabled": False, "slope_ms_per_trial": 0.5},
            "lag1_pair_modulation": {"enabled": True, "switch_cost_ms": 25.0},
        },
    }
    out = drift._extract_temporal_effects(tc)
    assert out == {
        "autocorrelation": {"rho": 0.15},
        "lag1_pair_modulation": {"switch_cost_ms": 25.0},
    }
    # fatigue_drift disabled → not included
    assert "fatigue_drift" not in out


def test_extract_performance_flattens_blocks():
    tc = {
        "performance": {
            "accuracy": {"go": 0.95, "stop": 0.50},
            "omission_rate": {"go": 0.02},
        },
    }
    out = drift._extract_performance(tc)
    assert out == {
        "accuracy.go": 0.95,
        "accuracy.stop": 0.50,
        "omission_rate.go": 0.02,
    }


def test_compare_taskcards_flags_over_threshold():
    """A 15% drift on a parameter should be flagged at threshold=10."""
    baseline = {
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 60, "tau": 80},
            },
        },
        "temporal_effects": {},
        "performance": {"accuracy": {"default": 0.95}},
    }
    current = {
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 580, "sigma": 60, "tau": 80},  # +16%
            },
        },
        "temporal_effects": {},
        "performance": {"accuracy": {"default": 0.95}},
    }
    res = drift.compare_taskcards(baseline, current, threshold_pct=10.0)
    mu_row = next(r for r in res["response_distributions"] if r["field"] == "default.mu")
    assert mu_row["flagged"] is True
    assert mu_row["drift_pct"] == pytest.approx(16.0)
    # sigma unchanged → not flagged
    sigma_row = next(r for r in res["response_distributions"] if r["field"] == "default.sigma")
    assert sigma_row["flagged"] is False


def test_compare_taskcards_under_threshold_not_flagged():
    """A 5% drift at threshold=10 should NOT be flagged."""
    baseline = {
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 60, "tau": 80},
            },
        },
        "temporal_effects": {},
        "performance": {},
    }
    current = {
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 525, "sigma": 60, "tau": 80},  # +5%
            },
        },
        "temporal_effects": {},
        "performance": {},
    }
    res = drift.compare_taskcards(baseline, current, threshold_pct=10.0)
    mu_row = next(r for r in res["response_distributions"] if r["field"] == "default.mu")
    assert mu_row["flagged"] is False


def test_compare_taskcards_added_field_no_flag():
    """A field present in current but not baseline should be marked
    'added' without a drift % or flag."""
    baseline = {
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 60},
            },
        },
        "temporal_effects": {},
        "performance": {},
    }
    current = {
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 60, "tau": 80},  # tau added
            },
        },
        "temporal_effects": {},
        "performance": {},
    }
    res = drift.compare_taskcards(baseline, current, threshold_pct=10.0)
    tau_row = next(r for r in res["response_distributions"] if r["field"] == "default.tau")
    assert tau_row["flagged"] is False
    assert tau_row.get("note") == "added"


def test_render_report_includes_flagged_section():
    """Flagged drifts should produce a FLAGGED line and an ACTION footer."""
    paradigm_results = {
        "test_paradigm": {
            "response_distributions": [
                {
                    "field": "default.mu", "baseline": 500, "current": 580,
                    "drift_pct": 16.0, "flagged": True,
                },
            ],
            "temporal_effects": [],
            "performance": [],
        },
    }
    text = drift.render_report(
        paradigm_results, threshold_pct=10.0, baseline_tag="sp8-complete",
    )
    assert "**FLAGGED**" in text
    assert "16.00%" in text
    assert "Stroop variance study" in text  # variance-framing footer
    assert "**Total flagged across all paradigms:** 1" in text


def test_render_report_clean_when_no_flags():
    paradigm_results = {
        "p1": {
            "response_distributions": [
                {
                    "field": "default.mu", "baseline": 500, "current": 510,
                    "drift_pct": 2.0, "flagged": False,
                },
            ],
            "temporal_effects": [],
            "performance": [],
        },
    }
    text = drift.render_report(
        paradigm_results, threshold_pct=10.0, baseline_tag="sp8-complete",
    )
    assert "No flags > threshold" in text  # variance-framing footer
    assert "**Total flagged across all paradigms:** 0" in text

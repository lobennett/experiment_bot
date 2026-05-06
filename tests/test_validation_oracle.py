import json
import math
from pathlib import Path
import numpy as np
import pytest
from experiment_bot.validation.oracle import (
    validate_session_set, ValidationReport, MetricResult, PillarResult,
)


@pytest.fixture
def fake_norms_conflict():
    return {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580], "sigma_range": [40, 90], "tau_range": [50, 130],
                "citations": [],
            },
            "post_error_slowing": {"range_ms": [10, 60], "citations": []},
            "cse_magnitude": {"range_ms": [-55, -15], "citations": []},
        },
    }


def _fake_session_dir(tmp_path: Path, mu: float, sigma: float, tau: float, n_trials: int, seed: int):
    """Make a session directory with bot_log.json containing alternating-condition trials."""
    rng = np.random.default_rng(seed)
    session_dir = tmp_path / f"session_{seed}"
    session_dir.mkdir(parents=True, exist_ok=True)
    log = []
    for i in range(n_trials):
        rt = rng.normal(mu, sigma) + rng.exponential(tau)
        log.append({
            "trial": i, "stimulus_id": "x",
            "condition": "congruent" if i % 2 == 0 else "incongruent",
            "response_key": "z", "actual_rt_ms": float(rt),
            "intended_error": False, "omission": False,
        })
    (session_dir / "bot_log.json").write_text(json.dumps(log))
    return session_dir


def test_oracle_passes_when_bot_within_norms(tmp_path, fake_norms_conflict):
    """Bot with mu=500, sigma=60, tau=80 should pass conflict norms."""
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=s) for s in range(5)]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    assert isinstance(report, ValidationReport)
    rt_pillar = report.pillar_results["rt_distribution"]
    assert rt_pillar.pass_, f"RT distribution should pass: {rt_pillar.metrics}"


def test_oracle_fails_when_mu_out_of_range(tmp_path, fake_norms_conflict):
    """Bot with mu=300 (below the [430, 580] range) should fail."""
    sessions = [_fake_session_dir(tmp_path, 300, 60, 80, n_trials=200, seed=s) for s in range(5)]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    rt_pillar = report.pillar_results["rt_distribution"]
    assert not rt_pillar.pass_


def test_oracle_metric_with_null_range_is_descriptive_only(tmp_path):
    """Metric with range=None reports a value but doesn't gate."""
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=0)]
    norms = {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                  "tau_range": [50, 130], "citations": []},
            "between_subject_sd": {
                "mu_sd_range": None, "sigma_sd_range": None, "tau_sd_range": None,
                "no_canonical_range_reason": "no meta-analysis available",
                "citations": [],
            },
        },
    }
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=norms,
    )
    # Find the descriptive-only between_subject_sd metric in any pillar
    found = False
    for pillar in report.pillar_results.values():
        for mname, m in pillar.metrics.items():
            if "between_subject_sd" in mname or "_sd" in mname:
                if m.published_range is None:
                    assert m.pass_ is None  # descriptive-only
                    found = True
    assert found, "Expected at least one descriptive-only between_subject_sd metric"


def test_oracle_empty_session_set_does_not_crash(tmp_path, fake_norms_conflict):
    """Calling validate_session_set with no session dirs should not crash."""
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=[],
        norms=fake_norms_conflict,
    )
    # All metrics should report bot_value=None or NaN; pillars shouldn't pass
    assert report.overall_pass is False or all(
        not p.pass_ for p in report.pillar_results.values() if p.pass_ is not None
    )


def _fake_session_dir_with_labels(
    tmp_path: Path, mu: float, sigma: float, tau: float, n_trials: int, seed: int,
    high_label: str, low_label: str,
):
    """Like _fake_session_dir but uses caller-provided condition labels."""
    rng = np.random.default_rng(seed)
    session_dir = tmp_path / f"session_{high_label}_{seed}"
    session_dir.mkdir(parents=True, exist_ok=True)
    log = []
    for i in range(n_trials):
        rt = rng.normal(mu, sigma) + rng.exponential(tau)
        # Pattern: low, high, high, low, high, high, ... → produces high-after-low and high-after-high pairs
        cond = high_label if i % 3 != 0 else low_label
        log.append({
            "trial": i, "stimulus_id": "x",
            "condition": cond, "response_key": "z",
            "actual_rt_ms": float(rt),
            "intended_error": False, "omission": False,
        })
    (session_dir / "bot_log.json").write_text(json.dumps(log))
    return session_dir


def test_oracle_uses_taskcard_cse_labels(tmp_path, fake_norms_conflict):
    """Oracle reads CSE condition labels from cse_labels arg, not magic strings.

    Bot logs use 'compatible'/'incompatible' (Eriksen-style) instead of
    'congruent'/'incongruent'. Without cse_labels passed in, the metric
    would compute NaN (no trials match the default 'incongruent'/'congruent').
    With cse_labels=("incompatible", "compatible"), it computes a real value.
    """
    sessions = [
        _fake_session_dir_with_labels(
            tmp_path, 500, 60, 80, n_trials=200, seed=s,
            high_label="incompatible", low_label="compatible",
        )
        for s in range(3)
    ]
    # Without cse_labels: should report NaN (no incongruent/congruent trials)
    report_default = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    seq = report_default.pillar_results["sequential"].metrics
    assert "cse_magnitude" in seq
    assert seq["cse_magnitude"].bot_value is None  # NaN → None

    # With cse_labels: should compute a real value
    report_custom = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
        cse_labels=("incompatible", "compatible"),
    )
    seq_custom = report_custom.pillar_results["sequential"].metrics
    assert seq_custom["cse_magnitude"].bot_value is not None  # finite value

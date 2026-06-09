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


# ---------------------------------------------------------------------------
# Data-driven oracle (audit findings M5/M6) — pillars and metrics from norms file
# ---------------------------------------------------------------------------

def test_oracle_unknown_metric_is_logged_not_crashed(tmp_path, fake_norms_conflict, caplog):
    """A metric in the norms file with no registered MetricSpec should be
    logged as a warning, not crash the oracle."""
    norms = dict(fake_norms_conflict)
    norms["metrics"] = dict(norms["metrics"])
    norms["metrics"]["my_brand_new_metric"] = {"range_ms": [10, 20], "citations": []}
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=s) for s in range(2)]
    with caplog.at_level("WARNING"):
        report = validate_session_set(
            paradigm_class="conflict",
            session_dirs=sessions,
            norms=norms,
        )
    # Existing metrics still validate
    assert "rt_distribution" in report.pillar_results
    # Warning surfaced
    assert any("my_brand_new_metric" in rec.message for rec in caplog.records)


def test_oracle_supports_arbitrary_pillar_name():
    """Registering a metric under a novel pillar name should produce a pillar
    of that name in the report (no hardcoded pillar list)."""
    from experiment_bot.validation.oracle import (
        METRIC_REGISTRY, MetricSpec, validate_session_set,
    )
    # Register a fake metric under a novel pillar; remove after the test
    METRIC_REGISTRY["dummy_speed_accuracy"] = MetricSpec(
        pillar="speed_accuracy_tradeoff",
        compute=lambda session_dirs, ctx: 0.42,
        range_key="range",
    )
    try:
        norms = {
            "paradigm_class": "novel_class",
            "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
            "metrics": {"dummy_speed_accuracy": {"range": [0.4, 0.5], "citations": []}},
        }
        report = validate_session_set(
            paradigm_class="novel_class",
            session_dirs=[],
            norms=norms,
        )
        assert "speed_accuracy_tradeoff" in report.pillar_results
        pillar = report.pillar_results["speed_accuracy_tradeoff"]
        assert "dummy_speed_accuracy" in pillar.metrics
        assert pillar.metrics["dummy_speed_accuracy"].bot_value == 0.42
        assert pillar.metrics["dummy_speed_accuracy"].pass_ is True  # 0.42 in [0.4, 0.5]
    finally:
        METRIC_REGISTRY.pop("dummy_speed_accuracy", None)


def test_oracle_pillars_dict_omits_unused_pillars(tmp_path):
    """If a norms file only declares rt_distribution metrics, the oracle
    shouldn't include sequential or individual_differences pillars."""
    norms_minimal = {
        "paradigm_class": "minimal",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580], "sigma_range": [40, 90], "tau_range": [50, 130],
                "citations": [],
            },
        },
    }
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=s) for s in range(2)]
    report = validate_session_set(
        paradigm_class="minimal",
        session_dirs=sessions,
        norms=norms_minimal,
    )
    # Only rt_distribution pillar should be present
    assert set(report.pillar_results.keys()) == {"rt_distribution"}


def test_oracle_uses_taskcard_contrast_labels(tmp_path, fake_norms_conflict):
    """Oracle reads contrast labels from contrast_labels arg; without them
    the CSE metric returns NaN (no paradigm-specific defaults).

    Bot logs use 'compatible'/'incompatible'. Without labels the metric
    has nothing to anchor to; with labels it computes a real value.
    """
    sessions = [
        _fake_session_dir_with_labels(
            tmp_path, 500, 60, 80, n_trials=200, seed=s,
            high_label="incompatible", low_label="compatible",
        )
        for s in range(3)
    ]
    # Without contrast_labels: should report NaN (oracle does not assume
    # any specific condition vocabulary)
    report_default = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    seq = report_default.pillar_results["sequential"].metrics
    assert "cse_magnitude" in seq
    assert seq["cse_magnitude"].bot_value is None  # NaN → None

    # With contrast_labels: should compute a real value
    report_custom = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
        contrast_labels=("incompatible", "compatible"),
    )
    seq_custom = report_custom.pillar_results["sequential"].metrics
    assert seq_custom["cse_magnitude"].bot_value is not None  # finite value


# ---------------------------------------------------------------------------
# SSRT dispatch — analysis-side wiring of the integration-method estimate
# ---------------------------------------------------------------------------

def _fake_stop_signal_session(tmp_path: Path, mu_go: float, sigma_go: float,
                               n_go: int, n_stop: int, p_respond: float,
                               mean_ssd: float, seed: int) -> Path:
    """Write a session whose trial loader exposes go/stop trials with SSD."""
    rng = np.random.default_rng(seed)
    session_dir = tmp_path / f"session_ss_{seed}"
    session_dir.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []
    for i in range(n_go):
        rt = float(rng.normal(mu_go, sigma_go))
        log.append({"trial": i, "stimulus_id": "go", "condition": "go",
                    "response_key": "z", "actual_rt_ms": rt,
                    "intended_error": False, "omission": False})
    for j in range(n_stop):
        ssd = float(rng.normal(mean_ssd, 5.0))
        responded = rng.random() < p_respond
        rt = float(rng.normal(mu_go - 30, sigma_go)) if responded else None
        log.append({"trial": n_go + j, "stimulus_id": "stop", "condition": "stop",
                    "response_key": "z" if responded else None,
                    "actual_rt_ms": rt, "intended_error": False,
                    "omission": not responded, "ssd": ssd})
    (session_dir / "bot_log.json").write_text(json.dumps(log))
    return session_dir


def _ssd_aware_loader(session_dir: Path) -> list[dict]:
    """Test loader that surfaces ssd alongside the canonical fields."""
    log = json.loads((session_dir / "bot_log.json").read_text())
    out = []
    for t in log:
        out.append({
            "condition": t.get("condition"),
            "rt": t.get("actual_rt_ms"),
            "correct": True,
            "omission": t.get("omission", False),
            "ssd": t.get("ssd"),
        })
    return out


def test_oracle_computes_ssrt_when_norms_declare_it(tmp_path):
    """A norms file declaring `ssrt` should drive _compute_ssrt and produce
    a finite value when the loader surfaces go-RTs and SSD-tagged stop
    trials."""
    norms = {
        "paradigm_class": "interrupt",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {"ssrt": {"range_ms": [180, 280], "citations": []}},
    }
    sessions = [
        _fake_stop_signal_session(
            tmp_path, mu_go=550, sigma_go=80, n_go=80, n_stop=40,
            p_respond=0.5, mean_ssd=300, seed=s,
        )
        for s in range(3)
    ]
    report = validate_session_set(
        paradigm_class="interrupt",
        session_dirs=sessions,
        norms=norms,
        trial_loader=_ssd_aware_loader,
    )
    assert "signature_metric" in report.pillar_results
    sig = report.pillar_results["signature_metric"].metrics
    assert "ssrt" in sig
    # Finite value (not NaN); rough range — Verbruggen's method on
    # mu_go=550, p_respond=0.5, mean_ssd=300 should give roughly mu_go - mean_ssd ≈ 250ms.
    assert sig["ssrt"].bot_value is not None
    assert 100 < sig["ssrt"].bot_value < 400


def test_oracle_ssrt_returns_nan_without_ssd_or_stop_trials(tmp_path):
    """SSRT computation has no paradigm defaults: missing data → NaN, not
    silent fallback."""
    # Loader returns trials with no stop trials (all go)
    def go_only_loader(session_dir):
        return [{"condition": "go", "rt": 500.0, "correct": True,
                 "omission": False, "ssd": None}] * 50

    norms = {
        "paradigm_class": "interrupt",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {"ssrt": {"range_ms": [180, 280], "citations": []}},
    }
    session_dir = tmp_path / "session_no_stop"
    session_dir.mkdir()
    report = validate_session_set(
        paradigm_class="interrupt",
        session_dirs=[session_dir],
        norms=norms,
        trial_loader=go_only_loader,
    )
    assert report.pillar_results["signature_metric"].metrics["ssrt"].bot_value is None


# ---------------------------------------------------------------------------
# SSRT validity-bound abstention (Verbruggen et al. 2019, eLife 10.7554/eLife.46323)
# ---------------------------------------------------------------------------

def _ssrt_trials(n_go, n_stop, n_stop_responded, ssd=300.0, go_rt=500.0):
    """Build a flat trial list: n_go go trials + n_stop stop trials, of which
    n_stop_responded are responded (omission=False) and the rest omitted."""
    trials = [
        {"condition": "go", "rt": go_rt, "correct": True, "omission": False, "ssd": None}
        for _ in range(n_go)
    ]
    for i in range(n_stop):
        responded = i < n_stop_responded
        trials.append({
            "condition": "stop",
            "rt": go_rt if responded else None,
            "correct": not responded,
            "omission": not responded,
            "ssd": ssd,
        })
    return trials


def test_compute_ssrt_abstains_below_min_stop_trials(caplog):
    from experiment_bot.validation.oracle import _compute_ssrt, SSRT_MIN_STOP_TRIALS
    # 40 stop trials (< 50), p_respond = 0.5 (in range) — abstain on count.
    trials = _ssrt_trials(n_go=100, n_stop=40, n_stop_responded=20)
    ctx = {"trial_loader": lambda s: trials}
    with caplog.at_level("WARNING"):
        val = _compute_ssrt([Path("dummy")], ctx)
    assert math.isnan(val)
    assert any("stop_total" in r.message and "40" in r.message for r in caplog.records)
    assert SSRT_MIN_STOP_TRIALS == 50


def test_compute_ssrt_abstains_when_prespond_out_of_range(caplog):
    from experiment_bot.validation.oracle import _compute_ssrt
    # 60 stop trials (>= 50) but p_respond = 0.9 (> 0.75) — abstain on p_respond.
    trials = _ssrt_trials(n_go=100, n_stop=60, n_stop_responded=54)
    ctx = {"trial_loader": lambda s: trials}
    with caplog.at_level("WARNING"):
        val = _compute_ssrt([Path("dummy")], ctx)
    assert math.isnan(val)
    assert any("p_respond" in r.message for r in caplog.records)


def test_compute_ssrt_finite_for_valid_data():
    from experiment_bot.validation.oracle import _compute_ssrt
    # 80 stop trials (>= 50), p_respond = 0.5 (in [0.25, 0.75]) — valid.
    trials = _ssrt_trials(n_go=100, n_stop=80, n_stop_responded=40, ssd=250.0, go_rt=500.0)
    ctx = {"trial_loader": lambda s: trials}
    val = _compute_ssrt([Path("dummy")], ctx)
    assert not math.isnan(val)
    assert math.isfinite(val)
    # mu_go quantile at 0.5 (~500) minus mean_ssd (250) ≈ 250ms.
    assert 100 < val < 400


# ---------------------------------------------------------------------------
# Task 5: completeness exclusion, tri-state overall_pass, bot_log guard
# ---------------------------------------------------------------------------

def _fake_session_with_metadata(
    tmp_path: Path, mu: float, sigma: float, tau: float, n_trials: int, seed: int,
    incomplete: bool = False, loop_exit_reason: str = "complete",
) -> Path:
    """Like _fake_session_dir but also writes run_metadata.json."""
    import numpy as np
    rng = np.random.default_rng(seed)
    session_dir = tmp_path / f"session_meta_{seed}"
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
    metadata = {
        "incomplete": incomplete,
        "loop_exit_reason": loop_exit_reason,
        "total_trials": n_trials,
    }
    (session_dir / "run_metadata.json").write_text(json.dumps(metadata))
    return session_dir


def test_oracle_excludes_gross_undercount_outlier(tmp_path, fake_norms_conflict):
    """A session whose trial count is a gross outlier below the cohort median is
    excluded from aggregation and recorded; n_used < n_supplied. (This is the
    real bug the audit cited: a 50-vs-200 partial session.)"""
    full = [
        _fake_session_with_metadata(tmp_path, 500, 60, 80, n_trials=200, seed=s)
        for s in range(3)
    ]
    partial = _fake_session_with_metadata(
        tmp_path, 500, 60, 80, n_trials=50, seed=9, incomplete=True,
        loop_exit_reason="max_misses",
    )
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=full + [partial],
        norms=fake_norms_conflict,
    )
    assert report.n_supplied == 4
    assert report.n_used == 3
    assert len(report.excluded_sessions) == 1
    excluded = report.excluded_sessions[0]
    assert excluded["session"] == partial.name
    assert excluded["trials"] == 50
    assert "gross_undercount" in excluded["reason"]


def test_oracle_does_not_exclude_complete_session_that_exited_via_max_misses(
    tmp_path, fake_norms_conflict
):
    """REGRESSION (smoke-found): a whole session that exits via max_misses
    because the COMPLETE predicate never fired (incomplete=True) but captured a
    cohort-typical trial count must NOT be excluded. Exit reason is diagnostic,
    not the exclusion trigger."""
    sessions = [
        _fake_session_with_metadata(
            tmp_path, 500, 60, 80, n_trials=125, seed=s,
            incomplete=True, loop_exit_reason="max_misses",
        )
        for s in range(3)
    ]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    # None excluded — all at the cohort median despite max_misses exits.
    assert report.n_used == 3
    assert report.n_supplied == 3
    assert report.excluded_sessions == []
    # But the uniform-incomplete diagnostic is surfaced for manual review.
    assert report.all_sessions_incomplete is True


def test_oracle_all_zero_trials_gives_false(tmp_path, fake_norms_conflict):
    """A cohort with no usable (nonzero-trial) sessions hard-fails."""
    sessions = [
        _fake_session_with_metadata(
            tmp_path, 500, 60, 80, n_trials=0, seed=i, incomplete=True,
            loop_exit_reason="window_closed",
        )
        for i in range(3)
    ]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    assert report.overall_pass is False
    assert report.n_used == 0
    assert report.n_supplied == 3


def test_oracle_tri_state_none_for_all_descriptive_with_data(tmp_path):
    """All-null-range norms + data present → overall_pass is None (not False).
    Preserves G4: zero-data must still return False."""
    norms_descriptive = {
        "paradigm_class": "working_memory",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": None, "sigma_range": None, "tau_range": None,
                "citations": [],
            },
            "lag1_autocorr": {"range": None, "citations": []},
        },
    }
    # Data present: should be None (unscored), NOT False
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=0)]
    report = validate_session_set(
        paradigm_class="working_memory",
        session_dirs=sessions,
        norms=norms_descriptive,
    )
    assert report.overall_pass is None, (
        f"Expected None for all-descriptive with data, got {report.overall_pass!r}"
    )


def test_oracle_tri_state_false_for_zero_data(tmp_path):
    """Zero-trial sessions → overall_pass is False (G4 broken-state signal).
    NOT None — None is only for 'gates don't exist but data does'."""
    norms_descriptive = {
        "paradigm_class": "working_memory",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": None, "sigma_range": None, "tau_range": None,
                "citations": [],
            },
        },
    }
    empty_session = tmp_path / "empty"
    empty_session.mkdir()
    (empty_session / "bot_log.json").write_text("[]")
    report = validate_session_set(
        paradigm_class="working_memory",
        session_dirs=[empty_session],
        norms=norms_descriptive,
    )
    assert report.overall_pass is False, (
        f"Expected False for zero-data (broken state), got {report.overall_pass!r}"
    )


def test_oracle_bot_log_guard_pes_none_other_metrics_gate(tmp_path):
    """With trial_source='bot_log', post_error_slowing pass_ must be None;
    correctness-free metrics (rt_distribution, lag1_autocorr) still gate normally."""
    norms = {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580], "sigma_range": [40, 90],
                "tau_range": [50, 130], "citations": [],
            },
            "lag1_autocorr": {"range": [-0.1, 0.3], "citations": []},
            "post_error_slowing": {"range_ms": [10, 60], "citations": []},
        },
    }
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=s) for s in range(3)]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=norms,
        trial_source="bot_log",
    )
    # post_error_slowing must be None (correctness-dependent)
    pes = report.pillar_results["sequential"].metrics["post_error_slowing"]
    assert pes.pass_ is None, f"Expected pass_=None for PES on bot_log, got {pes.pass_!r}"

    # rt_distribution should still gate (pass_ is bool)
    rt_pillar = report.pillar_results["rt_distribution"]
    for sub in ["mu", "sigma", "tau"]:
        m = rt_pillar.metrics[sub]
        assert m.pass_ is not None, f"Expected rt_distribution.{sub} to gate; got None"

    # lag1_autocorr should still gate
    lag = report.pillar_results["sequential"].metrics["lag1_autocorr"]
    assert lag.pass_ is not None, f"Expected lag1_autocorr to gate; got None"

    # data_source should be recorded
    assert report.data_source == "bot_log"


def test_oracle_report_has_data_source_field(tmp_path, fake_norms_conflict):
    """ValidationReport.data_source defaults to 'platform_adapter'."""
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=0)]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    assert report.data_source == "platform_adapter"

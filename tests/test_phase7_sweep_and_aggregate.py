"""SP11 Phase 7 — sweep wrapper + aggregator tests.

Covers (no live LLM):
- Sweep wrapper retry / failure-log logic
- Bot_no_match threshold discard
- evaluate_session_quality on synthetic session dirs
- Aggregator's paired_rate × within_pair × effective_fidelity computation
- §6 H1 / H2 thresholds in the markdown render
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_script(name: str, path: Path):
    """Load a script module and register it in sys.modules so
    @dataclass and other class-machinery work."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sweep = _load_script("phase7_sweep", Path("scripts/phase7_sweep.py"))
agg = _load_script("phase7_aggregate", Path("scripts/phase7_aggregate.py"))


# -----------------------------------------------------------------
# evaluate_session_quality
# -----------------------------------------------------------------


def _write_synthetic_session(
    tmp_dir: Path,
    bot_trials: list[dict],
    plat_rows: list[dict],
    *,
    use_csv: bool = False,
) -> Path:
    """Materialize a synthetic session dir with bot_log + platform data."""
    sd = tmp_dir
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "bot_log.json").write_text(json.dumps(bot_trials))
    if use_csv:
        if plat_rows:
            with (sd / "experiment_data.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(plat_rows[0].keys()))
                w.writeheader()
                w.writerows(plat_rows)
        else:
            (sd / "experiment_data.csv").write_text("")
    else:
        (sd / "experiment_data.json").write_text(json.dumps(plat_rows))
    return sd


def _bot_trial(marker: int, key: str, channel: str = "cdp_dispatchKeyEvent") -> dict:
    return {
        "trial": marker,
        "condition": "congruent",
        "response_key": key,
        "stimulus_id": "stim",
        "delivery": {
            "trial_marker_at_fire": marker,
            "channel": channel,
            "skipped": False,
            "skip_reason": None,
        },
    }


def _plat_test_trial(idx, response):
    return {
        "trial_index": idx,
        "trial_id": "test_trial",
        "response": response,
        "correct_response": response,
        "rt": "300",
        "condition": "congruent",
    }


def test_evaluate_session_quality_passes_clean_session(tmp_path):
    sd = _write_synthetic_session(
        tmp_path / "ok",
        bot_trials=[_bot_trial(10, ","), _bot_trial(11, ".")],
        plat_rows=[_plat_test_trial(10, ","), _plat_test_trial(11, ".")],
    )
    passed, info = sweep.evaluate_session_quality(sd, "expfactory_stroop")
    assert passed is True
    assert info["bot_no_match"] == 0
    assert info["bot_no_match_pct"] == 0.0


def test_evaluate_session_quality_flags_excess_bot_no_match(tmp_path):
    """If > 10% of bot fires land on trial_indices the platform didn't
    record, the session is discarded (Phase 7 user note 1)."""
    bot = [_bot_trial(10, ","), _bot_trial(99, ".")]  # marker 99 doesn't exist
    plat = [_plat_test_trial(10, ",")]
    sd = _write_synthetic_session(
        tmp_path / "fail", bot_trials=bot, plat_rows=plat,
    )
    passed, info = sweep.evaluate_session_quality(
        sd, "expfactory_stroop", bot_no_match_threshold_pct=10.0,
    )
    assert passed is False
    assert info["bot_no_match_pct"] == 50.0
    assert info["reason"] == "bot_no_match_threshold_exceeded"


def test_evaluate_session_quality_no_bot_log(tmp_path):
    sd = tmp_path / "missing"
    sd.mkdir()
    (sd / "experiment_data.json").write_text("[]")
    passed, info = sweep.evaluate_session_quality(sd, "expfactory_stroop")
    assert passed is False
    assert info["reason"] == "no_bot_log"


def test_evaluate_session_quality_handles_csv_platform(tmp_path):
    """Same logic should work on CSV platform data (string trial_index)."""
    bot = [_bot_trial(6, ","), _bot_trial(10, ".")]
    plat = [_plat_test_trial("6", ","), _plat_test_trial("10", ".")]
    sd = _write_synthetic_session(
        tmp_path / "csv", bot_trials=bot, plat_rows=plat, use_csv=True,
    )
    passed, info = sweep.evaluate_session_quality(sd, "expfactory_stroop")
    assert passed is True
    assert info["bot_no_match"] == 0


def test_evaluate_session_quality_handles_unknown_paradigm(tmp_path):
    sd = _write_synthetic_session(
        tmp_path / "u", bot_trials=[_bot_trial(1, ",")],
        plat_rows=[_plat_test_trial(1, ",")],
    )
    passed, info = sweep.evaluate_session_quality(sd, "made_up_paradigm")
    assert passed is False
    assert "no_predicate" in info["reason"]


# -----------------------------------------------------------------
# Failure log persistence
# -----------------------------------------------------------------


def test_append_failure_log_only_non_ok(tmp_path):
    """session_failures.json captures ONLY non-ok attempts."""
    attempts = [
        sweep.SessionAttempt(
            paradigm="expfactory_stroop", arm="post_cal", attempt=1,
            status="ok",
        ),
        sweep.SessionAttempt(
            paradigm="expfactory_stroop", arm="post_cal", attempt=2,
            status="executor_error", error_message="boom",
        ),
    ]
    sweep.append_failure_log(tmp_path, attempts)
    log = json.loads((tmp_path / "session_failures.json").read_text())
    assert len(log) == 1
    assert log[0]["status"] == "executor_error"


# -----------------------------------------------------------------
# Aggregator — paired_rate × within_pair_match
# -----------------------------------------------------------------


def test_aggregator_computes_effective_fidelity_correctly(tmp_path):
    """118/120 paired (98.3%) × 118/118 within-pair (100%) = 98.3%
    effective fidelity — the Phase 5a anchor."""
    audit = agg._load_audit_module()
    # Build a synthetic session with 120 total_bot_trials, 118 paired,
    # all 118 pressed_eq_recorded. Mimic the executor's output shape.
    arm_dir = tmp_path / "post_cal"
    sess = arm_dir / "expfactory_stroop" / "stroop_rdoc" / "ts"
    sess.mkdir(parents=True)
    bot: list[dict] = []
    plat: list[dict] = []
    # 118 paired + recorded
    for i in range(118):
        bot.append(_bot_trial(i, ","))
        plat.append(_plat_test_trial(i, ","))
    # 2 bot fires whose marker the platform never records
    for i in range(2):
        bot.append(_bot_trial(1000 + i, "."))
    # 2 extra platform rows (just to make total_plat_test=120)
    plat.append(_plat_test_trial(500, ","))
    plat.append(_plat_test_trial(501, ","))
    (sess / "bot_log.json").write_text(json.dumps(bot))
    (sess / "experiment_data.json").write_text(json.dumps(plat))

    result = agg.aggregate_arm(arm_dir, "expfactory_stroop", audit)
    assert result["n_sessions"] == 1
    s = result["summary"]
    # paired_rate = 118 / 120 bot_trials = 0.9833
    assert abs(s["paired_rate_mean"] - 118 / 120) < 1e-6
    # within_pair = 118 / 118 = 1.0
    assert abs(s["within_pair_rate_mean"] - 1.0) < 1e-6
    # effective = 0.9833 × 1.0 = 0.9833
    assert abs(s["effective_fidelity_mean"] - 118 / 120) < 1e-6


def test_aggregator_handles_within_pair_misrecording(tmp_path):
    """If platform records a different key for some paired fires,
    paired_rate stays high but within_pair_rate drops."""
    audit = agg._load_audit_module()
    arm_dir = tmp_path / "post_cal"
    sess = arm_dir / "expfactory_stroop" / "stroop_rdoc" / "ts"
    sess.mkdir(parents=True)
    bot = [_bot_trial(i, ",") for i in range(10)]
    plat = []
    for i in range(8):
        plat.append(_plat_test_trial(i, ","))  # correctly recorded
    for i in (8, 9):
        plat.append(_plat_test_trial(i, "."))  # mis-recorded
    (sess / "bot_log.json").write_text(json.dumps(bot))
    (sess / "experiment_data.json").write_text(json.dumps(plat))
    result = agg.aggregate_arm(arm_dir, "expfactory_stroop", audit)
    s = result["summary"]
    assert abs(s["paired_rate_mean"] - 1.0) < 1e-6
    assert abs(s["within_pair_rate_mean"] - 0.8) < 1e-6
    assert abs(s["effective_fidelity_mean"] - 0.8) < 1e-6


def test_aggregator_returns_zero_when_no_sessions(tmp_path):
    arm_dir = tmp_path / "post_cal"
    arm_dir.mkdir()
    audit = agg._load_audit_module()
    result = agg.aggregate_arm(arm_dir, "expfactory_stroop", audit)
    assert result["n_sessions"] == 0


def test_render_markdown_h1_pass_h2_pass(tmp_path):
    """Both gates pass when paired_rate and within_pair are high."""
    aggregates = {
        ("expfactory_stroop", "post_cal"): {
            "n_sessions": 30,
            "summary": {
                "paired_rate_mean": 0.99,
                "within_pair_rate_mean": 0.99,
                "effective_fidelity_mean": 0.98,
                "paired_rate_min": 0.95,
                "within_pair_rate_min": 0.96,
            },
        },
    }
    md = agg.render_markdown(
        tmp_path, aggregates, h1_threshold=0.85, h2_threshold=0.75,
    )
    assert "H1 (≥0.85)" in md
    assert "H2 floor (≥0.75)" in md
    # Effective fidelity 0.98 ≥ 0.85, min 0.95×0.96 = 0.912 ≥ 0.75
    assert "✓ (0.980)" in md
    assert "✓ (0.912)" in md


def test_render_markdown_h1_fail(tmp_path):
    aggregates = {
        ("expfactory_stop_signal", "pre_cal"): {
            "n_sessions": 30,
            "summary": {
                "paired_rate_mean": 0.95,
                "within_pair_rate_mean": 0.80,
                "effective_fidelity_mean": 0.76,
                "paired_rate_min": 0.50,
                "within_pair_rate_min": 0.40,
            },
        },
    }
    md = agg.render_markdown(
        tmp_path, aggregates, h1_threshold=0.85, h2_threshold=0.75,
    )
    # 0.76 < 0.85 → H1 fails
    assert "✗ (0.760)" in md
    # 0.50 × 0.40 = 0.20 < 0.75 → H2 fails
    assert "✗ (0.200)" in md

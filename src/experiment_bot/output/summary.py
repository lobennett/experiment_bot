"""Generate summary statistics from a bot run's trial log."""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def summarize_run(run_dir: Path) -> dict:
    """Compute summary statistics from bot_log.json and save to run directory."""
    log_path = run_dir / "bot_log.json"
    if not log_path.exists():
        logger.warning(f"No bot_log.json found in {run_dir}")
        return {}

    trials = json.loads(log_path.read_text())
    if not trials:
        return {}

    conditions = Counter(t["condition"] for t in trials)

    # Gather RTs by condition category
    go_rts = [
        t["sampled_rt_ms"]
        for t in trials
        if t["sampled_rt_ms"] is not None and t["condition"].startswith("go")
    ]
    stop_fail_rts = [
        t["sampled_rt_ms"]
        for t in trials
        if t["sampled_rt_ms"] is not None and t["condition"] == "stop_failure"
    ]
    all_rts = [t["sampled_rt_ms"] for t in trials if t["sampled_rt_ms"] is not None]

    stop_success = conditions.get("stop_success", 0)
    stop_failure = conditions.get("stop_failure", 0)
    total_stop = stop_success + stop_failure
    omissions = sum(1 for t in trials if t.get("omission"))

    summary: dict = {
        "total_trials": len(trials),
        "conditions": dict(conditions),
        "omissions": omissions,
        "omission_rate": round(omissions / len(trials), 4) if trials else 0,
    }

    if go_rts:
        summary["go_rt"] = {
            "n": len(go_rts),
            "mean": round(float(np.mean(go_rts)), 1),
            "median": round(float(np.median(go_rts)), 1),
            "sd": round(float(np.std(go_rts)), 1),
            "p25": round(float(np.percentile(go_rts, 25)), 1),
            "p75": round(float(np.percentile(go_rts, 75)), 1),
        }

    if stop_fail_rts:
        summary["stop_failure_rt"] = {
            "n": len(stop_fail_rts),
            "mean": round(float(np.mean(stop_fail_rts)), 1),
            "median": round(float(np.median(stop_fail_rts)), 1),
            "sd": round(float(np.std(stop_fail_rts)), 1),
            "p25": round(float(np.percentile(stop_fail_rts, 25)), 1),
            "p75": round(float(np.percentile(stop_fail_rts, 75)), 1),
        }

    if total_stop > 0:
        summary["stop_signal"] = {
            "total_stop_trials": total_stop,
            "stop_success": stop_success,
            "stop_failure": stop_failure,
            "stop_accuracy": round(stop_success / total_stop, 4),
        }

    # Race model validation (stop signal tasks only)
    if go_rts and stop_fail_rts:
        go_mean = float(np.mean(go_rts))
        sf_mean = float(np.mean(stop_fail_rts))
        summary["race_model_validation"] = {
            "go_mean_rt": round(go_mean, 1),
            "stop_failure_mean_rt": round(sf_mean, 1),
            "difference_ms": round(go_mean - sf_mean, 1),
            "pass": go_mean > sf_mean,
            "note": "Independent race model predicts stop_failure RT < go RT",
        }

    # Switch cost analysis (task switching tasks)
    switch_rts = [
        t["sampled_rt_ms"]
        for t in trials
        if t["sampled_rt_ms"] is not None and "switch" in t["condition"]
    ]
    repeat_rts = [
        t["sampled_rt_ms"]
        for t in trials
        if t["sampled_rt_ms"] is not None and "repeat" in t["condition"]
    ]
    if switch_rts and repeat_rts:
        sw_mean = float(np.mean(switch_rts))
        rp_mean = float(np.mean(repeat_rts))
        summary["switch_cost"] = {
            "switch_mean_rt": round(sw_mean, 1),
            "repeat_mean_rt": round(rp_mean, 1),
            "switch_cost_ms": round(sw_mean - rp_mean, 1),
            "note": "Positive switch cost expected (~50-150ms)",
        }

    # Overall RT
    if all_rts:
        summary["overall_rt"] = {
            "n": len(all_rts),
            "mean": round(float(np.mean(all_rts)), 1),
            "median": round(float(np.median(all_rts)), 1),
            "sd": round(float(np.std(all_rts)), 1),
        }

    # Save to run directory
    summary_path = run_dir / "summary_stats.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"Summary statistics saved to {summary_path}")

    return summary

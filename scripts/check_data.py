# /// script
# requires-python = ">=3.12"
# dependencies = ['pandas', 'numpy', 'tabulate']
# ///

"""Analyze experiment bot output data with formatted tables and optional save."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze experiment bot output data")
    p.add_argument("--output-dir", default="./output", help="Root output directory (default: ./output)")
    p.add_argument("--platform", choices=["expfactory", "psytoolkit"], help="Filter by platform")
    p.add_argument("--task", choices=["stop_signal", "task_switching"], help="Filter by canonical task type")
    p.add_argument("--save", action="store_true", help="Save analysis_summary.json and .csv")
    p.add_argument("--quiet", action="store_true", help="Suppress per-session output (use with --save)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Task type identification
# ---------------------------------------------------------------------------

STOP_SIGNAL_NAMES = {"stop_signal_task", "stop_signal_task_(rdoc)", "stopsignal"}
TASK_SWITCHING_NAMES = {"cued_task_switching", "cued_task_switching_(rdoc)", "taskswitching_cued"}


def identify_task_type(dir_name: str) -> str | None:
    name = dir_name.lower().strip()
    if name in STOP_SIGNAL_NAMES:
        return "stop_signal"
    if name in TASK_SWITCHING_NAMES:
        return "task_switching"
    return None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_session(session_dir: Path, platform: str, task_type: str) -> pd.DataFrame | None:
    """Load and normalize a single session's data."""
    status_map = {1: "correct", 2: "wrong", 3: "timeout"}
    switch_map = {1: "repeat", 2: "switch"}

    if platform == "expfactory":
        path = session_dir / "experiment_data.csv"
        if not path.exists():
            return None
        df = pd.read_csv(path)
        df = df[df["trial_id"] == "test_trial"].copy()
        # Normalize rt to numeric
        df["rt"] = pd.to_numeric(df["rt"], errors="coerce")
        return df

    # psytoolkit
    path = session_dir / "experiment_data.tsv"
    if not path.exists():
        return None
    df = pd.read_csv(path, sep="\t", header=None)

    if task_type == "stop_signal":
        df.columns = [
            "trial_type", "req_response", "stop_signal_ms",
            "rt_1", "status_1", "rt_2", "status_2", "is_correct",
        ]
        df["status_1"] = df["status_1"].replace(status_map)
        df["is_correct"] = df["is_correct"].map({1: True, 0: False})
    else:  # task_switching
        df.columns = [
            "block_name", "task_type", "congruency", "congruency_code",
            "req_key", "rt_ms", "status", "switch_type",
        ]
        df["status"] = df["status"].replace(status_map)
        df["switch_type"] = df["switch_type"].replace(switch_map)

    return df


# ---------------------------------------------------------------------------
# Analysis: stop signal
# ---------------------------------------------------------------------------

def analyze_stop_signal(df: pd.DataFrame, platform: str) -> dict:
    """Return flat dict of stop-signal metrics."""
    if platform == "expfactory":
        go = df[df["condition"] == "go"]
        stop = df[df["condition"] == "stop"]
        go_rt = go["rt"].dropna()
        stop_fail = stop[stop["correct_trial"] == 0]

        return {
            "n_go_trials": len(go),
            "n_stop_trials": len(stop),
            "go_accuracy": go["correct_trial"].mean(),
            "go_mean_rt": go_rt.mean(),
            "go_median_rt": go_rt.median(),
            "go_rt_sd": go_rt.std(),
            "go_omission_rate": go["rt"].isna().mean(),
            "stop_accuracy": stop["correct_trial"].mean(),
            "stop_failure_rt": stop_fail["rt"].dropna().mean(),
            "ssd_mean": stop["SSD"].mean(),
            "ssd_min": stop["SSD"].min(),
            "ssd_max": stop["SSD"].max(),
            "ssd_final": stop["SSD"].iloc[-1] if not stop.empty else np.nan,
            "ssrt_estimate": go_rt.mean() - stop["SSD"].mean(),
        }

    # psytoolkit
    go = df[df["trial_type"] == "go"]
    stop = df[df["trial_type"] == "nogo"]
    go_correct = go[go["status_1"] == "correct"]
    go_rt = go_correct["rt_1"].dropna()
    stop_fail = stop[~stop["is_correct"]]

    return {
        "n_go_trials": len(go),
        "n_stop_trials": len(stop),
        "go_accuracy": (go["status_1"] == "correct").mean(),
        "go_mean_rt": go_rt.mean(),
        "go_median_rt": go_rt.median(),
        "go_rt_sd": go_rt.std(),
        "go_omission_rate": (go["status_1"] == "timeout").mean(),
        "stop_accuracy": stop["is_correct"].mean(),
        "stop_failure_rt": stop_fail["rt_1"].dropna().mean() if not stop_fail.empty else np.nan,
        "ssd_mean": stop["stop_signal_ms"].mean(),
        "ssd_min": stop["stop_signal_ms"].min(),
        "ssd_max": stop["stop_signal_ms"].max(),
        "ssd_final": stop["stop_signal_ms"].iloc[-1] if not stop.empty else np.nan,
        "ssrt_estimate": go_rt.mean() - stop["stop_signal_ms"].mean() if not stop.empty else np.nan,
    }


# ---------------------------------------------------------------------------
# Analysis: task switching
# ---------------------------------------------------------------------------

def analyze_task_switching(df: pd.DataFrame, platform: str) -> dict:
    """Return flat dict of task-switching metrics."""
    if platform == "expfactory":
        conditions = df["condition"].unique().tolist()
        metrics: dict = {}
        for cond in sorted(conditions):
            subset = df[df["condition"] == cond]
            rt_vals = subset["rt"].dropna()
            prefix = cond
            metrics[f"{prefix}_mean_rt"] = rt_vals.mean()
            metrics[f"{prefix}_accuracy"] = subset["correct_trial"].mean()
            metrics[f"{prefix}_omission_rate"] = subset["rt"].isna().mean()
            metrics[f"{prefix}_n"] = len(subset)

        metrics["overall_omission_rate"] = df["rt"].isna().mean()

        # Switch cost: switch vs stay (using available conditions)
        switch_rt = df[df["condition"].str.contains("switch", case=False)]["rt"].dropna().mean()
        stay_rt = df[df["condition"].str.contains("stay", case=False)]["rt"].dropna().mean()
        metrics["switch_cost_rt"] = switch_rt - stay_rt if pd.notna(switch_rt) and pd.notna(stay_rt) else np.nan
        metrics["overall_accuracy"] = df["correct_trial"].mean()
        metrics["overall_mean_rt"] = df["rt"].dropna().mean()
        metrics["n_trials"] = len(df)
        return metrics

    # psytoolkit — filter to realblock
    df_real = df[df["block_name"] == "realblock"].copy()

    # Derive conditions from switch_type
    df_real["prev_task"] = df_real["task_type"].shift(1)
    df_real["prev_congruency"] = df_real["congruency"].shift(1)

    def get_condition(row):
        if pd.isna(row["prev_task"]):
            return "first_trial"
        if row["switch_type"] == "switch":
            return "task_switch"
        if row["congruency"] != row["prev_congruency"]:
            return "cue_switch"
        return "stay"

    df_real["condition"] = df_real.apply(get_condition, axis=1)
    df_clean = df_real[df_real["condition"] != "first_trial"]

    metrics = {}
    for cond in sorted(df_clean["condition"].unique()):
        subset = df_clean[df_clean["condition"] == cond]
        correct = subset[subset["status"] == "correct"]
        rt_vals = correct["rt_ms"].dropna()
        metrics[f"{cond}_mean_rt"] = rt_vals.mean()
        metrics[f"{cond}_accuracy"] = (subset["status"] == "correct").mean()
        metrics[f"{cond}_omission_rate"] = (subset["status"] == "timeout").mean()
        metrics[f"{cond}_n"] = len(subset)

    metrics["overall_omission_rate"] = (df_clean["status"] == "timeout").mean()

    switch_rt = df_clean[df_clean["condition"] == "task_switch"]
    switch_rt = switch_rt[switch_rt["status"] == "correct"]["rt_ms"].dropna().mean()
    stay_rt = df_clean[df_clean["condition"] == "stay"]
    stay_rt = stay_rt[stay_rt["status"] == "correct"]["rt_ms"].dropna().mean()
    metrics["switch_cost_rt"] = switch_rt - stay_rt if pd.notna(switch_rt) and pd.notna(stay_rt) else np.nan

    metrics["overall_accuracy"] = (df_clean["status"] == "correct").mean()
    metrics["overall_mean_rt"] = df_clean[df_clean["status"] == "correct"]["rt_ms"].dropna().mean()
    metrics["n_trials"] = len(df_clean)
    return metrics


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_sessions(session_results: list[dict]) -> dict:
    """Compute mean and std across sessions for each numeric metric."""
    if not session_results:
        return {}
    all_keys = set()
    for r in session_results:
        all_keys.update(r.keys())

    agg: dict = {}
    for key in sorted(all_keys):
        vals = [r[key] for r in session_results if key in r and pd.notna(r[key])]
        if not vals:
            continue
        if isinstance(vals[0], (int, float, np.integer, np.floating)):
            agg[f"{key}_mean"] = float(np.mean(vals))
            agg[f"{key}_std"] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
    agg["n_sessions"] = len(session_results)
    return agg


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt(v) -> str:
    if isinstance(v, float) and not np.isnan(v):
        return f"{v:.3f}"
    if isinstance(v, (int, np.integer)):
        return str(v)
    return str(v) if pd.notna(v) else "—"


def format_session_table(metrics: dict, label: str) -> str:
    rows = [[k, _fmt(v)] for k, v in metrics.items()]
    header = f"\n  {label}\n"
    return header + tabulate(rows, headers=["Metric", "Value"], tablefmt="grid")


def format_aggregate_table(agg: dict) -> str:
    rows = [[k, _fmt(v)] for k, v in agg.items()]
    return "\n  Aggregate (across sessions)\n" + tabulate(rows, headers=["Metric", "Value"], tablefmt="grid")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def _jsonable(obj):
    """Make numpy types JSON-serializable."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj) if not np.isnan(obj) else None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


def save_summary(output_dir: Path, all_sessions: list[dict], aggregates: dict) -> None:
    """Write analysis_summary.json and analysis_summary.csv."""
    # JSON — structured
    summary = {
        "sessions": [{k: _jsonable(v) for k, v in s.items()} for s in all_sessions],
        "aggregates": {k: {mk: _jsonable(mv) for mk, mv in mets.items()} for k, mets in aggregates.items()},
    }
    json_path = output_dir / "analysis_summary.json"
    json_path.write_text(json.dumps(summary, indent=2))
    print(f"  Saved {json_path}")

    # CSV — one row per session
    if all_sessions:
        csv_df = pd.DataFrame(all_sessions)
        csv_path = output_dir / "analysis_summary.csv"
        csv_df.to_csv(csv_path, index=False)
        print(f"  Saved {csv_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    platforms = [args.platform] if args.platform else ["expfactory", "psytoolkit"]
    all_sessions: list[dict] = []
    grouped: dict[str, list[dict]] = {}  # "platform/task_type" -> list of metric dicts

    for platform in platforms:
        plat_dir = output_dir / platform
        if not plat_dir.exists():
            continue

        for task_dir in sorted(plat_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            task_type = identify_task_type(task_dir.name)
            if task_type is None:
                continue
            if args.task and task_type != args.task:
                continue

            group_key = f"{platform}/{task_type}"

            for sess_dir in sorted(task_dir.iterdir()):
                if not sess_dir.is_dir():
                    continue

                try:
                    df = load_session(sess_dir, platform, task_type)
                    if df is None or df.empty:
                        continue

                    if task_type == "stop_signal":
                        metrics = analyze_stop_signal(df, platform)
                    else:
                        metrics = analyze_task_switching(df, platform)

                    # Attach metadata
                    session_info = {
                        "platform": platform,
                        "task_type": task_type,
                        "task_dir": task_dir.name,
                        "session": sess_dir.name,
                        **metrics,
                    }
                    all_sessions.append(session_info)
                    grouped.setdefault(group_key, []).append(metrics)

                    if not args.quiet:
                        label = f"{platform} / {task_dir.name} / {sess_dir.name}"
                        print(format_session_table(metrics, label))
                        print()

                except Exception as e:
                    print(f"  Error processing {sess_dir}: {e}")

    # Aggregates
    aggregates: dict[str, dict] = {}
    for group_key, results in grouped.items():
        agg = aggregate_sessions(results)
        aggregates[group_key] = agg
        if not args.quiet:
            print(f"\n{'='*60}")
            print(f"  {group_key}")
            print(format_aggregate_table(agg))
            print()

    # Summary
    if not args.quiet:
        print(f"\nTotal sessions analyzed: {len(all_sessions)}")

    if args.save:
        save_summary(output_dir, all_sessions, aggregates)


if __name__ == "__main__":
    main()

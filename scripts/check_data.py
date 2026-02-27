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
    p.add_argument("--task", choices=["stop_signal", "task_switching"], help="Filter by task type")
    p.add_argument("--save", action="store_true", help="Save analysis_summary.json and .csv")
    p.add_argument("--quiet", action="store_true", help="Suppress per-session output (use with --save)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Task type identification (from config or directory name)
# ---------------------------------------------------------------------------

STOP_SIGNAL_NAMES = {"stop_signal_task", "stop_signal_task_(rdoc)", "stopsignal", "stop_signal"}
TASK_SWITCHING_NAMES = {"cued_task_switching", "cued_task_switching_(rdoc)", "taskswitching_cued", "task_switching"}


def identify_task_type_from_config(config: dict) -> str | None:
    """Identify task type from a config.json's task.constructs or task.name."""
    constructs = config.get("task", {}).get("constructs", [])
    name = config.get("task", {}).get("name", "").lower().replace(" ", "_")

    for c in constructs:
        if "inhibit" in c.lower() or "stop" in c.lower():
            return "stop_signal"
        if "switch" in c.lower() or "flexibility" in c.lower():
            return "task_switching"

    if name in STOP_SIGNAL_NAMES:
        return "stop_signal"
    if name in TASK_SWITCHING_NAMES:
        return "task_switching"
    return None


def identify_task_type(dir_name: str) -> str | None:
    """Fall back to directory name-based identification."""
    name = dir_name.lower().strip()
    if name in STOP_SIGNAL_NAMES:
        return "stop_signal"
    if name in TASK_SWITCHING_NAMES:
        return "task_switching"
    return None


def detect_data_format(session_dir: Path) -> tuple[Path | None, str]:
    """Find the experiment data file and detect its format."""
    for ext in ("csv", "tsv", "json"):
        path = session_dir / f"experiment_data.{ext}"
        if path.exists():
            return path, ext
    return None, ""


def detect_platform(config: dict) -> str:
    """Detect platform from config (best effort for analysis column mapping)."""
    platform = config.get("task", {}).get("platform", "")
    if platform:
        return platform.lower()
    # Infer from data_capture method
    dc = config.get("runtime", {}).get("data_capture", {})
    if dc.get("method") == "button_click":
        return "psytoolkit"
    if dc.get("method") == "js_expression":
        return "expfactory"
    return "unknown"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_session(session_dir: Path, platform: str, task_type: str) -> pd.DataFrame | None:
    """Load and normalize a single session's data."""
    status_map = {1: "correct", 2: "wrong", 3: "timeout"}
    switch_map = {1: "repeat", 2: "switch"}

    data_path, fmt = detect_data_format(session_dir)
    if data_path is None:
        return None

    if fmt == "csv":
        df = pd.read_csv(data_path)
        if "trial_id" in df.columns:
            df = df[df["trial_id"] == "test_trial"].copy()
        df["rt"] = pd.to_numeric(df.get("rt", pd.Series(dtype=float)), errors="coerce")
        return df

    if fmt == "tsv":
        df = pd.read_csv(data_path, sep="\t", header=None)
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

    return None


# ---------------------------------------------------------------------------
# Analysis: stop signal
# ---------------------------------------------------------------------------

def analyze_stop_signal(df: pd.DataFrame, platform: str) -> dict:
    """Return flat dict of stop-signal metrics."""
    if platform != "psytoolkit" and "condition" in df.columns:
        go = df[df["condition"] == "go"]
        stop = df[df["condition"] == "stop"]
        go_rt = go["rt"].dropna()
        stop_fail = stop[stop.get("correct_trial", pd.Series(dtype=float)) == 0] if "correct_trial" in stop.columns else pd.DataFrame()

        return {
            "n_go_trials": len(go),
            "n_stop_trials": len(stop),
            "go_accuracy": go["correct_trial"].mean() if "correct_trial" in go.columns else np.nan,
            "go_mean_rt": go_rt.mean(),
            "go_median_rt": go_rt.median(),
            "go_rt_sd": go_rt.std(),
            "go_omission_rate": go["rt"].isna().mean(),
            "stop_accuracy": stop["correct_trial"].mean() if "correct_trial" in stop.columns else np.nan,
            "stop_failure_rt": stop_fail["rt"].dropna().mean() if not stop_fail.empty else np.nan,
            "ssd_mean": stop["SSD"].mean() if "SSD" in stop.columns else np.nan,
            "ssrt_estimate": go_rt.mean() - stop["SSD"].mean() if "SSD" in stop.columns else np.nan,
        }

    # psytoolkit-style TSV
    go = df[df["trial_type"] == "go"] if "trial_type" in df.columns else pd.DataFrame()
    stop = df[df["trial_type"] == "nogo"] if "trial_type" in df.columns else pd.DataFrame()
    go_correct = go[go["status_1"] == "correct"] if not go.empty else pd.DataFrame()
    go_rt = go_correct["rt_1"].dropna() if not go_correct.empty else pd.Series(dtype=float)
    stop_fail = stop[~stop["is_correct"]] if not stop.empty and "is_correct" in stop.columns else pd.DataFrame()

    return {
        "n_go_trials": len(go),
        "n_stop_trials": len(stop),
        "go_accuracy": (go["status_1"] == "correct").mean() if not go.empty else np.nan,
        "go_mean_rt": go_rt.mean(),
        "go_median_rt": go_rt.median(),
        "go_rt_sd": go_rt.std(),
        "go_omission_rate": (go["status_1"] == "timeout").mean() if not go.empty else np.nan,
        "stop_accuracy": stop["is_correct"].mean() if not stop.empty else np.nan,
        "stop_failure_rt": stop_fail["rt_1"].dropna().mean() if not stop_fail.empty else np.nan,
        "ssd_mean": stop["stop_signal_ms"].mean() if not stop.empty else np.nan,
        "ssrt_estimate": go_rt.mean() - stop["stop_signal_ms"].mean() if not stop.empty else np.nan,
    }


# ---------------------------------------------------------------------------
# Analysis: task switching
# ---------------------------------------------------------------------------

def analyze_task_switching(df: pd.DataFrame, platform: str) -> dict:
    """Return flat dict of task-switching metrics."""
    if platform != "psytoolkit" and "condition" in df.columns:
        metrics: dict = {}
        for cond in sorted(df["condition"].unique()):
            subset = df[df["condition"] == cond]
            rt_vals = subset["rt"].dropna()
            metrics[f"{cond}_mean_rt"] = rt_vals.mean()
            metrics[f"{cond}_accuracy"] = subset["correct_trial"].mean() if "correct_trial" in subset.columns else np.nan
            metrics[f"{cond}_n"] = len(subset)

        switch_rt = df[df["condition"].str.contains("switch", case=False)]["rt"].dropna().mean()
        stay_rt = df[df["condition"].str.contains("stay", case=False)]["rt"].dropna().mean()
        metrics["switch_cost_rt"] = switch_rt - stay_rt if pd.notna(switch_rt) and pd.notna(stay_rt) else np.nan
        metrics["overall_accuracy"] = df["correct_trial"].mean() if "correct_trial" in df.columns else np.nan
        metrics["overall_mean_rt"] = df["rt"].dropna().mean()
        metrics["n_trials"] = len(df)
        return metrics

    # psytoolkit — filter to realblock
    df_real = df[df["block_name"] == "realblock"].copy() if "block_name" in df.columns else df.copy()

    df_real["prev_task"] = df_real["task_type"].shift(1) if "task_type" in df_real.columns else pd.Series(dtype=str)

    def get_condition(row):
        if pd.isna(row.get("prev_task")):
            return "first_trial"
        if row.get("switch_type") == "switch":
            return "task_switch"
        return "stay"

    df_real["condition"] = df_real.apply(get_condition, axis=1)
    df_clean = df_real[df_real["condition"] != "first_trial"]

    metrics = {}
    for cond in sorted(df_clean["condition"].unique()):
        subset = df_clean[df_clean["condition"] == cond]
        correct = subset[subset["status"] == "correct"] if "status" in subset.columns else subset
        rt_col = "rt_ms" if "rt_ms" in correct.columns else "rt"
        rt_vals = correct[rt_col].dropna() if rt_col in correct.columns else pd.Series(dtype=float)
        metrics[f"{cond}_mean_rt"] = rt_vals.mean()
        metrics[f"{cond}_accuracy"] = (subset["status"] == "correct").mean() if "status" in subset.columns else np.nan
        metrics[f"{cond}_n"] = len(subset)

    switch_rt = df_clean[df_clean["condition"] == "task_switch"]
    rt_col = "rt_ms" if "rt_ms" in switch_rt.columns else "rt"
    if "status" in switch_rt.columns:
        switch_rt = switch_rt[switch_rt["status"] == "correct"][rt_col].dropna().mean()
    else:
        switch_rt = switch_rt[rt_col].dropna().mean() if rt_col in switch_rt.columns else np.nan

    stay_rt = df_clean[df_clean["condition"] == "stay"]
    if "status" in stay_rt.columns:
        stay_rt = stay_rt[stay_rt["status"] == "correct"][rt_col].dropna().mean()
    else:
        stay_rt = stay_rt[rt_col].dropna().mean() if rt_col in stay_rt.columns else np.nan

    metrics["switch_cost_rt"] = switch_rt - stay_rt if pd.notna(switch_rt) and pd.notna(stay_rt) else np.nan
    metrics["overall_accuracy"] = (df_clean["status"] == "correct").mean() if "status" in df_clean.columns else np.nan
    rt_col = "rt_ms" if "rt_ms" in df_clean.columns else "rt"
    metrics["overall_mean_rt"] = df_clean[rt_col].dropna().mean() if rt_col in df_clean.columns else np.nan
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
    summary = {
        "sessions": [{k: _jsonable(v) for k, v in s.items()} for s in all_sessions],
        "aggregates": {k: {mk: _jsonable(mv) for mk, mv in mets.items()} for k, mets in aggregates.items()},
    }
    json_path = output_dir / "analysis_summary.json"
    json_path.write_text(json.dumps(summary, indent=2))
    print(f"  Saved {json_path}")

    if all_sessions:
        csv_df = pd.DataFrame(all_sessions)
        csv_path = output_dir / "analysis_summary.csv"
        csv_df.to_csv(csv_path, index=False)
        print(f"  Saved {csv_path}")


# ---------------------------------------------------------------------------
# Main — walks output/<task_name>/<timestamp>/ (no platform subdirectory)
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    all_sessions: list[dict] = []
    grouped: dict[str, list[dict]] = {}

    # Walk output/<task_name>/<timestamp>/ structure
    if not output_dir.exists():
        print(f"Output directory {output_dir} does not exist.")
        return

    for task_dir in sorted(output_dir.iterdir()):
        if not task_dir.is_dir():
            continue

        for sess_dir in sorted(task_dir.iterdir()):
            if not sess_dir.is_dir():
                continue

            try:
                # Try to load config.json for task type detection
                config_path = sess_dir / "config.json"
                config = {}
                platform = "unknown"
                task_type = None

                if config_path.exists():
                    config = json.loads(config_path.read_text())
                    task_type = identify_task_type_from_config(config)
                    platform = detect_platform(config)

                # Fall back to directory name
                if task_type is None:
                    task_type = identify_task_type(task_dir.name)

                if task_type is None:
                    continue
                if args.task and task_type != args.task:
                    continue

                df = load_session(sess_dir, platform, task_type)
                if df is None or df.empty:
                    continue

                if task_type == "stop_signal":
                    metrics = analyze_stop_signal(df, platform)
                else:
                    metrics = analyze_task_switching(df, platform)

                session_info = {
                    "task_type": task_type,
                    "platform": platform,
                    "task_dir": task_dir.name,
                    "session": sess_dir.name,
                    **metrics,
                }
                all_sessions.append(session_info)
                grouped.setdefault(task_type, []).append(metrics)

                if not args.quiet:
                    label = f"{task_dir.name} / {sess_dir.name}"
                    print(format_session_table(metrics, label))
                    print()

            except Exception as e:
                print(f"  Error processing {sess_dir}: {e}")

    # Also walk legacy output/<platform>/<task_name>/<timestamp>/ structure
    for legacy_plat in ("expfactory", "psytoolkit"):
        plat_dir = output_dir / legacy_plat
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

            for sess_dir in sorted(task_dir.iterdir()):
                if not sess_dir.is_dir():
                    continue
                try:
                    df = load_session(sess_dir, legacy_plat, task_type)
                    if df is None or df.empty:
                        continue

                    if task_type == "stop_signal":
                        metrics = analyze_stop_signal(df, legacy_plat)
                    else:
                        metrics = analyze_task_switching(df, legacy_plat)

                    session_info = {
                        "task_type": task_type,
                        "platform": legacy_plat,
                        "task_dir": task_dir.name,
                        "session": sess_dir.name,
                        **metrics,
                    }
                    all_sessions.append(session_info)
                    grouped.setdefault(task_type, []).append(metrics)

                    if not args.quiet:
                        label = f"{legacy_plat} / {task_dir.name} / {sess_dir.name}"
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

    if not args.quiet:
        print(f"\nTotal sessions analyzed: {len(all_sessions)}")

    if args.save:
        save_summary(output_dir, all_sessions, aggregates)


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.12"
# dependencies = ['pandas', 'numpy', 'scipy']
# ///

"""Verify humanlike data improvements against plan criteria."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

print("=" * 70)
print("VERIFICATION: Post-Implementation Sessions Only")
print("=" * 70)

# ---- STOP SIGNAL ----
print("\n## STOP SIGNAL")
ss_dirs = sorted(Path("output/psytoolkit/stop_signal_task").glob("2026-02-24_17-*"))
ss_mean_rts: list[float] = []
ss_all_rts: list[float] = []
ss_autocorrs: list[float] = []

ss_dirs = [d for d in ss_dirs if (d / "experiment_data.tsv").exists()]
for d in ss_dirs:
    df = pd.read_csv(d / "experiment_data.tsv", sep="\t", header=None)
    df.columns = [
        "trial_type", "req_response", "stop_signal_ms",
        "rt_1", "status_1", "rt_2", "status_2", "is_correct",
    ]
    go = df[df["trial_type"] == "go"]
    correct = go[go["status_1"] == 1]
    rts = correct["rt_1"].values.astype(float)
    ss_mean_rts.append(float(rts.mean()))
    ss_all_rts.extend(rts.tolist())
    ac = np.corrcoef(rts[:-1], rts[1:])[0, 1] if len(rts) > 2 else float("nan")
    ss_autocorrs.append(ac)
    sub120 = int((rts < 120).sum())
    print(f"  {d.name}: mean_rt={rts.mean():.1f}, n={len(rts)}, sub120={sub120}, lag1_r={ac:.3f}")

print(f"\n  Between-session mean RT SD: {np.std(ss_mean_rts, ddof=1):.1f} ms (target: >30ms)")
print(f"  Mean lag-1 autocorrelation: {np.mean(ss_autocorrs):.3f} (target: >0.10)")
print(f"  Min RT across all sessions: {min(ss_all_rts):.0f} ms (target: >120ms)")
print(f"  RTs below 120ms: {sum(1 for r in ss_all_rts if r < 120)}/{len(ss_all_rts)}")

# ---- TASK SWITCHING ----
print("\n## TASK SWITCHING")
ts_dirs = sorted(Path("output/psytoolkit/cued_task_switching").glob("2026-02-24_17-*"))
ts_mean_rts: list[float] = []
ts_all_rts: list[float] = []
ts_autocorrs: list[float] = []

ts_dirs = [d for d in ts_dirs if (d / "experiment_data.tsv").exists()]
for d in ts_dirs:
    df = pd.read_csv(d / "experiment_data.tsv", sep="\t", header=None)
    df.columns = [
        "block_name", "task_type", "congruency", "congruency_code",
        "req_key", "rt_ms", "status", "switch_type",
    ]
    real = df[df["block_name"] == "realblock"]
    correct = real[real["status"] == 1]
    rts = correct["rt_ms"].values.astype(float)
    ts_mean_rts.append(float(rts.mean()))
    ts_all_rts.extend(rts.tolist())
    ac = np.corrcoef(rts[:-1], rts[1:])[0, 1] if len(rts) > 2 else float("nan")
    ts_autocorrs.append(ac)
    sub50 = int((rts < 50).sum())
    print(f"  {d.name}: mean_rt={rts.mean():.1f}, n={len(rts)}, sub50={sub50}, lag1_r={ac:.3f}")

print(f"\n  Between-session mean RT SD: {np.std(ts_mean_rts, ddof=1):.1f} ms (target: >30ms)")
print(f"  Mean lag-1 autocorrelation: {np.mean(ts_autocorrs):.3f} (target: >0.10)")
print(f"  Min RT across all sessions: {min(ts_all_rts):.0f} ms (target: >50ms)")
print(f"  RTs below 50ms: {sum(1 for r in ts_all_rts if r < 50)}/{len(ts_all_rts)}")

# ---- GO ERROR RATES ----
print("\n## GO ERROR RATES (from bot_log intended_error)")
for label, dirs in [("Stop Signal", ss_dirs), ("Task Switching", ts_dirs)]:
    rates = []
    for d in dirs:
        log = json.loads((d / "bot_log.json").read_text())
        go_trials = [t for t in log if "intended_error" in t]
        errors = sum(1 for t in go_trials if t["intended_error"])
        rate = errors / len(go_trials) if go_trials else 0
        rates.append(rate)
    print(f"  {label}: error rates = {[f'{r:.1%}' for r in rates]} (target: 2-5%)")

# ---- POST-ERROR SLOWING ----
print("\n## POST-ERROR SLOWING")
for label, dirs in [("Stop Signal", ss_dirs), ("Task Switching", ts_dirs)]:
    pes_values: list[float] = []
    non_pes_values: list[float] = []
    for d in dirs:
        log = json.loads((d / "bot_log.json").read_text())
        trials = [t for t in log if "sampled_rt_ms" in t and "intended_error" in t]
        for i in range(1, len(trials)):
            if trials[i - 1].get("intended_error") and not trials[i].get("intended_error"):
                pes_values.append(trials[i]["sampled_rt_ms"])
            elif not trials[i - 1].get("intended_error") and not trials[i].get("intended_error"):
                non_pes_values.append(trials[i]["sampled_rt_ms"])
    if pes_values and non_pes_values:
        diff = np.mean(pes_values) - np.mean(non_pes_values)
        print(
            f"  {label}: post-error mean={np.mean(pes_values):.1f}ms, "
            f"non-post-error mean={np.mean(non_pes_values):.1f}ms, "
            f"PES={diff:+.1f}ms (target: +30-60ms)"
        )
    else:
        print(f"  {label}: insufficient post-error trials (n={len(pes_values)})")

# ---- FATIGUE DRIFT ----
print("\n## FATIGUE DRIFT (first half vs second half mean RT)")
for label, dirs in [("Stop Signal", ss_dirs), ("Task Switching", ts_dirs)]:
    drifts = []
    for d in dirs:
        log = json.loads((d / "bot_log.json").read_text())
        trials = [t for t in log if t.get("sampled_rt_ms") is not None]
        if len(trials) < 10:
            continue
        half = len(trials) // 2
        first_half = np.mean([t["sampled_rt_ms"] for t in trials[:half]])
        second_half = np.mean([t["sampled_rt_ms"] for t in trials[half:]])
        drifts.append(second_half - first_half)
    if drifts:
        print(
            f"  {label}: mean drift (2nd - 1st half) = {np.mean(drifts):.1f}ms "
            f"({[f'{d:.1f}' for d in drifts]})"
        )

# ---- RT SKEW ----
print("\n## RT DISTRIBUTION SHAPE")
for label, all_rts in [("Stop Signal", ss_all_rts), ("Task Switching", ts_all_rts)]:
    sk = float(stats.skew(all_rts))
    print(f"  {label}: skewness = {sk:.3f} (target: positive)")

# ---- SUMMARY TABLE ----
print("\n" + "=" * 70)
print("PASS/FAIL SUMMARY")
print("=" * 70)

checks = [
    ("Between-session RT SD (SS)", np.std(ss_mean_rts, ddof=1) > 30, f"{np.std(ss_mean_rts, ddof=1):.1f}ms"),
    ("Between-session RT SD (TS)", np.std(ts_mean_rts, ddof=1) > 30, f"{np.std(ts_mean_rts, ddof=1):.1f}ms"),
    ("Go error rate > 0% (SS)", any(r > 0 for r in [sum(1 for t in json.loads((d / 'bot_log.json').read_text()) if t.get('intended_error')) for d in ss_dirs]), "errors present"),
    ("Go error rate > 0% (TS)", any(r > 0 for r in [sum(1 for t in json.loads((d / 'bot_log.json').read_text()) if t.get('intended_error')) for d in ts_dirs]), "errors present"),
    ("Lag-1 autocorrelation > 0.10 (SS)", np.mean(ss_autocorrs) > 0.10, f"r={np.mean(ss_autocorrs):.3f}"),
    ("Lag-1 autocorrelation > 0.10 (TS)", np.mean(ts_autocorrs) > 0.10, f"r={np.mean(ts_autocorrs):.3f}"),
    ("No RTs below 120ms (SS)", sum(1 for r in ss_all_rts if r < 120) == 0, f"{sum(1 for r in ss_all_rts if r < 120)} violations"),
    ("No RTs below 50ms (TS)", sum(1 for r in ts_all_rts if r < 50) == 0, f"{sum(1 for r in ts_all_rts if r < 50)} violations"),
    ("Positive RT skew (SS)", stats.skew(ss_all_rts) > 0, f"skew={stats.skew(ss_all_rts):.3f}"),
    ("Positive RT skew (TS)", stats.skew(ts_all_rts) > 0, f"skew={stats.skew(ts_all_rts):.3f}"),
]

for name, passed, detail in checks:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}: {detail}")

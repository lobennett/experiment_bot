#!/usr/bin/env python3
"""Run the lab's Python pipeline (lobennett/rdoc-beh) on the naive bot's
session exports and emit per-task wide matrices matching the human schema.

Three phases, none of which reimplement any pipeline metric math:

1. CONVERT — for each of the 12 RDoC tasks, take the 5 lowest naive seeds
   (latest session dir per seed that has an experiment_data export), wrap
   each session's jsPsych trial array in the pipeline's SubmissionData
   envelope, and write <pipeline>/raw_data/results_export/ with the
   unified.csv the pipeline's preprocess.create_unified_df expects.
2. RUN — invoke the pipeline's own entry points unmodified
   (`uv run preprocess`, then `uv run time_resolved`) from the pipeline
   clone; they produce results/wide/<exp>_time_averaged.csv.
3. ASSEMBLE — select/reorder each wide matrix's columns to the human
   target layout (data/human/rdoc/<task>.placeholder.csv) and write
   data/bot/rdoc/<task>.csv. Columns the pipeline does not compute are
   left out (reported, never faked); extra pipeline columns not in the
   human schema are dropped (reported).

Usage:  data/bot/rdoc/run_rdoc_beh.py [PIPELINE_CLONE_DIR] [--min-seed N]
        (default /private/tmp/rdoc-beh; must be `uv sync`ed. --min-seed
        selects the collection round: the 5 lowest seeds >= N per task.)
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BOT_OUT = REPO / "output_naive"
MIN_SEED = 0
HUMAN_DIR = REPO / "data" / "human" / "rdoc"
DST_DIR = REPO / "data" / "bot" / "rdoc"

TASKS = {  # bot output dir -> pipeline task name (exp_name = <task>_rdoc)
    "ax_cpt_rdoc": "ax_cpt",
    "cued_task_switching_rdoc": "cued_task_switching",
    "flanker_rdoc": "flanker",
    "go_nogo_rdoc": "go_nogo",
    "n_back_rdoc": "n_back",
    "operation_span_rdoc": "operation_span",
    "simple_span_rdoc": "simple_span",
    "spatial_cueing_rdoc": "spatial_cueing",
    "spatial_task_switching_rdoc": "spatial_task_switching",
    "stop_signal_rdoc": "stop_signal",
    "stroop_rdoc": "stroop",
    "visual_search_rdoc": "visual_search",
}

UNIFIED_COLS = [
    "fname", "exp_name", "exp_status", "assgn_status",
    "subject", "battery_id", "study_collection_id",
]


def dir_epoch_ms(dirname: str) -> int:
    # e.g. 2026-07-03_09-06-38-504092 -> epoch ms (local time)
    stamp, micros = dirname.rsplit("-", 1)
    dt = datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S")
    return int(dt.timestamp() * 1000 + int(micros) / 1000)


def coerce(v: str):
    """CSV cell -> native type. The pipeline's human inputs carry trialdata
    with native JSON types; jsPsych's CSV export stringifies them."""
    if v in ("", "null"):
        return None
    if v == "true":
        return True
    if v == "false":
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def load_trials(session_dir: Path):
    j = session_dir / "experiment_data.json"
    c = session_dir / "experiment_data.csv"
    if j.exists():
        return json.loads(j.read_text())
    if c.exists():
        with c.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        # Drop null-valued keys: jsPsych's JSON export omits absent fields
        # (the shape the pipeline's human inputs have), and polars'
        # from_dicts schema inference chokes on columns that are explicit
        # nulls for the first 100 rows and typed only later.
        return [
            {k: cv for k, v in row.items() if (cv := coerce(v)) is not None}
            for row in rows
        ]
    return None


def convert(pipeline: Path) -> list[tuple]:
    raw_dir = pipeline / "raw_data" / "results_export"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True)

    unified_rows, manifest = [], []
    for bot_dir, task in sorted(TASKS.items()):
        exp_name = f"{task}_rdoc"
        by_seed = {}  # latest session dir per seed that has an export
        for sess in sorted((BOT_OUT / bot_dir).iterdir()):
            meta = sess / "run_metadata.json"
            if not meta.exists():
                continue
            seed = json.loads(meta.read_text()).get("session_seed")
            trials = load_trials(sess)
            if trials is None:
                continue
            by_seed[seed] = (sess, trials)  # sorted() -> latest wins
        seeds = sorted(s for s in by_seed if s >= MIN_SEED)[:5]  # 5 lowest in-round seeds
        if len(seeds) < 5:
            sys.exit(f"{task}: only {len(seeds)} usable seeds: {seeds}")
        for seed in seeds:
            sess, trials = by_seed[seed]
            submission = {
                "uniqueid": str(seed),
                "current_trial": len(trials),
                "dateTime": dir_epoch_ms(sess.name),
                "trialdata": trials,
                "status": "finished",
                "browser": {},
                "interactionData": [],
                "prolific_id": str(seed),
                "user_agent": "experiment-bot (naive)",
                "ip": "0.0.0.0",
            }
            fname = f"sub-{seed}_exp-{exp_name}_data.json"
            (raw_dir / fname).write_text(json.dumps(submission))
            unified_rows.append({
                "fname": fname,
                "exp_name": exp_name,
                "exp_status": "completed",
                "assgn_status": "completed",
                # 's' prefix: the pipeline reads unified.csv with polars
                # type inference and os.path.join()s subject into a dir
                # path, so it must stay a string.
                "subject": f"s{seed}",
                "battery_id": 1,
                "study_collection_id": 1,
            })
            manifest.append((task, seed, sess.name, len(trials)))

    with (raw_dir / "unified.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=UNIFIED_COLS)
        w.writeheader()
        w.writerows(unified_rows)
    return manifest


def run_pipeline(pipeline: Path) -> None:
    # Fresh run: the pipeline skips existing parquets and appends nothing.
    for sub in ("preprocessed_data", "results", "logs"):
        d = pipeline / sub
        if d.exists():
            shutil.rmtree(d)
    for entry in ("preprocess", "time_resolved"):
        subprocess.run(
            ["uv", "run", entry], cwd=pipeline, check=True,
            capture_output=True, text=True,
        )


def assemble(pipeline: Path) -> list[dict]:
    report = []
    for task in sorted(TASKS.values()):
        wide = pipeline / "results" / "wide" / f"{task}_rdoc_time_averaged.csv"
        target_header = (
            (HUMAN_DIR / f"{task}.placeholder.csv")
            .read_text().splitlines()[0]
        )
        want = next(csv.reader([target_header]))
        with wide.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        have = list(rows[0].keys())
        missing = [c for c in want if c not in have]
        extra = [c for c in have if c not in want]
        out_cols = [c for c in want if c in have]
        out = DST_DIR / f"{task}.csv"
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=out_cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        report.append({
            "task": task, "rows": len(rows),
            "missing": missing, "extra_dropped": extra,
        })
    return report


def main() -> None:
    args = [a for a in sys.argv[1:]]
    global MIN_SEED
    MIN_SEED = 0
    if "--min-seed" in args:
        i = args.index("--min-seed")
        MIN_SEED = int(args[i + 1]); del args[i:i + 2]
    pipeline = Path(args[0] if args else "/private/tmp/rdoc-beh")
    manifest = convert(pipeline)
    for task, seed, sess, n in manifest:
        print(f"{task}\t{seed}\t{sess}\tn_trials={n}")
    print(f"\nWrote {len(manifest)} submissions to {pipeline}/raw_data/results_export")

    run_pipeline(pipeline)
    print("Pipeline entry points completed: uv run preprocess; uv run time_resolved")

    report = assemble(pipeline)
    print("\nParity vs data/human/rdoc/<task>.placeholder.csv:")
    exact = 0
    for r in report:
        status = "EXACT" if not r["missing"] and not r["extra_dropped"] else "PARTIAL"
        if status == "EXACT":
            exact += 1
        print(f"  {r['task']:24s} rows={r['rows']} {status}"
              + (f" missing={r['missing']}" if r["missing"] else "")
              + (f" dropped={r['extra_dropped']}" if r["extra_dropped"] else ""))
    print(f"\n{exact}/12 tasks match the human column schema exactly")


if __name__ == "__main__":
    main()

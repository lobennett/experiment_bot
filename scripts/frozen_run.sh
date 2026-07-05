#!/usr/bin/env bash
# Frozen, hermetic, reproducible bot run for the paper dataset.
# Each session pins its TaskCard by content hash (--taskcard-sha256) and uses an
# explicit recorded seed, so the whole dataset regenerates from this script.
# 4 paradigms run as parallel streams (sequential within a stream — the
# validated safe-concurrency pattern; >4-way risks RT inflation).
#
# Usage:  scripts/frozen_run.sh [N_PER_PARADIGM] [OUTPUT_DIR]
#   N_PER_PARADIGM default 30; OUTPUT_DIR default output_frozen (ISOLATED from
#   the mixed-provenance main output/ so the frozen dataset is clean).
# Pre-registration: docs/preregistration.md   Analysis: experiment-bot-per-subject
set -euo pipefail
cd "$(dirname "$0")/.."

N="${1:-30}"  # default MUST match the pre-registered N: the preflight deletes out-of-target seeds
# Isolate the frozen dataset: the executor honors EXPERIMENT_BOT_OUTPUT_DIR
# (output/writer.py), so sessions never mix with the old accreted output/.
export EXPERIMENT_BOT_OUTPUT_DIR="$(pwd)/${2:-output_frozen}"
mkdir -p "$EXPERIMENT_BOT_OUTPUT_DIR"
SEED_BASE=730000
echo "== frozen run: ${N} sessions/paradigm, hermetic (pinned TaskCards + seeds) =="
echo "== output -> $EXPERIMENT_BOT_OUTPUT_DIR =="

# Idempotent-by-seed preflight (SP21 final-review I6): keep complete sessions
# whose seed is in the target set, delete partials/out-of-set extras, and
# collect only the missing seeds — a re-run after partial failure never
# duplicates a seed's session in the cohort.
echo "=== preflight: normalize to N=$N target seeds ==="
uv run python - <<PY
import glob, json, shutil
from pathlib import Path
SEED_BASE, N = 730000, $N
OUT = "$EXPERIMENT_BOT_OUTPUT_DIR"
paradigms = {
    "expfactory_stroop":      ("stroop_rdoc", 1000),
    "expfactory_stop_signal": ("stop_signal_rdoc", 2000),
    "cognitionrun_stroop":    ("stroop_online_(cognition.run)", 3000),
    "stopit_stop_signal":     ("stop-it_stop-signal_task_(jspsych)", 4000),
}
for label, (d, off) in paradigms.items():
    target = {SEED_BASE + off + i for i in range(1, N + 1)}
    done = set()
    for sub in sorted(glob.glob(f"{OUT}/{d}/*/")):
        sd = Path(sub)
        has_export = bool(list(sd.glob("experiment_data.*")))
        seed = None
        m = sd / "run_metadata.json"
        if m.exists():
            try: seed = int(json.loads(m.read_text()).get("session_seed", -1))
            except Exception: seed = None
        if (not has_export) or (sd / ".incomplete").exists() or (seed not in target):
            shutil.rmtree(sd, ignore_errors=True); continue
        done.add(seed)
    missing = [s for s in sorted(target) if s not in done]
    Path(f"/tmp/frozen_{label}.seeds").write_text("\n".join(map(str, missing)) + ("\n" if missing else ""))
    print(f"  {label}: target={N} keep={len(done)} missing={len(missing)}")
PY

run_stream() {
  local label="$1" url="$2" hash="$3" log="/tmp/frozen_${1}.log"
  : > "$log"
  while read -r seed; do
    [ -z "$seed" ] && continue
    echo "[$label] seed=$seed start $(date +%H:%M:%S)" >> "$log"
    uv run experiment-bot "$url" --label "$label" --headless \
      --taskcard-sha256 "$hash" --seed "$seed" --no-calibration >> "$log" 2>&1 \
      && echo "[$label] $seed ok" >> "$log" || echo "[$label] $seed FAIL rc=$?" >> "$log"
  done < "/tmp/frozen_${label}.seeds"
  echo "[$label] DONE" >> "$log"
}

run_stream expfactory_stroop      "https://deploy.expfactory.org/preview/10/" 45751cfe &
run_stream expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  e29f22de &
run_stream cognitionrun_stroop    "https://strooptest.cognition.run/"         b16c7891 &
run_stream stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 6fc729c3 &
wait
echo "== ALL STREAMS DONE =="

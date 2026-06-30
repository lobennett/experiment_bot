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

N="${1:-30}"
# Isolate the frozen dataset: the executor honors EXPERIMENT_BOT_OUTPUT_DIR
# (output/writer.py), so sessions never mix with the old accreted output/.
export EXPERIMENT_BOT_OUTPUT_DIR="$(pwd)/${2:-output_frozen}"
mkdir -p "$EXPERIMENT_BOT_OUTPUT_DIR"
SEED_BASE=730000
echo "== frozen run: ${N} sessions/paradigm, hermetic (pinned TaskCards + seeds) =="
echo "== output -> $EXPERIMENT_BOT_OUTPUT_DIR =="

run_stream() {
  local label="$1" url="$2" hash="$3" offset="$4" log="/tmp/frozen_${1}.log"
  : > "$log"
  for i in $(seq 1 "$N"); do
    local seed=$(( SEED_BASE + offset + i ))
    echo "[$label] session $i/$N seed=$seed $(date +%H:%M:%S)" >> "$log"
    uv run experiment-bot "$url" --label "$label" --headless \
      --taskcard-sha256 "$hash" --seed "$seed" >> "$log" 2>&1 \
      && echo "[$label] $i ok" >> "$log" || echo "[$label] $i FAIL rc=$?" >> "$log"
  done
  echo "[$label] DONE" >> "$log"
}

run_stream expfactory_stroop      "https://deploy.expfactory.org/preview/10/" 45751cfe 1000 &
run_stream expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  e29f22de 2000 &
run_stream cognitionrun_stroop    "https://strooptest.cognition.run/"         b16c7891 3000 &
run_stream stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 6fc729c3 4000 &
wait
echo "== ALL STREAMS DONE =="

#!/usr/bin/env bash
# SP21 naive-arm collection: generate (once, gated) + N seeded sessions per
# paradigm. Idempotent by seed. Pre-registration: docs/preregistration-naive.md
set -uo pipefail
cd "$(dirname "$0")/.."
N="${1:-30}"
export EXPERIMENT_BOT_OUTPUT_DIR="$(pwd)/${2:-output_naive}"
mkdir -p "$EXPERIMENT_BOT_OUTPUT_DIR"
SEED_BASE=730000

gen_if_missing() {  # label url
  local label="$1" url="$2"
  if ! ls "naive_programs/$label/"*.py >/dev/null 2>&1; then
    uv run experiment-bot-naive-gen "$url" --label "$label" || return 1
  fi
}

run_stream() {  # label url structural_hash seed_offset
  local label="$1" url="$2" hash="$3" offset="$4" log="/tmp/naive_${1}.log"
  : > "$log"
  local prog
  prog=$(ls "naive_programs/$label/"*.py | head -1)
  for i in $(seq 1 "$N"); do
    local seed=$(( SEED_BASE + offset + i ))
    echo "[$label] session $i/$N seed=$seed $(date +%H:%M:%S)" >> "$log"
    uv run experiment-bot "$url" --label "$label" --headless --no-calibration \
      --taskcard-sha256 "$hash" --seed "$seed" \
      --behavior-program "$prog" >> "$log" 2>&1 \
      && echo "[$label] $i ok" >> "$log" || echo "[$label] $i FAIL rc=$?" >> "$log"
  done
  echo "[$label] DONE" >> "$log"
}

gen_if_missing expfactory_stroop      "https://deploy.expfactory.org/preview/10/" &
gen_if_missing expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  &
gen_if_missing cognitionrun_stroop    "https://strooptest.cognition.run/"         &
gen_if_missing stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" &
wait

run_stream expfactory_stroop      "https://deploy.expfactory.org/preview/10/" 45751cfe 5000 &
run_stream expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  e29f22de 6000 &
run_stream cognitionrun_stroop    "https://strooptest.cognition.run/"         b16c7891 7000 &
run_stream stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 6fc729c3 8000 &
wait
echo "== NAIVE ARM DONE =="

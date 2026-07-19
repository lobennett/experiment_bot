#!/usr/bin/env bash
# Canonical battery collection — 12 RDoC tasks, N seeded STEALTH sessions each.
#
# Stealth is the canonical run mode: one pass serves both (a) live
# bot-detection (Roundtable Proof-of-Human on the deployed tasks) and (b) the
# battery matrices/analyses. Sessions land in output_naive/<task>_rdoc/ so the
# downstream tooling (data/bot/rdoc/run_rdoc_beh.py, experiment-bot-per-subject)
# reads them unchanged.
#
# Reproducible from a clean clone: pins each task to its committed TaskCard
# (newest by mtime under its card label) and its gate-passed program; assigns
# explicit seeds; idempotent by seed (re-run collects only missing seeds).
#
# Usage:
#   bash scripts/collect_battery_stealth.sh [N] [task ...]
#     N     sessions per task (default 5)
#     task  one or more task labels to run (default: all 12). Pass a subset to
#           run parallel streams, e.g. two backgrounded invocations of 6 each.
#
# Headful real Chrome opens per session (see --stealth). Requires Google Chrome
# installed (falls back to bundled Chromium). Run experiment-bot-reason /
# -naive-gen first only if taskcards/ or naive_programs/ are absent.
set -uo pipefail
cd "$(dirname "$0")/.."
N="${1:-5}"; shift || true
export EXPERIMENT_BOT_OUTPUT_DIR="$(pwd)/output_naive"
mkdir -p "$EXPERIMENT_BOT_OUTPUT_DIR"

# task | card label | card sha (prefix) | program sha (prefix) | url | seed base
# Card + program are pinned to the battery-v2 assets by content hash so the
# stealth run faithfully reproduces the archived dataset (isolating run mode as
# the only variable vs battery-v2-data). Some labels carry multiple gate-passed
# programs (v1 + v2 regenerations); the explicit pin selects the v2 one.
# seed = base + 1..N; the 831xxx block is distinct from every prior round.
read -r -d '' TASKS <<'EOF'
ax_cpt_rdoc|expfactory_axcpt|345d2203|43aa985c|https://deploy.expfactory.org/preview/1/|831000
cued_task_switching_rdoc|expfactory_cued_ts|f72bb581|34a91e76|https://deploy.expfactory.org/preview/2/|831100
flanker_rdoc|expfactory_flanker|e0de7406|2d9f603e|https://deploy.expfactory.org/preview/3/|831200
go_nogo_rdoc|expfactory_gonogo|4a286474|19b54f3a|https://deploy.expfactory.org/preview/4/|831300
n_back_rdoc|n_back_rdoc|375ac6d3|62cf6130|https://deploy.expfactory.org/preview/5/|831400
spatial_cueing_rdoc|spatial_cueing_rdoc|dd91af12|4094d808|https://deploy.expfactory.org/preview/7/|831500
spatial_task_switching_rdoc|spatial_task_switching_rdoc|c1927128|885ed38e|https://deploy.expfactory.org/preview/8/|831600
stop_signal_rdoc|expfactory_stop_signal|e29f22de|a1a6e805|https://deploy.expfactory.org/preview/9/|831700
stroop_rdoc|expfactory_stroop|45751cfe|677b494a|https://deploy.expfactory.org/preview/10/|831800
visual_search_rdoc|visual_search_rdoc|8d201201|8ebcc988|https://deploy.expfactory.org/preview/28/|831900
operation_span_rdoc|operation_span_rdoc|409a6ee7|05ae3f83|https://deploy.expfactory.org/preview/49/|832000
simple_span_rdoc|simple_span_rdoc|8e786a52|3a9ac797|https://deploy.expfactory.org/preview/50/|832100
EOF

# --- helpers ---------------------------------------------------------------
resolve_one() {  # dir prefix ext -> full basename matching prefix (unambiguous)
  local matches=("$1/$2"*."$3")
  [ ${#matches[@]} -eq 1 ] && [ -e "${matches[0]}" ] && basename "${matches[0]}" ".$3"
}
seed_present() {  # task seed -> 0 if a completed session with this seed exists
  grep -rlsq "\"session_seed\": $2\b" "output_naive/$1/"*/run_metadata.json 2>/dev/null
}
normalize_dir() {  # task seed — move the session dir for this seed to output_naive/<task>/
  local task="$1" seed="$2" m d
  for m in output_naive/*/*/run_metadata.json; do
    [ -e "$m" ] || continue
    if grep -q "\"session_seed\": $seed\b" "$m"; then
      d="$(dirname "$m")"
      case "$d" in output_naive/"$task"/*) return 0;; esac
      mkdir -p "output_naive/$task"
      mv "$d" "output_naive/$task/"; return 0
    fi
  done
}

# --- run -------------------------------------------------------------------
run_task() {  # task card_label card_sha prog_sha url base
  local task="$1" clabel="$2" csha="$3" psha="$4" url="$5" base="$6" log="/tmp/battery_${1}.log"
  : > "$log"
  local card prog
  card="$(resolve_one "taskcards/$clabel" "$csha" json)"
  prog="$(resolve_one "naive_programs/$clabel" "$psha" py)"
  if [ -z "$card" ]; then echo "[$task] card $csha not found under taskcards/$clabel" | tee -a "$log"; return 1; fi
  if [ -z "$prog" ]; then echo "[$task] program $psha not found under naive_programs/$clabel" | tee -a "$log"; return 1; fi
  echo "[$task] card=$csha prog=$psha" | tee -a "$log"
  local i seed
  for i in $(seq 1 "$N"); do
    seed=$((base + i))
    if seed_present "$task" "$seed"; then echo "[$task] seed=$seed present, skip" >>"$log"; continue; fi
    echo "[$task] seed=$seed start $(date +%H:%M:%S)" >>"$log"
    if uv run experiment-bot "$url" --label "$clabel" --taskcard-sha256 "$card" \
         --behavior-program "$clabel/$prog" --seed "$seed" --stealth --no-calibration >>"$log" 2>&1; then
      normalize_dir "$task" "$seed"
      echo "[$task] seed=$seed ok" >>"$log"
    else
      echo "[$task] seed=$seed FAIL rc=$?" >>"$log"
    fi
  done
  echo "[$task] TASK_DONE" >>"$log"
}

want=("$@")
while IFS='|' read -r task clabel csha psha url base; do
  [ -z "$task" ] && continue
  if [ ${#want[@]} -gt 0 ]; then
    hit=0; for w in "${want[@]}"; do [ "$w" = "$task" ] && hit=1; done
    [ $hit -eq 1 ] || continue
  fi
  run_task "$task" "$clabel" "$csha" "$psha" "$url" "$base"
done <<< "$TASKS"
echo "== BATTERY STEALTH COLLECTION DONE =="

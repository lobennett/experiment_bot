#!/usr/bin/env bash
# SP21 naive-arm collection: generate (once, gated, hash-pinned) + N seeded
# sessions per paradigm. Idempotent by seed: a re-run keeps complete sessions
# whose seed is in the target set, deletes partials/out-of-set extras, and
# collects only the missing seeds. Pre-registration: docs/preregistration-naive.md
set -uo pipefail
cd "$(dirname "$0")/.."
N="${1:-30}"
export EXPERIMENT_BOT_OUTPUT_DIR="$(pwd)/${2:-output_naive}"
mkdir -p "$EXPERIMENT_BOT_OUTPUT_DIR"
SEED_BASE=730000

echo "=== [$(date +%H:%M:%S)] preflight: normalize to N=$N target seeds (idempotent) ==="
uv run python - <<PY
import glob, json, shutil
from pathlib import Path
SEED_BASE, N = 730000, $N
OUT = "$EXPERIMENT_BOT_OUTPUT_DIR"
# label -> (task-name output subdir, naive-arm seed offset)
paradigms = {
    "expfactory_stroop":      ("stroop_rdoc", 5000),
    "expfactory_stop_signal": ("stop_signal_rdoc", 6000),
    "cognitionrun_stroop":    ("stroop_online_(cognition.run)", 7000),
    "stopit_stop_signal":     ("stop-it_stop-signal_task_(jspsych)", 8000),
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
        # delete partials (no export / .incomplete) and out-of-target extras
        if (not has_export) or (sd / ".incomplete").exists() or (seed not in target):
            shutil.rmtree(sd, ignore_errors=True); continue
        done.add(seed)
    missing = [s for s in sorted(target) if s not in done]
    Path(f"/tmp/naive_{label}.seeds").write_text("\n".join(map(str, missing)) + ("\n" if missing else ""))
    print(f"  {label}: target={N} keep={len(done)} missing={len(missing)}")
PY

gen_if_missing() {  # label url structural_hash
  local label="$1" url="$2" hash="$3"
  if ! ls "naive_programs/$label/"*.py >/dev/null 2>&1; then
    uv run experiment-bot-naive-gen "$url" --label "$label" \
      --taskcard-sha256 "$hash" || return 1
  fi
}

run_stream() {  # label url structural_hash
  local label="$1" url="$2" hash="$3" log="/tmp/naive_${1}.log"
  : > "$log"
  local prog=""
  for f in "naive_programs/$label/"*.py; do
    local sha; sha="$(basename "$f" .py)"
    if grep -q '"passed": true' "naive_programs/$label/$sha.simgate.json" 2>/dev/null; then
      prog="$f"; break
    fi
  done
  if [ -z "$prog" ]; then
    echo "[$label] NO GATE-PASSED PROGRAM — skipping stream" >> "$log"; return 1
  fi
  while read -r seed; do
    [ -z "$seed" ] && continue
    echo "[$label] seed=$seed start $(date +%H:%M:%S)" >> "$log"
    uv run experiment-bot "$url" --label "$label" --headless --no-calibration \
      --taskcard-sha256 "$hash" --seed "$seed" \
      --behavior-program "$prog" >> "$log" 2>&1 \
      && echo "[$label] $seed ok" >> "$log" || echo "[$label] $seed FAIL rc=$?" >> "$log"
  done < "/tmp/naive_${label}.seeds"
  echo "[$label] STREAM_DONE" >> "$log"
}

gen_if_missing expfactory_stroop      "https://deploy.expfactory.org/preview/10/" 45751cfe &
gen_if_missing expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  e29f22de &
gen_if_missing cognitionrun_stroop    "https://strooptest.cognition.run/"         b16c7891 &
gen_if_missing stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 6fc729c3 &
wait

run_stream expfactory_stroop      "https://deploy.expfactory.org/preview/10/" 45751cfe &
run_stream expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  e29f22de &
run_stream cognitionrun_stroop    "https://strooptest.cognition.run/"         b16c7891 &
run_stream stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" 6fc729c3 &
wait
echo "== NAIVE ARM DONE =="

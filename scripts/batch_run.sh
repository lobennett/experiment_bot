#!/usr/bin/env bash
set -euo pipefail

# Sequential batch runner: runs N instances per task, one at a time.
# Uses cached configs by default. Pass --regenerate to force regeneration on the first run.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

TOTAL_PER_TASK=1
HEADLESS=""
STAGGER_SECS=3
REGENERATE=false

# Task registry: url|hint|label  (hints empty — Claude infers from source)
TASKS=(
    "https://deploy.expfactory.org/preview/9/||expfactory_stop_signal"
    "https://deploy.expfactory.org/preview/10/||expfactory_stroop"
    "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html||stopit_stop_signal"
    "https://strooptest.cognition.run/||cognitionrun_stroop"
)

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Run experiment-bot sequentially (one instance at a time).

Options:
  --count N         Instances per task (default: 1)
  --headless        Run browsers in headless mode
  --regenerate      Force regenerate config on first run of each task
  --stagger SECS    Delay between launches (default: 3)
  -h, --help        Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --count)      TOTAL_PER_TASK="$2"; shift 2 ;;
        --headless)   HEADLESS="--headless"; shift ;;
        --regenerate) REGENERATE=true; shift ;;
        --stagger)    STAGGER_SECS="$2"; shift 2 ;;
        -h|--help)    usage ;;
        *)            echo "Unknown option: $1"; usage ;;
    esac
done

COMPLETED=0
FAILED=0
TOTAL=$((${#TASKS[@]} * TOTAL_PER_TASK))

echo "============================================="
echo "Batch Run: $TOTAL_PER_TASK instances x ${#TASKS[@]} tasks = $TOTAL total"
echo "Regenerate: $REGENERATE"
echo "============================================="
echo ""

for (( i=1; i<=TOTAL_PER_TASK; i++ )); do
    for entry in "${TASKS[@]}"; do
        IFS="|" read -r url hint label <<< "$entry"

        EXTRA_FLAGS=""
        # Only regenerate on the first run of each task, and only if --regenerate was passed
        if [[ "$i" -eq 1 && "$REGENERATE" == "true" ]]; then
            EXTRA_FLAGS="--regenerate-config"
        fi

        HINT_FLAG=""
        [[ -n "$hint" ]] && HINT_FLAG="--hint \"$hint\""

        echo "[$label] Run $i/$TOTAL_PER_TASK ..."
        if eval uv run experiment-bot \"$url\" $HINT_FLAG --label \"$label\" $HEADLESS $EXTRA_FLAGS; then
            COMPLETED=$((COMPLETED + 1))
            echo "[$label] Run $i/$TOTAL_PER_TASK complete (total: $COMPLETED/$TOTAL, failed: $FAILED)"
        else
            FAILED=$((FAILED + 1))
            echo "[$label] Run $i/$TOTAL_PER_TASK FAILED (total: $COMPLETED/$TOTAL, failed: $FAILED)"
        fi
        sleep "$STAGGER_SECS"
    done
done

echo ""
echo "============================================="
echo "DONE: $COMPLETED/$TOTAL succeeded, $FAILED failed"
echo "============================================="

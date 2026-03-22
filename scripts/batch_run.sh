#!/usr/bin/env bash
set -euo pipefail

# Sequential batch runner: regenerates configs then runs N instances per task.
# Runs ONE instance at a time to avoid overwhelming platforms and the machine.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source .env for ANTHROPIC_API_KEY
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

TOTAL_PER_TASK=20
HEADLESS="--headless"
STAGGER_SECS=5  # seconds between runs

# Task registry: url|hint|label
TASKS=(
    "https://deploy.expfactory.org/preview/9/||expfactory_stop_signal"
    "https://deploy.expfactory.org/preview/10/||expfactory_stroop"
    "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html||stopit_stop_signal"
    "https://strooptest.cognition.run/||cognitionrun_stroop"
)

COMPLETED=0
FAILED=0
TOTAL=$((${#TASKS[@]} * TOTAL_PER_TASK))

echo "============================================="
echo "Batch Run: $TOTAL_PER_TASK instances x ${#TASKS[@]} tasks = $TOTAL total"
echo "============================================="
echo ""

# Phase 1: Regenerate configs (first run of each task)
echo "--- Phase 1: Regenerating configs (4 runs) ---"
for entry in "${TASKS[@]}"; do
    IFS="|" read -r url hint label <<< "$entry"
    echo ""
    echo "[$label] Regenerating config and running first instance..."
    if uv run experiment-bot "$url" --hint "$hint" --label "$label" --regenerate-config $HEADLESS; then
        COMPLETED=$((COMPLETED + 1))
        echo "[$label] Run 1/$TOTAL_PER_TASK complete (total: $COMPLETED/$TOTAL)"
    else
        FAILED=$((FAILED + 1))
        echo "[$label] Run 1/$TOTAL_PER_TASK FAILED (total failures: $FAILED)"
    fi
    sleep "$STAGGER_SECS"
done

echo ""
echo "--- Phase 2: Remaining runs (${#TASKS[@]} x $((TOTAL_PER_TASK - 1)) = $(( ${#TASKS[@]} * (TOTAL_PER_TASK - 1) )) runs) ---"

# Phase 2: Run remaining instances, interleaving tasks to spread load across platforms
for (( i=2; i<=TOTAL_PER_TASK; i++ )); do
    for entry in "${TASKS[@]}"; do
        IFS="|" read -r url hint label <<< "$entry"
        echo ""
        echo "[$label] Run $i/$TOTAL_PER_TASK ..."
        if uv run experiment-bot "$url" --hint "$hint" --label "$label" $HEADLESS; then
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

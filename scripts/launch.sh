#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Batch launcher for experiment-bot
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Task registry: platform:task_id:canonical_name
TASKS=(
    "expfactory:9:stop_signal"
    "expfactory:2:task_switching"
    "psytoolkit:stopsignal:stop_signal"
    "psytoolkit:taskswitching_cued:task_switching"
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
FILTER_PLATFORM=""
FILTER_TASK=""
COUNT=1
HEADLESS=""
STAGGER=2
DRY_RUN=false

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Launch experiment-bot runs in parallel.

Options:
  --platform PLATFORM   Filter: expfactory, psytoolkit
  --task TASK           Filter by canonical name (stop_signal, task_switching)
                        or platform ID (9, 2, stopsignal, taskswitching_cued)
  --count N             Instances per task (default: 1)
  --headless            Run browsers in headless mode
  --stagger SECS        Delay between launches (default: 2)
  --dry-run             Print commands without executing
  -h, --help            Show this help
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform)  FILTER_PLATFORM="$2"; shift 2 ;;
        --task)      FILTER_TASK="$2";     shift 2 ;;
        --count)     COUNT="$2";           shift 2 ;;
        --headless)  HEADLESS="--headless"; shift ;;
        --stagger)   STAGGER="$2";         shift 2 ;;
        --dry-run)   DRY_RUN=true;         shift ;;
        -h|--help)   usage ;;
        *)           echo "Unknown option: $1"; usage ;;
    esac
done

# ---------------------------------------------------------------------------
# Filter tasks
# ---------------------------------------------------------------------------
matches_filter() {
    local platform="$1" task_id="$2" canonical="$3"

    if [[ -n "$FILTER_PLATFORM" && "$platform" != "$FILTER_PLATFORM" ]]; then
        return 1
    fi

    if [[ -n "$FILTER_TASK" ]]; then
        # Match against canonical name OR platform-specific task ID
        if [[ "$canonical" != "$FILTER_TASK" && "$task_id" != "$FILTER_TASK" ]]; then
            return 1
        fi
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Build command list
# ---------------------------------------------------------------------------
COMMANDS=()
for entry in "${TASKS[@]}"; do
    IFS=":" read -r platform task_id canonical <<< "$entry"
    if ! matches_filter "$platform" "$task_id" "$canonical"; then
        continue
    fi
    for (( i=1; i<=COUNT; i++ )); do
        COMMANDS+=("uv run experiment-bot $platform --task $task_id $HEADLESS")
    done
done

if [[ ${#COMMANDS[@]} -eq 0 ]]; then
    echo "No tasks matched the given filters."
    exit 1
fi

echo "Launching ${#COMMANDS[@]} experiment-bot instance(s)..."
echo ""

# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------
if $DRY_RUN; then
    for cmd in "${COMMANDS[@]}"; do
        echo "  $cmd"
    done
    exit 0
fi

# ---------------------------------------------------------------------------
# Launch with background processes
# ---------------------------------------------------------------------------
PIDS=()
CMDS_BY_PID=()
SNAPSHOT_BEFORE=$(find output -name "experiment_data.*" 2>/dev/null | sort)

cleanup() {
    echo ""
    echo "Caught signal — killing child processes..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    exit 1
}
trap cleanup SIGINT SIGTERM

for cmd in "${COMMANDS[@]}"; do
    echo "  Starting: $cmd"
    eval "$cmd" &
    pid=$!
    PIDS+=("$pid")
    CMDS_BY_PID+=("$cmd")
    if (( STAGGER > 0 )); then
        sleep "$STAGGER"
    fi
done

echo ""
echo "All ${#COMMANDS[@]} instances launched. Waiting for completion..."
echo ""

# ---------------------------------------------------------------------------
# Wait and report
# ---------------------------------------------------------------------------
FAILURES=0
for i in "${!PIDS[@]}"; do
    pid="${PIDS[$i]}"
    cmd="${CMDS_BY_PID[$i]}"
    if wait "$pid"; then
        echo "  OK   (pid $pid): $cmd"
    else
        echo "  FAIL (pid $pid): $cmd"
        (( FAILURES++ )) || true
    fi
done

echo ""
echo "──────────────────────────────────────────────"
echo "Results: $((${#COMMANDS[@]} - FAILURES))/${#COMMANDS[@]} succeeded"

# Show newly created data files
SNAPSHOT_AFTER=$(find output -name "experiment_data.*" 2>/dev/null | sort)
NEW_FILES=$(comm -13 <(echo "$SNAPSHOT_BEFORE") <(echo "$SNAPSHOT_AFTER"))
if [[ -n "$NEW_FILES" ]]; then
    echo ""
    echo "New data files:"
    echo "$NEW_FILES" | while read -r f; do echo "  $f"; done
fi

if (( FAILURES > 0 )); then
    exit 1
fi

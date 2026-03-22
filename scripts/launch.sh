#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Batch launcher for experiment-bot (URL-based)
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source .env for ANTHROPIC_API_KEY if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Task registry: url|hint|label  (hints left empty — Claude infers the task from source code)
TASKS=(
    "https://deploy.expfactory.org/preview/9/||expfactory_stop_signal"
    "https://deploy.expfactory.org/preview/10/||expfactory_stroop"
    "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html||stopit_stop_signal"
    "https://strooptest.cognition.run/||cognitionrun_stroop"
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
FILTER_URL=""
FILTER_LABEL=""
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
  --url URL             Run a single URL (bypasses registry)
  --hint HINT           Hint for the single URL
  --label LABEL         Filter registry by label, or label for --url
  --count N             Instances per task (default: 1)
  --headless            Run browsers in headless mode
  --stagger SECS        Delay between launches (default: 2)
  --dry-run             Print commands without executing
  -h, --help            Show this help

Examples:
  $(basename "$0") --url "https://deploy.expfactory.org/preview/9/" --count 3 --headless
  $(basename "$0") --label expfactory_stop_signal --count 5
  $(basename "$0") --headless --count 2
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
HINT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)       FILTER_URL="$2";   shift 2 ;;
        --hint)      HINT="$2";         shift 2 ;;
        --label)     FILTER_LABEL="$2"; shift 2 ;;
        --count)     COUNT="$2";        shift 2 ;;
        --headless)  HEADLESS="--headless"; shift ;;
        --stagger)   STAGGER="$2";      shift 2 ;;
        --dry-run)   DRY_RUN=true;      shift ;;
        -h|--help)   usage ;;
        *)           echo "Unknown option: $1"; usage ;;
    esac
done

# ---------------------------------------------------------------------------
# Build command list
# ---------------------------------------------------------------------------
COMMANDS=()

if [[ -n "$FILTER_URL" ]]; then
    # Single URL mode
    LABEL_FLAG=""
    HINT_FLAG=""
    [[ -n "$FILTER_LABEL" ]] && LABEL_FLAG="--label $FILTER_LABEL"
    [[ -n "$HINT" ]] && HINT_FLAG="--hint \"$HINT\""
    for (( i=1; i<=COUNT; i++ )); do
        COMMANDS+=("uv run experiment-bot \"$FILTER_URL\" $HINT_FLAG $LABEL_FLAG $HEADLESS")
    done
else
    # Registry mode
    for entry in "${TASKS[@]}"; do
        IFS="|" read -r url hint label <<< "$entry"
        if [[ -n "$FILTER_LABEL" && "$label" != "$FILTER_LABEL" ]]; then
            continue
        fi
        for (( i=1; i<=COUNT; i++ )); do
            COMMANDS+=("uv run experiment-bot \"$url\" --hint \"$hint\" --label \"$label\" $HEADLESS")
        done
    done
fi

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

# ---------------------------------------------------------------------------
# Run all 4 validated tasks, 5 instances each, headless:
#   ./scripts/launch.sh --headless --count 5
#
# Run a single task with 10 instances:
#   ./scripts/launch.sh --label expfactory_stroop --headless --count 10
#
# Dry run to see what would launch:
#   ./scripts/launch.sh --headless --count 5 --dry-run
# ---------------------------------------------------------------------------

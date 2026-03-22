#!/usr/bin/env bash
set -euo pipefail

# Test run: regenerate configs (triggers pilot validation) then run 1 instance each.
# Sequential, one task at a time.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

HEADLESS="--headless"

TASKS=(
    "https://deploy.expfactory.org/preview/9/||expfactory_stop_signal"
    "https://deploy.expfactory.org/preview/10/||expfactory_stroop"
    "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html||stopit_stop_signal"
    "https://strooptest.cognition.run/||cognitionrun_stroop"
)

COMPLETED=0
FAILED=0

echo "============================================="
echo "Test Run: Regenerate + 1 run per task (4 total)"
echo "============================================="
echo ""

for entry in "${TASKS[@]}"; do
    IFS="|" read -r url hint label <<< "$entry"
    echo ""
    echo "[$label] Regenerating config (with pilot validation) and running..."
    echo "  URL: $url"
    echo "  Started: $(date '+%H:%M:%S')"
    if uv run experiment-bot "$url" --hint "$hint" --label "$label" --regenerate-config $HEADLESS -v; then
        COMPLETED=$((COMPLETED + 1))
        echo "[$label] DONE ($(date '+%H:%M:%S'))"
    else
        FAILED=$((FAILED + 1))
        echo "[$label] FAILED ($(date '+%H:%M:%S'))"
    fi
    echo ""
    sleep 3
done

echo "============================================="
echo "RESULTS: $COMPLETED/4 succeeded, $FAILED failed"
echo "============================================="
echo ""
echo "Output:"
find output -name "bot_log.json" -newer "$0" | while read f; do
    dir=$(dirname "$f")
    trials=$(python3 -c "import json; d=json.load(open('$f')); print(len(d))")
    echo "  $dir: $trials trials"
done

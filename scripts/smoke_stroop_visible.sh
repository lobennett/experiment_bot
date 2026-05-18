#!/usr/bin/env bash
# SP10 Task 17 — manual smoke run with VISIBLE browser.
#
# Watches the bot run end-to-end against expfactory stroop with the
# browser window visible, so you can see where it gets stuck.
#
# Usage:
#   ./scripts/smoke_stroop_visible.sh             # default seed 9709
#   ./scripts/smoke_stroop_visible.sh 9710        # custom seed
#
# Ctrl+C to kill the bot when you've seen enough.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source ANTHROPIC_API_KEY etc. from .env if present.
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  source "$PROJECT_ROOT/.env"
  set +a
elif [[ -f "$PROJECT_ROOT/../../.env" ]]; then
  # Fallback to the main repo's .env (worktrees share the same .env).
  set -a
  source "$PROJECT_ROOT/../../.env"
  set +a
fi

export EXPERIMENT_BOT_LLM_CLIENT=api

SEED="${1:-9709}"

echo "=== SP10 smoke: expfactory_stroop, seed=$SEED ==="
echo "Watching: https://deploy.expfactory.org/preview/10/"
echo "Chromium window will open. Watch for where the bot gets stuck."
echo "Ctrl+C to kill."
echo

uv run experiment-bot \
  --label expfactory_stroop \
  --seed "$SEED" \
  https://deploy.expfactory.org/preview/10/

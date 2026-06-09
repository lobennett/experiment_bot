#!/usr/bin/env bash
# Reproduce the shareable dataset + analyses end-to-end.
#
# Stages:
#   1. (cached) TaskCards — committed under taskcards/; regenerate only if
#      you intend to change them:  uv run experiment-bot-reason <URL> --label <label>
#   2. Sessions — N per paradigm, 4 paradigms as parallel streams
#      (sequential within a stream: the validated safe-concurrency pattern).
#   3. Oracle validation — point-estimate gates vs meta-analytic norms.
#   4. Human-reference comparison — z within the RDoC human distribution
#      (the paper's analysis; needs data/human/*_rdoc.csv, committed).
#
# Usage:  scripts/reproduce.sh [N_SESSIONS_PER_PARADIGM]   (default 5)
set -euo pipefail
cd "$(dirname "$0")/.."

N="${1:-5}"
echo "== experiment-bot reproduce: ${N} session(s) x 4 paradigms =="

run_stream() {
  local label="$1" url="$2"
  for i in $(seq 1 "$N"); do
    echo "[$label] session $i/$N"
    uv run experiment-bot "$url" --label "$label" --headless
  done
}

# expfactory previews are ephemeral deployments; if a URL 404s, redeploy and
# update here (see docs/validation-results.md for the as-run commands).
run_stream expfactory_stroop      "https://deploy.expfactory.org/preview/10/" &
run_stream expfactory_stop_signal "https://deploy.expfactory.org/preview/9/"  &
run_stream cognitionrun_stroop    "https://strooptest.cognition.run/"         &
run_stream stopit_stop_signal     "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" &
wait
echo "== sessions complete =="

# STOP-IT sessions land under the executor's task-name dir; stage them under
# the adapter label for validation/comparison.
STOPIT_SRC="output/stop-it_stop-signal_task_(jspsych)"
if [ -d "$STOPIT_SRC" ]; then
  mkdir -p "output/stop_signal_kywch_jspsych"
  cp -R "$STOPIT_SRC"/. "output/stop_signal_kywch_jspsych/"
fi

echo "== oracle validation (vs meta-analytic norms) =="
uv run experiment-bot-validate --paradigm-class conflict  --label stroop_rdoc
uv run experiment-bot-validate --paradigm-class interrupt --label stop_signal_rdoc
uv run experiment-bot-validate --paradigm-class conflict  --label "stroop_online_(cognition.run)"
uv run experiment-bot-validate --paradigm-class interrupt --label stop_signal_kywch_jspsych

echo "== human-reference comparison (z within human distribution) =="
uv run experiment-bot-compare --label stroop_rdoc \
  --human-csv data/human/stroop_rdoc.csv --map data/human/comparison_maps/stroop_rdoc.json
uv run experiment-bot-compare --label stop_signal_rdoc \
  --human-csv data/human/stop_signal_rdoc.csv --map data/human/comparison_maps/stop_signal_rdoc.json
uv run experiment-bot-compare --label "stroop_online_(cognition.run)" \
  --human-csv data/human/stroop_rdoc.csv --map data/human/comparison_maps/stroop_rdoc.json \
  --metrics congruent_rt,incongruent_rt,stroop_effect
uv run experiment-bot-compare --label stop_signal_kywch_jspsych \
  --human-csv data/human/stop_signal_rdoc.csv --map data/human/comparison_maps/stop_signal_rdoc.json

echo "== done; reports under validation/ =="

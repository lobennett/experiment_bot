# SP12 hardcoded-paradigm findings

This doc accumulates findings during the SP12 top-down walk. Each
section corresponds to a module; bullets within name a specific
hardcoded value, paradigm-specific assumption, or fragile coupling.
Findings inform whether the framework's generalizability claim
holds under scrutiny.

## Surviving scripts

(none — `audit_alignment.py` and `analyze_sessions.py` carry no
paradigm-specific values beyond the platform_adapters dispatch,
which is itself the generic mechanism for paradigm-awareness.)

## src/experiment_bot/cli.py

(no paradigm-specific values; CLI is paradigm-agnostic — `--label` routes
to whatever TaskCard exists for that label, and the rest of the CLI
contains no Stroop/stop_signal/jsPsych names.)

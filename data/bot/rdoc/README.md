# Naive-bot behavioral matrices (RDoC battery)

Per-task, session-level behavioral metric matrices for the **naive bot**,
in the same schema as the human reference (`data/human/rdoc/<task>.csv`).

## Provenance

Produced by the lab's own Python preprocessing pipeline
([lobennett/rdoc-beh](https://github.com/lobennett/rdoc-beh), clone at git SHA
`e7c8c04d039aad3a199495ec2936799490293f97`) — the pipeline that generated the human matrices — run on the bot's
platform-native session exports
(`output_naive/<task>_rdoc/<timestamp>/experiment_data.{json,csv}`).

- **N = 5 sessions per task** (one row per synthetic subject; `sub_id` =
  `s<seed>`). The 5 lowest naive seeds per task; for stroop/stop_signal
  (collected at N=30) the 5 lowest naive seeds were used.
- Each bot session's jsPsych trial array was wrapped in the Prolific raw
  envelope (SubmissionData: `uniqueid`, `dateTime`, `trialdata`, `status`,
  `interactionData`) and fed through the pipeline's preprocess + analyze
  stages unmodified. No metric math was reimplemented.

## Column parity vs `data/human/rdoc`

**11 of 12 tasks: exact column parity.** Values spot-checked sane (Stroop
incongruent RT > congruent; AX-CPT AY RT > AX; spatial-span recall metrics —
accuracy respective/irrespective of order, grid movement/response times,
number of responses — computed from the bot's arrow-key grid navigation).

Honest gaps (absent, never faked):
- **stop_signal** — missing `go_rt_all_responses` and `mean_stop_failure_RT`:
  the current pipeline's `get_stop_metrics` does not emit these two columns
  (the human file's pipeline version did). All other stop-signal columns match.
- **operation_span** — `8x8_grid_asymmetric_rt` is empty: the processing
  sub-task's asymmetric-trial RT did not separate out from the bot's data.

## Regenerate

See `run_rdoc_beh.py` (wraps the bot exports into the pipeline's raw format
and runs it). Requires the lobennett/rdoc-beh clone + `uv sync`.

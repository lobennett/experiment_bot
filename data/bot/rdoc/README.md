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
  `s<seed>`), battery v2 (seeds `8XX001–8XX005`; programs authored by
  Claude Opus 4.8). v1 matrices are archived at the `battery-v1` git tag.
- Each bot session's jsPsych trial array was wrapped in the Prolific raw
  envelope (SubmissionData: `uniqueid`, `dateTime`, `trialdata`, `status`,
  `interactionData`) and fed through the pipeline's preprocess + analyze
  stages unmodified. No metric math was reimplemented.

## Column parity vs `data/human/rdoc`

**12 of 12 tasks: exact column parity.** Values spot-checked sane (Stroop
incongruent RT > congruent; AX-CPT AY RT > AX; stop-failure RT < go RT per
the race model; spatial-span recall metrics — accuracy respective/irrespective
of order, grid movement/response times, number of responses — computed from
the bot's arrow-key grid navigation).

- **stop_signal** `go_rt_all_responses` and `mean_stop_failure_RT` are the two
  columns the current lobennett/rdoc-beh `get_stop_metrics` does not emit;
  they were computed from the bot's trial-level exports with the project's own
  tested estimator (`experiment_bot.analysis.per_subject.stop_signal_metrics`,
  identical definitions) and inserted at their human-schema positions.

Honest gap (sparse, never faked):
- **operation_span** — `8x8_grid_asymmetric_rt` is present for only 1 of 5
  sessions: the processing sub-task's asymmetric-trial RTs mostly did not
  separate out from the bot's data.

## Regenerate

See `run_rdoc_beh.py` (wraps the bot exports into the pipeline's raw format
and runs it); v2 selection is `--min-seed 800000`. Requires the
lobennett/rdoc-beh clone + `uv sync`.

# RDoC human behavioral reference data

Per-subject behavioral metric matrices for 12 RDoC tasks (one CSV per task),
used as the human reference for the naive-bot comparison.

- `<task>.csv` — the real matrices (N≈2510 subject-sessions each).
  **Git-ignored**: they carry real `sub_id`s. Sourced from the lab's
  `rdoc_behavioral` matrices, trimmed to behavioral metrics +
  `proportion_feedback` + `attention_check_mean_accuracy` (dropped:
  flipped_mappings, fullscreen_exit, blur_during_task, and all
  notes/comments/checked/exclusion admin columns).
- `<task>.placeholder.csv` — committed schema stubs (header + one fake row).

The cleaning that produced them from the lab's source matrices: keep
identity columns (`sub_id`/`date_time`/`session`) and every behavioral
metric plus the two columns named above; drop the admin/QA columns listed
above. (The one-shot ingest script lives in git history.)

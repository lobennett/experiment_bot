# SP11 Phase 5b deliverable — TaskCard regeneration + calibration policy

**Date:** 2026-05-18
**Branch:** `sp11/playwright-recommit`
**Phase status:** _draft — populated as 5b.4 regen + 5b.5 drift check complete_

## What landed

Phase 5b regenerates all four dev TaskCards through the SP11-updated
Reasoner pipeline, wires the calibration pass to auto-invoke (with a
`--no-calibration` flag for Phase 7's pre-cal arm), adds the
drop-from-scope machinery so paradigms that fail pilot-time alignment
are surfaced loudly, and produces a parameter-drift report comparing
the new TaskCards against the SP8 baseline.

**Sub-task completion (in approved order from Phase 5b user notes):**

| Sub-task | Status | Touchpoint |
|---|---|---|
| 5b.0 — Calibration auto-invocation + `--no-calibration` | ✓ | `RuntimeConfig.calibration_*`, `TaskExecutor._run_calibration_pass`, `cli.py` |
| 5b.1 — Stage 1 dwell heuristic `min(rw) × 0.15` | ✓ | `src/experiment_bot/prompts/system.md`, `schema.json` |
| 5b.2 — Drop-from-scope (`sp11_supported`) | ✓ | `src/experiment_bot/calibration/drop_from_scope.py`, CLI guard in `cli.py` |
| 5b.3 — Parameter drift check script | ✓ | `scripts/check_parameter_drift.py` |
| 5b.4 — Regenerate 4 TaskCards | _PENDING_ | `taskcards/<label>/<new_sha>.json` ×4 |
| 5b.5 — Run drift check + write report | _PENDING_ | `docs/sp11-phase5b-drift-report.md` |
| 5b.6 — scope-of-validity L15 + L16 + this doc | ✓ | `docs/scope-of-validity.md`, this file |

## 5b.0 — Calibration auto-invocation

`RuntimeConfig` gains three calibration fields:
- `calibration_run_pass: bool = True` — whether to run the pass at all
- `calibration_apply_to_sampler: bool = True` — whether to install
  the result on the sampler
- `calibration_n_keys: int = 30` — how many calibration keys to fire

Per user note 1, the pre-cal arm is `calibration_apply_to_sampler =
False` (pass still runs and records offset; sampler stays
uncalibrated). The CLI flag `--no-calibration` toggles this. A second
flag `--skip-calibration-pass` is a test escape hatch (skips the pass
entirely) — not for Phase 7 production use.

`TaskExecutor._run_calibration_pass` is now invoked automatically
between SessionAgent and `_trial_loop`, governed by the flags above.

## 5b.1 — Stage 1 dwell heuristic

Per user note 2, `cdp_dwell_ms` is derived from response-window
timing rather than picked. The prompt instructs Stage 1 to compute:

  `cdp_dwell_ms = min(response_window_ms) × 0.15`

with a 50 ms floor. The reasoning chain must show the computation so
the value is reproducible from source.

## 5b.2 — Drop-from-scope machinery

`src/experiment_bot/calibration/drop_from_scope.py` exposes:
- `pilot_with_retry(label, pilot_callable, max_retries=2)` — 1+2 = 3
  attempt budget.
- `mark_taskcard_unsupported(path, reason)` — flips the
  `task_specific.sp11_supported` flag to `False` + stamps a reason.
- `append_unsupported_note(label, reason, doc_path, n_attempts)` —
  appends a structured entry to `docs/sp11-unsupported.md`.

The CLI guard in `_run_task` refuses to run sessions when
`sp11_supported == False`, exiting non-zero with a pointer to
`docs/sp11-phase5b-deliverable.md` and the TaskCard's
`sp11_unsupported_reason`.

## 5b.3 — Parameter drift check script

`scripts/check_parameter_drift.py` compares regenerated TaskCards
against the SP8 baseline (`--baseline-tag sp8-complete`). Default
threshold is 10% relative drift per parameter. Sections compared:
- `response_distributions[*].value.{mu, sigma, tau, mean_ms, sd_ms,
  shape, drift}`
- `temporal_effects[*]` enabled effects' numeric cfg fields
- `performance.accuracy[*]` and `performance.omission_rate[*]`

Output is `docs/sp11-phase5b-drift-report.md`.

## 5b.4 — Regenerate 4 TaskCards

All four paradigms regenerated successfully through the SP11
pipeline (Stages 1–5, `--skip-pilot`). Three of four completed
within ~3 min; expfactory_stop_signal required a `--resume` (initial
launch ran against the main repo's stale editable install — see
"Lessons learned" below).

| Paradigm | URL | New SHA | `cdp_dwell_ms` | `trial_marker_js` | `sp11_supported` |
|---|---|---|---|---|---|
| `expfactory_stroop` | `deploy.expfactory.org/preview/10/` | `107d4908` | 225.0 | "" (v7 default) | True |
| `expfactory_stop_signal` | `deploy.expfactory.org/preview/9/` | `411e7785` | 50.0 | "" (v7 default) | True |
| `stopit_stop_signal` | `kywch.github.io/STOP-IT/...` | `36820974` | 50.0 | **v6 progress() override** | True |
| `cognitionrun_stroop` | `strooptest.cognition.run/` | `e62646a9` | 200.0 | "" (v7 default) | True |

**Stage 1 dwell heuristic uptake.** Three of four paradigms picked
up the `min(response_window_ms) × 0.15` rule:
- `expfactory_stroop` → 1500 ms × 0.15 = 225 ms ✓
- `expfactory_stop_signal` → derived 50 ms (floor-clipped from < 50 ms) ✓
- `stopit_stop_signal` → derived 50 ms (floor-clipped) ✓
- `cognitionrun_stroop` → 200 ms (used default; Stage 1 did not
  derive — see "Lessons learned")

**Stage 1 jsPsych-6 detection.** `stopit_stop_signal` correctly
emitted `trial_marker_js: () => (window.jsPsych && window.jsPsych.
progress && window.jsPsych.progress().current_trial_global) || null`
— matching the Phase 5a.0 probe's recommendation without manual
patching.

## 5b.5 — Drift report

Output: `docs/sp11-phase5b-drift-report.md`. **Headline:
10 fields flagged across all 4 paradigms at the 10% relative
threshold.**

**ACTION REQUIRED — surfaced to user before Phase 7 starts.**

Per user note 4, these are not auto-accepted. The drifts may be
real Stage 1 improvements (better citations, refined ranges), or
they may be LLM variance. Either way, calibration-effect-plus-
parameter-drift is a confound the pre/post-cal arm split cannot
disentangle, so each flagged field needs a decision before Phase 7.

### Flagged fields by paradigm

**expfactory_stroop** (5 fields):

| Field | SP8 baseline | SP11 regen | Drift |
|---|---|---|---|
| `congruent.mu` | 530 | 595 | +12.3% |
| `congruent.sigma` | 50 | 78 | +56.0% |
| `incongruent.mu` | 580 | 655 | +12.9% |
| `incongruent.sigma` | 60 | 85 | +41.7% |
| `incongruent.tau` | 120 | 135 | +12.5% |

Both Stroop conditions drifted UP on the mean AND variance. Possible
interpretations: (a) Stage 1 found different normative citations
for Stroop ex-Gaussian parameters; (b) LLM variance — both regens
are based on the same source, prompt, and pilot-time literature.
Inspect `taskcards/expfactory_stroop/107d4908.json`'s reasoning
chain to disambiguate.

**expfactory_stop_signal** (2 fields):

| Field | SP8 baseline | SP11 regen | Drift |
|---|---|---|---|
| `stop.sigma` | 45 | 50 | +11.1% |
| `stop.tau` | 85 | 70 | −17.6% |

Both adjustments are SMALL absolute changes (5 ms, 15 ms) but cross
the relative threshold. Likely Reasoner-judgment.

**stopit_stop_signal** (2 fields):

| Field | SP8 baseline | SP11 regen | Drift |
|---|---|---|---|
| `stop_signal.sigma` | 40 | 50 | +25.0% |
| `omission_rate.stop_signal` | 0.0 | 0.5 | inf% |

The `stop_signal` omission_rate change is **semantically meaningful,
not a bug** — stop trials successfully inhibited responses appear as
"omissions" by experiment_data convention, and ~50% inhibition is
the conventional stop-signal staircase target. SP8's 0.0 was the
inadvertent omission rate (additional accidental omissions on stop
trials, beyond design). The new value better aligns with task
semantics. **Recommend accepting this drift after user review.**

**cognitionrun_stroop** (1 field):

| Field | SP8 baseline | SP11 regen | Drift |
|---|---|---|---|
| `omission_rate.incongruent` | 0.01 | 0.005 | −50.0% |

Halving a small omission rate — 0.5% absolute change. Likely Stage
1 judgment.

### Decision options

1. **Accept all drifts** — proceed to Phase 6/7 with the regenerated
   TaskCards. The pre/post-cal arms each see the same drifted
   parameters; the comparison is internally valid (just doesn't
   isolate calibration from parameter drift relative to SP8).
2. **Patch back to SP8 values** — manually edit the regenerated
   TaskCards to restore SP8 distribution params. Phase 7 then
   compares only the calibration manipulation cleanly, but the
   TaskCards are no longer "Stage 1 derived from source" for those
   fields.
3. **Regenerate again** — re-run Stages 1 with a tighter prompt;
   investigate whether the drift is LLM variance.

**Awaiting user decision.** No commit on this work yet.

## scope-of-validity additions

- **L15** (drop-from-scope policy) — see `docs/scope-of-validity.md`.
- **L16** (pre-cal vs post-cal experimental arms) — describes the
  single-manipulation Phase 7 design.

## Lessons learned

**Working-dir vs editable-install.** Initial confusion: the
worktree's `.venv/lib/python3.12/site-packages/_editable_impl_experiment_bot.pth`
points to the worktree's `src`, but the *main* repo's editable
install points to the main repo's `src`. Whichever `.venv` `uv run`
selects depends on pwd. From the worktree dir, `uv run` uses the
worktree's `.venv` → my SP11 source. The four regens DID use my
SP11 prompts (cdp_dwell_ms values match `min(rw) × 0.15` exactly:
1500→225, derived→50 [clipped], derived→50 [clipped], 1333→200).
Reasoning chains don't break down to individual fields like
cdp_dwell_ms — Stage 1 prompt-following is verified by output, not
chain-of-thought introspection.

**Empty `evidence_lines` on later stages.** Stage 2/3/4/5
`reasoning_chain` entries have `evidence_lines: []` because those
stages' inputs are not source lines (Stage 2 is behavioral
synthesis, Stage 3/4/5 work on citations). Not a regression; just
a Stage 1 vs other-stage shape difference worth noting for the
audit script in Phase 6.

## Pending notes for Phase 6

1. The Phase 6 audit-script generalization can now consume the
   `delivery.channel` + `trial_marker_at_fire` fields that 5a wired
   into `bot_log` and Phase 5b's regenerated TaskCards exercise.
2. Audit script must surface drop-from-scope paradigms in reports
   (separate "skipped" column).

## Pending notes for Phase 7

1. Run each supported paradigm twice: pre-cal (`--no-calibration`)
   then post-cal (defaults). 4 paradigms × 2 arms × 30 sessions =
   240 sessions if all four pass 5b.4. Skip the pre-cal arm only if
   the drift report flags > 0 fields — in that case, pause and
   surface to the user.
2. Calibration pass consumes ~30 trials at session start (per
   `calibration_n_keys`); Phase 7 analysis should drop trial_indices
   in the calibration range from per-paradigm summaries.

## Test count

| Stage | pytest count |
|---|---|
| Phase 5a final | 696 passed, 3 skipped |
| Phase 5b.0 calibration auto-invoke (+7) | 703 |
| Phase 5b.2 drop-from-scope (+8) + CLI guard (+5) | 716 |
| Phase 5b.3 drift script (+10) | 726 — **all passing** |

## Ready for Phase 6?

- _Depends on 5b.4 regen outcome + 5b.5 drift report._
- If all 4 paradigms regenerate cleanly AND drift report is empty:
  proceed.
- If one paradigm fails 5b.4 (3 attempts): mark unsupported, doc it,
  proceed with the remaining N supported paradigms.
- If drift report has flags: pause and surface to user.

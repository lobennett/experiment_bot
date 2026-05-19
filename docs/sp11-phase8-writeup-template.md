# SP11 Phase 8 writeup template

This file is the working scaffold for `docs/sp11-results.md`. It
records advance commitments made during Phases 1–7 that the Phase 8
writeup must honor when it lands. **Do not edit Phase 1–7 commitments
in this file after Phase 7 data arrives** — that's post-hoc retargeting.

## Pre-registered commitments

- §6 hard gates from spec — restate per-metric with the Phase 7 number
  next to the threshold. Pass/fail in the table.
- §6.1 H1 (mean pressed==recorded ≥ 85%), H2 (per-paradigm floor ≥ 75%),
  H3 (pilot alignment ≥ 90% with ≤ 2 retries), H4 (sequential effects
  sign-correct).
- §6.2 S1-S7 — restate per row, mark non-degradation vs improvement
  per Class A/B labeling.
- §6.3 global non-degradation — walk through Appendix C row by row.
  ANY in-band row that drifts out is a failure regardless of whether
  it was in §6.1/§6.2.

## Honest reconciliation: cross-deployment vs cross-engine

**Background (committed 2026-05-18, Phase 4a context).** During Phase
3.1's cognition.run data-export probe, we discovered the cognition.run
deployment runs on jsPsych 7.3.1 under the hood (scripts loaded from
`static.cognition.run/js/jspsych-7.3.1/`). This is the same engine
the three expfactory paradigms use. The four SP11 dev paradigms break
down as:

| Paradigm | Hosting deployment | Underlying engine |
|---|---|---|
| `expfactory_stroop` | deploy.expfactory.org | jsPsych 7.3.1 |
| `expfactory_stop_signal` | deploy.expfactory.org | jsPsych 7.3.1 |
| `cognitionrun_stroop` | strooptest.cognition.run | jsPsych 7.3.1 |
| `stopit_stop_signal` | kywch.github.io/STOP-IT | jsPsych 6.0.5 |

Three of four paradigms share an engine (jsPsych 7.3.1) across two
different hosting deployments (expfactory + cognition.run). One uses
a different engine version (jsPsych 6.0.5). **The abstract's "cross-
platform generalization" framing must be reconciled honestly in
Phase 8:**

- The claim is best described as **cross-deployment** generalization
  on three paradigms (two deployments running the same engine), plus
  one **cross-engine-version** test on stopit (jsPsych 6 vs 7).
- It is NOT a test against a fully heterogeneous platform set
  (jsPsych + PsychoJS + Gorilla + lab.js + Inquisit + …). Future
  work should add platforms with different underlying engines to
  strengthen the cross-engine claim.

### Measurement-time engine disclosure (added 2026-05-18, Phase 4b)

The cross-deployment claim is bot-side. The *analysis-time* claim
is engine-aware: when reporting Phase 7 numbers, we MUST disclose
which engine version each paradigm's measurement session ran
against. The audit script's pairing method (trial-counter for sp11
input-layer path; RT-based for sp10 driver path) is one disclosure
point; the engine-version row in the per-paradigm result table is
the other. Reviewers should not need to dig into branch history to
learn that three of four dev paradigms shared an engine at
measurement time.

**Bot discipline does not change.** Even though we know three
paradigms share an engine, the bot's runtime code MUST NOT exploit
this knowledge:

- Stimulus detection stays derived per-paradigm from page source by
  the Stage 1 prompt; no jsPsych-specific selectors hardcoded in
  the bot library.
- Navigation stays driven by generic DOM probes + visible-text
  matching; no jsPsych-plugin-name dispatch in the bot library.
- Data retrieval reads via the per-paradigm
  `validation/platform_adapters.py` entry; the adapter knows about
  the *paradigm's* trial schema (e.g., `trial_id == 'test_trial'`
  for stroop), not about jsPsych version specifics.
- The calibration estimator's read-back goes through
  `jsPsych.data.get().values()` as a concrete read mechanism, but
  it's wrapped behind the `KeypressDeliverer` abstraction so a
  non-jsPsych platform driver could substitute its own read
  function. This is documented in scope-of-validity §L9.

The Phase 8 writeup should make these distinctions explicit so a
reviewer understands what the four paradigms actually exercise.

## Phase 8 writeup section headers (predeclared)

1. Headline numbers — table of §6 gates pass/fail.
2. Per-paradigm result tables (one per dev paradigm). Include a
   row naming the engine version observed at measurement time
   (jsPsych 7.3.1 / jsPsych 6.0.5 / etc.) as part of the disclosure
   contract above.
3. Pre/post-calibration comparison for Stroop and stop_signal.
4. Cross-deployment vs cross-engine reconciliation (the section
   informed by the Phase 4a context note above).
5. Sequential effects: PES, lag1, CSE 2×2 — observed values vs
   §6.2 S7 and Appendix C reference numbers.
6. Calibration diagnostics (model selection per paradigm; SD;
   bimodality detection outcomes).
7. CDP vs `keyboard.press` channel fidelity breakdown.
8. Honest reading: what generalizes, what doesn't, what's
   non-degradation vs improvement.
9. SP11 backlog: anything found in Phase 7 that didn't get fixed,
   handed to a future SP.
10. Charter bump (`docs/reviewer-1-charter.md`) "Last reviewed at"
    advance.

## What is NOT in scope for Phase 8

- Abstract revision. Per spec §4 Phase 8: the abstract is edited
  AFTER results land and reflect what SP11 actually achieved. No
  pre-edits.
- Re-running Phase 7 if the headline result is unflattering. The
  spec's pre-registration discipline says we report against the
  committed thresholds, not against a retargeted version.
- Adding new metrics not enumerated in §6 or Appendix C. Descriptive
  observations are fine; new pass/fail criteria are not.

## Phase 8 deliverable checklist (run-time)

When Phase 8 begins:
- [ ] Confirm `RUN_LIVE_LLM=1` test ran cleanly during Phase 5
      (per spec §4 Phase 5 + Phase 2 deliverable user-note 4 deferral).
- [ ] Cross-check Appendix C row by row against Phase 7 results.
- [ ] Run the cross-deployment vs cross-engine section honestly per
      the note above.
- [ ] Tag `sp11-complete` only after the writeup lands.
- [ ] Update `docs/reviewer-1-charter.md` "Last reviewed at" to
      `sp11-complete`.

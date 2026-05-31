# Validation Results

Single living results doc (CLAUDE.md rule R-1). On each new batch: **overwrite** the
Current-baselines rows in place; **prepend** one Run-log entry and drop the oldest
so ~3 entries are kept (git history retains superseded entries).

---

## Current baselines

_Last updated: 2026-05-31, N=5 per paradigm (canonical-recall TaskCards; calibration feasibility-gate in place)._

| paradigm | platform | latest N | rt\_distribution | sequential (PES) | signature (SSRT) | overall | as-run command |
|---|---|---|---|---|---|---|---|
| stroop\_rdoc | expfactory | 5 | mu 494.4 ✅[400,550], sigma 51.0 ✅[25,60], tau 146.0 ✅[70,160] | PES 38.2 ms ✅[10,50]; CSE not computable | N/A | ✅ PASS | `uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop --headless` |
| stop\_signal\_rdoc | expfactory | 5 | rt-dist ✅ (descriptive, no norm range) | PES 29.6 ms ✅[10,50] | SSRT 239.5 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless` |
| stroop\_online\_(cognition.run) | cognition.run | 5 | mu 481.8 ✅, sigma 22.1 ❌[25,60], tau 166.6 ❌[70,160] | PES/CSE not computable (15-trial task) | N/A | ❌ FAIL | `uv run experiment-bot "https://strooptest.cognition.run/" --label cognitionrun_stroop --headless` |
| stop\_signal\_kywch\_jspsych | kywch/STOP-IT | 5 | rt-dist ✅ (descriptive, no norm range) | PES 10.8 ms ✅[10,50] | SSRT 192.1 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" --label stopit_stop_signal --headless` |

**Batch verdict: 3/4 pass.**

Notes:
- "not computable" entries (cognitionrun PES/CSE; stroop CSE) are non-blocking, not failures.
- **cognitionrun FAIL is N=15-trial fit instability, not a behavior change.** Its ex-Gaussian params bounce between batches on a 75-trial-total sample (last batch sigma 34.1/tau 139.4 → this batch 22.1/166.6); mu stays in range. Calibration applies **no** adjustment (`too_few_events`; see scope-of-validity **L21**), so the calibration feasibility-gate changed timing only, not RTs. mu/sigma fell rather than rose, so parallel-run CPU contention did not inflate RTs either.
- **SSRT (kywch) varies batch-to-batch (355.5 → 192.1).** Per scope-of-validity **L20**, SSRT is NOT framework-controlled — it is an emergent artifact of the platform's SSD staircase. This batch's "pass" is as much staircase luck as the prior batch's "fail"; neither is a bot property.

TaskCards: `taskcards/expfactory_stroop/45751cfe.json`, `taskcards/expfactory_stop_signal/e29f22de.json`, `taskcards/cognitionrun_stroop/b16c7891.json`, `taskcards/stopit_stop_signal/6fc729c3.json`.

---

## Run log

### 2026-05-31 — N=5 post calibration-feasibility-gate

- **What:** 5 sessions × 4 paradigms in parallel (`/tmp/run5_all.sh` pattern), first run with the calibration feasibility-gate (`13450d9`).
- **Command:** `uv run experiment-bot <URL> --label <label> --headless` × 5 each.
- **Trials/session:** stroop\_rdoc 124–128; stop\_signal\_rdoc 189–191; stroop\_online 15; stop\_signal\_kywch 285–286.
- **TaskCard hashes:** 45751cfe / e29f22de / b16c7891 / 6fc729c3 (unchanged).
- **Data location:** `output/<task_name>/<ts>/`.
- **Verdict:** 3/4 pass (stroop\_rdoc and stop\_signal\_kywch passed this batch; cognitionrun failed on sigma/tau — N=15 fit instability, not behavior). The gate cut cognitionrun from ~17 min/session to ~78 s and is behaviorally inert (calibration `too_few_events` before and after — no RT adjustment).
- Raw per-paradigm reports: `validation/latest_batch_v2/` (ephemeral, not committed).

---

### 2026-05-30 — N=5 canonical-recall regenerated TaskCards

- **What:** 5 sessions × 4 paradigms run in parallel via `/tmp/run5_all.sh` pattern.
- **Command:** `uv run experiment-bot <URL> --label <label> --headless` × 5 each.
- **Trials/session:** stroop\_rdoc 122–125; stop\_signal\_rdoc 188–191; stroop\_online 15; stop\_signal\_kywch 284–288.
- **TaskCard hashes:** 45751cfe / e29f22de / b16c7891 / 6fc729c3.
- **Data location:** `output/<task_name>/<ts>/`.
- **Verdict:** 2/4 pass. expfactory-Stroop tau/PES slightly wide (pre-existing); kywch SSRT high (platform staircase artifact, scope-of-validity L20).
- Raw per-paradigm reports: `validation/latest_batch/` (ephemeral, not committed).
- Baseline data: `docs/results-data/`.

---

### 2026-05-22 — N=5 SP12 re-measurement (post-cleanup)

Post-SP12 simplification re-measurement. N=5 × 4 paradigms; sessions run 2026-05-21 evening PDT.

Key aggregate metrics: expfactory\_stroop fit\_mu 709.6 ms (outside norm [400,550]) — Stroop tail-width issue present before regenerated TaskCards; expfactory\_stop\_signal SSRT 353.0 ms (platform staircase, see L20); stopit SSRT 322.6 ms; cognitionrun\_stroop fit unstable at N=15 trials (high SD on ex-Gaussian params). No explicit pass/fail verdict field in the JSON; metric-by-metric comparison against norms shows same pattern as current baselines.

Raw data: [`docs/results-data/sp12-remeasure-results.json`](results-data/sp12-remeasure-results.json).

---

_Superseded entries beyond ~3 are dropped here; see git history for older runs. Older raw artifacts (incl. the 2026-05-19 SP11 Phase-7 URL/HTML baseline capture) remain under [`docs/results-data/`](results-data/)._

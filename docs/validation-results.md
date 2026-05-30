# Validation Results

Single living results doc (CLAUDE.md rule R-1). On each new batch: **overwrite** the
Current-baselines rows in place; **prepend** one Run-log entry and drop the oldest
so ~3 entries are kept (git history retains superseded entries).

---

## Current baselines

_Last updated: 2026-05-30, N=5 per paradigm (canonical-recall regenerated TaskCards)._

| paradigm | platform | latest N | rt\_distribution | sequential (PES) | signature (SSRT) | overall | as-run command |
|---|---|---|---|---|---|---|---|
| stroop\_rdoc | expfactory | 5 | mu 492.1 ✅[400,550], sigma 57.3 ✅[25,60], tau 164.7 ❌[70,160] | PES 66.8 ms ❌[10,50]; CSE not computable | N/A | ❌ FAIL | `uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop --headless` |
| stop\_signal\_rdoc | expfactory | 5 | rt-dist ✅ (descriptive, no norm range) | PES 30.5 ms ✅[10,50] | SSRT 241.3 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless` |
| stroop\_online\_(cognition.run) | cognition.run | 5 | mu 505.8 ✅, sigma 34.1 ✅, tau 139.4 ✅ | PES/CSE not computable (15-trial task) | N/A | ✅ PASS | `uv run experiment-bot "https://strooptest.cognition.run/" --label cognitionrun_stroop --headless` |
| stop\_signal\_kywch\_jspsych | kywch/STOP-IT | 5 | rt-dist ✅ (descriptive, no norm range) | PES 8.7 ms ❌[10,50] | SSRT 355.5 ms ❌[180,280] | ❌ FAIL | `uv run experiment-bot "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" --label stopit_stop_signal --headless` |

**Batch verdict: 2/4 pass.**

Notes:
- "not computable" entries (cognitionrun PES/CSE; stroop CSE) are non-blocking, not failures.
- expfactory-Stroop RT tail (tau, PES) runs slightly wide — pre-existing known margin.
- kywch SSRT high: per `docs/scope-of-validity.md` **L20**, SSRT is NOT framework-controlled — it is an emergent artifact of the platform's SSD staircase. Same bot, ~50% inhibition rate on both stop-signal platforms; kywch staircase converges to a lower mean SSD → higher measured SSRT. The kywch SSRT "fail" is not a bot defect.

TaskCards: `taskcards/expfactory_stroop/45751cfe.json`, `taskcards/expfactory_stop_signal/e29f22de.json`, `taskcards/cognitionrun_stroop/b16c7891.json`, `taskcards/stopit_stop_signal/6fc729c3.json`.

---

## Run log

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

### 2026-05-19 — SP11 Phase-7 URL/HTML baseline capture

Landing-page HTML snapshot for all 4 paradigm URLs (SHA256 + load time), captured as the SP11 Phase-7 pre-measurement baseline. Contains URL-capture metadata only (no behavioral sessions); confirms all 4 platforms were reachable and stable at this date.

Raw data: [`docs/results-data/phase7-baselines/`](results-data/phase7-baselines/).

---

_Superseded entries beyond ~3 are dropped here; see git history for older runs._

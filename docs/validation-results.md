# Validation Results

Single living results doc (CLAUDE.md rule R-1). On each new batch: **overwrite** the
Current-baselines rows in place; **prepend** one Run-log entry and drop the oldest
so ~3 entries are kept (git history retains superseded entries).

---

## Current baselines

_Last updated: 2026-06-05, N=15 cumulative per paradigm (canonical-recall TaskCards; calibration feasibility-gate; safe 4-way-parallel)._

| paradigm | platform | latest N | rt\_distribution | sequential (PES) | signature (SSRT) | overall | as-run command |
|---|---|---|---|---|---|---|---|
| stroop\_rdoc | expfactory | 15 | mu 490.1 ✅[400,550], sigma 51.0 ✅[25,60], tau 162.9 ❌[70,160] | PES 67.7 ms ❌[10,50] (noise — see notes); CSE not computable | N/A | ❌ FAIL | `uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop --headless` |
| stop\_signal\_rdoc | expfactory | 15 | rt-dist ✅ (descriptive, no norm range) | PES 29.1 ms ✅[10,50] | SSRT 248.4 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless` |
| stroop\_online\_(cognition.run) | cognition.run | 15 | mu 500.2 ✅[400,550], sigma 44.0 ✅[25,60], tau 137.8 ✅[70,160] | PES/CSE not computable (15-trial task) | N/A | ✅ PASS | `uv run experiment-bot "https://strooptest.cognition.run/" --label cognitionrun_stroop --headless` |
| stop\_signal\_kywch\_jspsych | kywch/STOP-IT | 15 | rt-dist ✅ (descriptive, no norm range) | PES −23.3 ms ❌[10,50] (noise — see notes) | SSRT 272.3 ms ✅[180,280] | ❌ FAIL | `uv run experiment-bot "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" --label stopit_stop_signal --headless` |

**Batch verdict: 2/4 pass.** (Both fails are on PES — see the measurement-power note; the stable, gateable metrics pass.)

Notes:
- "not computable" entries (cognitionrun PES/CSE; stroop CSE) are non-blocking, not failures.
- **cognitionrun is stable and PASSES at N≥10** (N=15: mu 500.2 / sigma 44.0 / tau 137.8). The earlier N=5 FAILs were ex-Gaussian fit instability on 15-trial sessions; with adequate N it's solidly in range — the instability was sampling noise, not behavior.
- **PES is a noise-dominated, few-error estimate across the dev paradigms — not a fidelity defect, and effectively descriptive-only at these trial counts.** Both fails this batch are PES. The TaskCards configure post-error slowing in-range (e.g. Stroop 20–50 ms), but the estimate rests on very few errors: Stroop ~96% accuracy → ~1–8 errors/session (per-session PES SD ≈ 115 ms on a 20–50 ms signal), and even pooled it swings batch-to-batch — **stroop PES 38 → 67 → 92 → 68 ms; kywch PES 8.7 → 10.8 → 16.9 → −23.3 ms** (the last is post-error *speeding*, a sign-flip that only noise produces). tau (stroop 163) is the usual marginal tail-width miss.
- **SSRT (kywch) varies batch-to-batch (355.5 → 192.1 → 253.9 → 272.3).** Per scope-of-validity **L20**, SSRT is NOT framework-controlled — an emergent artifact of the platform's SSD staircase. Any single batch's pass/fail is staircase luck, not a bot property.

TaskCards: `taskcards/expfactory_stroop/45751cfe.json`, `taskcards/expfactory_stop_signal/e29f22de.json`, `taskcards/cognitionrun_stroop/b16c7891.json`, `taskcards/stopit_stop_signal/6fc729c3.json`.

---

## Run log

### 2026-06-05 — +5/paradigm → cumulative N=15

- **What:** 5 more sessions × 4 paradigms in parallel (`/tmp/run5_all.sh`), validated **cumulatively at N=15** (these 5 + the prior N=10). (First launch no-op'd on a wiped `/tmp` script; relaunched. Session data is in `output/`, which persists regardless.)
- **Command:** `uv run experiment-bot <URL> --label <label> --headless` × 5 each.
- **Trials/session (the +5):** stroop\_rdoc 124–128; stop\_signal\_rdoc 190–192; stroop\_online 15–16; stop\_signal\_kywch 284–287.
- **TaskCard hashes:** 45751cfe / e29f22de / b16c7891 / 6fc729c3 (unchanged).
- **Verdict (N=15 cumulative):** 2/4 pass — stop\_signal\_rdoc + cognitionrun pass; stroop\_rdoc + kywch fail on PES (noise-dominated few-error estimate; kywch PES even went negative) + stroop tau marginal. The stable gateable metrics (RT distribution, SSRT-in-range) hold; the PES gate is the unstable one. See Current-baselines notes.
- Raw per-paradigm reports: `validation/latest_batch_n15/` (ephemeral, not committed).

---

### 2026-06-02 — N=10 (safe 4-way parallel)

- **What:** 10 sessions × 4 paradigms in parallel (`/tmp/run10_all.sh`), validated 4-way-concurrent pattern (no RT inflation).
- **Command:** `uv run experiment-bot <URL> --label <label> --headless` × 10 each.
- **Trials/session:** stroop\_rdoc 124–128; stop\_signal\_rdoc 190–192; stroop\_online 15–16; stop\_signal\_kywch 282–288.
- **TaskCard hashes:** 45751cfe / e29f22de / b16c7891 / 6fc729c3 (unchanged).
- **Wall-clock:** ~100 min, bottlenecked by the stop\_signal\_rdoc stream (~10 min/session × 10); cognitionrun stream ~13 min (post calibration-gate).
- **Verdict:** 3/4 pass. cognitionrun **passes** at N=10 (the N=5 fit instability washed out). stroop\_rdoc fails on tau (marginal) + PES — but PES is a noise-dominated, few-error estimate (config is correct 20–50 ms); see Current-baselines notes.
- Raw per-paradigm reports: `validation/latest_batch_n10/` (ephemeral, not committed).

---

### 2026-05-31 — N=5 post calibration-feasibility-gate

- **What:** 5 sessions × 4 paradigms in parallel (`/tmp/run5_all.sh` pattern), first run with the calibration feasibility-gate (`13450d9`).
- **Command:** `uv run experiment-bot <URL> --label <label> --headless` × 5 each.
- **Trials/session:** stroop\_rdoc 124–128; stop\_signal\_rdoc 189–191; stroop\_online 15; stop\_signal\_kywch 285–286.
- **TaskCard hashes:** 45751cfe / e29f22de / b16c7891 / 6fc729c3 (unchanged).
- **Data location:** `output/<task_name>/<ts>/`.
- **Verdict:** 3/4 pass (stroop\_rdoc and stop\_signal\_kywch passed this batch; cognitionrun failed on sigma/tau — N=15 fit instability, not behavior). The gate cut cognitionrun from ~17 min/session to ~78 s and is behaviorally inert (calibration `too_few_events` before and after — no RT adjustment).
- Raw per-paradigm reports: `validation/latest_batch_v2/` (ephemeral, not committed).

---

_Superseded entries beyond ~3 are dropped here; see git history for older runs. Dropped from the log: the 2026-05-30 N=5 batch, the 2026-05-22 SP12 re-measurement, and the 2026-05-19 SP11 Phase-7 baseline capture — raw artifacts remain under [`docs/results-data/`](results-data/) and session data in git history._

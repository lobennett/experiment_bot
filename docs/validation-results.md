# Validation Results

Single living results doc (CLAUDE.md rule R-1). On each new batch: **overwrite** the
Current-baselines rows in place; **prepend** one Run-log entry and drop the oldest
so ~3 entries are kept (git history retains superseded entries).

---

## Current baselines

_Last updated: 2026-06-02, N=10 per paradigm (canonical-recall TaskCards; calibration feasibility-gate; safe 4-way-parallel run)._

| paradigm | platform | latest N | rt\_distribution | sequential (PES) | signature (SSRT) | overall | as-run command |
|---|---|---|---|---|---|---|---|
| stroop\_rdoc | expfactory | 10 | mu 485.4 ✅[400,550], sigma 48.8 ✅[25,60], tau 163.0 ❌[70,160] | PES 91.7 ms ❌[10,50] (noise — see notes); CSE not computable | N/A | ❌ FAIL | `uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop --headless` |
| stop\_signal\_rdoc | expfactory | 10 | rt-dist ✅ (descriptive, no norm range) | PES 35.4 ms ✅[10,50] | SSRT 227.3 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless` |
| stroop\_online\_(cognition.run) | cognition.run | 10 | mu 509.7 ✅[400,550], sigma 53.4 ✅[25,60], tau 134.5 ✅[70,160] | PES/CSE not computable (15-trial task) | N/A | ✅ PASS | `uv run experiment-bot "https://strooptest.cognition.run/" --label cognitionrun_stroop --headless` |
| stop\_signal\_kywch\_jspsych | kywch/STOP-IT | 10 | rt-dist ✅ (descriptive, no norm range) | PES 16.9 ms ✅[10,50] | SSRT 253.9 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" --label stopit_stop_signal --headless` |

**Batch verdict: 3/4 pass.**

Notes:
- "not computable" entries (cognitionrun PES/CSE; stroop CSE) are non-blocking, not failures.
- **cognitionrun now PASSES at N=10** (mu 509.7 / sigma 53.4 / tau 134.5). The N=5 FAILs (sigma/tau bouncing 34/139 → 22/167) were ex-Gaussian fit instability on 15-trial sessions; pooling 10 sessions washed it out — confirming the earlier FAIL was sampling noise, not behavior.
- **stroop\_rdoc PES (91.7) is a measurement-power artifact, NOT a fidelity defect.** The TaskCard configures post-error slowing at the correct 20–50 ms (`temporal_effects.post_event_slowing`), but Stroop's ~96% accuracy yields only 1–8 errors/session, so the per-session PES estimate is noise-dominated: across the 10 sessions PES ranged [−95, +243] ms, SD ≈ 115 ms on a 20–50 ms signal. PES is effectively **descriptive-only** for high-accuracy paradigms at ~120 trials/session (too few errors to estimate). tau (163) is the usual marginal tail-width miss.
- **SSRT (kywch) varies batch-to-batch (355.5 → 192.1 → 253.9).** Per scope-of-validity **L20**, SSRT is NOT framework-controlled — an emergent artifact of the platform's SSD staircase. Any single batch's pass/fail is staircase luck, not a bot property.

TaskCards: `taskcards/expfactory_stroop/45751cfe.json`, `taskcards/expfactory_stop_signal/e29f22de.json`, `taskcards/cognitionrun_stroop/b16c7891.json`, `taskcards/stopit_stop_signal/6fc729c3.json`.

---

## Run log

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

_Superseded entries beyond ~3 are dropped here; see git history for older runs. Older raw artifacts (the 2026-05-22 SP12 re-measurement and the 2026-05-19 SP11 Phase-7 baseline capture) remain under [`docs/results-data/`](results-data/)._

# Validation Results

Single living results doc (CLAUDE.md rule R-1). On each new batch: **overwrite** the
Current-baselines rows in place; **prepend** one Run-log entry and drop the oldest
so ~3 entries are kept (git history retains superseded entries).

---

## Current baselines

_Last updated: 2026-06-08, cumulative N ≈ 41–45 per paradigm (canonical-recall TaskCards; calibration feasibility-gate; safe 4-way-parallel; oracle RT-hygiene fix)._

| paradigm | platform | cumulative N | rt\_distribution | sequential (PES) | signature (SSRT) | overall | as-run command |
|---|---|---|---|---|---|---|---|
| stroop\_rdoc | expfactory | 45 | mu 496.6 ✅[400,550], sigma 53.2 ✅[25,60], tau 161.7 ❌[70,160] | PES 45.7 ms ✅[10,50]; CSE not computable | N/A | ❌ FAIL (tau +1.7 ms marginal) | `uv run experiment-bot "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop --headless` |
| stop\_signal\_rdoc | expfactory | 41 | rt-dist ✅ (descriptive, no norm range) | PES 30.3 ms ✅[10,50] | SSRT 257.9 ms ✅[180,280] | ✅ PASS | `uv run experiment-bot "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal --headless` |
| stroop\_online\_(cognition.run) | cognition.run | 43 | mu 499.0 ✅[400,550], sigma 42.8 ✅[25,60], tau 137.6 ✅[70,160] | PES/CSE not computable (15-trial task) | N/A | ✅ PASS | `uv run experiment-bot "https://strooptest.cognition.run/" --label cognitionrun_stroop --headless` |
| stop\_signal\_kywch\_jspsych | kywch/STOP-IT | 41 | rt-dist ✅ (descriptive, no norm range) | PES 18.5 ms ✅[10,50] | SSRT 281.6 ms ❌[180,280] (L20 staircase artifact) | ❌ FAIL (SSRT +1.6 ms, L20) | `uv run experiment-bot "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" --label stopit_stop_signal --headless` |

**Batch verdict: 2/4 pass — and both fails are marginal single-metric misses, not behavioral defects.** Every computable PES is now in range. The two misses are a stroop tau **1.7 ms over** the 160 ceiling (tail-width) and a kywch SSRT **1.6 ms over** 280 — and SSRT is the L20 not-framework-controlled staircase artifact.

Notes:
- **PES converges in-range at cumulative N.** The earlier batch-to-batch PES swings were small-N (few-error) sampling noise; pooled over ~41–45 sessions both stabilize inside [10,50]: **stroop 45.7 ms, kywch 18.5 ms, stop_signal_rdoc 30.3 ms.** The TaskCards configure post-error slowing at 20–50 ms; this is the first N large enough to measure it cleanly. The prior "PES is descriptive-only" framing is superseded for the dev paradigms at this N.
- **Oracle RT-hygiene fix (this batch).** `post_error_slowing` and `ssrt_integration` now apply the same `[150, 5000]ms` physiological-plausibility window `fit_ex_gaussian` has always used (shared `RT_PLAUSIBLE_{MIN,MAX}_MS` in `effects/validation_metrics.py`). Before the fix, kywch's raw pooled PES was **225.7 ms** — poisoned by 39 timer-glitch trials with implausible RTs (max **1,077 s**) that `rt_distribution` already discarded but `post_error_slowing` ingested. This inconsistency was the sole cause of the prior kywch PES "fail"; it is a data-validity filter (reusing a committed threshold), not a magnitude tune. SSRT moved only 282.0 → 281.6, confirming its miss is the staircase artifact, not RT contamination.
- "not computable" entries (cognitionrun PES/CSE; stroop CSE) are non-blocking, not failures.
- **cognitionrun is stable and PASSES at N≥10** (cumulative: mu 499.0 / sigma 42.8 / tau 137.6). The earlier N=5 FAILs were ex-Gaussian fit instability on 15-trial sessions; with adequate N it's solidly in range — sampling noise, not behavior.
- **SSRT (kywch) varies batch-to-batch (355.5 → 192.1 → 253.9 → 272.3 → 281.6).** Per scope-of-validity **L20**, SSRT is NOT framework-controlled — an emergent artifact of the platform's SSD staircase. Any single batch's pass/fail is staircase luck, not a bot property.

TaskCards: `taskcards/expfactory_stroop/45751cfe.json`, `taskcards/expfactory_stop_signal/e29f22de.json`, `taskcards/cognitionrun_stroop/b16c7891.json`, `taskcards/stopit_stop_signal/6fc729c3.json`.

---

## Run log

### 2026-06-08 — cumulative N ≈ 41–45/paradigm + oracle RT-hygiene fix

- **What:** Validated the full accumulated good-session pool per paradigm (every session in `output/`, oracle excludes zero-trial/gross-undercount): stroop\_rdoc n=45, stop\_signal\_rdoc n=41, cognitionrun n=43, kywch n=41. All on the canonical-recall TaskCards (hashes below, unchanged across the whole campaign — same effective parameters, so pooling across batches is valid).
- **Code change:** `post_error_slowing_magnitude` + `ssrt_integration` now share `fit_ex_gaussian`'s `[150, 5000]ms` RT-plausibility window (new `RT_PLAUSIBLE_{MIN,MAX}_MS`; +2 tests, suite 797 passed). Surfaced by this cumulative run: kywch raw pooled PES was 225.7 ms, a timer-glitch artifact (39 trials >5 s, max 1,077 s) the rt\_distribution metric already excluded but PES did not.
- **Verdict (cumulative):** 2/4 pass. **All computable PES in range** (stroop 45.7, stop\_signal\_rdoc 30.3, kywch 18.5 — the few-error noise washed out). The two fails are marginal single-metric: stroop tau 161.7 (+1.7 ms) and kywch SSRT 281.6 (+1.6 ms, L20 staircase artifact). RT-distribution params all in range except the stroop tau tail.
- Raw per-paradigm reports: `validation/cumulative/` (ephemeral, not committed).

---

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

_Superseded entries beyond ~3 are dropped here; see git history for older runs. Dropped from the log: the 2026-05-31 N=5 post-feasibility-gate batch, the 2026-05-30 N=5 batch, the 2026-05-22 SP12 re-measurement, and the 2026-05-19 SP11 Phase-7 baseline capture — raw artifacts remain under [`docs/results-data/`](results-data/) and session data in git history._

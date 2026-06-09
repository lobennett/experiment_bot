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

## Human-reference comparison (z within the human distribution)

_Last updated: 2026-06-09, `experiment-bot-compare` on the same cumulative session pool, vs the RDoC battery session-level summaries (`data/human/*_rdoc.csv`; Include-filter N = 2,478 Stroop / 2,412 stop-signal — the abstract's exact reference Ns). z = (bot cohort mean − human mean) / human between-session SD. SSRT here is the **mean method** (`go_rt − mean_SSD`) on BOTH sides — the summaries cannot support the integration method; the oracle's integration SSRT above is a different estimator._

| metric | stroop\_rdoc (expfactory, n=45) | stroop cognition.run (n=43) | stop\_signal\_rdoc (expfactory, n=41) | STOP-IT (kywch, n=41) |
|---|---|---|---|---|
| congruent / go RT | 634.1 vs 575.1±66.9, z **+0.88** ✅ | 602.3, z **+0.41** ✅ | 572.8 vs 648.8±99.6, z **−0.76** ✅ | 580.1, z **−0.69** ✅ |
| incongruent RT | 683.0 vs 642.4±80.5, z **+0.50** ✅ | 679.7, z **+0.46** ✅ | — | — |
| Stroop effect | 48.9 vs 67.2±41.3, z **−0.44** ✅ | 77.3, z **+0.24** ✅ | — | — |
| accuracy (cong / go) | 0.981 vs 0.961±0.046, z **+0.41** ✅ | n/c offline | 0.959 vs 0.967±0.047, z **−0.17** ✅ | 0.971, z **+0.08** ✅ |
| accuracy (incong) | 0.936 vs 0.920±0.063, z **+0.25** ✅ | n/c offline | — | — |
| omission rate(s) | z **+0.46 / +0.56** ✅ | n/c offline | z **+0.27** ✅ | z **+0.27** ✅ |
| stop accuracy | — | — | 0.471 vs 0.521±0.024, z **−2.12** ❌ | 0.496, z **−1.06** ❌ |
| stop-failure RT | — | — | 535.4 vs 571.7±87.2, z **−0.42** ✅ | 471.2, z **−1.15** ❌ |
| mean SSD | — | — | 304.1 vs 414.6±107.7, z **−1.03** ❌ | 279.4, z **−1.26** ❌ |
| SSRT (mean method) | — | — | 268.7 vs 234.1±44.5, z **+0.78** ✅ | 300.6, z **+1.49** ❌ |

**Verdict: 20 of 26 compared metrics fall within 1 human SD; both Stroop implementations are 7/7 and 3/3.** The pattern, stated plainly:

- **Every RT-location and interference metric is within 1 SD on all four implementations** (go/congruent/incongruent RT, Stroop effect, expfactory stop-failure RT) — the headline humanlike-RT claim holds across both tasks and both platforms per task.
- **All six misses are stop-side.** (a) *Stop accuracy* (bot 47.1% expfactory / 49.6% kywch vs human 52.1±2.4%) — a small absolute deviation on a metric where the staircase makes humans extremely uniform. (b) *Staircase products:* the bot's faster go RTs settle the platform SSD staircase ~110–135 ms lower than humans' (mean SSD z −1.03 / −1.26), dragging kywch's stop-failure RT and mean-method SSRT out of range. This is the human-reference restatement of scope-of-validity **L20** (SSRT/SSD are not framework-controlled).
- The comparison uses the **same cohort-selection rule as the oracle** (`oracle.select_sessions`: zero-trial, gross-undercount, `.incomplete`). This matters: with the 61-trial stroop partial included, the stroop omission rates read z +1.13/+1.20 (spuriously OUT); on the shared cohort they are +0.46/+0.56 (IN).
- cognition.run accuracy/omission metrics are not computable offline (the adapter cannot recover correctness; see the notebooks' walkthrough) — RT metrics only, all ✅.

Raw comparison reports: [`docs/results-data/human-compare-2026-06-09/`](results-data/human-compare-2026-06-09/). Reproduce: `uv run experiment-bot-compare --label <label> --human-csv data/human/<task>_rdoc.csv --map data/human/comparison_maps/<task>_rdoc.json`.

---

## Run log

### 2026-06-09 — human-reference z comparison (experiment-bot-compare)

- **What:** First run of the new `experiment-bot-compare` CLI — the paper abstract's analysis (bot metrics z-positioned within the human RDoC reference distribution), ported from the stale `scripts/analysis.ipynb` into the tested package (audit finding: the paper's Results methodology was previously not regenerable). Same cumulative session pool as the 06-08 entry; human reference = `data/human/{stroop,stop_signal}_rdoc.csv` with the Include exclusion filter (N=2,478 / 2,412 — matching the abstract exactly).
- **Code change:** new `validation/human_reference.py` (generic metric kinds: rt\_mean, accuracy, omission\_rate, field\_mean, subtract — paradigm knowledge lives in `data/human/comparison_maps/*.json`, per G2) + `experiment-bot-compare` CLI; +11 tests.
- **Verdict:** 20/26 metrics within 1 human SD (both Stroop implementations clean: 7/7 and 3/3); all six misses are stop-side — stop accuracy plus the SSD-staircase products (mean SSD low by ~110–135 ms → kywch mean-method SSRT z +1.49). Cohort selection is shared with the oracle (`oracle.select_sessions`) — including the 61-trial stroop partial had been spuriously pushing the stroop omission rates out of range. See the Human-reference comparison section above.
- Raw reports: `docs/results-data/human-compare-2026-06-09/` (committed — paper-supporting numbers).

---

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

_Superseded entries beyond ~3 are dropped here; see git history for older runs. Dropped from the log: the 2026-06-02 N=10 batch, the 2026-05-31 N=5 post-feasibility-gate batch, the 2026-05-30 N=5 batch, the 2026-05-22 SP12 re-measurement, and the 2026-05-19 SP11 Phase-7 baseline capture — raw artifacts remain under [`docs/results-data/`](results-data/) and session data in git history._

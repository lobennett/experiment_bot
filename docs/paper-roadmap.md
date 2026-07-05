# experiment_bot — State of the Repository & Path to a Paper

_Authoritative audit, 2026-06-30. Grounded in verified findings against the
committed `main` tree. Refuted claims have been dropped. Where the findings
corpus and the actual source disagreed, the source wins — three corrections are
flagged inline (§2)._

---

## 1. Where the repository concretely is today

A working three-layer pipeline that turns a task URL into platform-native
behavioral data and a scored human-comparison. Everything below is present and
exercised on `main`.

**Pipeline (Reasoner → TaskCard → Executor → Oracle).** The Reasoner (LLM
Stages 1–6) scrapes a page's source + runtime JS, identifies the paradigm, and
emits a versioned, content-addressed `TaskCard` (ex-Gaussian μ/σ/τ per
condition, per-condition accuracy + omission targets, sequential-effect
configs, between-subject variance). A ~20-trial pilot validates stimulus
selectors against the live DOM. The Executor (Playwright) drives the live page,
sampling RTs/responses from the configured parameters. The Oracle scores the
resulting sessions against pre-committed meta-analytic norms.

**Five CLIs** (`pyproject.toml [project.scripts]`):
`experiment-bot` (run), `experiment-bot-reason`, `experiment-bot-extract-norms`,
`experiment-bot-validate` (oracle gate vs `norms/*.json`),
`experiment-bot-compare` (z vs human RDoC distribution).

**Tests + CI.** 756 test functions across `tests/`; GitHub Actions CI gate;
negative-assertion tests enforce the G2 "no paradigm vocabulary in the bot
library" rule (e.g. `assert "congruency_sequence" not in EFFECT_REGISTRY`).

**Committed data (a self-contained submission package).** Submission-era bot
sessions live in `output/` under **task-name** dirs:
`stop_signal_task_(rdoc)` (35), `stroop_(rdoc)` (31),
`stop-signal_task_(stop-it)` (29), `stroop_online` (29) — 124 dirs total
(plus a few stray 1-session dirs from later regenerations:
`stroop_rdoc`, `stop-it_stop_signal_task_(jspsych)`, `stroop_task_(color-word)`).
Human reference: `data/human/{stroop,stop_signal}_rdoc.csv` (Include-filtered
N = 2,478 / 2,412, matching the abstract's reference Ns). Raw trial-level
`data/human/{stroop,stop_signal}_eisenberg.csv` also present (rt/condition/correct
columns) but **not** wired into any norms or comparison map. Norms:
`norms/{conflict,interrupt,working_memory}.json`. Comparison maps:
`data/human/comparison_maps/{stroop,stop_signal}_rdoc.json`.

**Committed results.** `docs/validation-results.md` (single living results doc,
R-1). Last oracle batch 2026-06-08 (cumulative N ≈ 41–45/paradigm): **2/4 dev
paradigms pass** — `stop_signal_rdoc` ✅ and `stroop_online_(cognition.run)` ✅;
`stroop_rdoc` ❌ (τ 161.7 ms, 1.7 ms over the 160 ceiling) and
`stop_signal_kywch_jspsych` ❌ (SSRT 281.6 ms, 1.6 ms over 280, flagged as the
L20 SSD-staircase artifact, not a bot property). Human-reference z-comparison
2026-06-09: **20/26 metrics within 1 human SD**; both Stroop implementations
clean (7/7 and 3/3); all six misses are stop-side (stop accuracy + SSD-staircase
products).

**Provenance + reproducibility.** `run_metadata.json` records `session_seed` +
`taskcard_sha256`; `taskcard.loader.load_by_hash` enables hermetic replay via
`--taskcard-sha256` (opt-in; default load is newest-by-mtime). `scripts/reproduce.sh`
documents as-run URLs (expfactory previews are ephemeral).

**Honest internal audit already on record.** `docs/research-review.md` (SP17):
104 raw findings → 16 verified → 15 surviving. `docs/stage3-citation-history.md`
documents the Stage-3 citation-fabrication history. This roadmap builds on those.

---

## 2. The honest gap between the abstract's claims and the instantiation

**The single most important framing for the whole paper: the bot simulates a
participant; it does not solve the task.** Scope-of-validity L1 states it
plainly — the bot "samples RTs from parameters the Reasoner configured, not
derived by performing the task." It does not read a stimulus, decide a response,
and emit a keypress on the basis of that decision. It samples an RT from a
pre-set ex-Gaussian, draws accuracy from a pre-set Bernoulli target, and adds
configured temporal nudges. Every "humanlikeness" result below is therefore
**output-distribution equivalence**, never mechanism equivalence. The abstract
currently frames the bot as "completing the task" / "agentic AI… can produce
human-like performance" with no explicit simulate-vs-solve subheading. That
distinction must be elevated to a heading in Methods/Discussion or every C2/C3
result reads as a stronger claim than the evidence supports.

| Claim | What the bot mechanism actually does | What the committed data supports | Sharpest falsification test | Verdict |
|---|---|---|---|---|
| **C1 — "given only an experiment URL … the bot completes the task"** | URL → scrape → staged LLM reasoning → versioned TaskCard → ~20-trial pilot → cached card replayed by the Executor. **Correction:** the abstract does **not** say "in a single API call" (the claims-matrix finding misquoted it); it states the card is "cached (content-addressed by hash) and reused" and "no session in the evaluated cohorts required LLM calls at execution time," with a bounded ≤10-call adaptive-nav fallback. | The pipeline genuinely runs URL→TaskCard→session for the dev paradigms. But a session is **not** produced from the URL alone: it needs a per-paradigm `platform_adapter` (`validation/platform_adapters.py`), a pre-committed `norms/<class>.json`, a comparison map, and — for unfamiliar flows — the runtime adaptive-nav budget. Scope L24: "only a URL requires scaffolding." | Point the bot at a genuinely novel URL on an unsupported platform family with **zero** pre-staged adapter/norms/map and require a scored session. | **Overclaim as worded.** The reasoning-from-URL step is real; end-to-end "from the URL alone" is not. Reframe to "generalization within supported platform families" + a supported-platforms × paradigm-class table. |
| **C2 — humanlike MEANS** (go RT, stop accuracy, SSRT, congruent/incongruent RT, Stroop interference, accuracy, omission within the human distribution) | RTs sampled from configured ex-Gaussian μ/σ/τ; accuracy from configured per-condition Bernoulli targets; SSRT is **not** sampled — it emerges from the platform's SSD staircase interacting with the bot's go-RTs (no race model; scope L20). | Partial. 20/26 z-metrics within 1 SD (validation-results 06-09). **All RT-location/interference metrics within 1 SD on all four implementations.** All six misses stop-side: stop accuracy (z −2.12 / −1.06), mean SSD ~110–135 ms low, dragging kywch stop-failure RT and mean-method SSRT out. **Correction #2 (a genuine, paper-blocking discrepancy):** the abstract's headline numbers do **not** match the committed validation-results. Abstract: stop accuracy 53.2% (z +0.45), congruent 706±42 ms (z +1.95), incongruent 798±56 ms (z +1.93), go RT 622 ms (z −0.27), SSRT 214 ms. Committed 06-09: stop accuracy 47.1%/49.6% (z −2.12/−1.06), congruent/go RT 634.1 (z +0.88), incongruent 683.0 (z +0.50). The abstract's numbers appear **nowhere** in `output/` or `docs/results-data/` — they are from a superseded batch. | Re-run the committed cohort under `experiment-bot-compare` and diff against the abstract table. (Already effectively done: they disagree.) Then a per-subject KS/TOST test of bot vs human (§5). | **Partially supported, but the abstract is numerically stale.** The qualitative claim (RT location + interference within 1 SD) holds on the committed cohort; the **specific z-values in the abstract are out of date and must be reconciled before submission.** SSRT must be relabeled an emergent platform artifact, not a controlled fidelity metric. |
| **C3 — humanlike TEMPORAL effects** (positive lag-1 RT autocorrelation + post-error slowing, comparable to human) | Lag-1: `handlers.apply_autocorrelation` applies a configured AR(1) pull `φ·(prev_rt − mean_rt)` (φ is a TaskCard parameter, **not** emergent). PES: `handlers.apply_post_event_slowing` adds a configured delta (TaskCard 20–50 ms) after an error. | Output statistics land in plausible territory (abstract: lag-1 r .10±.09 / .16±.10; PES 37±54 / 60±59 ms; validation-results: PES 30.3 / 45.7 / 18.5 ms in [10,50]). **But:** lag-1 autocorr has **`range: null` in both `conflict.json` and `interrupt.json`** with explicit `no_canonical_range_reason` ("essentially never reported in stop-signal meta-analyses"). The oracle treats null-range as **non-gating** (`_in_range` → `None`). So the bot can produce *any* lag-1 value and pass. The abstract calls lag-1 "consistent with human performance" with **no human autocorr range cited anywhere.** | (1) Extract or cite a human lag-1 autocorr distribution and z-compare per subject. (2) Ablate the configured effect (disable φ/PES) and show the metric leaves the range — proving the effect is doing the work, not the base sampler. | **C3 is the weakest claim: output-level pattern present, but "comparable to human" is currently un-operationalized and partly untestable.** No human comparison range for lag-1; PES is a cohort point-estimate gated by a tolerance band, not an inferential comparison. Mechanistically the effects are configured, not emergent — output equivalence only. |

**Correction #3 (citation integrity, applies under every claim).** Stage 3
fabricated a large fraction of committed citations (invented DOIs; real DOIs
paired with quotes/pages the papers do not contain — `docs/stage3-citation-history.md`).
`norms/conflict.json`'s μ-range attribution to Matzke & Wagenmakers 2009 points
at a diffusion *simulation*, not an empirical meta-analytic range. Stage 3 has
since been refactored to propose→verify with honest abstention, but the
**committed** TaskCards and the LLM-asserted ranges in `norms/*.json` are not
trustworthy. Until re-extracted, the paper must call behavioral parameters
**model-prior estimates**, and rest defensibility on the oracle's gating
arithmetic — not on the citation quotes (research-review §3/§4:
"anti-circularity rests on arithmetic, not citations").

---

## 3. What is missing to make this a defensible paper

Prioritized. Each item names its finding lens.

### P0 — blocking for a credible submission

- **P0-1. Reconcile the abstract's numbers with the committed results.**
  (claims_matrix C2a/C2b.) The abstract's 706 ms / 53.2% / z +1.95 do not match
  `validation-results.md` (634.1 / 47.1% / z +0.88) and appear in no committed
  artifact. Either migrate the paper to the 06-09 numbers (cite the commit hash)
  or document an erratum. Do not submit with discrepant z-scores.
- **P0-2. Citation re-extraction or honest relabeling.** (repo_state, claims_matrix.)
  Run the canonical-recall Stage 3 over the dev-4 + held-out TaskCards, OR state
  in Methods that committed parameters are model-prior estimates with unreliable
  citation quotes. Update `norms/*.json` attributions (Matzke → honest abstention
  or a real meta-analysis). Add a norms-verification step to CI.
- **P0-3. SSRT relabeled as emergent platform artifact.** (repo_state, field_norms.)
  Remove SSRT from any "bot control" framing. Keep the Verbruggen validity gate
  (`SSRT_MIN_STOP_TRIALS=50`, `SSRT_PRESPOND_RANGE=(0.25,0.75)`) but document the
  pooled-cohort caveat. The C2 headline should rest on go-RT, stop accuracy
  (accounting for the lower staircase SSD), and inhibition rate.
- **P0-4. Operationalize C3 or downgrade it.** (temporal_stats, critical.) Lag-1
  has no human comparison range and is non-gating; "comparable to human" is not
  defined quantitatively. Either build a per-subject human lag-1/PES reference
  (the `*_eisenberg.csv` trial-level files can supply it) and z-compare, or
  reframe C3 as "reported descriptively, not gated."

### P1 — required for "defensible," not just "honest"

- **P1-1. Per-subject estimation, not pooling.** (per_subject + field_norms,
  major.) The oracle pools raw trials across all sessions into one pseudo-subject
  (`_gather_rts`, `_compute_pes`, `_compute_ssrt`) and emits one cohort number.
  The field computes one value per subject, then summarizes — that is the unit a
  reviewer evaluates and the only structure that supports between-subject SD,
  z-scores, and power. This is the §4 deliverable.
- **P1-2. Statistical rigor: multiplicity + equivalence.** (repo_state,
  field_norms.) The oracle AND-aggregates independent sub-tests (μ/σ/τ; lag-1 +
  PES) with no Bonferroni/FDR, and gates on naive point-in-range rather than TOST
  equivalence (Lakens 2017). Either apply a correction and recompute verdicts, or
  explicitly reframe the gate as a descriptive screen (scope L22 already half-does
  this) and add TOST where an equivalence *claim* is made.
- **P1-3. Pre-registration + power.** (repo_state.) No OSF registration, no power
  calc. Register the analysis plan (metrics, gating rules, cohort selection)
  before any further runs; estimate N to detect Stroop-τ / SSRT effects at 80%.
- **P1-4. Field-standard estimator fixes** (field_norms, all major):
  (a) SSRT integration must replace go-omissions with max-RT before the quantile
  (Verbruggen 2019 rec #8) — currently omissions are dropped (`oracle.py:155`,
  `:277`); (b) add the race-model validity gate: abstain when mean signal-respond
  RT > mean go RT (rec #7); (c) PES should use the Dutilh 2012 robust triplet
  estimator `mean(RT_{E+1} − RT_{E−1})`, not the drift-confounded
  `mean(post-error) − mean(post-correct)` (`validation_metrics.py:152`);
  (d) raise the ex-Gaussian per-fit floor toward ~100 RTs (currently `< 5` →
  NaN) or flag sub-floor fits low-confidence, especially τ.
- **P1-5. Generalization breadth.** (repo_state, claims_matrix.) Dev = 2 classes
  (conflict, interrupt); held-out = n-back (N=5, all descriptive, no gates) +
  `stop_signal_with_integrated_memory` (N=1, SSRT 458 ms vs [180,280]). One N=1
  out-of-norm point cannot support a generalization claim. Run N=5 on the
  integrated-memory paradigm and/or 1–2 fresh classes (Flanker/Simon, RDM) with
  pre-registered pass criteria.

### P2 — strengthens, optional for v1

- **P2-1. Ablation table.** (repo_state, minor.) Disable PES / lag-1 / drift one
  at a time (N=1/paradigm) and report τ/PES/SSRT to demonstrate each mechanism's
  necessity. If out of scope, note as a limitation.
- **P2-2. Adversarial/robustness boundary statement.** (repo_state, minor.) One
  Discussion subsection on failure modes (partial page load, broken selectors,
  platform refactor → TaskCard regeneration).
- **P2-3. Hermetic-replay regression test.** (other_findings, minor.) CI test:
  `--seed` + `--taskcard-sha256` reproduces a known session's metrics.
- **P2-4. Threat-model calibration.** (repo_state, minor.) Distinguish "proof
  that bot performance is feasible" from "evidence that bots are widespread
  today." Cite Westwood 2025 (surveys) + this work (speeded tasks); flag
  adversary adoption as open.

---

## 4. Deliverable spec — per-subject reliable-metrics CSVs for an external expert

**Why this is the critical missing piece.** `human_reference.compare_metrics`
already computes per-session metrics (`per_session.append(bot_session_metrics(...))`,
`human_reference.py:185`) but **discards them**, returning only pooled
`bot_mean`/`bot_sd`/`z` per metric (`human_reference.py:198–207`). The oracle
pools raw trials. The **only** per-subject export path is the untested, demoted
`scripts/analysis.ipynb` → `data/bot/{stop_signal,stroop}.csv` (1–2 rows each,
hardcoded task-name patterns, no ex-Gaussian/SSRT/lag-1/PES columns). A cognitive-
control expert cannot benchmark individual sessions today. The fix reuses
production-tested infrastructure; it does **not** require new estimators.

### 4.1 Where the code should live

**Extend the tested package; do not resurrect the notebook.** Add a new module
`src/experiment_bot/validation/per_subject_export.py` and a CLI
`experiment-bot-per-subject` (`pyproject.toml [project.scripts]`). Reuse
`resolve_trial_loader` + `load_human_reference` from `compare_cli.py`, and call
`bot_session_metrics` per session. Officially deprecate `scripts/analysis.ipynb`
(its `lag1_autocorr`/`post_error_slowing` already exist as tested
`effects/validation_metrics` functions — the notebook is redundant). Full test
coverage required, including the block-boundary and sparse-fit risks below.

### 4.2 Resolve the output-dir / adapter-label mismatch

`PLATFORM_ADAPTERS` (`platform_adapters.py:283`) registers
`stop_signal_rdoc`, `stroop_rdoc`, `stop_signal_kywch_jspsych`,
`stroop_online_(cognition.run)` (+ URL-label aliases `expfactory_*`,
`stopit_stop_signal`, `cognitionrun_stroop`). The submission `output/` dirs are
named differently. Add explicit aliases under a comment
`# Main submission-era task.name → label mapping`:

| `output/` dir (submission) | adapter label | sessions |
|---|---|---|
| `stop_signal_task_(rdoc)` | `stop_signal_rdoc` | 35 |
| `stroop_(rdoc)` | `stroop_rdoc` | 31 |
| `stop-signal_task_(stop-it)` | `stop_signal_kywch_jspsych` | 29 |
| `stroop_online` | `stroop_online_(cognition.run)` | 29 |

(Verify counts: 35+31+29+29 = 124; the abstract's per-paradigm Ns 41–45 are the
**later cumulative SP-era pool**, not the submission dirs — the CLI must let the
user point at either by `--output-dir`.) Exclude `.incomplete` and zero-trial
dirs (the oracle's `select_sessions` rule), which `compare_metrics` already does.

### 4.3 Bot and human computed by the SAME estimators

Both sides flow through `bot_session_metrics` / `human_metric_values` driven by
the committed `comparison_maps/*.json`, so a given metric is the identical
function on bot and human. Ex-Gaussian uses `fit_ex_gaussian`; SSRT (integration)
uses `ssrt_integration` with the Verbruggen rec #8 omission-replacement fix
(P1-4a); PES uses the Dutilh robust triplet (P1-4c); lag-1 uses
`lag1_autocorrelation` **with the RT-plausibility filter added** (it currently
lacks one — `validation_metrics.py:143`) and **within-session only** (never
across the concatenation seam). Human lag-1/PES require extending the comparison
maps + `human_reference` kinds (today they cover rt_mean/accuracy/omission/
field_mean/subtract only) — the `*_eisenberg.csv` trial-level files supply the
raw sequences.

### 4.4 Per-task CSV schema (one row per subject)

**`per_subject_stop_signal.csv`**

| column | source / estimator |
|---|---|
| `sub_id` | session-dir name |
| `run_date` | ISO from `run_metadata.json` |
| `platform` | adapter label |
| `n_trials`, `incomplete` | trial count; `.incomplete` marker |
| `go_rt_mean`, `go_rt_median` | go-trial correct RTs |
| `go_accuracy`, `go_omission_rate` | go trials |
| `p_respond_given_signal` | stop trials with a response / stop total |
| `mean_ssd`, `min_ssd`, `max_ssd`, `final_ssd` | SSD staircase |
| `stop_accuracy` | 1 − p(respond\|signal) |
| `stop_failure_rt_mean` | unsuccessful-stop RTs |
| `mu`, `sigma`, `tau` | `fit_ex_gaussian` on go RTs (NaN if < floor) |
| `ssrt_integration` | `ssrt_integration` w/ omission→max-RT replacement (rec #8) |
| `ssrt_valid` | race-model gate: NaN if signal-respond RT > go RT, or counts/p out of bounds (rec #7) |
| `lag1_autocorr` | within-session, RT-plausibility-filtered |
| `pes_robust_ms` | Dutilh triplet `mean(RT_{E+1} − RT_{E−1})` |
| `z_<metric>`, `within_1sd_<metric>` | per mapped metric: `(bot − human_mean)/human_sd` |

**`per_subject_stroop.csv`**

| column | source / estimator |
|---|---|
| `sub_id`, `run_date`, `platform`, `n_trials`, `incomplete` | as above |
| `congruent_rt`, `incongruent_rt` | per-condition correct RTs |
| `stroop_effect_ms` | incongruent − congruent RT (first-class metric) |
| `congruent_accuracy`, `incongruent_accuracy` | per condition |
| `congruent_omission_rate`, `incongruent_omission_rate` | per condition |
| `mu`, `sigma`, `tau` | `fit_ex_gaussian` (per condition if N permits, else pooled-go; NaN-graceful for 15-trial cognition.run) |
| `lag1_autocorr`, `pes_robust_ms` | as above |
| `z_<metric>`, `within_1sd_<metric>` | per mapped metric |

NaN-handling: sparse sessions (cognition.run ~15 trials split by condition) yield
NaN μ/σ/τ; export must write NaN, not crash. Block-awareness: lag-1/PES must skip
cross-block pairs — adapters do not populate `block_num` today, so either populate
it where the source carries it or document a single-block assumption explicitly.

### 4.5 Human-readable companion report

Alongside each CSV, emit `per_subject_<label>_report.md`: (1) header (task, date,
norms reference, TaskCard hash); (2) Methods (cohort-selection rule, adapters,
estimator definitions + citations, exclusion rule); (3) Results summary table
(bot N/mean/SD vs human N/mean/SD/z per metric, within-1SD flag); (4) pedagogical
notes per metric, including non-gating flags (e.g. "lag1_autocorr: no canonical
human range — reported descriptively"; "SSRT abstained: outside Verbruggen
validity bounds"). CLI: `--label --human-csv --map --output-dir --metrics
(subset) --format {csv,json,xlsx} --reports-dir`.

**Estimator citations (URLs).** SSRT integration + validity gates + report-all:
Verbruggen et al. 2019, eLife — https://elifesciences.org/articles/46323 .
Robust PES: Dutilh et al. 2012, J Math Psychol —
https://www.sciencedirect.com/science/article/abs/pii/S0022249612000454 .
PES × RSI dependence: Danielmeier & Ullsperger 2011 —
https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2011.00233/full .
ex-Gaussian sample-size: Lacouture & Cousineau 2008 —
https://www.researchgate.net/publication/49619434 ; τ instability: Matzke &
Wagenmakers 2009 — https://link.springer.com/article/10.3758/PBR.16.5.798 .
Equivalence/TOST: Lakens 2017 —
https://journals.sagepub.com/doi/10.1177/1948550617697177 .
1/f vs AR(1) serial structure: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9423631/ .
Online-RT QC conventions: https://link.springer.com/article/10.3758/s13428-016-0783-4 .

---

## 5. Adversarial claim-testing harness spec

Goal: replace point-in-range screening with the tests a skeptical cognitive-
control reviewer would actually run. All bot and human metrics go through the
**identical** §4 estimators.

**C2 (means), per-subject.** Produce the per-subject metric arrays (§4) for bot
and human on each paradigm. For each metric:
- **Distribution-level test:** two-sample Kolmogorov–Smirnov (and Mann–Whitney U
  as a location-robust companion) on the bot vs human per-subject distributions.
  A *non-significant* KS is weak evidence of similarity; report it as such.
- **Equivalence (TOST):** specify equivalence bounds (e.g. the published human
  range, or ±0.5 human SD) and run TOST (Lakens 2017). This is the only test
  that licenses "within human range" as a *claim* rather than an observation.
  Report bot point estimate + CI overlaid on the human range, never a bare
  pass/fail.
- **Multiplicity:** across the ~7–10 metrics per paradigm, apply Benjamini–Hochberg
  FDR (or Bonferroni) and report corrected as well as raw decisions. Record the
  choice in `norms/*.json` (`multiplicity_correction` field) and in Methods.

**C3 (temporal), per-subject.** Compute per-subject lag-1 r and robust PES on
both bot and human (the `*_eisenberg.csv` raw sequences enable the human side).
Then z-compare and TOST exactly as C2. For lag-1, report series length n and a
CI, acknowledge it captures only short-range AR(1)-like structure (add DFA /
spectral slope if long-range 1/f is ever claimed), and **keep the norm null** —
the honest position is "reported, not gated" until a human range exists.

**Adversarial probes (at least one is mandatory for the paper).**
1. **Bot-vs-human classifier.** Train a simple classifier (logistic / gradient-
   boosted) on the per-subject metric vectors to discriminate bot from human.
   Report AUC. The defensible humanlikeness claim is "near-chance AUC on the
   gated metrics"; a high AUC localizes *which* metric gives the bot away (the
   prediction is: SSD/SSRT staircase products and absolute Stroop RT, per the
   stop-side misses).
2. **Unconfigured-effect probe.** Pick an effect the TaskCard does **not**
   configure (e.g. a congruency-sequence/CSE contrast on a paradigm where it was
   left disabled) and test whether the bot reproduces it. A human would; a
   correctly-scoped bot should **not** (G3). Absence here is a feature — it
   demonstrates the bot only shows configured effects — and presence would expose
   leakage. Either result is informative and honest.
3. **Ablation as causal check (ties to P2-1).** Disable φ / PES and confirm the
   corresponding metric leaves its range — proving the configured mechanism, not
   the base sampler, produces the C3 effect.

---

## 6. Recommended next steps (sequenced)

1. **[code, now]** Build `per_subject_export.py` + `experiment-bot-per-subject`
   CLI reusing `bot_session_metrics` / `human_reference`; add the submission-dir
   adapter aliases (§4.2). Tests including block-boundary + sparse-fit. → unblocks
   everything downstream.
2. **[code, now]** Apply the field-standard estimator fixes (P1-4): SSRT
   omission→max-RT replacement + race-model gate; robust Dutilh PES; lag-1
   RT-filter + within-session; raise ex-Gaussian floor / low-confidence flag. Add
   regression tests. (These change committed numbers — do it before any
   measurement run, never after seeing results, per the operational rules.)
3. **[code, now]** Build the §5 harness: KS/Mann–Whitney + TOST + FDR + the
   bot-vs-human classifier + the unconfigured-effect probe. Tests.
4. **[writing, now]** Reconcile the abstract's stale numbers against the committed
   06-09 results (P0-1); add the simulate-vs-solve heading; relabel SSRT as
   emergent (P0-3); reframe C3 as descriptive-or-operationalized (P0-4); reframe
   C1 to "generalization within supported platform families" + supported-platforms
   table. Cite `validation-results.md` by commit hash.
5. **[code/writing, now]** Citation remediation (P0-2): run canonical-recall
   Stage 3 over committed TaskCards OR write the model-prior-estimate framing;
   fix `norms/*.json` attributions; add the CI norms-verification step.
6. **[writing, now]** Pre-register the analysis plan on OSF (P1-3) **before** any
   new live run; include the §5 tests, gating rules, cohort selection, and a power
   estimate from current N.
7. **[measurement, live]** Re-run the dev-4 cohort through the fixed estimators +
   §5 harness; regenerate `validation-results.md` and the per-subject CSVs.
8. **[measurement, live]** Generalization breadth (P1-5): N=5 on
   `stop_signal_with_integrated_memory` and 1–2 fresh paradigm classes
   (Flanker/Simon, RDM) under pre-registered criteria. Do not iterate held-out
   prompts to make them pass — document failures (G1 discipline).
9. **[code/measurement, optional]** Ablation table (P2-1) and hermetic-replay CI
   regression (P2-3).
10. **[writing]** Assemble Results around the per-subject tables + TOST/classifier
    figures; Limitations explicitly addresses each `docs/research-review.md`
    recommendation (addressed / deferred); add the robustness-boundary and
    threat-model-calibration subsections (P2-2, P2-4).

---

## Citations

**Code references (path:line on `main`).**
- `pyproject.toml` `[project.scripts]` — five CLIs.
- `src/experiment_bot/validation/platform_adapters.py:283` — `PLATFORM_ADAPTERS`
  dispatch (labels `stop_signal_rdoc`, `stroop_rdoc`, `stop_signal_kywch_jspsych`,
  `stroop_online_(cognition.run)` + `expfactory_*` / `stopit_stop_signal` /
  `cognitionrun_stroop` aliases); `:318` `resolve_trial_loader`.
- `src/experiment_bot/validation/human_reference.py:177–185` — per-session metrics
  computed; `:198–207` — only pooled `bot_mean`/`bot_sd`/`z` returned (per-subject
  rows discarded).
- `src/experiment_bot/validation/oracle.py:46–47` — `SSRT_MIN_STOP_TRIALS=50`,
  `SSRT_PRESPOND_RANGE=(0.25,0.75)`; `:84` `_in_range` (point-in-range, non-
  inferential); `:142–155` `_gather_rts` pools across sessions; `:206`
  `_compute_lag1`; `:212` `_compute_pes`; `:248–307` `_compute_ssrt` (omissions
  dropped at `:155`/`:277`, no race-model gate); `:310` `_compute_between_subject_sd`
  (only per-session fitter).
- `src/experiment_bot/effects/validation_metrics.py:20–21` `RT_PLAUSIBLE_{MIN,MAX}_MS`
  150/5000; `:85` `fit_ex_gaussian` (`:100` `< 5` → NaN); `:143` `lag1_autocorrelation`
  (no RT filter); `:152` `post_error_slowing_magnitude` (simple difference, not
  robust); `:196` `ssrt_integration`.
- `norms/conflict.json:47` / `norms/interrupt.json:18` — `lag1_autocorr` `range: null`,
  non-gating; `norms/conflict.json:5` μ-range (Matzke 2009 simulation attribution).
- `Task Turing Bot Abstract.md` lines 12 (Methods, cached-card/no-execution-LLM),
  14 (Results: 53.2% / 706 / 798 / z +1.95 / lag-1 .10–.16 / PES 37–60).
- `docs/validation-results.md` — 2/4 oracle (06-08); 20/26 z (06-09: 634.1/47.1%/etc.).
- `scripts/analysis.ipynb`, `data/bot/{stop_signal,stroop}.csv` — legacy untested
  per-subject export. `data/human/{stroop,stop_signal}_eisenberg.csv` — raw
  trial-level human sequences (unused by norms/maps).
- `docs/research-review.md`, `docs/stage3-citation-history.md`, `docs/scope-of-validity.md`
  (L1 simulate-not-solve, L20 SSRT-not-controlled, L22 descriptive-screen, L24
  scaffolding-beyond-URL).

**External references (estimator + norm choices).**
- Verbruggen et al. 2019, eLife — SSRT integration, validity gates, report-all:
  https://elifesciences.org/articles/46323
- Dutilh et al. 2012, J Math Psychol — robust post-error-slowing estimator:
  https://www.sciencedirect.com/science/article/abs/pii/S0022249612000454
- Danielmeier & Ullsperger 2011, Front Psychol — PES × RSI dependence:
  https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2011.00233/full
- Lacouture & Cousineau 2008 — ex-Gaussian fitting / sample size:
  https://www.researchgate.net/publication/49619434
- Matzke & Wagenmakers 2009, Psychon Bull Rev — ex-Gaussian / τ instability:
  https://link.springer.com/article/10.3758/PBR.16.5.798
- Lakens 2017, SPPS — TOST equivalence testing:
  https://journals.sagepub.com/doi/10.1177/1948550617697177
- RT serial structure (1/f vs AR(1)):
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9423631/ ,
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4104308/
- Online-RT QC conventions:
  https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2021.675558/full ,
  https://link.springer.com/article/10.3758/s13428-016-0783-4

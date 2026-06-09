# Research Review: experiment_bot

_Adversarial, reviewer-facing review produced 2026-06-08 by a multi-agent
research workflow (4 codebase-audit lenses + 5 web-benchmark angles → 104 raw
findings → top 16 load-bearing claims 3-vote adversarially verified → 15
survived, 1 refuted). Code claims cite `path:line`; external claims cite `[n]`
in the Citations list. This is an analysis document — measured values are owned
by `docs/validation-results.md` (rule R-2) and cited here, not re-established._

**Executive verdict.** The central thesis — "Claude performs a cognitive task given only a URL, producing a structured understanding of the code and responses" — holds only in a heavily qualified form. The framework demonstrably produces a structured artifact (the TaskCard) and drives a live page to completion on held-out paradigms (`stop_signal_with_integrated_memory`: 666 trials, all 5 conditions, SP16). But the bot does not *solve* tasks in the cognitive sense: it executes a stimulus-response protocol and emits reaction times *sampled from parameters the Reasoner configured*, not derived by performing the task. "Only a URL" is also an overstatement — the pipeline depends on platform-default navigation backfills, paradigm adapters, pre-committed norms files, and (on held-out runs) a session-time LLM adaptive-nav budget. The structured-understanding claim is partly undercut by the project's own admission that committed citation quotes/pages are fabricated and untrustworthy (CLAUDE.md G4). The honest framing is: a working web-automation + behavioral-simulation pipeline with real generalization signal, gated by a statistically underpowered, point-estimate oracle whose anti-circularity rests on arithmetic, not on a verified citation trail.

## 1. Thesis integrity (the central claim)

- **Simulate, not solve.** The bot does not compute task answers from stimuli; it samples RTs and responses from Reasoner-configured parameters. Generic mechanisms (`lag1_pair_modulation`, `post_event_slowing`, `linear_drift`) are *configurations*, not task performance (CLAUDE.md G2). A passing RT distribution reflects a well-tuned sampler, not cognition.
- **"Only a URL" requires scaffolding.** Beyond the URL, a session depends on: platform-default navigation phases backfilled when the LLM under-specifies them (`reasoner/platform_defaults.py`, SP15); per-paradigm platform adapters for scoring (`validation/platform_adapters.py`); pre-committed norms files; and, on held-out paradigms, a session-time LLM adaptive-nav budget of 10 steps (SP16, `_adaptive_nav_step`). The held-out 666-trial run used 10 adaptive-nav steps — i.e. the URL alone did not navigate it.
- **Structured understanding is real but compromised.** The TaskCard is a genuine structured representation (stimulus/response rules, navigation, parameters). But its citation layer is self-described as fabricated (invented DOIs; real DOIs paired with quotes the papers do not contain), so the "understanding" cannot currently be audited against sources (CLAUDE.md G4, `supported`).
- **Reviewer takeaway.** The defensible claim is narrower than the abstract: Claude can construct a replayable protocol from a page and emit behaviorally plausible data. It cannot be said to "perform the cognitive task."

## 2. Generalizability (G1)

- **Held-out evidence exists and is non-trivial.** `stop_signal_with_integrated_memory` (an untuned, held-out paradigm) produced a TaskCard via the Stage 6 walker and 1 session of 666 trials across all 5 conditions, with race-model ordering intact (stop-fail 505ms < go 826ms) (CLAUDE.md:389-398, `supported`).
- **But the strongest held-out result is N=1 and out-of-norm.** SSRT was 458ms versus the [180,280]ms norm — well outside range — attributed to dual-task load plus the bot's systemic SSRT-high pattern (CLAUDE.md:389-398). A single session cannot establish behavioral generalization; it establishes pipeline reach.
- **Leak points remain.** Platform-default backfills and per-paradigm adapters are paradigm-adjacent infrastructure. They are defended as "infrastructure recognition, not overfitting" (SP15), but a reviewer should note that each new platform/paradigm class still requires an adapter (`validation/platform_adapters.py`) and may require a defaults entry — so "no code changes" (G1) holds for paradigms within already-supported platform families, not universally.
- **History of failure is documented honestly.** SP3 falsified G1 for Flanker + n-back at Stage 2; later SPs recovered them. This honest trail is a strength, but it shows generalization is iteratively engineered, not emergent.

## 3. Analysis-code correctness

- **SSRT is computed without the standard validity gates** (`supported`). `_compute_ssrt` checks only that go RTs, stop trials, and SSD samples are non-empty (`src/experiment_bot/validation/oracle.py:270`), then calls integration-method SSRT. Verbruggen et al. 2019 require ≥50 stop trials and p(respond|signal) within 0.25–0.75 before estimating; 25 stop trials "rarely produced reliable estimates" [5]. The oracle enforces neither bound, so it will emit an SSRT number from data the consensus method says is uninterpretable.
- **Ex-Gaussian is fit to as few as 5 samples** (`supported`). `src/experiment_bot/effects/validation_metrics.py:100` returns NaN only when `len(samples) < 5`. The methodological literature places the floor far higher: ~40 trials/cell for low-bias ML, ~100+ recommended, and tau (the tail) — exactly what the conflict norms gate on — is the most sample-hungry parameter [4]. (Mitigated in practice by pooling across sessions before fitting, but the guard itself is permissive.)
- **Point-estimate gating with no multiple-comparison control** (`supported`). `_in_range` is a binary in/out test (`oracle.py:73-89`); mu/sigma/tau are checked independently (`oracle.py:490-502`) and AND-aggregated (`oracle.py:514-522`) with no Bonferroni/FDR correction. Across three independent rt_distribution sub-tests plus other pillars, metrics can pass (or fail) by coincidence.
- **Anti-circularity rests on arithmetic, not citations.** The Reasoner/Oracle evidence-tier separation (G4) is sound in principle, but the conflict ex-Gaussian ranges (mu 400–550, sigma 25–60, tau 70–160) are attributed to Matzke & Wagenmakers 2009 — a diffusion-model *simulation* study that explicitly denies a direct ex-Gaussian-to-cognition mapping and does not survey empirical cross-task ranges [6] (`supported`). The norm's provenance is misattributed, so the gate's empirical authority is weaker than presented.
- **No citation verification at validation time** (`supported`). Norms carry DOI/quote/page fields (`norms/conflict.json:19-26`) but the oracle passes them through to the report unverified (`oracle.py:471-472`).

## 4. Scientific software design

- **Reproducibility is recorded, not enforced** (`supported`). `run_metadata` stores `session_seed` and `taskcard_sha256`, but the executor loads the **newest-by-mtime** card via `load_latest` (`README.md:98-99`), not by hash. Regenerating a card for the same URL silently breaks the seed→card association; there is no `load_by_hash` path. The content-addressing scheme (`taskcard/hashing.py`, canonical JSON, zeroed self-hash) is correct but unused on load — so the hermetic-replay claim does not hold.
- **Provenance vs FAIR4RS R1.2** [3] (`supported`). R1.2 requires "detailed provenance." The pipeline partially meets it (run_trace.json, session_seed, taskcard_sha256) but the project's own G4 caveat states committed citation quotes/pages are "NOT trustworthy" — a direct provenance-integrity gap. The honesty is commendable; the gap is real and unresolved.
- **Testing and doc discipline are genuine strengths.** Internal CI grew to 710+ passing (SP16; 797 at time of this review) with negative-assertion tests guarding paradigm-vocabulary leakage (CLAUDE.md). Doc-workflow rules R-1/R-2/R-3 enforce single-source-of-truth for results. These are above typical research-software norms.

## 5. External benchmarking

- **The task is genuinely under-benchmarked, not solved** [9] (`supported`, strength). Web-agent benchmarks (WebVoyager: 643 tasks/15 sites; also WebArena, Mind2Web, OSWorld, GAIA) score open-ended goal completion, not faithful execution of a fixed stimulus-response protocol with calibrated human-like RT distributions. experiment_bot occupies a distinct problem space — a legitimate novelty claim.
- **The threat model is demonstrated-in-principle, not yet widespread** [1] (`supported`). A 2026 13-platform screen flagged <1% likely-non-human responses on 12 platforms versus ~16% on MTurk; flagged responses looked like scripted bots, not modern chatbots. So the thesis's urgency ("bots challenge online data collection") is real on MTurk and prospective elsewhere — frame it as anticipatory, with the lead author's own caveat that "things are changing so quickly." MTurk-specific fraud is documented but study-specific, not an established general rate [10] (`uncertain`).
- **Matching means can mask broken correlational structure** [8] (`supported`). LLM survey-simulation work found 48% of coefficients differed significantly from human-derived counterparts, with sign flips 32% of the time among those — "aggregate-level accuracy masks deeper failures." Directly relevant: the oracle gates on point estimates (means/SDs/effect magnitudes), not covariance structure, so passing norms does not establish that the bot reproduces the relationships researchers study.
- **Simulated data is not human evidence** [7] (`supported`). The "Six Fallacies" framework names "substituting model data for human evidence" as a fallacy and recommends LLMs as simulation tools, not participant replacements — reinforcing that an oracle pass does not license treating bot data as human data.
- **RT/SSRT methodology gaps** [4][5] — see §3; the external standards are explicit and the oracle does not meet them.
- **CAPTCHA/automation gate is partly defeated, not "effectively defeated"** [2] (`uncertain`): a YOLO model solves reCAPTCHAv2 image puzzles at ~100%, but behavioral risk-scoring defenses (reCAPTCHAv3) are not addressed by that result; do not overclaim.

## 6. Prioritized recommendations

1. **Gate SSRT on Verbruggen 2019 validity bounds** — refuse to emit SSRT when stop trials <50 or p(respond|signal) ∉ [0.25, 0.75] (`oracle.py:270`); return a documented abstention, not a number [5]. (§3, most impactful: current output can be method-invalid.)
2. **Enforce a per-cell sample floor for ex-Gaussian fits** — raise the `< 5` guard (`effects/validation_metrics.py:100`) toward ≥40/cell, and flag tau as low-confidence below ~100; surface N alongside every fitted parameter [4]. (§3.)
3. **Re-extract or honestly demote the citation trail** — re-run Stage 3 / norms extraction for verifiable DOIs only (no quotes/pages), fix the Matzke & Wagenmakers misattribution for the conflict ranges, and until then label all behavioral parameters as model-prior estimates in reviewer materials [6]. (§3/§4, G4.)
4. **Make replay hermetic** — load the TaskCard by `taskcard_sha256` recorded in `run_metadata`, not by mtime (`README.md:98-99`, `taskcard/hashing.py`); add a `load_by_hash` path and a replay regression test. (§4.)
5. **Add multiplicity control or report it as descriptive** — either apply FDR/Bonferroni across the independent sub-tests in `_in_range` aggregation (`oracle.py:490-522`), or explicitly document the gate as a descriptive screen, not an inferential test. (§3.)
6. **Add covariance/effect-structure checks to the oracle** — point-estimate matching can mask broken relationships [8]; gate at least one within-paradigm contrast's *structure*, not just its magnitude. (§5.)
7. **Power the held-out claim** — run the deferred N=5 (and ideally more) on `stop_signal_with_integrated_memory`; the N=1 out-of-norm SSRT cannot support a generalization claim (CLAUDE.md:389-398). (§2.)
8. **Reframe the thesis precisely in reviewer-facing docs** — state "simulates from a structured protocol," enumerate the non-URL scaffolding (adapters, platform defaults, norms, adaptive-nav budget), and frame the data-integrity threat as anticipatory per [1]. (§1/§5.)

## Citations

**Code**
- `src/experiment_bot/validation/oracle.py:73-89, 270, 471-472, 490-502, 514-522` — point-estimate gate, SSRT compute, unverified citation passthrough, range aggregation
- `src/experiment_bot/effects/validation_metrics.py:100` — ex-Gaussian 5-sample floor
- `norms/conflict.json:19-26` — conflict ex-Gaussian ranges + citation fields
- `src/experiment_bot/taskcard/hashing.py` — content-addressed TaskCard hashing
- `README.md:98-99` — newest-by-mtime TaskCard load policy
- `CLAUDE.md:389-398` — SP16 held-out behavioral result + SSRT-high finding
- `CLAUDE.md` (G2, G4) — generic-mechanism mandate; citation-fabrication honesty caveat
- `src/experiment_bot/reasoner/platform_defaults.py` (SP15) — navigation backfill registry
- `src/experiment_bot/validation/platform_adapters.py` — per-paradigm scoring adapters

**External**
- [1] https://retractionwatch.com/2026/04/30/are-ai-chatbots-infiltrating-online-survey-data-not-yet-says-new-study/ — AI bots not yet widespread
- [2] https://www.tomshardware.com/tech-industry/artificial-intelligence/ai-researchers-demonstrate-100-success-rate-in-bypassing-online-captchas — AI solves reCAPTCHA puzzles
- [3] https://pmc.ncbi.nlm.nih.gov/articles/PMC9562067/ — FAIR4RS software provenance principle
- [4] https://pmc.ncbi.nlm.nih.gov/articles/PMC9499371/ — ex-Gaussian sample-size requirements
- [5] https://elifesciences.org/articles/46323 — SSRT consensus validity criteria
- [6] https://link.springer.com/article/10.3758/PBR.16.5.798 — Matzke & Wagenmakers ex-Gaussian study
- [7] https://arxiv.org/abs/2402.04470 — Six Fallacies of LLM-as-human
- [8] https://www.cambridge.org/core/journals/political-analysis/article/synthetic-replacements-for-human-survey-data-the-perils-of-large-language-models/B92267DC26195C7F36E63EA04A47D2FE — synthetic data masks correlations
- [9] https://www.emergentmind.com/topics/webvoyager-benchmark — web-agent goal-completion benchmarks
- [10] https://www.tandfonline.com/doi/full/10.1080/13645579.2025.2601994 — MTurk fraud case study

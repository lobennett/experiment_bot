# Retrieval-Grounded Stage 3 — Live Smoke Results

_From-scratch reason on `expfactory_stroop` (deploy.expfactory.org/preview/10), retrieval ON, `--skip-pilot`, real OpenAlex. 2026-05-29. TaskCard `f32e75c9.json` (throwaway label `expfactory_stroop_retrieval_smoke`, deleted after recording)._

## The core guarantee held — fabrication is now structurally impossible

| Invariant | Result |
|---|---|
| Stage 3 completed without refusal | ✅ (the old prompt reliably refused as fabrication; the grounded prompt does not) |
| Every emitted citation has a real DOI | ✅ 12/12 |
| Every citation carries an `abstract_snippet` (retrieved grounding text) | ✅ 12/12 |
| Every citation `doi_verified=True` (existence + year + author + **title** match) | ✅ 12/12 |
| Off-pool DOIs | ✅ none possible (model cites by `pool_idx`; Python maps to retrieved works) |
| Rationales grounded in the retrieved abstract | ✅ e.g. "The abstract uses ex-Gaussian mu/sigma/tau parameters to characterize…" |

This is the decisive improvement over the prior corpus (`docs/stage3-citation-integrity-2026-05.md`), where 20% of DOIs were invented and "verified" ones paired real DOIs with fabricated quotes. Here, **the model could only cite what Python retrieved from OpenAlex, and every citation is a real, title-verified paper whose abstract it actually saw.**

## What the smoke also honestly exposes

**1. Values stayed `model_prior` (0 revisions).** Both conditions (congruent, incongruent) ended `value_source=model_prior`. The abstracts did not state concrete mu/sigma/tau ranges, so the evidence-bounded revision guard correctly applied nothing. **Honest reading: the citations are real *topical support*, not sources of the specific parameter values — the values remain model-prior estimates, now correctly labeled as such.** A real, on-topic, verified citation ≠ a citation that reports the exact number.

**2. Retrieval surfaced recent/topical papers, not canonical norms.** Only **2 distinct DOIs**, both **2023** — a bioRxiv preprint (`10.1101/2023.05.29.542684`) and an ADHD interindividual-similarity paper (`10.1177/10870547231214966`). Both genuinely discuss ex-Gaussian RT decomposition, but neither is a canonical Stroop ex-Gaussian norm source (e.g. Heathcote 1991). Cause: the deterministic query (`"conflict speeded_choice ex-Gaussian reaction time distribution"`) + OpenAlex relevance ranking skews toward recent, lexically-matching work. **The citations are real, verified, and on-topic — but not authoritative.**

## Verdict

The retrieval-grounded Stage 3 achieves its core objective: **no fabrication is possible, every citation is real + title-verified + abstract-grounded, and uncited/unrevised values are honestly labeled `model_prior`.** It does not, on its own, restore the framework's original (over-)claim that parameters are *derived from canonical literature* — it makes the honest state visible: the values are model-prior estimates with real topical citations, and the literature did not pin them.

## Future work (not in this build; for a follow-up decision)

- **Better recall of canonical sources:** add an LLM query-writer (richer queries, +1 call, less reproducible) and/or rank retrieval by citation-count / review-type / older-seminal rather than recency; optionally seed known canonical papers per paradigm class.
- **Value grounding needs full text:** abstracts rarely report specific ex-Gaussian numbers; revising values toward literature would require full-text/table extraction (paywalls), or accepting that values stay model-prior with topical citations (the current honest state).
- **Regenerate the 15 committed cards** under the grounded Stage 3 (separate run): replaces the fabricated corpus with real-but-topical citations + honest `model_prior` labels. Will shrink/relabel the corpus — the truthful outcome.

---

## Canonical-recall update (propose→verify + citation-ranked search)

_Re-run after the canonical-recall enhancement (spec `docs/superpowers/specs/2026-05-29-canonical-recall-stage3-design.md`). Same paradigm (`expfactory_stroop`, deploy.expfactory.org/preview/10 → stroop_rdoc), retrieval ON, `--skip-pilot`, real OpenAlex, CLI LLM client. 2026-05-29. Throwaway card `69a59c7a.json` (label `canonical_recall_smoke`), deleted after recording._

Stage 3 inference line: **`proposed=8, title-verified=7, search_hits=115, pool=30; 5 parameters cited, 5 abstained, 0 values revised within grounded ranges.`**

### 1. Citation authority — strongly improved (success criterion #2: MET)

Prior topical-only smoke surfaced **2 distinct DOIs, both 2023**, neither canonical. The propose→verify phase surfaced **7 distinct DOIs, all `doi_verified=True`** (title + year + author matched against OpenAlex), including the seminal sources a relevance-only search missed:

| Year | DOI | Work |
|---|---|---|
| 1966 | 10.1037/h0022853 | Rabbitt — Errors and error correction in choice-response tasks |
| 1991 | 10.1037/0033-2909.109.2.163 | MacLeod — Half a century of research on the Stroop effect (the canonical review) |
| 1992 | 10.1037//0096-3445.121.4.480 | Cohen et al. — Optimizing the use of information: strategic control of activation |
| 2001 | 10.1037/0033-295x.108.3.624 | Botvinick et al. — Conflict monitoring and cognitive control |
| 2011 | 10.3758/s13414-011-0243-2 | Dutilh et al. — Testing theories of post-error slowing |
| 2023 | 10.1177/10870547231214966 | ADHD adults ex-Gaussian RT (from the search arm) |
| 2023 | 10.1101/2023.05.29.542684 | Ex-Gaussian RT signature similarity (from the search arm) |

Attribution is sensible and respects the generic-mechanism contract (G2): the canonical conflict/error papers land on the **generic** mechanisms, not paradigm-named ones — `post_event_slowing` ← Rabbitt 1966 + Dutilh 2011 (the two foundational post-error papers); `lag1_pair_modulation` ← Cohen 1992, Botvinick 2001, Rabbitt 1966, Dutilh 2011; the RT-distribution conditions ← MacLeod 1991 + Cohen 1992 + the 2023 ex-Gaussian papers. The six disabled temporal mechanisms (autocorrelation, practice_effect, fatigue_drift, pink_noise, condition_repetition, vigilance_decrement) carry **zero** citations — uncited as they should be (G3).

### 2. Anti-fabrication invariant — intact (success criterion #1: MET)

`proposed=8, title-verified=7`: one model-proposed paper failed title verification and was **dropped** — the hallucination guard firing exactly as designed. Every surviving DOI came from a Python API lookup (propose→verify or citation-ranked search); none from the model. Pool capped at 30 (`search_hits=115` trimmed by `cited_by_count`, verified-canonical works kept first).

### 3. Revisions — still 0; honest no-range outcome (success criterion #3: MET, honest branch)

Zero values were revised. This is the truthful result, **not a failure to force**: even the canonical review abstracts do not state concrete numeric ranges. The MacLeod 1991 abstract retrieved is qualitative — _"a set of 18 reliable empirical findings is isolated…"_ — with no mu/sigma/tau numbers, so the evidence-bounded revision guard correctly applied nothing. All values remain `value_source=model_prior`, honestly labeled. As the prior smoke's "Future work" notes, moving values toward the literature would require full-text/table extraction (paywalls); abstract-level grounding cannot pin specific parameter values, and we did not loosen the guard to manufacture revisions.

### 4. Minor cosmetic follow-up (not a defect)

Within a parameter block, the same DOI can repeat (e.g. the 2023 preprint appears multiple times under `congruent`): when `mu`/`sigma`/`tau` share one `ParameterValue` dict and the ground call cites the same `pool_idx` for several of them, citations accumulate without dedup. All entries are real and verified — this is noise, not fabrication. A per-`tgt` citation dedup is a small future tidy-up; it does not affect the invariant or the authority finding.

### Verdict

The canonical-recall enhancement delivered its core objective: **citations are now authoritative** (MacLeod 1991, Botvinick 2001, Cohen 1992, Rabbitt 1966, Dutilh 2011 — verified, abstract-grounded, on the right generic mechanisms) **with the anti-fabrication invariant fully intact** (1/8 hallucinated proposal dropped; no model-supplied DOIs). It did **not** turn the values into literature-derived numbers — that ceiling is unchanged and honest: abstracts state no ranges, so the values remain model-prior estimates carrying real canonical citations.

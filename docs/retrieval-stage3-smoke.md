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

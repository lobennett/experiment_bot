# Stage 3 Citation History

_How the Reasoner's Stage 3 citation trail evolved: from a confirmed
fabrication finding, through a retrieval-grounded rebuild, to the current
honest state. Consolidated 2026-05-29 from the original integrity
investigation and the retrieval-rebuild smoke results._

## 1. The fabrication finding (CRITICAL, confirmed)

A 6-agent adversarial investigation confirmed that the original Stage 3
**fabricated** its citation trail. The pipeline runs strictly 1→6, each stage
mutating one partial. Stage 2 sets the numeric `value`s (mu/sigma/tau,
accuracy, effect magnitudes) as point estimates and is explicitly forbidden to
cite ("Citations come in stage 3 — do NOT include them yet"). Stage 3 then
reads those already-set values and `.update()`s `literature_range` /
`between_subject_sd` onto them — bracketing pre-chosen numbers post-hoc (e.g.
Stroop congruent `value mu=530` wrapped by `literature_range mu=[480,580]`).
So **values were chosen first and retro-cited.**

The Stage 3 prompt demanded, per parameter, a non-empty citation list with
`{doi, authors, year, title, table_or_figure, page, quote}` — verbatim quotes
and exact page/table locators an un-tooled LLM cannot truthfully produce for a
held-out paper. This induced two fabrication modes, both independently
CrossRef-verified:

- **Mode 1 — real DOI / fabricated quote.** MacLeod 1991
  (`10.1037/0033-2909.109.2.163`, a narrative review with no ex-Gaussian
  tables) quoted ~36× with tabulated mu/accuracy; Heathcote 1991
  (`10.1037/0033-2909.109.2.340`, an 8-page vocal-Stroop note) quoted ~56× with
  manual-keypress mu/sigma/tau and an impossible "Table 3 p.346-348"; Matzke &
  Wagenmakers 2009 (`10.3758/PBR.16.5.798`, a diffusion *simulation*) quoted as
  an empirical norms table; Verbruggen 2019 (`10.7554/eLife.46323`, a consensus
  guide) quoted ~55× with "reference dataset" SDs it never reports, mostly
  tagged "Paraphrased / p. general".
- **Mode 2 — fabricated DOI.** `10.3758/BF03206482` resolves to Wagenmakers &
  Farrell 2004 ("AIC model selection using Akaike weights") yet is attached to
  TWO other papers in-corpus (one with `doi_verified=True`);
  `10.3758/BF03334412` resolves to a 1973 Richards animal-learning paper;
  `10.1037/0096-1523.17.3.853` is a CrossRef 404. Real DOIs are 1:1 with
  papers, so these are dispositive.

Corpus stats (committed state): 666 citation records, only 82 distinct DOIs
(8.1× reuse), 525 `doi_verified=True`. The flag gated nothing: `verify_doi`
checked only HTTP 200 + exact publication year + a loose surname-substring
overlap — never title, quote, page, or range — and was write-only (its sole
reader was Stage 4's own log count). The aligned model **refused** to emit the
Stage 3 JSON on all 3/3 attempts across held-out runs ("producing what this
prompt literally asks would constitute fabrication") — a correct diagnosis.
This defeated G4's "every parameter has a verifiable citation + quote" claim
and partially leaked into the oracle's `norms/*.json` tier (a simulation paper
cited as a meta-analysis).

## 2. The retrieval-grounded rebuild

Stage 3 was redesigned so **fabrication is structurally impossible — the DOI
never comes from the model.** Python retrieves a real-literature pool
(OpenAlex/CrossRef); one LLM "ground" call cites ONLY by `pool_idx` (an index
into the retrieved works). Guards: pool-membership (a cited index must exist in
the pool), evidence-bounded revision (a value moves toward the literature only
if the retrieved text actually states a range), title-checked `verify_doi`
(existence + year + author + **title**), and an honest abstain path.

Live smoke (from-scratch reason on `expfactory_stroop`, retrieval ON, real
OpenAlex): Stage 3 completed without refusal; 12/12 citations carried a real
DOI, an `abstract_snippet`, and `doi_verified=True`; no off-pool DOIs were
possible. But it honestly exposed two ceilings — **0 value revisions** (both
conditions stayed `value_source=model_prior`; abstracts state no concrete
mu/sigma/tau ranges) and **recency skew**: the deterministic query surfaced
only 2 distinct DOIs, both 2023 (`10.1101/2023.05.29.542684`,
`10.1177/10870547231214966`) — real and on-topic, but not canonical norm
sources.

## 3. Canonical-recall (propose→verify + citation-ranked search)

To fix the recency skew without reopening the fabrication hole: the model
**proposes** canonical papers (authors/year/title, **NO DOI**); Python
title-verifies each against OpenAlex and **unions** the survivors with a
citation-count-ranked search. The ground+revise guards are unchanged.

Re-run smoke (same paradigm) inference line:
`proposed=8, title-verified=7, search_hits=115, pool=30; 5 parameters cited,
5 abstained, 0 values revised`. The propose→verify phase surfaced **7 distinct
DOIs, all `doi_verified=True`**, including the seminal sources a relevance-only
search missed:

| Year | DOI | Work |
|---|---|---|
| 1966 | `10.1037/h0022853` | Rabbitt — Errors and error correction in choice-response tasks |
| 1991 | `10.1037/0033-2909.109.2.163` | MacLeod — Half a century of research on the Stroop effect |
| 1992 | `10.1037//0096-3445.121.4.480` | Cohen et al. — Strategic control of activation |
| 2001 | `10.1037/0033-295x.108.3.624` | Botvinick et al. — Conflict monitoring and cognitive control |
| 2011 | `10.3758/s13414-011-0243-2` | Dutilh et al. — Testing theories of post-error slowing |
| 2023 | `10.1177/10870547231214966` | ADHD adults ex-Gaussian RT (search arm) |
| 2023 | `10.1101/2023.05.29.542684` | Ex-Gaussian RT signature similarity (search arm) |

Attribution respected the generic-mechanism contract (G2): canonical
conflict/error papers landed on *generic* mechanisms, not paradigm-named ones
(`post_event_slowing` ← Rabbitt 1966 + Dutilh 2011; `lag1_pair_modulation` ←
Cohen 1992, Botvinick 2001, Rabbitt 1966, Dutilh 2011). The 6 disabled temporal
mechanisms carried zero citations (G3). The anti-fabrication invariant held:
1 of 8 model-proposed papers failed title verification and was **dropped**; no
DOI came from the model.

## 4. Current honest state

Citations are now **real, title-verified, and canonical** (MacLeod 1991,
Botvinick 2001, Cohen 1992, Rabbitt 1966, Dutilh 2011 all surfaced) with
fabrication structurally impossible. **But 0 values were revised:** behavioral
*values* remain `model_prior` estimates carrying real *topical* citations. Even
the canonical review abstracts state no numeric ranges (the MacLeod 1991
abstract retrieved is qualitative — "a set of 18 reliable empirical findings is
isolated…"), so the evidence-bounded revision guard correctly applied nothing,
and the guard was not loosened to manufacture revisions.

This is the honest state, not an over-claim: a real, on-topic, verified
citation is **not** a citation that reports the exact number. Abstract-level
grounding cannot pin specific numeric values — that would require full-text /
table extraction (paywalls). The defensibility surface therefore rests on the
oracle's numeric gating (which reads ranges, not quote strings), with the
citation trail now an honest topical-support layer rather than a source of the
values.

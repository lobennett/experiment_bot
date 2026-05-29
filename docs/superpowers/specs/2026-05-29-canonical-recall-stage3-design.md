# Canonical-Recall Stage 3 (propose→verify + citation-ranked search) — design spec

**Status:** approved (fork: Hybrid — propose→verify UNION citation-ranked search).
**Builds on:** the committed retrieval-grounded Stage 3 (`docs/superpowers/specs/2026-05-29-retrieval-grounded-stage3-design.md`) and its smoke (`docs/retrieval-stage3-smoke.md`), which proved no-fabrication works but surfaced recent/topical (not canonical) sources and 0 abstract-supported revisions.

## Goal

Push Stage 3 toward genuine literature-derivation by surfacing **canonical/seminal/review** sources into the verified pool, so (a) citations are authoritative, not merely topical, and (b) more retrieved abstracts actually state usable ranges → more legitimate evidence-bounded revisions. The structural anti-fabrication invariant is unchanged: **a citation survives only if Python independently found a real, title-matching paper and fetched its abstract; the DOI never comes from the model.**

## Non-goals

- NOT loosening the revision guard. A value is still revised ONLY within a range an actually-retrieved abstract states. We never let the model assert a number a verified abstract does not contain.
- NOT full-text / table extraction (paywalled; separate effort). Grounding stays abstract-level. The honest ceiling: derivation improves only to the extent canonical/review abstracts state ranges.
- NOT changing the ground+revise call, the four guards, the offline switch, or `ParameterValue`/`Citation` from the prior build — those are reused unchanged.

## Components

### 1. `retrieval.py` — `verify_by_title` (new) + citation-ranked `search_works`

```python
async def verify_by_title(authors: str, year: int | None, title: str, *,
                          mailto: str | None = None,
                          title_threshold: float = 0.5) -> RetrievedWork | None:
    """Look a paper up BY TITLE (model-proposed candidate; no DOI from the model).
    Query OpenAlex /works?search=<title> (then CrossRef fallback); accept the top
    hit only if title-token Jaccard >= title_threshold AND (year is None or within
    ±1 of the hit's year). Return a RetrievedWork built from the API's real DOI +
    reconstructed abstract, or None if no acceptable match. NEVER raises."""
```

- Reuse the `_title_overlap` token-Jaccard logic from `openalex.py` (import or duplicate the small helper). The 0.5 threshold is stricter than `verify_doi`'s 0.4 because here the title is the *search key*, so a strong match is expected.
- `search_works` gains OpenAlex `sort=cited_by_count:desc` so the deterministic pool favors seminal/highly-cited works (reviews + foundational papers rank up). Add `RetrievedWork.cited_by_count: int = 0` (from OpenAlex `cited_by_count`; CrossRef `is-referenced-by-count`) so the pool can be ordered/trimmed by impact. Backward-compatible default 0.

### 2. New prompt `reasoner/prompts/stage3_propose.md`

The propose-call prompt. Given the task name + `paradigm_classes` + the parameter list, ask the model to name the **canonical published works it is confident exist** for these behavioral parameters — `{authors, year, title}` only, **explicitly NO DOI** (DOIs will be looked up + verified by the system). Tell it: prefer reviews / meta-analyses / seminal primary papers; it is fine to return few or none; do NOT invent titles. Output:
```json
{"candidates": [{"authors": "...", "year": <int>, "title": "..."}, ...]}
```

### 3. `stage3_citations.py` — add the propose→verify phase before the pool ground call

New orchestration order in `run_stage3` (offline switch unchanged):
1. **Propose (new LLM call):** `parse_with_retry(stage_name="stage3_propose")` with `stage3_propose.md` → `candidates`. Wrap in try/except → on failure, skip (candidates=[]); never hard-fail.
2. **Verify candidates:** for each candidate, `verify_by_title(authors, year, title)`; collect the non-None `RetrievedWork`s. (Python-verified canonical sources.)
3. **Citation-ranked search:** the existing per-parameter `search_works` (now cited_by_count-sorted).
4. **Union → pool:** dedupe by DOI (verified-canonical first, then search hits); cap pool size (e.g. 30) keeping highest `cited_by_count`.
5. **Ground + revise:** the existing single ground call + the four guards (pool-membership, evidence-bounded revision, verify_doi, abstain) — UNCHANGED.

The ReasoningStep inference reports: # proposed, # title-verified, # search hits, pool size, # cited / abstained / revised.

## Data flow

Stage 2 → **Stage 3** [propose call → verify_by_title each candidate → union with cited_by_count-ranked search → ground call → 4 guards] → Stage 4 → Stage 5.
`run_stage3(client, partial)` signature unchanged.

## Error handling (every failure → honest, never fabricated)

| Failure | Behavior |
|---|---|
| Propose call fails/garbles | candidates=[]; fall back to search-only pool (prior behavior) |
| A proposed title doesn't verify (hallucinated / not found / title mismatch) | dropped — not added to pool |
| Both propose-verify and search yield nothing | empty pool → abstain-all (unchanged) |
| Retrieval off (`EXPERIMENT_BOT_RETRIEVAL=off`) | abstain-all, no propose call (unchanged) |
| Abstract has no stated range | no revision — value stays model_prior (unchanged) |

## Testing

- **`verify_by_title`** (mock httpx): exact-title hit → RetrievedWork with API DOI; title-mismatch hit → None; year-off-by-2 → None; network error → None; a hallucinated title (no results) → None.
- **`search_works` ranking**: assert the OpenAlex request includes `sort=cited_by_count:desc`; `cited_by_count` parsed onto RetrievedWork.
- **stage3 propose→verify** (mock propose LLM + mock `verify_by_title` + mock `search_works` + mock ground LLM):
  - a proposed-and-verified canonical work appears in the pool the ground call sees AND can be cited;
  - a proposed-but-unverifiable candidate (verify_by_title→None) does NOT enter the pool;
  - propose-call failure → falls back to search-only pool (no crash);
  - the four existing guards still hold on the unioned pool (off-pool dropped, out-of-range revision rejected, abstain on empty).
- **Live smoke** (regression): re-run the `expfactory_stroop` smoke; expect canonical/older sources (e.g. a Heathcote/MacLeod/Logan-class paper) to appear among citations and ≥1 evidence-bounded revision OR an explicit honest note that abstracts still didn't state ranges. Compare authority + revision count vs the prior topical-only smoke.

## Success criteria

1. Anti-fabrication invariant intact: every citation's DOI comes from a Python-verified API lookup (propose→verify or search); no model-supplied DOIs; off-pool still dropped.
2. The verified pool now contains canonical/highly-cited sources (live smoke shows ≥1 seminal/review paper a relevance-only search missed).
3. ≥1 legitimate evidence-bounded revision in the live smoke, OR an explicit, honest "abstracts still did not state ranges" finding (either is an acceptable, truthful outcome — no fabrication to force a revision).
4. Full suite green; new `verify_by_title` + ranking + propose-phase tests pass.
5. Graceful degradation: propose-call failure / retrieval-off / empty pool all reduce to the prior committed behavior, never to fabrication.

## Decomposition preview (for writing-plans)

1. `retrieval.py`: `verify_by_title` + `cited_by_count` field + `sort=cited_by_count:desc` in `search_works` + tests.
2. `prompts/stage3_propose.md` + invariant test.
3. `stage3_citations.py`: propose→verify phase + union/dedupe/cap into the pool (ground call + guards unchanged) + mocked unit tests.
4. Live smoke re-run on `expfactory_stroop` + update `docs/retrieval-stage3-smoke.md` (authority + revision comparison).

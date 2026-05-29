# Retrieval-Grounded Stage 3 (ground + revise) — design spec

**Status:** approved (forks decided: ground+revise; OpenAlex primary + CrossRef fallback; abstract-only grounding).
**Motivates:** `docs/stage3-citation-integrity-2026-05.md` (Stage 3 fabricated citations; the honest-baseline fix is committed; this is the XL retrieval rebuild).

## Goal

Make the Reasoner's citations *structurally* honest: the model can only cite works that Python actually retrieved from the literature, may only ground a quote/rationale in a retrieved abstract, and may only revise a behavioral parameter toward a range grounded in a retrieved abstract. Fabrication becomes impossible by construction, not merely discouraged. Where no supporting literature is retrieved, Stage 3 abstains and the value is honestly labeled a model-prior estimate.

## Non-goals

- NOT a full literature-first rewrite of Stage 2 (that was the rejected XL+ fork). Stage 2 still produces initial values; Stage 3 grounds + (evidence-boundedly) revises them.
- NOT full-text retrieval/PDF parsing. Grounding is abstract-level (OpenAlex `abstract_inverted_index` + CrossRef metadata). Claims requiring table values not in an abstract → abstain.
- NOT changing the oracle, norms extractor (already hardened in the baseline commit), executor, or navigation.
- NOT re-generating the 15 committed TaskCards here — that's a separate regeneration run after this lands.

## Components

### 1. `src/experiment_bot/reasoner/retrieval.py` (new)

The literature retrieval client. Pure I/O + parsing; no LLM.

```python
@dataclass
class RetrievedWork:
    doi: str | None
    authors: str        # "Surname, I., Surname2, I2."
    year: int | None
    title: str
    abstract: str       # reconstructed; "" if unavailable
    source: str         # "openalex" | "crossref"

async def search_works(query: str, *, per_page: int = 5,
                       year_from: int | None = None,
                       mailto: str | None = None) -> list[RetrievedWork]:
    """Search OpenAlex /works?search=<query> (filter from_publication_date when
    year_from set), reconstruct each work's abstract from abstract_inverted_index,
    return up to per_page RetrievedWork. On OpenAlex miss/no-abstract for a hit,
    fall back to CrossRef /works?query=<query> for metadata (CrossRef abstracts
    are sparse/JATS — strip tags when present, else abstract="").
    NEVER raises: network errors / non-200 / parse errors → return []."""
```

- Abstract reconstruction: OpenAlex returns `abstract_inverted_index = {token: [positions]}`; rebuild by placing each token at its positions and joining. Cap length (~2000 chars).
- Polite pool: send `mailto` param to OpenAlex when available (env `EXPERIMENT_BOT_OPENALEX_MAILTO`), else anonymous.
- Reuse the existing `openalex.py` HTTP pattern (httpx, 10s timeout).

### 2. `src/experiment_bot/reasoner/stage3_citations.py` (rewritten)

Python-orchestrated ground + revise. Replaces the current single-LLM retro-citation call.

**Step A — build queries (deterministic, no LLM):** for each enumerated parameter `<section>/<key>/<param>`, build a query string from `task.paradigm_classes` + the condition/key + a param-semantics phrase. Mapping is a small table:
- `mu`/`sigma`/`tau` → "ex-Gaussian reaction time distribution"; `ssrt` → "stop-signal reaction time"; `cse`/`congruency` → "congruency sequence effect"; `post_error_slowing` → "post-error slowing"; `accuracy`/`omission` → "accuracy error rate"; `lag1`/`autocorr` → "sequential dependency reaction time"; default → the param name.
- e.g. `response_distributions/congruent/mu` for a `["conflict","speeded_choice"]` Stroop task → `"Stroop conflict ex-Gaussian reaction time distribution"`.

**Step B — retrieve the pool:** call `search_works` per distinct query (dedupe queries; cache within the run). Union the results into a candidate **pool** (list of RetrievedWork, deduped by DOI). Each pool entry gets a stable integer index.

**Step C — one LLM "ground" call:** prompt (new `prompts/stage3_ground.md`) provides (1) the parameters with their Stage-2 `value`s, (2) the numbered pool (idx, doi, authors, year, title, abstract). Instructions: for each parameter, return
```json
{"<section>/<key>/<param>": {
  "citations": [{"pool_idx": <int>, "rationale": "<grounded in that abstract>", "confidence": "..."}],
  "literature_range": {"<param>": [low, high]} | null,   // ONLY if an abstract states it
  "revised_value": {"<subparam>": <number>} | null,      // ONLY within a literature_range above
  "revision_reason": "<why, citing pool_idx>" | null,
  "no_citation_reason": "<required when citations empty>"
}}
```
The model MUST cite by `pool_idx` (cannot emit a DOI not in the pool). It must abstain (empty citations + reason) rather than cite a non-supporting paper.

**Step D — Python validation + apply (the structural guards):**
1. **Pool-membership:** resolve each `pool_idx` to its RetrievedWork; drop any citation whose idx is out of range. (The model literally cannot introduce a DOI we didn't retrieve.)
2. **Quote grounding:** the stored citation keeps the RetrievedWork's real {doi, authors, year, title} + the model's `rationale`; we also store `abstract_snippet` = the retrieved abstract (truncated) as the auditable grounding. No free-text `quote`/`page` is accepted (those fields stay empty per the honest-baseline schema).
3. **Evidence-bounded revision:** apply `revised_value[sub]` to the ParameterValue **only if** (a) a `literature_range` for `sub` was provided AND (b) the revised number lies within that range AND (c) the range came from a cited pool work. Record `value_source="literature_revised"`, `original_value=<stage2>`, `revision_reason`. Otherwise keep the Stage-2 value, set `value_source="model_prior"`, and log a rejected-revision warning.
4. **verify_doi gate:** run each surviving citation's {doi, authors, year, title} through `verify_doi` (title-check, already added). Mark `doi_verified`. (Pool DOIs are from OpenAlex so should pass; this is defense-in-depth + catches CrossRef-fallback drift.)
5. **Abstain:** if a parameter ends with zero citations, set `no_citation_reason` and `value_source="model_prior"`.

**Offline/empty:** if `EXPERIMENT_BOT_RETRIEVAL` is `off`/`0`/`false`, OR the pool is empty (network down), skip the ground call and abstain for every parameter (values stay model-prior, `no_citation_reason="retrieval unavailable"`). Never fabricate.

### 3. `src/experiment_bot/taskcard/types.py` `ParameterValue`

Add audit fields (all optional, backward-compatible defaults):
- `value_source: Literal["model_prior", "literature_revised"] = "model_prior"`
- `original_value: dict | None = None`  (the pre-revision value when revised)
- `revision_reason: str = ""`

`from_dict`/`to_dict` carry them. Existing 18 cards (no these keys) default to `model_prior`.

### 4. New prompt `src/experiment_bot/reasoner/prompts/stage3_ground.md`

The ground-call prompt (Step C). Emphasizes: cite ONLY by `pool_idx`; rationale must reflect that abstract; assert a range ONLY if the abstract states it; revise ONLY within an asserted range; abstain honestly otherwise; return JSON only. (Replaces `stage3_citations.md` as the active Stage-3 prompt; keep the old file or repurpose it.)

## Data flow

`pipeline.py` Stage 2 (values) → **Stage 3** [build queries → `search_works` pool → 1 ground LLM call → pool-filter + evidence-bounded revise + `verify_doi`] → Stage 4 (independent DOI re-verify) → Stage 5 → Stage 6.

`run_stage3(client, partial)` signature unchanged (still `(client, partial) -> (partial, ReasoningStep)`), so the pipeline and `--resume` are unaffected. The ReasoningStep inference reports: pool size, # parameters cited vs abstained, # values revised.

## Error handling (every failure → honest, never fabricated)

| Failure | Behavior |
|---|---|
| OpenAlex/CrossRef network error or non-200 | `search_works` → `[]`; empty pool → abstain-all |
| Retrieval disabled (`EXPERIMENT_BOT_RETRIEVAL=off`) | skip retrieval; abstain-all (honest-baseline behavior) |
| LLM cites `pool_idx` out of range | drop that citation |
| LLM proposes revision outside the grounded range | reject; keep Stage-2 value; log |
| LLM ground call refuses/garbles JSON | `parse_with_retry` retries; on exhaustion → abstain-all (not a hard pipeline failure) |
| Abstract empty for a hit | citation allowed with `abstract_snippet=""` only if title/metadata support; prefer abstain |

## Testing

- **retrieval.py** (mock httpx): inverted-index → abstract reconstruction; OpenAlex hit→RetrievedWork; OpenAlex miss → CrossRef fallback; network error → `[]`; year_from filter included in the request.
- **stage3 ground** (mock `search_works` + mock LLM ground response):
  - off-pool `pool_idx` is dropped (inject idx=99 → not in output);
  - in-range `revised_value` applied + `value_source="literature_revised"` + `original_value` recorded;
  - out-of-range `revised_value` rejected (value unchanged, `model_prior`);
  - empty pool → all parameters abstain with `no_citation_reason`, no LLM call made;
  - `EXPERIMENT_BOT_RETRIEVAL=off` → abstain-all, no network, no LLM call;
  - surviving citations carry real pool {doi,title} + `abstract_snippet`.
- **verify_doi** integration: a pool DOI with matching title verifies; a CrossRef-fallback wrong-title drops.
- **Regression / live smoke** (regression task, not unit): run Stage 3 on one paradigm with real OpenAlex; assert every emitted citation's DOI is one that was retrieved (no off-pool DOIs), and that abstentions are explicit. Compare corpus honesty vs the committed (fabricated) cards.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Abstracts rarely contain specific ex-Gaussian numbers → many abstentions | That is the *honest* state; abstention + model-prior label is correct. The corpus shrinking is the point. |
| OpenAlex rate limits in batch | polite-pool `mailto`; small per_page; dedupe queries within a run; retrieval is cached per query per run |
| Deterministic queries miss the right paper | acceptable — a missed paper → abstain, not fabricate; query table can be tuned; (a future LLM-query-generation step is possible but adds a call + nondeterminism) |
| Added latency/network in Stage 3 | bounded (N distinct queries × 1 request + 1 LLM call); `--resume` skips it; offline switch for deterministic runs |
| ParameterValue new fields break loaders/tests | all optional with defaults; round-trip test added |

## Success criteria

1. Every citation Stage 3 emits has a DOI that was in the retrieved pool (verifiable in a live smoke); no off-pool DOIs possible.
2. Value revisions occur only within a grounded literature_range and are recorded (`value_source`, `original_value`, `revision_reason`).
3. Empty pool / retrieval-off / refusal → abstain-all, never fabricate; pipeline does not hard-fail.
4. Full test suite green; new retrieval + stage3-ground + ParameterValue tests pass.
5. Live smoke on one paradigm produces an honest card (real retrieved cites + explicit abstentions) — demonstrably different from the fabricated committed corpus.

## Decomposition preview (for writing-plans)

1. `retrieval.py` + tests (abstract reconstruction, CrossRef fallback, network-error→[]).
2. `ParameterValue` audit fields + round-trip test.
3. `prompts/stage3_ground.md` + invariant test.
4. `stage3_citations.py` rewrite: query-build → pool → ground call → guards (pool-filter, evidence-bounded revise, verify_doi, abstain) + offline switch; unit tests with mocked retrieval + LLM.
5. Live smoke on one paradigm + a short results note; (regeneration of all cards is a separate follow-up run).

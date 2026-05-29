# Canonical-Recall Stage 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface canonical/seminal/review sources into Stage 3's verified pool — the model proposes papers (authors/year/title, no DOI), Python verifies each by title-search and unions them with a citation-count-ranked search — so citations are authoritative and more abstracts can legitimately support evidence-bounded revisions, without weakening the anti-fabrication invariant (the DOI never comes from the model).

**Architecture:** Three code units. (1) `retrieval.py` gains `verify_by_title` (look a model-proposed paper up BY TITLE, accept only on title-overlap + year gate, return the API's real DOI + abstract) plus a `cited_by_count` field and `sort=cited_by_count:desc` on the OpenAlex search. (2) `prompts/stage3_propose.md` is a new propose-phase prompt. (3) `stage3_citations.run_stage3` inserts a propose→verify phase, unions verified-canonical works (always kept) with the highest-cited search hits (capped), and feeds the unioned pool to the **unchanged** ground call + four guards. A live smoke re-run + doc update closes the loop.

**Tech Stack:** Python 3, `httpx` (async, mocked in tests), `pytest`/`pytest-asyncio`, `unittest.mock`, `click` CLI (`experiment-bot-reason`). OpenAlex + CrossRef REST APIs.

**Spec:** `docs/superpowers/specs/2026-05-29-canonical-recall-stage3-design.md`

**Reviewer note (per project convention):** dispatch the spec-compliance reviewer subagent after each code task; SKIP the code-quality reviewer (see memory `feedback_skip_code_quality_reviewer`).

---

## File Structure

- **Modify** `src/experiment_bot/reasoner/retrieval.py` — add `cited_by_count` to `RetrievedWork`; add `sort_by_citations` param threading `sort=cited_by_count:desc` into the OpenAlex query (default on); parse citation counts from both providers; add `verify_by_title`. (Task 1)
- **Modify** `tests/test_retrieval.py` — citation-sort + count-parse test; five `verify_by_title` tests. (Task 1)
- **Create** `src/experiment_bot/reasoner/prompts/stage3_propose.md` — propose-phase prompt. (Task 2)
- **Modify** `tests/test_reasoner_stage3.py` — add propose-prompt invariant test; rewrite the behavioral tests' mocking to a stage-name router + add three propose→verify tests. (Tasks 2, 3)
- **Modify** `src/experiment_bot/reasoner/stage3_citations.py` — insert propose→verify phase; union verified-canonical + citation-ranked search into the pool (cap 30); ground call + guards unchanged; updated inference line. (Task 3)
- **Modify** `docs/retrieval-stage3-smoke.md` — append a "Canonical-recall update" section comparing authority + revision count. (Task 4)

---

## Task 1: `retrieval.py` — citation-count ranking + `verify_by_title`

**Files:**
- Modify: `src/experiment_bot/reasoner/retrieval.py`
- Test: `tests/test_retrieval.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_retrieval.py`. Update the top import line to include `verify_by_title`:

```python
from experiment_bot.reasoner.retrieval import (
    search_works, verify_by_title, _reconstruct_abstract, RetrievedWork,
)
```

Then append these tests:

```python
@pytest.mark.asyncio
async def test_search_works_requests_citation_sort_and_parses_count():
    oa = {"results": [{
        "doi": "10.1/seminal", "publication_year": 1991, "title": "Seminal work",
        "authorships": [{"author": {"display_name": "A. Author"}}],
        "abstract_inverted_index": {"x": [0]}, "cited_by_count": 4200,
    }]}
    captured = {}
    resp = MagicMock(); resp.status_code = 200; resp.json = MagicMock(return_value=oa)
    async def _get(url, params=None, **k):
        captured["params"] = params or {}
        return resp
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=_get)
    with patch("httpx.AsyncClient", return_value=client):
        works = await search_works("ex-gaussian", per_page=5)
    # the deterministic pool search favors highly-cited (canonical) works
    assert captured["params"].get("sort") == "cited_by_count:desc"
    assert works[0].cited_by_count == 4200


@pytest.mark.asyncio
async def test_verify_by_title_accepts_strong_match():
    hit = RetrievedWork(doi="10.1037/canonical", authors="MacLeod, C. M.", year=1991,
        title="Half a century of research on the Stroop effect",
        abstract="A review of Stroop interference.", source="openalex", cited_by_count=9000)
    with patch("experiment_bot.reasoner.retrieval.search_works",
               new=AsyncMock(return_value=[hit])):
        out = await verify_by_title("MacLeod", 1991,
            "Half a century of research on the Stroop effect")
    assert out is not None and out.doi == "10.1037/canonical"


@pytest.mark.asyncio
async def test_verify_by_title_rejects_title_mismatch():
    hit = RetrievedWork(doi="10.1/other", authors="X", year=1991,
        title="An entirely unrelated paper about fish migration",
        abstract="", source="openalex")
    with patch("experiment_bot.reasoner.retrieval.search_works",
               new=AsyncMock(return_value=[hit])):
        out = await verify_by_title("MacLeod", 1991,
            "Half a century of research on the Stroop effect")
    assert out is None


@pytest.mark.asyncio
async def test_verify_by_title_rejects_year_off_by_two():
    hit = RetrievedWork(doi="10.1/x", authors="MacLeod", year=1989,
        title="Half a century of research on the Stroop effect",
        abstract="", source="openalex")
    with patch("experiment_bot.reasoner.retrieval.search_works",
               new=AsyncMock(return_value=[hit])):
        out = await verify_by_title("MacLeod", 1991,
            "Half a century of research on the Stroop effect")
    assert out is None


@pytest.mark.asyncio
async def test_verify_by_title_hallucinated_returns_none():
    with patch("experiment_bot.reasoner.retrieval.search_works",
               new=AsyncMock(return_value=[])):
        out = await verify_by_title("Nobody", 2050, "A paper that does not exist")
    assert out is None


@pytest.mark.asyncio
async def test_verify_by_title_skips_doi_less_hit():
    hit = RetrievedWork(doi=None, authors="MacLeod", year=1991,
        title="Half a century of research on the Stroop effect",
        abstract="", source="openalex")
    with patch("experiment_bot.reasoner.retrieval.search_works",
               new=AsyncMock(return_value=[hit])):
        out = await verify_by_title("MacLeod", 1991,
            "Half a century of research on the Stroop effect")
    assert out is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_retrieval.py -q`
Expected: FAIL — `ImportError: cannot import name 'verify_by_title'` (and `cited_by_count` AttributeError once the import is fixed).

- [ ] **Step 3: Implement the changes in `retrieval.py`**

3a. Add the citation-count field to the dataclass (after `source`):

```python
@dataclass
class RetrievedWork:
    doi: str | None
    authors: str
    year: int | None
    title: str
    abstract: str
    source: str  # "openalex" | "crossref"
    cited_by_count: int = 0
```

3b. Add the title-overlap import near the top (after the existing imports):

```python
from experiment_bot.reasoner.openalex import _title_overlap
```

3c. Thread `sort_by_citations` through `_openalex` and parse the count:

```python
async def _openalex(client: httpx.AsyncClient, query: str, per_page: int,
                    year_from: int | None, mailto: str | None,
                    sort_by_citations: bool) -> list[RetrievedWork]:
    params = {"search": query, "per-page": str(per_page)}
    if sort_by_citations:
        params["sort"] = "cited_by_count:desc"
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    if mailto:
        params["mailto"] = mailto
    resp = await client.get(_OPENALEX, params=params)
    if resp.status_code != 200:
        return []
    out: list[RetrievedWork] = []
    for w in resp.json().get("results", []):
        out.append(RetrievedWork(
            doi=_norm_doi(w.get("doi")),
            authors=_oa_authors(w),
            year=w.get("publication_year"),
            title=w.get("title") or w.get("display_name") or "",
            abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
            source="openalex",
            cited_by_count=w.get("cited_by_count") or 0,
        ))
    return out
```

3d. Parse the count in `_crossref` (add `cited_by_count=` to the constructor):

```python
        out.append(RetrievedWork(
            doi=_norm_doi(it.get("DOI")),
            authors=authors,
            year=year,
            title=title,
            abstract=_strip_jats(it.get("abstract", "")),
            source="crossref",
            cited_by_count=it.get("is-referenced-by-count") or 0,
        ))
```

3e. Add `sort_by_citations` to `search_works` and pass it through:

```python
async def search_works(query: str, *, per_page: int = 5,
                       year_from: int | None = None,
                       mailto: str | None = None,
                       sort_by_citations: bool = True) -> list[RetrievedWork]:
    """Search OpenAlex; fall back to CrossRef when OpenAlex yields nothing.
    OpenAlex results are sorted by citation count (canonical works first) unless
    sort_by_citations=False. NEVER raises — any network/parse error returns []."""
    mailto = mailto or os.environ.get("EXPERIMENT_BOT_OPENALEX_MAILTO")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            works = await _openalex(client, query, per_page, year_from, mailto,
                                    sort_by_citations)
            if not works:
                works = await _crossref(client, query, per_page, mailto)
            return works
    except Exception as e:
        logger.warning("retrieval.search_works failed for %r: %s", query, e)
        return []
```

3f. Add `verify_by_title` at the end of the file:

```python
async def verify_by_title(authors: str, year: int | None, title: str, *,
                          mailto: str | None = None,
                          title_threshold: float = 0.5) -> RetrievedWork | None:
    """Look a paper up BY TITLE (a model-PROPOSED candidate; the model supplies no
    DOI). Search OpenAlex/CrossRef by title (relevance-ordered), then accept the
    best-overlapping hit only if it has a real DOI, its title-token Jaccard overlap
    is >= title_threshold, and (year is None or the hit's year is within ±1). Return
    a RetrievedWork built from the API's own DOI + abstract, or None. NEVER raises.

    A hallucinated candidate returns no acceptable match, so nothing enters the
    pool. The DOI always comes from the API, never from the model."""
    if not title or not title.strip():
        return None
    try:
        y = int(year) if year is not None else None
    except (TypeError, ValueError):
        y = None
    works = await search_works(title, per_page=5, sort_by_citations=False, mailto=mailto)
    best: RetrievedWork | None = None
    best_overlap = 0.0
    for w in works:
        if not w.doi:
            continue
        overlap = _title_overlap(title, w.title)
        if overlap < title_threshold:
            continue
        if y is not None and w.year is not None and abs(int(w.year) - y) > 1:
            continue
        if overlap > best_overlap:
            best_overlap, best = overlap, w
    return best
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_retrieval.py -q`
Expected: PASS (all existing + 6 new tests).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/retrieval.py tests/test_retrieval.py
git commit -m "feat(retrieval): citation-count ranking + verify_by_title

search_works now sorts OpenAlex by cited_by_count (canonical works first);
RetrievedWork carries cited_by_count from both providers. New verify_by_title
looks a model-proposed paper up BY TITLE and accepts only on title-overlap +
year gate, returning the API's real DOI+abstract — hallucinated titles return
None. The DOI never comes from the model.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `stage3_propose.md` prompt + invariant test

**Files:**
- Create: `src/experiment_bot/reasoner/prompts/stage3_propose.md`
- Test: `tests/test_reasoner_stage3.py`

- [ ] **Step 1: Write the failing invariant test**

Append to `tests/test_reasoner_stage3.py`:

```python
def test_stage3_propose_prompt_invariants():
    from pathlib import Path
    p = Path("src/experiment_bot/reasoner/prompts/stage3_propose.md").read_text()
    low = p.lower()
    # asks for candidates with authors/year/title
    assert "candidates" in low
    assert "authors" in low and "year" in low and "title" in low
    # explicitly must NOT ask the model for a DOI
    assert "do not provide a doi" in low or "not provide a doi" in low or "no doi" in low
    # must forbid invented papers
    assert "invent" in low
    # must permit returning few or none
    assert "none" in low
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_reasoner_stage3.py::test_stage3_propose_prompt_invariants -q`
Expected: FAIL — `FileNotFoundError` (prompt does not exist yet).

- [ ] **Step 3: Create the prompt file**

Create `src/experiment_bot/reasoner/prompts/stage3_propose.md`:

```markdown
You are naming the CANONICAL published literature for a cognitive task's
behavioral parameters, so the system can retrieve and verify those papers.

You are given the task name, its paradigm classes, and the list of behavioral
parameters being set. Name the seminal / review / meta-analytic papers you are
CONFIDENT exist for these parameters in this paradigm class.

RULES:
- Provide ONLY `authors`, `year`, and `title` for each paper. Do NOT provide a
  DOI — the system looks the DOI up itself and verifies the paper exists by its
  title. Any DOI you supply will be ignored.
- Prefer review articles, meta-analyses, and foundational primary papers (the
  works a domain expert would cite as the source for these parameters) over
  recent, narrow studies.
- Name a paper ONLY if you are confident it is real. Do NOT invent titles,
  authors, or years. An invented paper will fail title verification and be
  discarded — but do not rely on that; only propose works you actually know.
- It is fine to return FEW papers, or NONE, if you are not confident. Quality
  over quantity. An honest short list beats a padded one.

Return JSON only, no preamble:
{"candidates": [{"authors": "<surnames>", "year": <int>, "title": "<exact title>"}]}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_reasoner_stage3.py::test_stage3_propose_prompt_invariants -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/prompts/stage3_propose.md tests/test_reasoner_stage3.py
git commit -m "feat(stage3): add propose-phase prompt (canonical papers, no DOI)

Model names seminal/review/meta-analytic papers as {authors, year, title}
only; explicitly no DOI (system verifies by title). Few-or-none allowed; do
not invent. Invariant test guards the no-DOI / no-invent / abstain contract.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `stage3_citations.py` — propose→verify phase + unioned pool

**Files:**
- Modify: `src/experiment_bot/reasoner/stage3_citations.py`
- Test: `tests/test_reasoner_stage3.py`

This task rewrites the behavioral tests' mocking to a stage-name router (so the new propose LLM call is mocked distinctly from the ground call, and `verify_doi` is mocked for hermeticity), then implements the propose→verify phase.

- [ ] **Step 1: Rewrite the behavioral tests + add three propose→verify tests**

In `tests/test_reasoner_stage3.py`, replace the top imports and the FIVE existing `@pytest.mark.asyncio` behavioral tests (`test_stage3_grounds_and_revises_within_evidence`, `test_stage3_drops_off_pool_citation`, `test_stage3_rejects_out_of_range_revision`, `test_stage3_empty_pool_abstains_without_llm`, `test_stage3_retrieval_off_abstains`) with the code below. Leave `test_stage3_ground_prompt_invariants`, `test_stage3_propose_prompt_invariants` (Task 2), and `test_enumerate_parameters_lists_all_paths` unchanged.

Replace the import block at the top of the file:

```python
import pytest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch
from experiment_bot.reasoner.stage3_citations import run_stage3, _enumerate_parameters
from experiment_bot.reasoner.retrieval import RetrievedWork


def _partial():
    return {
        "task": {"name": "Stroop", "paradigm_classes": ["conflict", "speeded_choice"]},
        "response_distributions": {"congruent": {"distribution": "ex_gaussian",
            "value": {"mu": 530, "sigma": 60, "tau": 90}, "rationale": "x"}},
        "temporal_effects": {}, "between_subject_jitter": {},
    }


def _pool():
    return [RetrievedWork(doi="10.1037/real", authors="Heathcote, J.", year=2009,
            title="Ex-Gaussian Stroop RT", abstract="congruent mu ranged 480-520 ms",
            source="openalex", cited_by_count=120)]


def _router(*, ground, propose=None, propose_exc=None):
    """Dispatch parse_with_retry by stage_name: propose vs ground."""
    async def _p(client, *, system, user, stage_name):
        if stage_name == "stage3_propose":
            if propose_exc is not None:
                raise propose_exc
            return propose if propose is not None else {"candidates": []}
        return ground
    return _p


def _patches(*, ground, propose=None, propose_exc=None, search=None, verify_title=None):
    """Patch the four Stage-3 boundaries: propose/ground LLM (router), search,
    verify_by_title, and verify_doi (mocked True so tests stay offline)."""
    es = ExitStack()
    es.enter_context(patch("experiment_bot.reasoner.stage3_citations.parse_with_retry",
                           new=_router(ground=ground, propose=propose, propose_exc=propose_exc)))
    es.enter_context(patch("experiment_bot.reasoner.stage3_citations.search_works",
                           new=AsyncMock(return_value=_pool() if search is None else search)))
    es.enter_context(patch("experiment_bot.reasoner.stage3_citations.verify_by_title",
                           new=AsyncMock(return_value=verify_title)))
    es.enter_context(patch("experiment_bot.reasoner.stage3_citations.verify_doi",
                           new=AsyncMock(return_value=(True, {}))))
    return es


@pytest.mark.asyncio
async def test_stage3_grounds_and_revises_within_evidence(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    ground = {"response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "abstract reports congruent mu 480-520", "confidence": "high"}],
        "literature_range": {"mu": [480, 520]},
        "revised_value": {"mu": 500}, "revision_reason": "pool_idx 0 reports 480-520"}}
    with _patches(ground=ground):
        out, step = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"][0]["doi"] == "10.1037/real"     # REAL pool DOI
    assert "480-520" in cong["citations"][0]["abstract_snippet"]
    assert cong["value"]["mu"] == 500                        # revised within range
    assert cong["value_source"] == "literature_revised"
    assert cong["original_value"]["mu"] == 530


@pytest.mark.asyncio
async def test_stage3_drops_off_pool_citation(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    ground = {"response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 99, "rationale": "made up", "confidence": "high"}]}}
    with _patches(ground=ground):
        out, _ = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"] == []                           # off-pool dropped
    assert cong["value"]["mu"] == 530 and cong["value_source"] == "model_prior"


@pytest.mark.asyncio
async def test_stage3_rejects_out_of_range_revision(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    ground = {"response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "ok", "confidence": "medium"}],
        "literature_range": {"mu": [480, 520]},
        "revised_value": {"mu": 700}, "revision_reason": "out of its own range"}}
    with _patches(ground=ground):
        out, _ = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["value"]["mu"] == 530                        # revision rejected
    assert cong["value_source"] == "model_prior"


@pytest.mark.asyncio
async def test_stage3_empty_pool_abstains_without_ground_call(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    ground_calls = {"n": 0}
    async def _router_count(client, *, system, user, stage_name):
        if stage_name == "stage3_propose":
            return {"candidates": []}
        ground_calls["n"] += 1
        return {}
    with patch("experiment_bot.reasoner.stage3_citations.parse_with_retry", new=_router_count), \
         patch("experiment_bot.reasoner.stage3_citations.search_works", new=AsyncMock(return_value=[])), \
         patch("experiment_bot.reasoner.stage3_citations.verify_by_title", new=AsyncMock(return_value=None)):
        out, step = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"] == [] and cong.get("no_citation_reason")
    assert ground_calls["n"] == 0                            # propose ran; NO ground call on empty pool


@pytest.mark.asyncio
async def test_stage3_retrieval_off_abstains(monkeypatch):
    monkeypatch.setenv("EXPERIMENT_BOT_RETRIEVAL", "off")
    pr = AsyncMock(); sw = AsyncMock(return_value=_pool()); vt = AsyncMock(return_value=None)
    with patch("experiment_bot.reasoner.stage3_citations.parse_with_retry", new=pr), \
         patch("experiment_bot.reasoner.stage3_citations.search_works", new=sw), \
         patch("experiment_bot.reasoner.stage3_citations.verify_by_title", new=vt):
        out, _ = await run_stage3(AsyncMock(), _partial())
    pr.assert_not_awaited()                                  # no propose, no ground
    sw.assert_not_awaited()
    vt.assert_not_awaited()
    assert out["response_distributions"]["congruent"]["value_source"] == "model_prior"


@pytest.mark.asyncio
async def test_stage3_verified_canonical_enters_pool_and_cited(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    canonical = RetrievedWork(doi="10.1037/canonical", authors="MacLeod, C. M.", year=1991,
        title="Half a century of research on the Stroop effect",
        abstract="Review of Stroop interference; congruent mu around 500 ms.",
        source="openalex", cited_by_count=9000)
    propose = {"candidates": [{"authors": "MacLeod", "year": 1991,
        "title": "Half a century of research on the Stroop effect"}]}
    ground = {"response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "MacLeod review", "confidence": "high"}]}}
    # canonical added FIRST → pool_idx 0; search empty so it is the only pooled work
    with _patches(ground=ground, propose=propose, search=[], verify_title=canonical):
        out, _ = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"][0]["doi"] == "10.1037/canonical"
    assert "MacLeod" in cong["citations"][0]["authors"]


@pytest.mark.asyncio
async def test_stage3_unverifiable_candidate_excluded(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    propose = {"candidates": [{"authors": "Ghost", "year": 3000, "title": "Imaginary paper"}]}
    ground = {"response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "uses search hit", "confidence": "low"}]}}
    # verify_title=None → the imaginary paper is dropped; pool = the search hit only
    with _patches(ground=ground, propose=propose, search=_pool(), verify_title=None):
        out, _ = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"][0]["doi"] == "10.1037/real"     # only the verified search hit pooled


@pytest.mark.asyncio
async def test_stage3_propose_failure_falls_back_to_search(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    ground = {"response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "search hit", "confidence": "low"}]}}
    with _patches(ground=ground, propose_exc=RuntimeError("propose boom"),
                  search=_pool(), verify_title=None):
        out, _ = await run_stage3(AsyncMock(), _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"][0]["doi"] == "10.1037/real"     # no crash; search-only pool used
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_reasoner_stage3.py -q`
Expected: FAIL — the new tests reference `verify_by_title` in the stage3 namespace (not yet imported there) and assert propose→verify behavior the code doesn't implement; `test_stage3_empty_pool_abstains_without_ground_call` is new.

- [ ] **Step 3: Implement the propose→verify phase in `stage3_citations.py`**

3a. Update the retrieval import (line 9) to add `verify_by_title`:

```python
from experiment_bot.reasoner.retrieval import search_works, verify_by_title
```

3b. Add a pool-cap constant near the top (after `_PARAM_PHRASE` table or beside `PROMPTS_DIR`):

```python
_POOL_CAP = 30
```

3c. Replace the pool-building block — everything from the comment
`# Retrieve a deduped pool (cache queries within the run)` down to and including
the `if not pool:` early-return (the current lines that build `pool`/`seen_doi`/`qcache`)
— with the propose→verify phase + unioned pool:

```python
    # --- Propose phase: model names canonical papers (NO DOI); Python verifies each ---
    propose_system = (PROMPTS_DIR / "stage3_propose.md").read_text()
    propose_user = "## Task\n" + json.dumps(
        {"name": result.get("task", {}).get("name", ""),
         "paradigm_classes": pclasses, "parameters": paths}, indent=2)
    candidates: list = []
    try:
        proposed = await parse_with_retry(client, system=propose_system,
                                          user=propose_user, stage_name="stage3_propose")
        if isinstance(proposed, dict) and isinstance(proposed.get("candidates"), list):
            candidates = proposed["candidates"]
    except Exception as e:
        logger.warning("stage3 propose call failed (%s); using search-only pool", e)
        candidates = []

    canonical: list = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        w = await verify_by_title(cand.get("authors", ""), cand.get("year"),
                                  cand.get("title", ""))
        if w is not None:
            canonical.append(w)

    # --- Deterministic citation-ranked search (OpenAlex sorted by cited_by_count) ---
    search_hits: list = []
    qcache: dict[str, list] = {}
    for path in paths:
        q = _query_for(path, pclasses)
        if q not in qcache:
            qcache[q] = await search_works(q, per_page=5)
        search_hits.extend(qcache[q])

    # --- Union: verified-canonical first (always kept), then highest-cited search hits ---
    pool: list = []
    seen: set = set()

    def _add(w) -> None:
        k = w.doi or (w.title, w.year)
        if k in seen:
            return
        seen.add(k)
        pool.append(w)

    for w in canonical:
        _add(w)
    for w in sorted(search_hits, key=lambda x: x.cited_by_count, reverse=True):
        if len(pool) >= _POOL_CAP:
            break
        _add(w)

    if not pool:
        return _abstain_all("retrieval unavailable or no candidates found")
```

3d. Update the final `ReasoningStep` inference line to report the new counts. Replace the existing `step = ReasoningStep(...)` near the end with:

```python
    step = ReasoningStep(
        step="stage3_citations",
        inference=(f"Canonical-recall: proposed={len(candidates)}, "
                   f"title-verified={len(canonical)}, search_hits={len(search_hits)}, "
                   f"pool={len(pool)}; {n_cited} parameters cited, {n_abstain} abstained, "
                   f"{n_revised} values revised within grounded ranges."),
        evidence_lines=[], confidence="high")
    return result, step
```

Leave the ground call (`stage3_ground.md` read, `pool_json` build, `parse_with_retry(stage_name="stage3_ground")`), the four guards (off-pool drop, evidence-bounded revision, abstain, `verify_doi` loop), and the offline-switch early return UNCHANGED.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_reasoner_stage3.py -q`
Expected: PASS (8 behavioral + 2 prompt-invariant + enumerate = all green).

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `python -m pytest -q`
Expected: PASS — same count as the pre-task baseline plus the new tests (no failures, no new skips).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage3_citations.py tests/test_reasoner_stage3.py
git commit -m "feat(stage3): propose->verify phase + citation-ranked unioned pool

run_stage3 now: (1) one propose LLM call lists canonical papers (no DOI);
(2) verify_by_title confirms each against OpenAlex/CrossRef (real DOI+abstract
or dropped); (3) unions verified-canonical works (always kept) with the
highest-cited search hits, capped at 30; (4) feeds the unioned pool to the
UNCHANGED ground call + four guards. Propose failure / retrieval-off / empty
pool degrade to prior behavior. Anti-fabrication invariant intact.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Live smoke re-run + results doc

**Files:**
- Modify: `docs/retrieval-stage3-smoke.md`

This task has no unit tests — it is an empirical regression against the prior topical-only smoke. Run from the worktree root with a real network connection.

- [ ] **Step 1: Run the from-scratch reason with retrieval ON, pilot skipped**

Run (writes to a throwaway dir so the committed corpus is untouched):

```bash
EXPERIMENT_BOT_RETRIEVAL=on EXPERIMENT_BOT_OPENALEX_MAILTO=logben@stanford.edu \
  experiment-bot-reason https://deploy.expfactory.org/preview/10 \
  --label canonical_recall_smoke --skip-pilot \
  --taskcards-dir /tmp/canonical_smoke --work-dir /tmp/canonical_smoke_work -v
```

Expected: completes Stages 1–5 without refusal; a TaskCard written under `/tmp/canonical_smoke/`.

- [ ] **Step 2: Inspect citations for canonical sources + revisions**

Run (lists each citation's year/DOI/title and any literature_revised values):

```bash
python - <<'PY'
import json, glob
f = sorted(glob.glob("/tmp/canonical_smoke/*.json"))[-1]
tc = json.load(open(f))
revised = []
cites = []
for cond, body in tc.get("response_distributions", {}).items():
    for c in body.get("citations", []):
        cites.append((c.get("year"), c.get("doi"), (c.get("title") or "")[:70],
                      c.get("doi_verified")))
    if body.get("value_source") == "literature_revised":
        revised.append((cond, body.get("original_value"), body.get("value"),
                        body.get("revision_reason", "")[:80]))
print(f"file: {f}")
print(f"distinct DOIs: {len({d for _,d,_,_ in cites})}, total citations: {len(cites)}")
for y,d,t,v in sorted(set(cites)):
    print(f"  {y}  verified={v}  {d}  {t}")
print(f"revisions: {len(revised)}")
for r in revised:
    print(f"  {r}")
PY
```

Expected: at least one older/seminal/review source (e.g. a MacLeod/Heathcote/Logan-class paper) among the citations — a work the prior topical-only relevance search missed — and EITHER ≥1 `literature_revised` value OR none (an honest outcome if abstracts still state no ranges).

- [ ] **Step 3: Append the comparison to `docs/retrieval-stage3-smoke.md`**

Add a new section at the end of `docs/retrieval-stage3-smoke.md` titled
`## Canonical-recall update (propose→verify + citation-ranked search)` recording, **from the actual Step 2 output**:
- distinct DOIs and total citations vs the prior 2-DOI/2023-only result;
- the specific canonical/review source(s) now surfaced (authors, year, DOI), if any;
- the revision count, and — if still 0 — the honest statement that retrieved abstracts did not state usable ranges (no fabrication to force a revision);
- a one-line verdict on success criteria #2 (canonical source surfaced) and #3 (≥1 revision OR honest no-range finding).

Do NOT soften a null result. If no canonical source surfaced or no revision occurred, state that plainly as the finding (per memory `feedback_honest_generalization_findings`).

- [ ] **Step 4: Delete the throwaway artifacts**

Run:

```bash
rm -rf /tmp/canonical_smoke /tmp/canonical_smoke_work
```

- [ ] **Step 5: Commit the results doc**

```bash
git add docs/retrieval-stage3-smoke.md
git commit -m "docs: canonical-recall Stage 3 live smoke (authority + revision comparison)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Spec §1 (`verify_by_title` + `cited_by_count` + `sort=cited_by_count:desc`) → Task 1. ✓
- Spec §2 (`stage3_propose.md`) → Task 2. ✓
- Spec §3 (propose→verify phase, union/dedupe/cap, ground+guards unchanged) → Task 3. ✓
- Spec testing (verify_by_title cases; ranking; propose→verify; guards on unioned pool; live smoke) → Tasks 1, 3, 4. ✓
- Spec error-handling table (propose fail → search-only; unverifiable dropped; empty → abstain; retrieval-off; no-range → no revision) → Task 3 tests cover propose-failure, unverifiable-dropped, empty-pool-no-ground-call, retrieval-off; no-range is the unchanged guard. ✓
- Spec success criteria #1–#5 → invariant preserved (DOI from API only), canonical surfaced + revision-or-honest-null verified in Task 4. ✓

**Placeholder scan:** No TBD/TODO. Every code step shows complete code; the smoke command is concrete (`experiment-bot-reason ... --label ... --skip-pilot`). Task 4 Step 3 is descriptive (a results writeup keyed to actual output) by necessity, with explicit anti-softener instruction.

**Type/name consistency:** `verify_by_title(authors, year, title, *, mailto, title_threshold)` defined in Task 1, called identically in Task 3 (positional `authors, year, title`). `cited_by_count` field used by `sorted(..., key=lambda x: x.cited_by_count)` in Task 3. `search_works(..., sort_by_citations=...)` default True (Task 1) — Task 3 calls `search_works(q, per_page=5)` (sort on); `verify_by_title` calls with `sort_by_citations=False`. `_POOL_CAP` defined and used in Task 3. Stage names `"stage3_propose"` / `"stage3_ground"` consistent across prompt, code, and test router. `_router`/`_patches` test helpers defined before use.

**Scope:** Single focused enhancement to one subsystem; 4 sequential tasks. No decomposition needed.

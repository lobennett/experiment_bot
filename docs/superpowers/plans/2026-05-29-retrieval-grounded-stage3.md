# Retrieval-Grounded Stage 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Spec-compliance reviewer per task; SKIP code-quality reviewer (per `feedback_skip_code_quality_reviewer`). Tasks are SEQUENTIAL. Steps use `- [ ]` tracking.

**Goal:** Make Stage 3 citations structurally honest — the LLM can only cite works Python actually retrieved from the literature, ground rationales in retrieved abstracts, and revise a parameter only within a range grounded in a cited abstract; otherwise abstain (model-prior). Fabrication becomes impossible by construction.

**Architecture:** New `reasoner/retrieval.py` (OpenAlex search + abstract reconstruction + CrossRef fallback, never-raises). Stage 3 rewritten as Python orchestration: deterministic per-parameter queries → retrieved candidate pool → one LLM "ground" call that cites only by pool index → Python guards (pool-membership filter, evidence-bounded value revision, `verify_doi` title-gate, abstain). Offline switch + empty-pool both degrade to abstain.

**Tech Stack:** Python 3.12, httpx (async), pytest-asyncio, OpenAlex + CrossRef REST APIs, Claude via `LLMClient.complete` (single-shot; mocked in tests).

**Spec:** `docs/superpowers/specs/2026-05-29-retrieval-grounded-stage3-design.md`.

**Guardrails:** every failure mode degrades to *honest* (abstain / model-prior), never to fabricated. Builds on the committed honest-baseline (rationale field, abstain path, `verify_doi` title-check). Do not touch the oracle/executor/navigation.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/experiment_bot/reasoner/retrieval.py` | Create | OpenAlex/CrossRef literature client: `RetrievedWork`, `search_works`, abstract reconstruction |
| `src/experiment_bot/taskcard/types.py` | Modify | `ParameterValue` audit fields; `Citation.abstract_snippet` |
| `src/experiment_bot/reasoner/prompts/stage3_ground.md` | Create | The ground-call prompt (cite by pool_idx, abstain, evidence-bounded revise) |
| `src/experiment_bot/reasoner/stage3_citations.py` | Rewrite | Query-build → pool → ground call → guards + offline switch |
| `tests/test_retrieval.py` | Create | retrieval unit tests (mock httpx) |
| `tests/test_taskcard_types.py` | Modify | ParameterValue audit-field + abstract_snippet round-trip |
| `tests/test_reasoner_stage3.py` | Modify | rewrite for the ground+revise orchestration (mock retrieval + LLM) |
| `docs/retrieval-stage3-smoke.md` | Create | live-smoke results note (Task 5) |

---

## Task 1: `retrieval.py` — OpenAlex search + abstract reconstruction + CrossRef fallback

**Files:**
- Create: `src/experiment_bot/reasoner/retrieval.py`
- Test: `tests/test_retrieval.py`

**Why:** Stage 3 must retrieve real works to ground against. This module is pure I/O + parsing, never raises (network error → `[]`), so callers can treat "no results" uniformly as the abstain trigger.

- [ ] **Step 1: Write failing tests** — `tests/test_retrieval.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.reasoner.retrieval import search_works, _reconstruct_abstract, RetrievedWork


def test_reconstruct_abstract_from_inverted_index():
    inv = {"Stroop": [0], "interference": [1], "is": [2], "robust": [3]}
    assert _reconstruct_abstract(inv) == "Stroop interference is robust"
    assert _reconstruct_abstract(None) == ""
    assert _reconstruct_abstract({}) == ""


def _mk_client(json_obj, status=200):
    resp = MagicMock(); resp.status_code = status; resp.json = MagicMock(return_value=json_obj)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_search_works_parses_openalex_hit_with_abstract():
    oa = {"results": [{
        "doi": "https://doi.org/10.1037/x", "publication_year": 2009,
        "title": "Ex-Gaussian analysis of Stroop RT",
        "authorships": [{"author": {"display_name": "Jane Heathcote"}}],
        "abstract_inverted_index": {"mu": [0], "near": [1], "500": [2], "ms": [3]},
    }]}
    with patch("httpx.AsyncClient", return_value=_mk_client(oa)):
        works = await search_works("stroop ex-gaussian", per_page=5)
    assert len(works) == 1
    w = works[0]
    assert w.doi == "10.1037/x"          # normalized: scheme/host stripped
    assert w.year == 2009 and "Heathcote" in w.authors
    assert w.abstract == "mu near 500 ms" and w.source == "openalex"


@pytest.mark.asyncio
async def test_search_works_network_error_returns_empty():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=RuntimeError("offline"))
    with patch("httpx.AsyncClient", return_value=client):
        assert await search_works("anything") == []


@pytest.mark.asyncio
async def test_search_works_falls_back_to_crossref_when_openalex_empty():
    # OpenAlex returns no results; CrossRef returns one item.
    oa_empty = {"results": []}
    cr = {"message": {"items": [{
        "DOI": "10.1037/y", "title": ["A real review of conflict tasks"],
        "published": {"date-parts": [[2015]]},
        "author": [{"family": "Smith", "given": "J."}],
        "abstract": "<jats:p>Conflict effects summarized.</jats:p>",
    }]}}
    calls = {"n": 0}
    resp_oa = MagicMock(); resp_oa.status_code = 200; resp_oa.json = MagicMock(return_value=oa_empty)
    resp_cr = MagicMock(); resp_cr.status_code = 200; resp_cr.json = MagicMock(return_value=cr)
    async def _get(url, *a, **k):
        calls["n"] += 1
        return resp_oa if "openalex" in url else resp_cr
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=_get)
    with patch("httpx.AsyncClient", return_value=client):
        works = await search_works("conflict tasks")
    assert len(works) == 1 and works[0].source == "crossref"
    assert works[0].doi == "10.1037/y" and "Smith" in works[0].authors
    assert "Conflict effects" in works[0].abstract  # JATS tags stripped
```

Run: `uv run pytest tests/test_retrieval.py -v` → FAIL (module missing).

- [ ] **Step 2: Implement `src/experiment_bot/reasoner/retrieval.py`:**

```python
from __future__ import annotations
import logging
import os
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_OPENALEX = "https://api.openalex.org/works"
_CROSSREF = "https://api.crossref.org/works"
_ABSTRACT_CAP = 2000


@dataclass
class RetrievedWork:
    doi: str | None
    authors: str
    year: int | None
    title: str
    abstract: str
    source: str  # "openalex" | "crossref"


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.strip().replace("https://doi.org/", "").replace("http://doi.org/", "").lower() or None


def _reconstruct_abstract(inv: dict | None) -> str:
    """Rebuild text from OpenAlex abstract_inverted_index {token: [positions]}."""
    if not inv:
        return ""
    positioned: list[tuple[int, str]] = []
    for token, posns in inv.items():
        for p in posns:
            positioned.append((p, token))
    positioned.sort(key=lambda t: t[0])
    return " ".join(tok for _, tok in positioned)[:_ABSTRACT_CAP]


def _oa_authors(work: dict) -> str:
    names = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
    return ", ".join(n for n in names if n)


def _strip_jats(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()[:_ABSTRACT_CAP]


async def _openalex(client: httpx.AsyncClient, query: str, per_page: int,
                    year_from: int | None, mailto: str | None) -> list[RetrievedWork]:
    params = {"search": query, "per-page": str(per_page)}
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
        ))
    return out


async def _crossref(client: httpx.AsyncClient, query: str, per_page: int,
                    mailto: str | None) -> list[RetrievedWork]:
    params = {"query": query, "rows": str(per_page)}
    if mailto:
        params["mailto"] = mailto
    resp = await client.get(_CROSSREF, params=params)
    if resp.status_code != 200:
        return []
    out: list[RetrievedWork] = []
    for it in resp.json().get("message", {}).get("items", []):
        title = (it.get("title") or [""])[0]
        year = None
        dp = it.get("published", {}).get("date-parts", [[None]])
        if dp and dp[0]:
            year = dp[0][0]
        authors = ", ".join(
            f"{a.get('family','')}, {a.get('given','')}".strip(", ")
            for a in it.get("author", [])
        )
        out.append(RetrievedWork(
            doi=_norm_doi(it.get("DOI")),
            authors=authors,
            year=year,
            title=title,
            abstract=_strip_jats(it.get("abstract", "")),
            source="crossref",
        ))
    return out


async def search_works(query: str, *, per_page: int = 5,
                       year_from: int | None = None,
                       mailto: str | None = None) -> list[RetrievedWork]:
    """Search OpenAlex; fall back to CrossRef when OpenAlex yields nothing.
    NEVER raises — any network/parse error returns []."""
    mailto = mailto or os.environ.get("EXPERIMENT_BOT_OPENALEX_MAILTO")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            works = await _openalex(client, query, per_page, year_from, mailto)
            if not works:
                works = await _crossref(client, query, per_page, mailto)
            return works
    except Exception as e:
        logger.warning("retrieval.search_works failed for %r: %s", query, e)
        return []
```

- [ ] **Step 3:** `uv run pytest tests/test_retrieval.py -v` → all pass.
- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/reasoner/retrieval.py tests/test_retrieval.py
git commit -m "$(cat <<'EOF'
feat(retrieval): OpenAlex+CrossRef literature client for grounded Stage 3

New reasoner/retrieval.py: search_works() queries OpenAlex (reconstructing the
abstract from abstract_inverted_index), falls back to CrossRef metadata when
OpenAlex yields nothing, normalizes DOIs, and NEVER raises (network/parse error
-> []). This is the retrieval substrate for the grounded Stage 3; an empty
result is the uniform abstain trigger. +4 unit tests (mock httpx).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `ParameterValue` audit fields + `Citation.abstract_snippet`

**Files:**
- Modify: `src/experiment_bot/taskcard/types.py`
- Test: `tests/test_taskcard_types.py`

**Why:** Record provenance of every value (model-prior vs literature-revised) and the auditable grounding text for each citation.

- [ ] **Step 1: Failing tests** — append to `tests/test_taskcard_types.py`:

```python
def test_parameter_value_audit_fields_round_trip():
    from experiment_bot.taskcard.types import ParameterValue
    d = {
        "value": {"mu": 510},
        "distribution": "ex_gaussian",
        "value_source": "literature_revised",
        "original_value": {"mu": 530},
        "revision_reason": "retrieved review reports mu 480-520; moved 530->510",
    }
    pv = ParameterValue.from_dict(d)
    assert pv.value_source == "literature_revised"
    assert pv.original_value == {"mu": 530}
    assert pv.to_dict()["value_source"] == "literature_revised"
    assert pv.to_dict()["original_value"] == {"mu": 530}


def test_parameter_value_audit_fields_default_model_prior():
    from experiment_bot.taskcard.types import ParameterValue
    pv = ParameterValue.from_dict({"value": {"mu": 530}})
    assert pv.value_source == "model_prior"
    assert pv.original_value is None and pv.revision_reason == ""


def test_citation_abstract_snippet_round_trips():
    from experiment_bot.taskcard.types import Citation
    c = Citation.from_dict({
        "doi": "10.1037/x", "authors": "Heathcote, J.", "year": 2009,
        "title": "Ex-Gaussian Stroop", "rationale": "supports mu",
        "abstract_snippet": "mu near 500 ms in young adults",
    })
    assert c.abstract_snippet == "mu near 500 ms in young adults"
    assert c.to_dict()["abstract_snippet"] == "mu near 500 ms in young adults"
```

Run: FAIL (fields missing).

- [ ] **Step 2: Add `abstract_snippet` to `Citation`** (after `quote`, before `doi_verified`):

```python
    quote: str = ""
    abstract_snippet: str = ""   # retrieved abstract text grounding this citation
    doi_verified: bool = False
    doi_verified_at: str | None = None
```

- [ ] **Step 3: Add audit fields to `ParameterValue`** (after `distribution`):

```python
    distribution: str = "ex_gaussian"
    value_source: Literal["model_prior", "literature_revised"] = "model_prior"
    original_value: dict | None = None
    revision_reason: str = ""
```

And in `from_dict`, add:
```python
            value_source=d.get("value_source", "model_prior"),
            original_value=d.get("original_value"),
            revision_reason=d.get("revision_reason", ""),
```
And in `to_dict`, add the three keys (`value_source`, `original_value`, `revision_reason`). (`Citation.to_dict` uses `asdict`, so `abstract_snippet` is automatic.)

- [ ] **Step 4:** `uv run pytest tests/test_taskcard_types.py -v` → all pass.
- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/taskcard/types.py tests/test_taskcard_types.py
git commit -m "$(cat <<'EOF'
feat(types): ParameterValue value-source audit fields + Citation.abstract_snippet

ParameterValue gains value_source (model_prior|literature_revised), original_value,
revision_reason so a literature-grounded revision is auditable. Citation gains
abstract_snippet (the retrieved abstract text grounding the cite). All optional,
backward-compatible defaults. +3 round-trip tests.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `prompts/stage3_ground.md` — the ground-call prompt

**Files:**
- Create: `src/experiment_bot/reasoner/prompts/stage3_ground.md`
- Test: `tests/test_reasoner_stage3.py` (invariant test)

**Why:** The prompt is the contract for the ground call. It must force citing by pool index, abstaining honestly, and revising only within a grounded range.

- [ ] **Step 1: Failing invariant test** — append to `tests/test_reasoner_stage3.py`:

```python
def test_stage3_ground_prompt_invariants():
    from pathlib import Path
    p = Path("src/experiment_bot/reasoner/prompts/stage3_ground.md").read_text()
    assert "pool_idx" in p                       # cite by pool index
    assert "no_citation_reason" in p             # abstain path
    assert "revised_value" in p and "literature_range" in p
    # must forbid citing anything not in the pool
    assert "only" in p.lower() and "pool" in p.lower()
    # must forbid fabricated verbatim quotes
    assert "do not" in p.lower() and ("quote" in p.lower() or "fabricat" in p.lower())
```

Run: FAIL (file missing).

- [ ] **Step 2: Create `src/experiment_bot/reasoner/prompts/stage3_ground.md`:**

```markdown
You are grounding the citations for a cognitive task's behavioral parameters in
REAL retrieved literature. You are given (1) each parameter with its current
point-estimate value, and (2) a NUMBERED POOL of works that were actually
retrieved from OpenAlex/CrossRef, each with its abstract.

ABSOLUTE RULES:
- You may ONLY cite works from the POOL, by their `pool_idx`. You CANNOT cite a
  DOI or paper that is not in the pool. There is no other source of truth.
- Ground every `rationale` in the cited work's ABSTRACT as shown. Do NOT invent
  verbatim quotes, page numbers, or table references — they are not provided and
  must not be fabricated. The rationale is your own words about why the abstract
  supports the parameter.
- Assert a `literature_range` ONLY if a cited abstract actually states such a
  range. If no abstract gives a range, leave it null.
- Propose a `revised_value` ONLY when a cited abstract supports a value different
  from the current estimate, and ONLY within the `literature_range` you assert.
  Give `revision_reason` naming the supporting `pool_idx`. Otherwise null (the
  current value stands as a model-prior estimate).
- ABSTAIN when the pool contains nothing that genuinely supports a parameter:
  return empty `citations` and a `no_citation_reason`. An honest abstention is
  REQUIRED over citing a non-supporting paper.

Return a JSON object keyed by parameter path:
{
  "response_distributions/<cond>/mu": {
    "citations": [{"pool_idx": <int>, "rationale": "<grounded in that abstract>",
                   "confidence": "high|medium|low"}],
    "literature_range": {"mu": [<low>, <high>]} | null,
    "revised_value": {"mu": <number>} | null,
    "revision_reason": "<why, cites pool_idx>" | null,
    "no_citation_reason": "<required iff citations empty>"
  },
  ...
}

Return JSON only, no preamble.
```

- [ ] **Step 3:** `uv run pytest tests/test_reasoner_stage3.py::test_stage3_ground_prompt_invariants -v` → pass.
- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/reasoner/prompts/stage3_ground.md tests/test_reasoner_stage3.py
git commit -m "$(cat <<'EOF'
feat(reasoner): stage3_ground.md — cite-by-pool-index grounding prompt

The ground-call prompt: cite ONLY by pool_idx (cannot introduce an off-pool DOI),
ground rationale in the retrieved abstract, assert a range only if an abstract
states it, revise a value only within that grounded range, abstain otherwise.
+1 invariant test.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Rewrite `stage3_citations.py` — orchestrate ground + revise

**Files:**
- Modify: `src/experiment_bot/reasoner/stage3_citations.py`
- Test: `tests/test_reasoner_stage3.py` (rewrite the run_stage3 tests)

**Why:** The core change. Replace the retro-citation LLM call with retrieval-grounded orchestration + Python guards.

- [ ] **Step 1: Failing tests** — replace the existing `run_stage3` behavior tests in `tests/test_reasoner_stage3.py` (keep `test_enumerate_parameters_*`, the prompt-invariant, and the malformed-path tests). Add:

```python
import pytest
from unittest.mock import AsyncMock, patch
from experiment_bot.reasoner.stage3_citations import run_stage3
from experiment_bot.reasoner.retrieval import RetrievedWork
from experiment_bot.llm.protocol import LLMResponse


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
            source="openalex")]


@pytest.mark.asyncio
async def test_stage3_grounds_and_revises_within_evidence(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text='''{
      "response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "abstract reports congruent mu 480-520", "confidence": "high"}],
        "literature_range": {"mu": [480, 520]},
        "revised_value": {"mu": 500}, "revision_reason": "pool_idx 0 reports 480-520"
      }
    }'''))
    with patch("experiment_bot.reasoner.stage3_citations.search_works",
               new=AsyncMock(return_value=_pool())):
        out, step = await run_stage3(fake, _partial())
    cong = out["response_distributions"]["congruent"]
    # citation carries the REAL pool DOI + abstract snippet
    assert cong["citations"][0]["doi"] == "10.1037/real"
    assert "480-520" in cong["citations"][0]["abstract_snippet"]
    # value revised within the grounded range, recorded
    assert cong["value"]["mu"] == 500
    assert cong["value_source"] == "literature_revised"
    assert cong["original_value"]["mu"] == 530


@pytest.mark.asyncio
async def test_stage3_drops_off_pool_citation(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text='''{
      "response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 99, "rationale": "made up", "confidence": "high"}]
      }
    }'''))
    with patch("experiment_bot.reasoner.stage3_citations.search_works",
               new=AsyncMock(return_value=_pool())):
        out, _ = await run_stage3(fake, _partial())
    # off-pool idx dropped -> no citations -> value unchanged, model_prior
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"] == []
    assert cong["value"]["mu"] == 530 and cong["value_source"] == "model_prior"


@pytest.mark.asyncio
async def test_stage3_rejects_out_of_range_revision(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text='''{
      "response_distributions/congruent/mu": {
        "citations": [{"pool_idx": 0, "rationale": "ok", "confidence": "medium"}],
        "literature_range": {"mu": [480, 520]},
        "revised_value": {"mu": 700}, "revision_reason": "out of its own range"
      }
    }'''))
    with patch("experiment_bot.reasoner.stage3_citations.search_works",
               new=AsyncMock(return_value=_pool())):
        out, _ = await run_stage3(fake, _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["value"]["mu"] == 530           # revision rejected
    assert cong["value_source"] == "model_prior"


@pytest.mark.asyncio
async def test_stage3_empty_pool_abstains_without_llm(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    fake = AsyncMock(); fake.complete = AsyncMock()
    with patch("experiment_bot.reasoner.stage3_citations.search_works",
               new=AsyncMock(return_value=[])):
        out, step = await run_stage3(fake, _partial())
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"] == [] and cong.get("no_citation_reason")
    fake.complete.assert_not_awaited()          # no ground call on empty pool


@pytest.mark.asyncio
async def test_stage3_retrieval_off_abstains(monkeypatch):
    monkeypatch.setenv("EXPERIMENT_BOT_RETRIEVAL", "off")
    fake = AsyncMock(); fake.complete = AsyncMock()
    sw = AsyncMock(return_value=_pool())
    with patch("experiment_bot.reasoner.stage3_citations.search_works", new=sw):
        out, _ = await run_stage3(fake, _partial())
    sw.assert_not_awaited()                      # no retrieval when off
    fake.complete.assert_not_awaited()
    assert out["response_distributions"]["congruent"]["value_source"] == "model_prior"
```

Run: FAIL.

- [ ] **Step 2: Rewrite `run_stage3`** in `src/experiment_bot/reasoner/stage3_citations.py`. Keep `_enumerate_parameters` and the path-parsing/merge target-resolution from the current file. Replace the body:

```python
from __future__ import annotations
import copy
import json
import logging
import os
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.parse_retry import parse_with_retry
from experiment_bot.reasoner.retrieval import search_works
from experiment_bot.reasoner.openalex import verify_doi
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"

# param-name -> search phrase (deterministic queries; reproducible, no LLM call)
_PARAM_PHRASE = {
    "mu": "ex-Gaussian reaction time distribution",
    "sigma": "ex-Gaussian reaction time distribution",
    "tau": "ex-Gaussian reaction time distribution",
    "ssrt": "stop-signal reaction time",
    "cse_magnitude": "congruency sequence effect",
    "post_error_slowing": "post-error slowing",
    "accuracy": "accuracy error rate",
    "omission": "omission error rate",
    "lag1_autocorr": "sequential dependency reaction time",
}


def _query_for(path: str, paradigm_classes: list[str]) -> str:
    _, key, param = (path.split("/", 2) + ["", ""])[:3]
    phrase = _PARAM_PHRASE.get(param, param.replace("_", " "))
    classes = " ".join(paradigm_classes[:2])
    return f"{classes} {key if key != '_' else ''} {phrase}".strip()
```

(NOTE: `_enumerate_parameters` already exists above this — keep it.)

Then the new `run_stage3`:

```python
async def run_stage3(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    """Stage 3 (retrieval-grounded): retrieve a real-literature pool per parameter,
    then one LLM 'ground' call cites ONLY by pool index, grounds rationale in
    retrieved abstracts, and revises a value ONLY within a grounded range —
    else abstains (model-prior). Python enforces every guard. Fabrication is
    structurally impossible."""
    result = copy.deepcopy(partial)
    paths = _enumerate_parameters(result)
    pclasses = result.get("task", {}).get("paradigm_classes", []) or []

    def _abstain_all(reason: str):
        for path in paths:
            tgt = _resolve_target(result, path)
            if tgt is not None and not tgt.get("citations"):
                tgt["no_citation_reason"] = reason
                tgt.setdefault("value_source", "model_prior")
        return result, ReasoningStep(
            step="stage3_citations",
            inference=f"Retrieval-grounded Stage 3 abstained for all {len(paths)} parameters ({reason}).",
            evidence_lines=[], confidence="high")

    # Offline switch
    if os.environ.get("EXPERIMENT_BOT_RETRIEVAL", "").lower() in ("off", "0", "false"):
        return _abstain_all("retrieval disabled (EXPERIMENT_BOT_RETRIEVAL=off)")

    # Retrieve a deduped pool (cache queries within the run)
    pool: list = []
    seen_doi: set = set()
    qcache: dict[str, list] = {}
    for path in paths:
        q = _query_for(path, pclasses)
        if q not in qcache:
            qcache[q] = await search_works(q, per_page=5)
        for w in qcache[q]:
            k = w.doi or (w.title, w.year)
            if k not in seen_doi:
                seen_doi.add(k)
                pool.append(w)

    if not pool:
        return _abstain_all("retrieval unavailable or no candidates found")

    # One LLM ground call
    system = (PROMPTS_DIR / "stage3_ground.md").read_text()
    pool_json = [
        {"pool_idx": i, "doi": w.doi, "authors": w.authors, "year": w.year,
         "title": w.title, "abstract": w.abstract}
        for i, w in enumerate(pool)
    ]
    cur = {p: _resolve_target(result, p) for p in paths}
    user = "## Parameters + current values\n" + json.dumps(
        {"parameters": {p: (cur[p] or {}).get("value") for p in paths}}, indent=2
    ) + "\n\n## Retrieved pool\n" + json.dumps(pool_json, indent=2)
    try:
        grounded = await parse_with_retry(client, system=system, user=user,
                                          stage_name="stage3_ground")
    except Exception as e:
        logger.warning("stage3 ground call failed (%s); abstaining all", e)
        return _abstain_all(f"ground call failed: {e}")

    n_cited = n_revised = n_abstain = 0
    to_verify: list[dict] = []
    for path in paths:
        tgt = _resolve_target(result, path)
        if tgt is None:
            continue
        body = grounded.get(path) or {}
        param = path.split("/", 2)[-1]
        kept: list[dict] = []
        for c in body.get("citations", []):
            idx = c.get("pool_idx")
            if not isinstance(idx, int) or not (0 <= idx < len(pool)):
                continue  # GUARD: drop off-pool citations
            w = pool[idx]
            cit = {"doi": w.doi, "authors": w.authors, "year": w.year,
                   "title": w.title, "rationale": c.get("rationale", ""),
                   "confidence": c.get("confidence", "low"),
                   "abstract_snippet": w.abstract[:500]}
            kept.append(cit)
            to_verify.append(cit)
        if kept:
            tgt["citations"] = kept
            n_cited += 1
            lr = body.get("literature_range")
            if isinstance(lr, dict):
                tgt.setdefault("literature_range", {}).update(lr)
            # GUARD: evidence-bounded revision
            rv = body.get("revised_value")
            if isinstance(rv, dict) and isinstance(lr, dict) and param in rv and param in lr:
                low, high = lr[param][0], lr[param][1]
                new = rv[param]
                if isinstance(new, (int, float)) and low <= new <= high:
                    orig = dict(tgt.get("value", {}))
                    tgt.setdefault("value", {})[param] = new
                    tgt["value_source"] = "literature_revised"
                    tgt["original_value"] = orig
                    tgt["revision_reason"] = body.get("revision_reason", "")
                    n_revised += 1
                else:
                    tgt["value_source"] = "model_prior"
                    logger.warning("stage3: rejected out-of-range revision for %s: %r not in %r",
                                   path, new, lr.get(param))
            else:
                tgt.setdefault("value_source", "model_prior")
        else:
            tgt["citations"] = []
            tgt["no_citation_reason"] = body.get("no_citation_reason", "no pool work supported this parameter")
            tgt.setdefault("value_source", "model_prior")
            n_abstain += 1

    # GUARD: verify_doi title-gate on survivors (independent of pool source)
    for cit in to_verify:
        try:
            ok, _m = await verify_doi(doi=cit["doi"], expected_authors=cit["authors"],
                                      expected_year=int(cit["year"]), expected_title=cit["title"])
        except Exception:
            ok = False
        cit["doi_verified"] = bool(ok)

    step = ReasoningStep(
        step="stage3_citations",
        inference=(f"Retrieval-grounded: pool={len(pool)} works; {n_cited} parameters cited, "
                   f"{n_abstain} abstained, {n_revised} values revised within grounded ranges."),
        evidence_lines=[], confidence="high")
    return result, step
```

You must also add a `_resolve_target(result, path)` helper that returns the dict to mutate for a given path (reuse the section/key logic already in the file's merge loop — extract it):

```python
def _resolve_target(result: dict, path: str) -> dict | None:
    parts = path.split("/")
    section = parts[0]
    key = parts[1] if len(parts) > 1 else None
    if section == "response_distributions":
        return result.get("response_distributions", {}).get(key)
    if section == "temporal_effects":
        return result.get("temporal_effects", {}).get(key)
    if section == "between_subject_jitter":
        return result.get("between_subject_jitter")
    return None
```

Delete the old retro-citation merge body (the `citations_map`/`_deep`/path-split loop) that this replaces. Keep `_enumerate_parameters`.

- [ ] **Step 3:** `uv run pytest tests/test_reasoner_stage3.py -v` → all pass (new ground tests + retained enumerate/prompt/malformed tests; remove now-obsolete retro-citation tests like the old `test_stage3_attaches_citations_and_ranges` and `test_stage3_skips_malformed_or_unmatched_citation_paths` if they assert the old `citations_map` contract — replace with the `_resolve_target`/path tests as needed).
- [ ] **Step 4:** `uv run pytest -x -q` → full suite green.
- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/stage3_citations.py tests/test_reasoner_stage3.py
git commit -m "$(cat <<'EOF'
feat(reasoner): retrieval-grounded Stage 3 (ground + revise)

run_stage3 rewritten: deterministic per-parameter queries -> real-literature pool
(retrieval.search_works) -> one LLM ground call that cites ONLY by pool_idx ->
Python guards: off-pool citations dropped; value revision applied ONLY within a
literature_range grounded in a cited abstract (recorded via value_source/
original_value/revision_reason); verify_doi title-gate on survivors; abstain
(model-prior) on empty pool, retrieval-off, or ground-call failure. Citations
carry real pool DOI + abstract_snippet. Fabrication is structurally impossible
(the model cannot name a DOI we did not retrieve). +5 orchestration tests.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Live smoke on one paradigm + results note

**Files:**
- Create: `docs/retrieval-stage3-smoke.md`

**Why:** Verify against real OpenAlex that emitted citations are all from the retrieved pool and abstentions are explicit — the end-to-end honesty proof.

- [ ] **Step 1: Restore a clean stage5-minus-citations resume point** for one dev paradigm (per `project_reasoner_work_staleness`): rebuild `.reasoner_work/expfactory_stroop/stage2.json` (or run Stages 1–2 fresh) so Stage 3 can run on real Stage-2 values. Simplest: run the reasoner to Stage 2 only is not a flag, so instead run a from-scratch reason with retrieval ON and capture Stage 3's behavior in the log.

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp11
EXPERIMENT_BOT_OPENALEX_MAILTO="logben@stanford.edu" \
  uv run experiment-bot-reason https://deploy.expfactory.org/preview/10/ \
  --label expfactory_stroop_retrieval_smoke --skip-pilot \
  > /tmp/stage3-retrieval-smoke.log 2>&1; echo "exit=$?"; tail -30 /tmp/stage3-retrieval-smoke.log
```

- [ ] **Step 2: Verify honesty invariants** on the produced card:

```bash
python3 - <<'PYEOF'
import json, glob
card = sorted(glob.glob("taskcards/expfactory_stroop_retrieval_smoke/*.json"))[-1]
d = json.load(open(card))
cits, abstains, revised = 0, 0, 0
for cond, v in d.get("response_distributions", {}).items():
    cs = v.get("citations", [])
    cits += len(cs)
    if not cs and v.get("no_citation_reason"): abstains += 1
    if v.get("value_source") == "literature_revised": revised += 1
    for c in cs:
        assert c.get("doi"), "every citation has a DOI"
        assert "abstract_snippet" in c, "every citation has grounding text"
print(f"citations={cits} abstained_params={abstains} revised={revised}")
print("Stage4 verified rate:", sum(c.get('doi_verified',False)
      for v in d['response_distributions'].values() for c in v.get('citations',[])))
PYEOF
```

Expected: it RUNS (no Stage-3 refusal — the model now cites from a pool or abstains), every citation has a DOI + abstract_snippet, and there is a healthy mix of cited + abstained parameters. (If most parameters abstain, that is the honest state — record it.)

- [ ] **Step 3: Write `docs/retrieval-stage3-smoke.md`** — record: pool sizes, # cited vs abstained vs revised, Stage-4 verification rate, 2–3 example grounded citations (DOI + abstract_snippet + rationale), and an honest statement of coverage (how many parameters found real support vs stayed model-prior). Contrast with the fabricated committed corpus.

- [ ] **Step 4: Commit** (the smoke TaskCard label is a throwaway — delete the `taskcards/expfactory_stroop_retrieval_smoke/` dir after recording, keep only the doc).

```bash
rm -rf taskcards/expfactory_stroop_retrieval_smoke .reasoner_work/expfactory_stroop_retrieval_smoke
git add docs/retrieval-stage3-smoke.md
git commit -m "docs: retrieval-grounded Stage 3 live smoke results

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** retrieval.py → T1; ParameterValue/Citation fields → T2; ground prompt → T3; orchestration + all four guards (pool-membership, evidence-bounded revision, verify_doi, abstain) + offline switch → T4; live smoke → T5. All spec components covered. ✓

**Placeholder scan:** none. Every code step has concrete code; Task 5's verification is a real script. The only judgement call flagged inline is which obsolete retro-citation tests to remove in T4 Step 3 (named explicitly).

**Type consistency:** `RetrievedWork{doi,authors,year,title,abstract,source}` consistent across T1 + T4. `search_works(query,*,per_page,year_from,mailto)` consistent (T1 def, T4 call uses `per_page=5`). `_resolve_target(result, path) -> dict|None` defined + used in T4. `ParameterValue.value_source/original_value/revision_reason` (T2) written by T4. `Citation.abstract_snippet` (T2) written by T4. ✓

**Guardrail check:** every failure path (offline, empty pool, ground-call failure, off-pool idx, out-of-range revision) degrades to abstain/model-prior — never fabricated. Builds on committed honest-baseline (rationale, abstain, verify_doi title-check). ✓

---

## Execution Handoff

Execute via **superpowers:subagent-driven-development** — fresh implementer per task, spec-compliance reviewer between tasks, SKIP code-quality reviewer. Sequential. Task 5 is a live run (real OpenAlex; needs network) — gate it on Tasks 1–4 being green.

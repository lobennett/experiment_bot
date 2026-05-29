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


@pytest.mark.asyncio
async def test_stage3_dedups_repeated_doi_within_parameter(monkeypatch):
    monkeypatch.delenv("EXPERIMENT_BOT_RETRIEVAL", raising=False)
    # mu, sigma, tau share one ParameterValue dict and each cites the SAME pool work
    # → the work appears ONCE in the tgt's citations, not three times.
    ground = {
        "response_distributions/congruent/mu": {
            "citations": [{"pool_idx": 0, "rationale": "a", "confidence": "high"}]},
        "response_distributions/congruent/sigma": {
            "citations": [{"pool_idx": 0, "rationale": "b", "confidence": "high"}]},
        "response_distributions/congruent/tau": {
            "citations": [{"pool_idx": 0, "rationale": "c", "confidence": "high"}]},
    }
    with _patches(ground=ground):
        out, _ = await run_stage3(AsyncMock(), _partial())
    dois = [c["doi"] for c in out["response_distributions"]["congruent"]["citations"]]
    assert dois == ["10.1037/real"]                          # deduped, not 3 copies


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


def test_enumerate_parameters_lists_all_paths():
    partial = {
        "response_distributions": {
            "go": {"value": {"mu": 480, "sigma": 60, "tau": 80}}
        },
        "temporal_effects": {
            "post_error_slowing": {"value": {"enabled": True, "slowing_ms_min": 30, "slowing_ms_max": 80}}
        },
        "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}},
    }
    paths = _enumerate_parameters(partial)
    assert "response_distributions/go/mu" in paths
    assert "response_distributions/go/sigma" in paths
    assert "response_distributions/go/tau" in paths
    assert "temporal_effects/post_error_slowing/slowing_ms_min" in paths
    assert "temporal_effects/post_error_slowing/slowing_ms_max" in paths
    # 'enabled' is excluded — it's not a numeric parameter
    assert "temporal_effects/post_error_slowing/enabled" not in paths
    assert "between_subject_jitter/_/rt_mean_sd_ms" in paths


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

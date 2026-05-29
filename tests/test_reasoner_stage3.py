import pytest
from unittest.mock import AsyncMock, patch
from experiment_bot.reasoner.stage3_citations import run_stage3, _enumerate_parameters
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

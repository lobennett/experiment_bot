import pytest
from unittest.mock import patch, AsyncMock
from experiment_bot.reasoner.stage4_doi_verify import run_stage4

# ---------------------------------------------------------------------------
# Task 7 — Stage 4 hardening: malformed citations must NOT raise KeyError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage4_missing_doi_does_not_raise():
    """Citation without 'doi' key is skipped (doi_verified=False), not KeyError."""
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {"mu": 580},
                "citations": [
                    {"authors": "Smith, J.", "year": 2020, "title": "no doi here"},
                ],
            }
        }
    }
    # verify_doi should NOT be called — no valid doi to submit
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {}))) as mock_verify:
        out, step = await run_stage4(partial)
    mock_verify.assert_not_called()
    cit = out["response_distributions"]["congruent"]["citations"][0]
    assert cit["doi_verified"] is False
    assert "doi_verified_at" in cit
    assert "skipped" in step.inference.lower() or "malformed" in step.inference.lower()


@pytest.mark.asyncio
async def test_stage4_missing_authors_does_not_raise():
    """Citation without 'authors' key is skipped, not KeyError."""
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {},
                "citations": [{"doi": "10.0000/x", "year": 2021, "title": "no authors"}],
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {}))) as mock_verify:
        out, _step = await run_stage4(partial)
    mock_verify.assert_not_called()
    assert out["response_distributions"]["congruent"]["citations"][0]["doi_verified"] is False


@pytest.mark.asyncio
async def test_stage4_missing_year_does_not_raise():
    """Citation without 'year' key is skipped, not KeyError."""
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {},
                "citations": [{"doi": "10.0000/x", "authors": "Jones", "title": "no year"}],
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {}))) as mock_verify:
        out, _step = await run_stage4(partial)
    mock_verify.assert_not_called()
    assert out["response_distributions"]["congruent"]["citations"][0]["doi_verified"] is False


@pytest.mark.asyncio
async def test_stage4_doi_verified_count_in_step():
    """Step inference reports verified count and skipped count."""
    partial = {
        "response_distributions": {
            "c1": {
                "value": {},
                "citations": [
                    {"doi": "10.0000/good", "authors": "A", "year": 2020, "title": ""},
                    {"title": "missing everything"},  # malformed
                ],
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {}))):
        out, step = await run_stage4(partial)
    assert "2" in step.inference  # n_total
    assert "1" in step.inference  # n_verified or n_skipped


@pytest.mark.asyncio
async def test_stage4_marks_verified_on_success():
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {"mu": 580},
                "citations": [{"doi": "10.0000/x", "authors": "Smith, J.", "year": 2020,
                               "title": "x", "table_or_figure": "T1", "page": 1,
                               "quote": "...", "confidence": "high"}],
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {"title": "x"}))):
        out, step = await run_stage4(partial)
    cit = out["response_distributions"]["congruent"]["citations"][0]
    assert cit["doi_verified"] is True
    assert "doi_verified_at" in cit
    from experiment_bot.taskcard.types import ReasoningStep
    assert isinstance(step, ReasoningStep)
    assert step.step == "stage4_doi_verify"


@pytest.mark.asyncio
async def test_stage4_marks_unverified_on_failure():
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {"mu": 580},
                "citations": [{"doi": "10.0000/y", "authors": "Doe", "year": 2000,
                               "title": "y", "table_or_figure": "T2", "page": 2,
                               "quote": "...", "confidence": "low"}]
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(False, {}))):
        out, _step = await run_stage4(partial)
    cit = out["response_distributions"]["congruent"]["citations"][0]
    assert cit["doi_verified"] is False


@pytest.mark.asyncio
async def test_stage4_handles_no_citations_gracefully():
    partial = {"response_distributions": {"congruent": {"value": {"mu": 580}, "citations": []}}}
    out, _step = await run_stage4(partial)
    assert out["response_distributions"]["congruent"]["citations"] == []


@pytest.mark.asyncio
async def test_stage4_iterates_temporal_effects_and_jitter():
    partial = {
        "response_distributions": {},
        "temporal_effects": {
            "post_error_slowing": {
                "value": {"slowing_ms_min": 30},
                "citations": [{"doi": "10.0000/te", "authors": "Rabbitt", "year": 1966,
                               "title": "x", "table_or_figure": "T1", "page": 1,
                               "quote": "...", "confidence": "high"}],
            }
        },
        "between_subject_jitter": {
            "citations": [{"doi": "10.0000/bsj", "authors": "Jones", "year": 2010,
                           "title": "x", "table_or_figure": "T1", "page": 1,
                           "quote": "...", "confidence": "high"}]
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {}))):
        out, _step = await run_stage4(partial)
    assert out["temporal_effects"]["post_error_slowing"]["citations"][0]["doi_verified"] is True
    assert out["between_subject_jitter"]["citations"][0]["doi_verified"] is True

import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage3_citations import run_stage3, _enumerate_parameters
from experiment_bot.llm.protocol import LLMResponse


STAGE3_RESPONSE = """
{
  "response_distributions/congruent/mu": {
    "citations": [{"doi": "10.0000/test", "authors": "Smith, J.", "year": 2020,
                   "title": "x", "table_or_figure": "T1", "page": 1,
                   "quote": "mu=580 ms", "confidence": "high"}],
    "literature_range": {"mu": [560, 620]},
    "between_subject_sd": {"mu": 40}
  },
  "response_distributions/congruent/sigma": {
    "citations": [{"doi": "10.0000/test", "authors": "Smith, J.", "year": 2020,
                   "title": "x", "table_or_figure": "T1", "page": 1,
                   "quote": "sigma=80 ms", "confidence": "high"}],
    "literature_range": {"sigma": [60, 100]},
    "between_subject_sd": {"sigma": 15}
  }
}
"""


MALFORMED_PATHS_RESPONSE = """
{
  "between_subject_jitter": {
    "citations": [{"doi": "10.0000/bsj", "authors": "Lee, K.", "year": 2019,
                   "title": "y", "table_or_figure": "T2", "page": 3,
                   "quote": "jitter", "confidence": "medium"}]
  },
  "response_distributions/congruent/mu": {
    "citations": [{"doi": "10.0000/ok", "authors": "Smith, J.", "year": 2020,
                   "title": "x", "table_or_figure": "T1", "page": 1,
                   "quote": "mu=580 ms", "confidence": "high"}],
    "literature_range": {"mu": [560, 620]}
  },
  "response_distributions/nonexistent_condition/mu": {
    "citations": [{"doi": "10.0000/bad", "authors": "X", "year": 2000,
                   "title": "z", "table_or_figure": "T9", "page": 9,
                   "quote": "ignore me", "confidence": "low"}]
  },
  "garbage_section_no_slash": {
    "citations": [{"doi": "10.0000/junk", "authors": "Y", "year": 2001,
                   "title": "w", "table_or_figure": "T8", "page": 8,
                   "quote": "also ignore", "confidence": "low"}]
  }
}
"""


@pytest.mark.asyncio
async def test_stage3_skips_malformed_or_unmatched_citation_paths():
    """REGRESSION (held-out): a 1-part path (between_subject_jitter), a path to a
    nonexistent key, and an unknown section must be handled — between_subject_jitter
    attaches, the valid response_distributions path attaches, and the bad ones are
    skipped — instead of crashing on `section, key, _param = path.split('/', 2)`."""
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=MALFORMED_PATHS_RESPONSE))
    partial = {
        "response_distributions": {
            "congruent": {"distribution": "ex_gaussian",
                          "value": {"mu": 580, "sigma": 80, "tau": 100}, "rationale": "x"}
        },
        "temporal_effects": {},
        "between_subject_jitter": {},
    }
    out, step = await run_stage3(client=fake, partial=partial)  # must not raise
    # 1-part between_subject_jitter path attached
    assert out["between_subject_jitter"].get("citations"), "between_subject_jitter citation attached"
    # valid response_distributions path attached
    assert any(c["quote"] == "mu=580 ms" for c in out["response_distributions"]["congruent"]["citations"])
    # the nonexistent-key + no-slash-garbage paths were skipped (no crash, not attached)
    assert "nonexistent_condition" not in out["response_distributions"]


@pytest.mark.asyncio
async def test_stage3_attaches_citations_and_ranges():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE3_RESPONSE))
    partial = {
        "response_distributions": {
            "congruent": {
                "distribution": "ex_gaussian",
                "value": {"mu": 580, "sigma": 80, "tau": 100},
                "rationale": "stroop congruent",
            }
        },
        "temporal_effects": {},
        "between_subject_jitter": {},
    }
    out, step = await run_stage3(client=fake, partial=partial)
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"]
    # Citations now de-duplicate by DOI (one citation per real paper per
    # condition) — both mu/sigma paths cite the same DOI, so it appears once.
    dois = [c["doi"] for c in cong["citations"]]
    assert dois.count("10.0000/test") == 1, dois
    # Literature ranges still merge across params (mu and sigma both present)
    assert "mu" in cong["literature_range"]
    assert "sigma" in cong["literature_range"]
    assert cong["literature_range"]["mu"] == [560, 620]
    assert cong["literature_range"]["sigma"] == [60, 100]
    # between_subject_sd merged similarly
    assert cong["between_subject_sd"]["mu"] == 40
    assert cong["between_subject_sd"]["sigma"] == 15
    from experiment_bot.taskcard.types import ReasoningStep
    assert isinstance(step, ReasoningStep)
    assert step.step == "stage3_citations"


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

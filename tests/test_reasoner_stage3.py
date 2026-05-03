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
    out = await run_stage3(client=fake, partial=partial)
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"]
    # Citations from BOTH mu and sigma paths get merged
    assert any(c["quote"] == "mu=580 ms" for c in cong["citations"])
    assert any(c["quote"] == "sigma=80 ms" for c in cong["citations"])
    # Literature ranges merged across params
    assert "mu" in cong["literature_range"]
    assert "sigma" in cong["literature_range"]
    assert cong["literature_range"]["mu"] == [560, 620]
    assert cong["literature_range"]["sigma"] == [60, 100]
    # between_subject_sd merged similarly
    assert cong["between_subject_sd"]["mu"] == 40
    assert cong["between_subject_sd"]["sigma"] == 15


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

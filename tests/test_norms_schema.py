import pytest
from experiment_bot.reasoner.norms_extractor import validate_norms_dict, NormsSchemaError


def test_validate_norms_dict_passes_on_minimal_valid():
    payload = {
        "paradigm_class": "conflict",
        "produced_by": {
            "model": "claude-opus-4-7",
            "extraction_prompt_sha256": "x",
            "timestamp": "2026-05-04T00:00:00Z",
        },
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580],
                "sigma_range": [40, 90],
                "tau_range": [50, 130],
                "citations": [
                    {"doi": "10.0/x", "authors": "Whelan", "year": 2008,
                     "title": "x", "table_or_figure": "T1", "page": 1,
                     "quote": "...", "confidence": "high"}
                ]
            }
        }
    }
    validate_norms_dict(payload)  # no exception


def test_validate_norms_dict_fails_on_missing_paradigm_class():
    payload = {"produced_by": {}, "metrics": {}}
    with pytest.raises(NormsSchemaError, match="paradigm_class"):
        validate_norms_dict(payload)


def test_validate_norms_dict_fails_on_metric_with_no_range_and_no_explicit_null():
    """A metric must either have a non-null range or an explicit null with reason."""
    payload = {
        "paradigm_class": "x",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"citations": []}  # no range fields, no null+reason
        }
    }
    with pytest.raises(NormsSchemaError, match="range"):
        validate_norms_dict(payload)


def test_validate_norms_dict_accepts_explicit_no_canonical_range():
    payload = {
        "paradigm_class": "x",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "obscure_metric": {"range": None, "no_canonical_range_reason": "no meta-analysis"}
        }
    }
    validate_norms_dict(payload)  # no exception


def test_validate_norms_dict_fails_on_missing_produced_by_field():
    """produced_by must have model, extraction_prompt_sha256, timestamp."""
    payload = {
        "paradigm_class": "x",
        "produced_by": {"model": "x"},  # missing the other two
        "metrics": {}
    }
    with pytest.raises(NormsSchemaError):
        validate_norms_dict(payload)

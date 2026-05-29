from experiment_bot.taskcard.types import Citation


def test_citation_round_trip():
    data = {
        "doi": "10.1016/j.cognition.2008.07.011",
        "authors": "Whelan, R.",
        "year": 2008,
        "title": "Effective analysis of reaction time data",
        "confidence": "high",
        "rationale": "Whelan reviews ex-Gaussian RT analysis relevant to go-trial mu.",
        "table_or_figure": "Table 2",
        "page": 481,
        "quote": "Healthy adults on go trials: mu=460 ms",
        "doi_verified": False,
        "doi_verified_at": None,
    }
    c = Citation.from_dict(data)
    assert c.to_dict() == data


def test_citation_honest_minimal_round_trips_and_defaults():
    """Honest-citation policy: a citation with only DOI/authors/year/title +
    rationale (no fabricated quote/page) is valid; legacy fields default empty."""
    minimal = {
        "doi": "10.1037/0033-295X.91.3.295",
        "authors": "Logan, G. D., Cowan, W. B.",
        "year": 1984,
        "title": "On the ability to inhibit thought and action: A theory of an act of control",
        "rationale": "Foundational race-model account bounding SSRT.",
        "confidence": "high",
    }
    c = Citation.from_dict(minimal)
    assert c.quote == "" and c.page is None and c.table_or_figure == ""
    assert c.rationale.startswith("Foundational")


from experiment_bot.taskcard.types import ParameterValue, ReasoningStep, ProducedBy


def test_parameter_value_round_trip():
    data = {
        "value": {"mu": 480, "sigma": 60, "tau": 80},
        "distribution": "ex_gaussian",
        "literature_range": {"mu": [430, 530], "sigma": [40, 80], "tau": [50, 110]},
        "between_subject_sd": {"mu": 50, "sigma": 10, "tau": 20},
        "citations": [],
        "rationale": "Whelan 2008 norms",
        "sensitivity": "high",
    }
    pv = ParameterValue.from_dict(data)
    rt = pv.to_dict()
    assert rt == data


def test_reasoning_step_round_trip():
    data = {
        "step": "task_identification",
        "input_hash": "abc",
        "inference": "this is a stop-signal task",
        "evidence_lines": ["main.js line 47"],
        "confidence": "high",
    }
    rs = ReasoningStep.from_dict(data)
    assert rs.to_dict() == data


def test_produced_by_round_trip():
    data = {
        "model": "claude-opus-4-7",
        "prompt_sha256": "deadbeef",
        "scraper_version": "1.2.0",
        "source_sha256": "feedface",
        "timestamp": "2026-04-23T12:00:00Z",
        "taskcard_sha256": "789xyz",
    }
    pb = ProducedBy.from_dict(data)
    assert pb.to_dict() == data


from experiment_bot.taskcard.types import TaskCard


def _minimal_taskcard_dict() -> dict:
    return {
        "schema_version": "2.0",
        "produced_by": {
            "model": "claude-opus-4-7",
            "prompt_sha256": "x",
            "scraper_version": "1.0.0",
            "source_sha256": "y",
            "timestamp": "2026-04-23T12:00:00Z",
            "taskcard_sha256": "",
        },
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "navigation": {"phases": []},
        "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {},
        "temporal_effects": {},
        "between_subject_jitter": {},
        "reasoning_chain": [],
        "pilot_validation": {"passed": True, "iterations": 0, "trials_completed": 0},
    }


def test_taskcard_round_trip_minimal():
    data = _minimal_taskcard_dict()
    tc = TaskCard.from_dict(data)
    out = tc.to_dict()
    assert out["schema_version"] == "2.0"
    assert out["produced_by"]["model"] == "claude-opus-4-7"


def test_task_metadata_has_paradigm_classes_field():
    from experiment_bot.core.config import TaskMetadata
    tm = TaskMetadata.from_dict({
        "name": "Stroop",
        "constructs": [],
        "reference_literature": [],
        "paradigm_classes": ["conflict"],
    })
    assert tm.paradigm_classes == ["conflict"]


def test_task_metadata_paradigm_classes_default_empty():
    from experiment_bot.core.config import TaskMetadata
    tm = TaskMetadata.from_dict({"name": "x", "constructs": [], "reference_literature": []})
    assert tm.paradigm_classes == []


# --- Task 1: RT distribution family wiring ---

def test_parameter_value_distribution_round_trip():
    """distribution field survives from_dict → to_dict."""
    data = {
        "value": {"mu": 0.5, "sigma": 0.4},
        "distribution": "lognormal",
        "citations": [],
        "rationale": "",
        "sensitivity": "unknown",
        "literature_range": None,
        "between_subject_sd": None,
    }
    pv = ParameterValue.from_dict(data)
    assert pv.distribution == "lognormal"
    assert pv.to_dict()["distribution"] == "lognormal"


def test_parameter_value_distribution_default_ex_gaussian():
    """A dict with no distribution key defaults to ex_gaussian (backward-compat)."""
    data = {
        "value": {"mu": 480, "sigma": 60, "tau": 80},
        "citations": [],
        "rationale": "",
        "sensitivity": "unknown",
        "literature_range": None,
        "between_subject_sd": None,
    }
    pv = ParameterValue.from_dict(data)
    assert pv.distribution == "ex_gaussian"


def test_parameter_value_round_trip_preserves_distribution():
    """Existing round-trip test still holds and distribution is included."""
    data = {
        "value": {"mu": 480, "sigma": 60, "tau": 80},
        "literature_range": {"mu": [430, 530], "sigma": [40, 80], "tau": [50, 110]},
        "between_subject_sd": {"mu": 50, "sigma": 10, "tau": 20},
        "citations": [],
        "rationale": "Whelan 2008 norms",
        "sensitivity": "high",
        "distribution": "ex_gaussian",
    }
    pv = ParameterValue.from_dict(data)
    rt = pv.to_dict()
    assert rt == data


def test_shifted_wald_taskcard_drives_sampler():
    """A TaskCard with shifted_wald distribution instantiates ShiftedWaldSampler
    through _taskcard_to_config → ResponseSampler without KeyError."""
    import copy
    from experiment_bot.core.executor import _taskcard_to_config
    from experiment_bot.core.distributions import ResponseSampler, ShiftedWaldSampler

    tc_dict = _minimal_taskcard_dict()
    tc_dict["response_distributions"] = {
        "go": {
            "value": {"drift_rate": 1.2, "boundary": 0.8, "shift_ms": 150.0},
            "distribution": "shifted_wald",
            "citations": [],
            "rationale": "",
            "sensitivity": "unknown",
            "literature_range": None,
            "between_subject_sd": None,
        }
    }
    tc = TaskCard.from_dict(tc_dict)
    cfg = _taskcard_to_config(tc)
    # ResponseSampler must instantiate without KeyError
    sampler = ResponseSampler(cfg.response_distributions, seed=42)
    # Verify the underlying sampler is ShiftedWaldSampler
    assert isinstance(sampler._samplers["go"], ShiftedWaldSampler)
    # And sampling produces a positive value
    rt = sampler.sample_rt("go")
    assert rt > 0

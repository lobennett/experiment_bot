from experiment_bot.taskcard.types import Citation


def test_citation_round_trip():
    data = {
        "doi": "10.1016/j.cognition.2008.07.011",
        "authors": "Whelan, R.",
        "year": 2008,
        "title": "Effective analysis of reaction time data",
        "table_or_figure": "Table 2",
        "page": 481,
        "quote": "Healthy adults on go trials: mu=460 ms",
        "confidence": "high",
        "doi_verified": False,
        "doi_verified_at": None,
    }
    c = Citation.from_dict(data)
    assert c.to_dict() == data


from experiment_bot.taskcard.types import ParameterValue, ReasoningStep, ProducedBy


def test_parameter_value_round_trip():
    data = {
        "value": {"mu": 480, "sigma": 60, "tau": 80},
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

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Literal


@dataclass
class Citation:
    """A reference for a behavioral parameter.

    Honest-citation policy (post citation-integrity finding, 2026-05): the
    Reasoner is asked for a REAL, verifiable DOI + authors/year/title and a
    `rationale` (its own prose reasoning for why this source is relevant) — NOT
    a fabricated verbatim `quote` or page/table reference, which an LLM cannot
    produce truthfully from weights and which were confirmed fabricated in the
    prior corpus. `quote`/`page`/`table_or_figure` are retained as optional
    legacy fields for backward-compat with already-committed cards; new
    citations should leave them empty and use `rationale`.
    """
    doi: str
    authors: str
    year: int
    title: str
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""
    table_or_figure: str = ""
    page: int | None = None
    quote: str = ""
    abstract_snippet: str = ""   # retrieved abstract text grounding this citation
    doi_verified: bool = False
    doi_verified_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Citation":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParameterValue:
    """A behavioral parameter with provenance and sensitivity metadata.

    The `sensitivity` field accepts either:
      - A single string: "high" / "medium" / "low" / "unknown" — applies to
        the parameter as a whole.
      - A dict keyed by sub-parameter name: e.g. {"mu": "high", "sigma": "medium"}
        — used when Stage 5 of the Reasoner tags individual sub-parameters
        (mu/sigma/tau) at different sensitivity levels.

    The `distribution` field names the RT sampler family the Reasoner chose
    for this condition. Defaults to "ex_gaussian" for backward compatibility
    with existing TaskCards that predate this field. The executor honors it
    via _taskcard_to_config → DistributionConfig; see core/distributions.py.
    """
    value: dict
    literature_range: dict | None = None
    between_subject_sd: dict | None = None
    citations: list[Citation] = field(default_factory=list)
    rationale: str = ""
    sensitivity: Literal["high", "medium", "low", "unknown"] | dict = "unknown"
    distribution: str = "ex_gaussian"
    value_source: Literal["model_prior", "literature_revised"] = "model_prior"
    original_value: dict | None = None
    revision_reason: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ParameterValue":
        cits = [Citation.from_dict(c) for c in d.get("citations", [])]
        return cls(
            value=d["value"],
            literature_range=d.get("literature_range"),
            between_subject_sd=d.get("between_subject_sd"),
            citations=cits,
            rationale=d.get("rationale", ""),
            sensitivity=d.get("sensitivity", "unknown"),
            distribution=d.get("distribution", "ex_gaussian"),
            value_source=d.get("value_source", "model_prior"),
            original_value=d.get("original_value"),
            revision_reason=d.get("revision_reason", ""),
        )

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "distribution": self.distribution,
            "literature_range": self.literature_range,
            "between_subject_sd": self.between_subject_sd,
            "citations": [c.to_dict() for c in self.citations],
            "rationale": self.rationale,
            "sensitivity": self.sensitivity,
            "value_source": self.value_source,
            "original_value": self.original_value,
            "revision_reason": self.revision_reason,
        }


@dataclass
class ReasoningStep:
    step: str
    input_hash: str = ""
    inference: str = ""
    evidence_lines: list[str] = field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"

    @classmethod
    def from_dict(cls, d: dict) -> "ReasoningStep":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProducedBy:
    model: str
    prompt_sha256: str
    scraper_version: str
    source_sha256: str
    timestamp: str
    taskcard_sha256: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ProducedBy":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


from experiment_bot.core.config import (
    TaskMetadata, StimulusConfig, NavigationConfig, RuntimeConfig,
    PerformanceConfig,
)


@dataclass
class TaskCard:
    schema_version: str
    produced_by: ProducedBy
    task: TaskMetadata
    stimuli: list[StimulusConfig]
    navigation: NavigationConfig
    runtime: RuntimeConfig
    task_specific: dict
    performance: PerformanceConfig
    response_distributions: dict[str, ParameterValue]
    temporal_effects: dict[str, ParameterValue]
    between_subject_jitter: dict
    reasoning_chain: list[ReasoningStep]
    pilot_validation: dict

    @classmethod
    def from_dict(cls, d: dict) -> "TaskCard":
        return cls(
            schema_version=d["schema_version"],
            produced_by=ProducedBy.from_dict(d["produced_by"]),
            task=TaskMetadata.from_dict(d["task"]),
            stimuli=[StimulusConfig.from_dict(s) for s in d.get("stimuli", [])],
            navigation=NavigationConfig.from_dict(d.get("navigation", {"phases": []})),
            runtime=RuntimeConfig.from_dict(d.get("runtime", {})),
            task_specific=d.get("task_specific", {}),
            performance=PerformanceConfig.from_dict(d["performance"]),
            response_distributions={
                k: ParameterValue.from_dict(v)
                for k, v in d.get("response_distributions", {}).items()
            },
            temporal_effects={
                k: ParameterValue.from_dict(v)
                for k, v in d.get("temporal_effects", {}).items()
            },
            between_subject_jitter=d.get("between_subject_jitter", {}),
            reasoning_chain=[ReasoningStep.from_dict(s) for s in d.get("reasoning_chain", [])],
            pilot_validation=d.get("pilot_validation", {}),
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "produced_by": self.produced_by.to_dict(),
            "task": self.task.to_dict(),
            "stimuli": [s.to_dict() for s in self.stimuli],
            "navigation": self.navigation.to_dict(),
            "runtime": self.runtime.to_dict(),
            "task_specific": self.task_specific,
            "performance": self.performance.to_dict(),
            "response_distributions": {k: v.to_dict() for k, v in self.response_distributions.items()},
            "temporal_effects": {k: v.to_dict() for k, v in self.temporal_effects.items()},
            "between_subject_jitter": self.between_subject_jitter,
            "reasoning_chain": [s.to_dict() for s in self.reasoning_chain],
            "pilot_validation": self.pilot_validation,
        }



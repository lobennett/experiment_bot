from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Literal


@dataclass
class Citation:
    doi: str
    authors: str
    year: int
    title: str
    table_or_figure: str
    page: int
    quote: str
    confidence: Literal["high", "medium", "low"]
    doi_verified: bool = False
    doi_verified_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Citation":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParameterValue:
    value: dict
    literature_range: dict | None = None
    between_subject_sd: dict | None = None
    citations: list[Citation] = field(default_factory=list)
    rationale: str = ""
    sensitivity: Literal["high", "medium", "low", "unknown"] | dict = "unknown"

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
        )

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "literature_range": self.literature_range,
            "between_subject_sd": self.between_subject_sd,
            "citations": [c.to_dict() for c in self.citations],
            "rationale": self.rationale,
            "sensitivity": self.sensitivity,
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
    PerformanceConfig, BetweenSubjectJitterConfig,
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
    between_subject_jitter: BetweenSubjectJitterConfig | dict
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
                k: ParameterValue.from_dict(v) if "value" in v else _wrap_legacy_dist(v)
                for k, v in d.get("response_distributions", {}).items()
            },
            temporal_effects={
                k: ParameterValue.from_dict(v) if "value" in v else _wrap_legacy_effect(v)
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
            "between_subject_jitter": (
                self.between_subject_jitter.to_dict()
                if hasattr(self.between_subject_jitter, "to_dict")
                else self.between_subject_jitter
            ),
            "reasoning_chain": [s.to_dict() for s in self.reasoning_chain],
            "pilot_validation": self.pilot_validation,
        }


def _wrap_legacy_dist(d: dict) -> ParameterValue:
    """Wrap a v1 DistributionConfig dict into a ParameterValue with empty provenance.

    v1 layout: {"distribution": "ex_gaussian", "params": {...}, "unit": "ms"}
    v2 layout: {"value": {...}, ...}
    """
    return ParameterValue(
        value=d.get("params", {}),
        literature_range=None,
        between_subject_sd=None,
        citations=[],
        rationale="",
        sensitivity="unknown",
    )


def _wrap_legacy_effect(d: dict) -> ParameterValue:
    """Wrap a v1 temporal-effect dict into a ParameterValue.

    v1 layout: {"enabled": bool, "<param>": <number>, "rationale": "..."}
    v2 layout: {"value": {"enabled": bool, "<param>": ...}, "rationale": "..."}
    """
    return ParameterValue(
        value={k: v for k, v in d.items() if k != "rationale"},
        literature_range=None,
        between_subject_sd=None,
        citations=[],
        rationale=d.get("rationale", ""),
        sensitivity="unknown",
    )

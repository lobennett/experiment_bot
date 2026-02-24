from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class TaskPhase(Enum):
    LOADING = "loading"
    INSTRUCTIONS = "instructions"
    PRACTICE = "practice"
    FEEDBACK = "feedback"
    TEST = "test"
    ATTENTION_CHECK = "attention_check"
    COMPLETE = "complete"


@dataclass
class SourceBundle:
    platform: str
    task_id: str
    source_files: dict[str, str]
    description_text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class DetectionConfig:
    method: str
    selector: str
    alt_method: str = ""
    pattern: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> DetectionConfig:
        return cls(
            method=d["method"],
            selector=d["selector"],
            alt_method=d.get("alt_method", ""),
            pattern=d.get("pattern", ""),
        )

    def to_dict(self) -> dict:
        return {"method": self.method, "selector": self.selector,
                "alt_method": self.alt_method, "pattern": self.pattern}


@dataclass
class ResponseConfig:
    key: str | None
    condition: str

    @classmethod
    def from_dict(cls, d: dict) -> ResponseConfig:
        return cls(key=d.get("key"), condition=d["condition"])

    def to_dict(self) -> dict:
        return {"key": self.key, "condition": self.condition}


@dataclass
class StimulusConfig:
    id: str
    description: str
    detection: DetectionConfig
    response: ResponseConfig

    @classmethod
    def from_dict(cls, d: dict) -> StimulusConfig:
        return cls(
            id=d["id"],
            description=d["description"],
            detection=DetectionConfig.from_dict(d["detection"]),
            response=ResponseConfig.from_dict(d["response"]),
        )

    def to_dict(self) -> dict:
        return {"id": self.id, "description": self.description,
                "detection": self.detection.to_dict(),
                "response": self.response.to_dict()}


@dataclass
class DistributionConfig:
    distribution: str
    params: dict
    unit: str = "ms"

    @classmethod
    def from_dict(cls, d: dict) -> DistributionConfig:
        return cls(distribution=d["distribution"], params=d["params"],
                   unit=d.get("unit", "ms"))

    def to_dict(self) -> dict:
        return {"distribution": self.distribution, "params": self.params,
                "unit": self.unit}


@dataclass
class PerformanceConfig:
    go_accuracy: float
    stop_accuracy: float
    omission_rate: float
    practice_accuracy: float

    @classmethod
    def from_dict(cls, d: dict) -> PerformanceConfig:
        return cls(
            go_accuracy=d["go_accuracy"],
            stop_accuracy=d["stop_accuracy"],
            omission_rate=d["omission_rate"],
            practice_accuracy=d["practice_accuracy"],
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NavigationPhase:
    phase: str = ""
    action: str = ""
    target: str = ""
    key: str = ""
    steps: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    pre_js: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> NavigationPhase:
        return cls(
            phase=d.get("phase", ""),
            action=d.get("action", ""),
            target=d.get("target", ""),
            key=d.get("key", ""),
            steps=d.get("steps", []),
            duration_ms=d.get("duration_ms", 0),
            pre_js=d.get("pre_js", ""),
        )

    def to_dict(self) -> dict:
        d = {"phase": self.phase, "action": self.action,
             "target": self.target, "key": self.key,
             "steps": self.steps, "duration_ms": self.duration_ms}
        if self.pre_js:
            d["pre_js"] = self.pre_js
        return d


@dataclass
class NavigationConfig:
    phases: list[NavigationPhase]

    @classmethod
    def from_dict(cls, d: dict) -> NavigationConfig:
        return cls(phases=[NavigationPhase.from_dict(p) for p in d.get("phases", [])])

    def to_dict(self) -> dict:
        return {"phases": [p.to_dict() for p in self.phases]}


@dataclass
class TaskMetadata:
    name: str
    platform: str
    constructs: list[str]
    reference_literature: list[str]

    @classmethod
    def from_dict(cls, d: dict) -> TaskMetadata:
        return cls(
            name=d["name"],
            platform=d["platform"],
            constructs=d.get("constructs", []),
            reference_literature=d.get("reference_literature", []),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskConfig:
    task: TaskMetadata
    stimuli: list[StimulusConfig]
    response_distributions: dict[str, DistributionConfig]
    performance: PerformanceConfig
    navigation: NavigationConfig
    task_specific: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> TaskConfig:
        return cls(
            task=TaskMetadata.from_dict(d["task"]),
            stimuli=[StimulusConfig.from_dict(s) for s in d.get("stimuli", [])],
            response_distributions={
                k: DistributionConfig.from_dict(v)
                for k, v in d.get("response_distributions", {}).items()
            },
            performance=PerformanceConfig.from_dict(d["performance"]),
            navigation=NavigationConfig.from_dict(d.get("navigation", {"phases": []})),
            task_specific=d.get("task_specific", {}),
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task.to_dict(),
            "stimuli": [s.to_dict() for s in self.stimuli],
            "response_distributions": {
                k: v.to_dict() for k, v in self.response_distributions.items()
            },
            "performance": self.performance.to_dict(),
            "navigation": self.navigation.to_dict(),
            "task_specific": self.task_specific,
        }

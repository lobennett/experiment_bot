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
class PhaseDetectionConfig:
    method: str = "js_eval"
    complete: str = ""
    test: str = "true"
    loading: str = ""
    instructions: str = ""
    practice: str = ""
    feedback: str = ""
    attention_check: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> PhaseDetectionConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class TimingConfig:
    poll_interval_ms: int = 20
    max_no_stimulus_polls: int = 500
    stuck_timeout_s: float = 10.0
    completion_wait_ms: int = 5000
    feedback_delay_ms: int = 2000
    omission_wait_ms: int = 2000
    stop_success_wait_ms: int = 1500
    rt_floor_ms: float = 150.0
    rt_cap_fraction: float = 0.90
    response_window_js: str = ""
    autocorrelation_phi: float = 0.25
    fatigue_drift_per_trial: float = 0.15
    viewport: dict = field(default_factory=lambda: {"width": 1280, "height": 800})

    @classmethod
    def from_dict(cls, d: dict) -> TimingConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AdvanceBehaviorConfig:
    pre_keypress_js: str = ""
    advance_keys: list[str] = field(default_factory=lambda: [" "])
    exit_pager_key: str = ""
    advance_interval_polls: int = 100
    feedback_selectors: list[str] = field(default_factory=lambda: ["button"])
    feedback_fallback_keys: list[str] = field(default_factory=lambda: ["Enter"])

    @classmethod
    def from_dict(cls, d: dict) -> AdvanceBehaviorConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParadigmConfig:
    type: str = "simple"
    stop_condition: str = "stop"
    stop_failure_rt_key: str = "stop_failure"
    stop_rt_cap_fraction: float = 0.85

    @classmethod
    def from_dict(cls, d: dict) -> ParadigmConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuntimeConfig:
    phase_detection: PhaseDetectionConfig = field(default_factory=PhaseDetectionConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    advance_behavior: AdvanceBehaviorConfig = field(default_factory=AdvanceBehaviorConfig)
    paradigm: ParadigmConfig = field(default_factory=ParadigmConfig)

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeConfig:
        return cls(
            phase_detection=PhaseDetectionConfig.from_dict(d.get("phase_detection", {})),
            timing=TimingConfig.from_dict(d.get("timing", {})),
            advance_behavior=AdvanceBehaviorConfig.from_dict(d.get("advance_behavior", {})),
            paradigm=ParadigmConfig.from_dict(d.get("paradigm", {})),
        )

    def to_dict(self) -> dict:
        return {
            "phase_detection": self.phase_detection.to_dict(),
            "timing": self.timing.to_dict(),
            "advance_behavior": self.advance_behavior.to_dict(),
            "paradigm": self.paradigm.to_dict(),
        }


@dataclass
class TaskConfig:
    task: TaskMetadata
    stimuli: list[StimulusConfig]
    response_distributions: dict[str, DistributionConfig]
    performance: PerformanceConfig
    navigation: NavigationConfig
    task_specific: dict = field(default_factory=dict)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

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
            runtime=RuntimeConfig.from_dict(d.get("runtime", {})),
        )

    def to_dict(self) -> dict:
        result = {
            "task": self.task.to_dict(),
            "stimuli": [s.to_dict() for s in self.stimuli],
            "response_distributions": {
                k: v.to_dict() for k, v in self.response_distributions.items()
            },
            "performance": self.performance.to_dict(),
            "navigation": self.navigation.to_dict(),
            "task_specific": self.task_specific,
        }
        runtime_dict = self.runtime.to_dict()
        if any(v for v in runtime_dict.values()):
            result["runtime"] = runtime_dict
        return result

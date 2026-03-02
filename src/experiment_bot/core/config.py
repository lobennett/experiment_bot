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
    url: str                          # The experiment URL
    source_files: dict[str, str]      # filename -> content
    description_text: str             # Human-readable description or page HTML
    metadata: dict = field(default_factory=dict)
    hint: str = ""                    # User-provided hint about the task


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
    accuracy: dict[str, float]           # condition → accuracy (0-1)
    omission_rate: dict[str, float]      # condition → omission rate (0-1)
    practice_accuracy: float = 0.85

    @classmethod
    def from_dict(cls, d: dict) -> PerformanceConfig:
        return cls(
            accuracy=d["accuracy"],
            omission_rate=d.get("omission_rate", {}),
            practice_accuracy=d.get("practice_accuracy", 0.85),
        )

    def get_accuracy(self, condition: str) -> float:
        if condition in self.accuracy:
            return self.accuracy[condition]
        if "default" in self.accuracy:
            return self.accuracy["default"]
        if self.accuracy:
            return next(iter(self.accuracy.values()))
        return 0.90

    def get_omission_rate(self, condition: str) -> float:
        if condition in self.omission_rate:
            return self.omission_rate[condition]
        if "default" in self.omission_rate:
            return self.omission_rate["default"]
        if self.omission_rate:
            return next(iter(self.omission_rate.values()))
        return 0.02

    def to_dict(self) -> dict:
        result = {"accuracy": self.accuracy, "practice_accuracy": self.practice_accuracy}
        if self.omission_rate:
            result["omission_rate"] = self.omission_rate
        return result


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
    constructs: list[str]
    reference_literature: list[str]
    platform: str = ""  # Optional — Claude may infer platform or leave blank

    @classmethod
    def from_dict(cls, d: dict) -> TaskMetadata:
        return cls(
            name=d["name"],
            constructs=d.get("constructs", []),
            reference_literature=d.get("reference_literature", []),
            platform=d.get("platform", ""),
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
    rt_floor_ms: float = 150.0
    rt_cap_fraction: float = 0.90
    response_window_js: str = ""
    trial_context_js: str = ""
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
class TrialInterruptConfig:
    detection_condition: str = ""
    failure_rt_key: str = ""
    failure_rt_cap_fraction: float = 0.85
    inhibit_wait_ms: int = 1500

    @classmethod
    def from_dict(cls, d: dict) -> TrialInterruptConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataCaptureConfig:
    method: str = ""            # "js_expression", "button_click", ""
    expression: str = ""        # JS expression returning data string (for js_expression)
    button_selector: str = ""   # CSS selector for data button (for button_click)
    result_selector: str = ""   # CSS selector for result element (for button_click)
    format: str = "csv"         # "csv", "tsv", "json"
    wait_ms: int = 1000         # Wait after button click before reading result

    @classmethod
    def from_dict(cls, d: dict) -> DataCaptureConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class AttentionCheckConfig:
    detection_selector: str = ""  # CSS/JS selector to detect attention check presence
    text_selector: str = ""       # CSS selector to read attention check text
    response_js: str = ""         # Optional JS to determine response (overrides regex parsing)

    @classmethod
    def from_dict(cls, d: dict) -> AttentionCheckConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class RuntimeConfig:
    phase_detection: PhaseDetectionConfig = field(default_factory=PhaseDetectionConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    advance_behavior: AdvanceBehaviorConfig = field(default_factory=AdvanceBehaviorConfig)
    trial_interrupt: TrialInterruptConfig = field(default_factory=TrialInterruptConfig)
    data_capture: DataCaptureConfig = field(default_factory=DataCaptureConfig)
    attention_check: AttentionCheckConfig = field(default_factory=AttentionCheckConfig)

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeConfig:
        # Migrate legacy "paradigm" key → "trial_interrupt"
        interrupt_raw = dict(d.get("trial_interrupt", {}))
        if not interrupt_raw and "paradigm" in d:
            p = d["paradigm"]
            interrupt_raw = {
                "detection_condition": p.get("stop_condition", ""),
                "failure_rt_key": p.get("stop_failure_rt_key", ""),
                "failure_rt_cap_fraction": p.get("stop_rt_cap_fraction", 0.85),
            }
            if "inhibit_wait_ms" in p:
                interrupt_raw["inhibit_wait_ms"] = p["inhibit_wait_ms"]
        timing_raw = dict(d.get("timing", {}))
        if "stop_success_wait_ms" in timing_raw and "inhibit_wait_ms" not in interrupt_raw:
            interrupt_raw["inhibit_wait_ms"] = timing_raw.pop("stop_success_wait_ms")
        if "cue_selector_js" in timing_raw and "trial_context_js" not in timing_raw:
            timing_raw["trial_context_js"] = timing_raw.pop("cue_selector_js")

        return cls(
            phase_detection=PhaseDetectionConfig.from_dict(d.get("phase_detection", {})),
            timing=TimingConfig.from_dict(timing_raw),
            advance_behavior=AdvanceBehaviorConfig.from_dict(d.get("advance_behavior", {})),
            trial_interrupt=TrialInterruptConfig.from_dict(interrupt_raw),
            data_capture=DataCaptureConfig.from_dict(d.get("data_capture", {})),
            attention_check=AttentionCheckConfig.from_dict(d.get("attention_check", {})),
        )

    def to_dict(self) -> dict:
        return {
            "phase_detection": self.phase_detection.to_dict(),
            "timing": self.timing.to_dict(),
            "advance_behavior": self.advance_behavior.to_dict(),
            "trial_interrupt": self.trial_interrupt.to_dict(),
            "data_capture": self.data_capture.to_dict(),
            "attention_check": self.attention_check.to_dict(),
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

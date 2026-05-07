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
    response_key_js: str = ""  # JS expression returning the correct key at runtime

    @classmethod
    def from_dict(cls, d: dict) -> ResponseConfig:
        return cls(
            key=d.get("key"),
            condition=d["condition"],
            response_key_js=d.get("response_key_js", ""),
        )

    def to_dict(self) -> dict:
        d = {"key": self.key, "condition": self.condition}
        if self.response_key_js:
            d["response_key_js"] = self.response_key_js
        return d


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
class AutocorrelationConfig:
    enabled: bool = False
    phi: float = 0.0
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> AutocorrelationConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FatigueDriftConfig:
    enabled: bool = False
    drift_per_trial_ms: float = 0.0
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> FatigueDriftConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PostErrorSlowingConfig:
    enabled: bool = False
    slowing_ms_min: float = 0.0
    slowing_ms_max: float = 0.0
    # decay_weights: optional weight per recent trial (most recent first).
    # Empty list (default) = single-trial PES (the historical default).
    # [1.0] = explicit 1-trial decay (identical to default).
    # [1.0, 0.6, 0.3] = 3-trial decay; the contribution from a trial N back
    #   is `weight_N * uniform(slowing_ms_min, slowing_ms_max) if recent_errors[N] else 0`.
    # This lets the Reasoner declare a paradigm-specific decay profile from
    # literature (e.g. Notebaert 2009's multi-trial decay) instead of being
    # locked to 1-trial behavior. Sum of weights does not need to equal 1.
    decay_weights: list = field(default_factory=list)
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> PostErrorSlowingConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConditionRepetitionConfig:
    enabled: bool = False
    facilitation_ms: float = 0.0
    cost_ms: float = 0.0
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> ConditionRepetitionConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PinkNoiseConfig:
    enabled: bool = False
    sd_ms: float = 0.0
    hurst: float = 0.0
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> PinkNoiseConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PostInterruptSlowingConfig:
    enabled: bool = False
    slowing_ms_min: float = 0.0
    slowing_ms_max: float = 0.0
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> PostInterruptSlowingConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


class TemporalEffectsConfig:
    """Open registry of effect configurations.

    Each registered effect (in `effects.registry.EFFECT_REGISTRY`) has a
    config entry here, populated either as a typed dataclass instance
    (when the registry declares `config_class`) or as a `SimpleNamespace`
    built from the raw dict (when no config_class is declared). Adding a
    new effect — registering its handler with `register_effect()` — does
    NOT require editing this class. The sampler iterates the registry
    and looks up configs by name; missing entries yield a default
    "disabled" SimpleNamespace so handlers short-circuit cleanly.

    The class accepts named-effect kwargs in `__init__` for convenience
    when constructing in tests/code:
        TemporalEffectsConfig(autocorrelation=AutocorrelationConfig(enabled=True, phi=0.3))
    """

    def __init__(self, **kwargs):
        # Storage keyed by registry effect name. Accepts either typed
        # dataclass instances or SimpleNamespace objects.
        self._effects: dict[str, object] = dict(kwargs)

    @classmethod
    def from_dict(cls, d: dict) -> "TemporalEffectsConfig":
        from types import SimpleNamespace
        from experiment_bot.effects.registry import EFFECT_REGISTRY

        out = cls()
        # For each registered effect, instantiate via its config_class if
        # available, otherwise wrap the dict as a SimpleNamespace so
        # attribute access works in the handler.
        d = d or {}
        for name, et in EFFECT_REGISTRY.items():
            sub = d.get(name, {})
            cfg_class = getattr(et, "config_class", None)
            if cfg_class is not None and isinstance(sub, dict):
                out._effects[name] = cfg_class.from_dict(sub)
            elif isinstance(sub, dict):
                out._effects[name] = SimpleNamespace(**sub)
            else:
                out._effects[name] = sub
        # Pass through any non-registry effects the caller emitted
        for name in d:
            if name not in out._effects:
                out._effects[name] = (SimpleNamespace(**d[name])
                                       if isinstance(d[name], dict) else d[name])
        return out

    def get(self, name: str):
        """Return the config for `name`, or None if not present."""
        return self._effects.get(name)

    def __getattr__(self, name: str):
        # Backward-compat: `te.autocorrelation` returns the stored config;
        # if no config is stored, returns a disabled-by-default
        # SimpleNamespace so handlers short-circuit cleanly.
        # Dunder names (__deepcopy__, __reduce__, etc.) MUST raise so
        # Python's protocol probes (copy.deepcopy, pickle) fall back
        # cleanly — returning a SimpleNamespace fakes a callable and
        # crashes deepcopy.
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._effects:
            return self._effects[name]
        from types import SimpleNamespace
        return SimpleNamespace(enabled=False)

    def to_dict(self) -> dict:
        from dataclasses import is_dataclass, asdict as _asdict
        out: dict = {}
        for k, v in self._effects.items():
            if hasattr(v, "to_dict"):
                out[k] = v.to_dict()
            elif is_dataclass(v):
                out[k] = _asdict(v)
            elif hasattr(v, "__dict__"):
                out[k] = dict(vars(v))
            else:
                out[k] = v
        return out


@dataclass
class BetweenSubjectJitterConfig:
    rt_mean_sd_ms: float = 0.0
    rt_condition_sd_ms: float = 0.0
    sigma_tau_range: list = field(default_factory=lambda: [1.0, 1.0])
    accuracy_sd: float = 0.0
    omission_sd: float = 0.0
    # Plausible bounds for jittered accuracy / omission. Defaults reflect
    # typical conflict/interrupt-task ranges; the Reasoner should override
    # these per paradigm class — perceptual-threshold tasks need a lower
    # accuracy floor, slow-paced tasks may need a higher omission ceiling.
    accuracy_clip_range: list = field(default_factory=lambda: [0.60, 0.995])
    omission_clip_range: list = field(default_factory=lambda: [0.0, 0.04])
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> BetweenSubjectJitterConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PilotConfig:
    min_trials: int = 20
    target_conditions: list[str] = field(default_factory=list)
    # Pilot stops at this many FEEDBACK phase firings. Default 3 covers
    # paradigms with a single-trial practice block followed by feedback,
    # then the start of test (where the pilot will reach min_trials and
    # exit naturally). Set to 1 for tasks that are a single block.
    max_blocks: int = 3
    stimulus_container_selector: str = ""
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> PilotConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PerformanceConfig:
    accuracy: dict[str, float]           # condition → accuracy (0-1)
    omission_rate: dict[str, float]      # condition → omission rate (0-1)
    practice_accuracy: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> PerformanceConfig:
        return cls(
            accuracy=d["accuracy"],
            omission_rate=d.get("omission_rate", {}),
            practice_accuracy=d.get("practice_accuracy"),
        )

    def get_accuracy(self, condition: str) -> float:
        if condition in self.accuracy:
            return self.accuracy[condition]
        if "default" in self.accuracy:
            return self.accuracy["default"]
        if self.accuracy:
            return next(iter(self.accuracy.values()))
        raise ValueError("No accuracy values configured")

    def get_omission_rate(self, condition: str) -> float:
        if condition in self.omission_rate:
            return self.omission_rate[condition]
        if "default" in self.omission_rate:
            return self.omission_rate["default"]
        if self.omission_rate:
            return next(iter(self.omission_rate.values()))
        raise ValueError("No omission rate values configured")

    def to_dict(self) -> dict:
        result = {"accuracy": self.accuracy}
        if self.practice_accuracy is not None:
            result["practice_accuracy"] = self.practice_accuracy
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
    paradigm_classes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> TaskMetadata:
        return cls(
            name=d["name"],
            constructs=d.get("constructs", []),
            reference_literature=d.get("reference_literature", []),
            platform=d.get("platform", ""),
            paradigm_classes=d.get("paradigm_classes", []),
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
    viewport: dict = field(default_factory=lambda: {"width": 1280, "height": 800})
    # Behavioral timing knobs (previously hardcoded in executor.py)
    navigation_delay_ms: int = 1000      # Pause before pressing key on navigation stimuli
    attention_check_delay_ms: int = 1500  # Pause before handling an attention check
    completion_settle_ms: int = 2000     # Brief settle time in _wait_for_completion
    trial_end_timeout_s: float = 5.0     # Max wait for response window to close after a trial

    @classmethod
    def from_dict(cls, d: dict) -> TimingConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AdvanceBehaviorConfig:
    pre_keypress_js: str = ""
    advance_keys: list[str] = field(default_factory=list)
    exit_pager_key: str = ""
    advance_interval_polls: int = 100
    feedback_selectors: list[str] = field(default_factory=lambda: ["button"])
    feedback_fallback_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> AdvanceBehaviorConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrialInterruptConfig:
    detection_condition: str = ""
    failure_rt_key: str = ""
    failure_rt_cap_fraction: float = 0.0
    inhibit_wait_ms: int = 0

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
    # Condition labels (matching response.condition) that trigger attention-check handling.
    # Defaults to the legacy set so existing configs without this field still work.
    stimulus_conditions: list = field(
        default_factory=lambda: ["attention_check", "attention_check_response"]
    )

    @classmethod
    def from_dict(cls, d: dict) -> AttentionCheckConfig:
        obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        return obj

    def to_dict(self) -> dict:
        result = {k: v for k, v in asdict(self).items() if v}
        # Always include stimulus_conditions (even if default) so round-trips are stable
        result["stimulus_conditions"] = self.stimulus_conditions
        return result


@dataclass
class RuntimeConfig:
    phase_detection: PhaseDetectionConfig = field(default_factory=PhaseDetectionConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    advance_behavior: AdvanceBehaviorConfig = field(default_factory=AdvanceBehaviorConfig)
    trial_interrupt: TrialInterruptConfig = field(default_factory=TrialInterruptConfig)
    data_capture: DataCaptureConfig = field(default_factory=DataCaptureConfig)
    attention_check: AttentionCheckConfig = field(default_factory=AttentionCheckConfig)
    # Condition label used to detect navigation stimuli in the trial loop.
    # Defaults to "" (empty) — when empty, the executor falls back to the legacy
    # hardcoded value "navigation" so existing configs still work.
    navigation_stimulus_condition: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeConfig:
        return cls(
            phase_detection=PhaseDetectionConfig.from_dict(d.get("phase_detection", {})),
            timing=TimingConfig.from_dict(d.get("timing", {})),
            advance_behavior=AdvanceBehaviorConfig.from_dict(d.get("advance_behavior", {})),
            trial_interrupt=TrialInterruptConfig.from_dict(d.get("trial_interrupt", {})),
            data_capture=DataCaptureConfig.from_dict(d.get("data_capture", {})),
            attention_check=AttentionCheckConfig.from_dict(d.get("attention_check", {})),
            navigation_stimulus_condition=d.get("navigation_stimulus_condition", ""),
        )

    def to_dict(self) -> dict:
        return {
            "phase_detection": self.phase_detection.to_dict(),
            "timing": self.timing.to_dict(),
            "advance_behavior": self.advance_behavior.to_dict(),
            "trial_interrupt": self.trial_interrupt.to_dict(),
            "data_capture": self.data_capture.to_dict(),
            "attention_check": self.attention_check.to_dict(),
            # Always emit for round-trip stability, matching AttentionCheckConfig policy.
            "navigation_stimulus_condition": self.navigation_stimulus_condition,
        }


@dataclass
class TaskConfig:
    task: TaskMetadata
    stimuli: list[StimulusConfig]
    response_distributions: dict[str, DistributionConfig]
    performance: PerformanceConfig
    navigation: NavigationConfig
    task_specific: dict = field(default_factory=dict)
    temporal_effects: TemporalEffectsConfig = field(default_factory=TemporalEffectsConfig)
    between_subject_jitter: BetweenSubjectJitterConfig = field(default_factory=BetweenSubjectJitterConfig)
    pilot: PilotConfig = field(default_factory=PilotConfig)
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
            temporal_effects=TemporalEffectsConfig.from_dict(d.get("temporal_effects", {})),
            between_subject_jitter=BetweenSubjectJitterConfig.from_dict(d.get("between_subject_jitter", {})),
            pilot=PilotConfig.from_dict(d.get("pilot", {})),
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
            "temporal_effects": self.temporal_effects.to_dict(),
            "between_subject_jitter": self.between_subject_jitter.to_dict(),
            "pilot": self.pilot.to_dict(),
        }
        runtime_dict = self.runtime.to_dict()
        if any(v for v in runtime_dict.values()):
            result["runtime"] = runtime_dict
        return result

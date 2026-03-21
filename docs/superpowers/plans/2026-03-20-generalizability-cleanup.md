# Generalizability Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the experiment bot so all behavioral parameters are Claude-determined at config time, with no hardcoded domain knowledge in Python.

**Architecture:** Add `TemporalEffectsConfig` and `BetweenSubjectJitterConfig` as top-level fields on `TaskConfig`. `ResponseSampler` and `TaskExecutor` read from these configs instead of using hardcoded constants. Prompt split into technical vs. behavioral sections. Scripts consolidated into a single analysis notebook.

**Tech Stack:** Python 3.12, numpy, playwright, pytest, pytest-asyncio, pandas, uv

**Spec:** `docs/superpowers/specs/2026-03-20-generalizability-cleanup-design.md`

---

## Chunk 1: Config Layer — New Dataclasses and Schema

### Task 1: Add temporal effect dataclasses to config.py

**Files:**
- Modify: `src/experiment_bot/core/config.py`
- Test: `tests/test_config_temporal.py`

- [ ] **Step 1: Write failing tests for new dataclasses**

Create `tests/test_config_temporal.py`:

```python
from experiment_bot.core.config import (
    AutocorrelationConfig, FatigueDriftConfig, PostErrorSlowingConfig,
    ConditionRepetitionConfig, PinkNoiseConfig, PostInterruptSlowingConfig,
    TemporalEffectsConfig, BetweenSubjectJitterConfig,
)


def test_temporal_effects_all_disabled_by_default():
    te = TemporalEffectsConfig.from_dict({})
    assert te.autocorrelation.enabled is False
    assert te.fatigue_drift.enabled is False
    assert te.post_error_slowing.enabled is False
    assert te.condition_repetition.enabled is False
    assert te.pink_noise.enabled is False
    assert te.post_interrupt_slowing.enabled is False


def test_temporal_effects_from_dict_partial():
    te = TemporalEffectsConfig.from_dict({
        "autocorrelation": {"enabled": True, "phi": 0.3, "rationale": "test"},
    })
    assert te.autocorrelation.enabled is True
    assert te.autocorrelation.phi == 0.3
    assert te.fatigue_drift.enabled is False


def test_temporal_effects_round_trip():
    original = {
        "autocorrelation": {"enabled": True, "phi": 0.22, "rationale": "Gilden 2001"},
        "pink_noise": {"enabled": True, "sd_ms": 12, "hurst": 0.75, "rationale": "1/f"},
    }
    te = TemporalEffectsConfig.from_dict(original)
    d = te.to_dict()
    assert d["autocorrelation"]["phi"] == 0.22
    assert d["pink_noise"]["hurst"] == 0.75


def test_between_subject_jitter_from_dict():
    bsj = BetweenSubjectJitterConfig.from_dict({
        "rt_mean_sd_ms": 40, "rt_condition_sd_ms": 15,
        "sigma_tau_range": [0.85, 1.15],
        "accuracy_sd": 0.015, "omission_sd": 0.005,
        "rationale": "test",
    })
    assert bsj.rt_mean_sd_ms == 40
    assert bsj.sigma_tau_range == [0.85, 1.15]


def test_between_subject_jitter_defaults_to_zero():
    bsj = BetweenSubjectJitterConfig.from_dict({})
    assert bsj.rt_mean_sd_ms == 0.0
    assert bsj.rt_condition_sd_ms == 0.0
    assert bsj.sigma_tau_range == [1.0, 1.0]
    assert bsj.accuracy_sd == 0.0
    assert bsj.omission_sd == 0.0


def test_pink_noise_enabled_zero_hurst_raises():
    """Pink noise enabled with hurst=0.0 should raise ValueError."""
    from experiment_bot.core.distributions import ResponseSampler
    from experiment_bot.core.config import DistributionConfig
    effects = TemporalEffectsConfig.from_dict({
        "pink_noise": {"enabled": True, "sd_ms": 12, "hurst": 0.0, "rationale": "test"},
    })
    dists = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}
    try:
        ResponseSampler(dists, effects, floor_ms=150.0, seed=42)
        assert False, "Should raise ValueError for hurst=0"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run python -m pytest tests/test_config_temporal.py -v`
Expected: FAIL — classes don't exist yet

- [ ] **Step 3: Implement the dataclasses**

Add to `src/experiment_bot/core/config.py`, before `PerformanceConfig`:

```python
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


@dataclass
class TemporalEffectsConfig:
    autocorrelation: AutocorrelationConfig = field(default_factory=AutocorrelationConfig)
    fatigue_drift: FatigueDriftConfig = field(default_factory=FatigueDriftConfig)
    post_error_slowing: PostErrorSlowingConfig = field(default_factory=PostErrorSlowingConfig)
    condition_repetition: ConditionRepetitionConfig = field(default_factory=ConditionRepetitionConfig)
    pink_noise: PinkNoiseConfig = field(default_factory=PinkNoiseConfig)
    post_interrupt_slowing: PostInterruptSlowingConfig = field(default_factory=PostInterruptSlowingConfig)

    @classmethod
    def from_dict(cls, d: dict) -> TemporalEffectsConfig:
        return cls(
            autocorrelation=AutocorrelationConfig.from_dict(d.get("autocorrelation", {})),
            fatigue_drift=FatigueDriftConfig.from_dict(d.get("fatigue_drift", {})),
            post_error_slowing=PostErrorSlowingConfig.from_dict(d.get("post_error_slowing", {})),
            condition_repetition=ConditionRepetitionConfig.from_dict(d.get("condition_repetition", {})),
            pink_noise=PinkNoiseConfig.from_dict(d.get("pink_noise", {})),
            post_interrupt_slowing=PostInterruptSlowingConfig.from_dict(d.get("post_interrupt_slowing", {})),
        )

    def to_dict(self) -> dict:
        return {
            "autocorrelation": self.autocorrelation.to_dict(),
            "fatigue_drift": self.fatigue_drift.to_dict(),
            "post_error_slowing": self.post_error_slowing.to_dict(),
            "condition_repetition": self.condition_repetition.to_dict(),
            "pink_noise": self.pink_noise.to_dict(),
            "post_interrupt_slowing": self.post_interrupt_slowing.to_dict(),
        }


@dataclass
class BetweenSubjectJitterConfig:
    rt_mean_sd_ms: float = 0.0
    rt_condition_sd_ms: float = 0.0
    sigma_tau_range: list[float] = field(default_factory=lambda: [1.0, 1.0])
    accuracy_sd: float = 0.0
    omission_sd: float = 0.0
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> BetweenSubjectJitterConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run python -m pytest tests/test_config_temporal.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/config.py tests/test_config_temporal.py
git commit -m "feat: add TemporalEffectsConfig and BetweenSubjectJitterConfig dataclasses"
```

---

### Task 2: Wire new configs into TaskConfig, remove TimingConfig behavioral defaults

**Files:**
- Modify: `src/experiment_bot/core/config.py`
- Test: `tests/test_config_temporal.py` (add tests)

- [ ] **Step 1: Write failing tests for TaskConfig integration**

Add to `tests/test_config_temporal.py`:

```python
from experiment_bot.core.config import TaskConfig, PerformanceConfig


MINIMAL_CONFIG = {
    "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_task_config_has_temporal_effects():
    config = TaskConfig.from_dict(MINIMAL_CONFIG)
    assert config.temporal_effects.autocorrelation.enabled is False


def test_task_config_has_between_subject_jitter():
    config = TaskConfig.from_dict(MINIMAL_CONFIG)
    assert config.between_subject_jitter.rt_mean_sd_ms == 0.0


def test_task_config_temporal_effects_from_dict():
    d = dict(MINIMAL_CONFIG)
    d["temporal_effects"] = {
        "autocorrelation": {"enabled": True, "phi": 0.3, "rationale": "test"},
    }
    config = TaskConfig.from_dict(d)
    assert config.temporal_effects.autocorrelation.phi == 0.3


def test_task_config_round_trip_includes_temporal():
    d = dict(MINIMAL_CONFIG)
    d["temporal_effects"] = {
        "pink_noise": {"enabled": True, "sd_ms": 10, "hurst": 0.7, "rationale": "test"},
    }
    d["between_subject_jitter"] = {
        "rt_mean_sd_ms": 40, "rt_condition_sd_ms": 15,
        "sigma_tau_range": [0.85, 1.15], "accuracy_sd": 0.015,
        "omission_sd": 0.005, "rationale": "test",
    }
    config = TaskConfig.from_dict(d)
    out = config.to_dict()
    assert out["temporal_effects"]["pink_noise"]["sd_ms"] == 10
    assert out["between_subject_jitter"]["rt_mean_sd_ms"] == 40


def test_timing_config_no_behavioral_defaults():
    """TimingConfig should not have autocorrelation_phi or fatigue_drift_per_trial."""
    from experiment_bot.core.config import TimingConfig
    assert not hasattr(TimingConfig(), "autocorrelation_phi")
    assert not hasattr(TimingConfig(), "fatigue_drift_per_trial")


def test_performance_config_no_hardcoded_fallback():
    """get_accuracy/get_omission_rate raise ValueError on empty dict."""
    perf = PerformanceConfig(accuracy={}, omission_rate={}, practice_accuracy=0.85)
    try:
        perf.get_accuracy("go")
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    try:
        perf.get_omission_rate("go")
        assert False, "Should raise ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests — expect failures**

Run: `uv run python -m pytest tests/test_config_temporal.py -v`
Expected: New tests FAIL (TaskConfig doesn't have `temporal_effects` field yet, TimingConfig still has old fields, PerformanceConfig still returns hardcoded fallbacks)

- [ ] **Step 3: Modify TaskConfig to include new fields**

In `src/experiment_bot/core/config.py`:

1. Remove `autocorrelation_phi` and `fatigue_drift_per_trial` from `TimingConfig`
2. Remove hardcoded `return 0.90` from `PerformanceConfig.get_accuracy()` — replace with `raise ValueError("No accuracy values configured")`
3. Remove hardcoded `return 0.02` from `PerformanceConfig.get_omission_rate()` — replace with `raise ValueError("No omission rate values configured")`
4. Remove `practice_accuracy` default (`0.85`) from `PerformanceConfig` — make it a required field with no default. Update `from_dict` to require it explicitly. Update `PerformanceConfig.from_dict()` to raise if `practice_accuracy` is missing.
5. Add `temporal_effects` and `between_subject_jitter` fields to `TaskConfig`:

```python
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
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
```

Update `TaskConfig.from_dict()` to parse the new fields:

```python
temporal_effects=TemporalEffectsConfig.from_dict(d.get("temporal_effects", {})),
between_subject_jitter=BetweenSubjectJitterConfig.from_dict(d.get("between_subject_jitter", {})),
```

Update `TaskConfig.to_dict()` to include them:

```python
"temporal_effects": self.temporal_effects.to_dict(),
"between_subject_jitter": self.between_subject_jitter.to_dict(),
```

- [ ] **Step 4: Run new tests — expect PASS**

Run: `uv run python -m pytest tests/test_config_temporal.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite — fix cascading failures**

Run: `uv run python -m pytest tests/ -v`
Expected: Some existing tests may fail due to TimingConfig field removal or PerformanceConfig fallback change. Fix each by:
- Tests referencing `autocorrelation_phi` or `fatigue_drift_per_trial` on TimingConfig: remove those references
- Tests relying on hardcoded accuracy/omission fallbacks: add explicit accuracy/omission values to test configs

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/core/config.py tests/
git commit -m "feat: wire TemporalEffectsConfig into TaskConfig, remove behavioral defaults"
```

---

### Task 3: Update schema.json with temporal_effects and between_subject_jitter

**Files:**
- Modify: `src/experiment_bot/prompts/schema.json`

- [ ] **Step 1: Add temporal_effects to schema.json**

Add as a top-level property in the schema, after `task_specific`:

```json
"temporal_effects": {
  "type": "object",
  "description": "Temporal effects on the RT series. Each effect is optional — enable only those supported by the literature for this task. Provide rationale citing published studies.",
  "properties": {
    "autocorrelation": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "phi": {"type": "number", "minimum": 0, "maximum": 1, "description": "Lag-1 autocorrelation coefficient"},
        "rationale": {"type": "string"}
      }
    },
    "fatigue_drift": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "drift_per_trial_ms": {"type": "number", "minimum": 0, "description": "Milliseconds added per trial"},
        "rationale": {"type": "string"}
      }
    },
    "post_error_slowing": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "slowing_ms_min": {"type": "number", "minimum": 0},
        "slowing_ms_max": {"type": "number", "minimum": 0},
        "rationale": {"type": "string"}
      }
    },
    "condition_repetition": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "facilitation_ms": {"type": "number", "minimum": 0, "description": "RT reduction on condition repetition"},
        "cost_ms": {"type": "number", "minimum": 0, "description": "RT increase on condition alternation"},
        "rationale": {"type": "string"}
      }
    },
    "pink_noise": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "sd_ms": {"type": "number", "minimum": 0, "description": "Standard deviation of pink noise contribution"},
        "hurst": {"type": "number", "minimum": 0, "maximum": 1, "description": "Hurst exponent for 1/f noise spectral structure"},
        "rationale": {"type": "string"}
      }
    },
    "post_interrupt_slowing": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean"},
        "slowing_ms_min": {"type": "number", "minimum": 0},
        "slowing_ms_max": {"type": "number", "minimum": 0},
        "rationale": {"type": "string"}
      }
    }
  }
},
"between_subject_jitter": {
  "type": "object",
  "description": "Between-subject variability parameters. Controls how much each simulated session varies from the base parameters.",
  "properties": {
    "rt_mean_sd_ms": {"type": "number", "minimum": 0, "description": "SD of shared mean RT shift across conditions"},
    "rt_condition_sd_ms": {"type": "number", "minimum": 0, "description": "SD of per-condition RT shift"},
    "sigma_tau_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "[min, max] multiplier range for sigma and tau jitter"},
    "accuracy_sd": {"type": "number", "minimum": 0, "description": "SD of accuracy jitter"},
    "omission_sd": {"type": "number", "minimum": 0, "description": "SD of omission rate jitter"},
    "rationale": {"type": "string"}
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/experiment_bot/prompts/schema.json
git commit -m "feat: add temporal_effects and between_subject_jitter to schema.json"
```

---

## Chunk 2: Distribution and Executor Layer — Config-Driven Temporal Effects

### Task 4: Refactor ResponseSampler to use TemporalEffectsConfig

**Files:**
- Modify: `src/experiment_bot/core/distributions.py`
- Modify: `tests/test_distributions.py`

- [ ] **Step 1: Write failing tests for config-driven ResponseSampler**

Replace the current constructor-param tests in `tests/test_distributions.py`:

```python
from experiment_bot.core.config import (
    DistributionConfig, TemporalEffectsConfig, BetweenSubjectJitterConfig, TaskConfig,
)
from experiment_bot.core.distributions import ExGaussianSampler, ResponseSampler, jitter_distributions, _generate_pink_noise
import numpy as np


def _make_effects(**overrides) -> TemporalEffectsConfig:
    """Helper to build a TemporalEffectsConfig with specific effects enabled."""
    return TemporalEffectsConfig.from_dict(overrides)


GO_DIST = {"go": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80})}


def test_no_effects_produces_raw_ex_gaussian():
    """With all effects disabled, output is pure ex-Gaussian + floor."""
    effects = _make_effects()
    sampler = ResponseSampler(GO_DIST, effects, floor_ms=150.0, seed=42)
    rts = [sampler.sample_rt("go") for _ in range(100)]
    assert all(rt >= 150.0 for rt in rts)


def test_autocorrelation_enabled():
    """Enabling autocorrelation should produce lag-1 correlation."""
    effects = _make_effects(
        autocorrelation={"enabled": True, "phi": 0.5, "rationale": "test"},
    )
    sampler = ResponseSampler(GO_DIST, effects, floor_ms=150.0, seed=42)
    rts = [sampler.sample_rt("go") for _ in range(500)]
    # Lag-1 correlation should be positive with phi=0.5
    rts_arr = np.array(rts)
    corr = np.corrcoef(rts_arr[:-1], rts_arr[1:])[0, 1]
    assert corr > 0.05


def test_condition_repetition_enabled():
    """Repetitions faster than alternations when condition_repetition enabled."""
    effects = _make_effects(
        condition_repetition={"enabled": True, "facilitation_ms": 10, "cost_ms": 10, "rationale": "test"},
    )
    dists = {
        "a": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80}),
        "b": DistributionConfig(distribution="ex_gaussian", params={"mu": 450, "sigma": 60, "tau": 80}),
    }
    # All repetitions
    s1 = ResponseSampler(dists, effects, floor_ms=150.0, seed=42)
    rep_rts = [s1.sample_rt("a") for _ in range(1000)]
    # All alternations
    s2 = ResponseSampler(dists, effects, floor_ms=150.0, seed=42)
    alt_rts = []
    for i in range(1000):
        alt_rts.append(s2.sample_rt("a" if i % 2 == 0 else "b"))
    assert np.mean(rep_rts[1:]) < np.mean(alt_rts[1:])


def test_pink_noise_disabled_no_buffer():
    """When pink noise is disabled, no buffer is allocated."""
    effects = _make_effects()
    sampler = ResponseSampler(GO_DIST, effects, floor_ms=150.0, seed=42)
    assert sampler._pink_buffer is None


def test_pink_noise_enabled_allocates_buffer():
    effects = _make_effects(
        pink_noise={"enabled": True, "sd_ms": 12, "hurst": 0.75, "rationale": "test"},
    )
    sampler = ResponseSampler(GO_DIST, effects, floor_ms=150.0, seed=42)
    assert sampler._pink_buffer is not None
    assert len(sampler._pink_buffer) == 2048
```

- [ ] **Step 2: Run tests — expect failures**

Run: `uv run python -m pytest tests/test_distributions.py -v`
Expected: FAIL — ResponseSampler constructor signature changed

- [ ] **Step 3: Rewrite ResponseSampler**

Rewrite `src/experiment_bot/core/distributions.py`:

- Remove `_PINK_BUFFER_LEN` and `_GRATTON_MS` constants
- Import `TemporalEffectsConfig` from config
- Delete old tests that use the old constructor signature: `test_response_sampler_floor`, `test_response_sampler_unknown_condition`, `test_gratton_repetition_faster_than_alternation`, `test_response_sampler_tracks_condition`, `test_omission_jitter_stays_within_tight_bounds` (jitter tests move to Task 5)
- Also update `test_sampler_fallback_to_first_distribution` in `tests/test_executor.py` to use the new constructor signature

New `ResponseSampler` implementation:

```python
from experiment_bot.core.config import DistributionConfig, TaskConfig, TemporalEffectsConfig

_PINK_BUFFER_LEN = 2048  # Power of 2 for FFT efficiency


class ResponseSampler:
    def __init__(
        self,
        distributions: dict[str, DistributionConfig],
        temporal_effects: TemporalEffectsConfig,
        floor_ms: float = 150.0,
        seed: int | None = None,
    ):
        self._floor_ms = floor_ms
        self._effects = temporal_effects
        self._prev_condition: str | None = None
        self._prev_rt: float | None = None
        self._trial_index: int = 0

        # Validate enabled effects have non-zero required params
        pn = temporal_effects.pink_noise
        if pn.enabled and pn.hurst <= 0:
            raise ValueError("pink_noise.hurst must be in (0, 1] when enabled")
        if pn.enabled:
            self._pink_buffer = _generate_pink_noise(
                _PINK_BUFFER_LEN, pn.hurst, np.random.default_rng(seed)
            )
        else:
            self._pink_buffer = None

        self._samplers: dict[str, ExGaussianSampler] = {}
        for condition, dist_config in distributions.items():
            if dist_config.distribution == "ex_gaussian":
                self._samplers[condition] = ExGaussianSampler(
                    mu=dist_config.params["mu"],
                    sigma=dist_config.params["sigma"],
                    tau=dist_config.params["tau"],
                    seed=seed,
                )

    def _apply_temporal_effects(
        self, raw_rt: float, sampler: ExGaussianSampler, condition: str,
        skip_condition_repetition: bool = False,
    ) -> float:
        """Apply config-driven sequential temporal effects to a raw RT sample.

        Args:
            skip_condition_repetition: If True, suppress condition-repetition effect
                for this trial (used when post-interrupt slowing already applies).
        """
        rt = raw_rt
        te = self._effects

        # AR(1) autocorrelation
        if te.autocorrelation.enabled and te.autocorrelation.phi > 0:
            if self._prev_rt is not None:
                mean_rt = sampler.mu + sampler.tau
                deviation = self._prev_rt - mean_rt
                rt += te.autocorrelation.phi * deviation

        # Condition repetition (Gratton effect) — skipped when post-interrupt
        if te.condition_repetition.enabled and not skip_condition_repetition:
            if self._prev_condition is not None:
                if condition == self._prev_condition:
                    rt -= te.condition_repetition.facilitation_ms
                else:
                    rt += te.condition_repetition.cost_ms

        # 1/f (pink) noise
        if self._pink_buffer is not None and te.pink_noise.enabled:
            pink_idx = self._trial_index % len(self._pink_buffer)
            rt += self._pink_buffer[pink_idx] * te.pink_noise.sd_ms

        # Fatigue drift
        if te.fatigue_drift.enabled and te.fatigue_drift.drift_per_trial_ms > 0:
            rt += self._trial_index * te.fatigue_drift.drift_per_trial_ms

        rt = max(rt, self._floor_ms)
        self._prev_rt = rt
        self._prev_condition = condition
        self._trial_index += 1
        return rt

    def sample_rt(self, condition: str, skip_condition_repetition: bool = False) -> float:
        if condition not in self._samplers:
            raise KeyError(f"Unknown condition: {condition}")
        sampler = self._samplers[condition]
        raw_rt = sampler.sample()
        return self._apply_temporal_effects(raw_rt, sampler, condition, skip_condition_repetition)

    def sample_rt_with_fallback(self, condition: str, skip_condition_repetition: bool = False) -> float:
        """Sample RT for condition, falling back to first available distribution."""
        if condition in self._samplers:
            sampler = self._samplers[condition]
        elif self._samplers:
            sampler = next(iter(self._samplers.values()))
        else:
            # No samplers — apply drift + pink noise without AR(1)/condition_repetition
            te = self._effects
            rt = 500.0
            if te.fatigue_drift.enabled:
                rt += self._trial_index * te.fatigue_drift.drift_per_trial_ms
            if self._pink_buffer is not None and te.pink_noise.enabled:
                pink_idx = self._trial_index % len(self._pink_buffer)
                rt += self._pink_buffer[pink_idx] * te.pink_noise.sd_ms
            rt = max(rt, self._floor_ms)
            self._prev_condition = condition
            self._trial_index += 1
            return rt
        raw_rt = sampler.sample()
        return self._apply_temporal_effects(raw_rt, sampler, condition, skip_condition_repetition)
```

Note: `_apply_temporal_effects` takes a `skip_condition_repetition` parameter. This implements the spec's effect interaction rule: the executor passes `skip_condition_repetition=True` when post-interrupt slowing was applied, preventing double-counting.

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run python -m pytest tests/test_distributions.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/distributions.py tests/test_distributions.py
git commit -m "refactor: ResponseSampler reads temporal effects from config"
```

---

### Task 5: Refactor jitter_distributions to use BetweenSubjectJitterConfig

**Files:**
- Modify: `src/experiment_bot/core/distributions.py`
- Test: `tests/test_distributions.py`

- [ ] **Step 1: Write failing test for config-driven jitter**

Add to `tests/test_distributions.py`:

```python
def test_jitter_uses_config_values():
    """jitter_distributions reads magnitudes from between_subject_jitter config."""
    config_data = {
        "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "response_distributions": {
            "go": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
        },
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
        "navigation": {"phases": []},
        "task_specific": {},
        "between_subject_jitter": {
            "rt_mean_sd_ms": 40, "rt_condition_sd_ms": 15,
            "sigma_tau_range": [0.85, 1.15],
            "accuracy_sd": 0.015, "omission_sd": 0.005,
            "rationale": "test",
        },
    }
    config = TaskConfig.from_dict(config_data)
    rng = np.random.default_rng(42)
    jittered = jitter_distributions(config, rng)
    # Mu should have shifted from 450
    assert jittered.response_distributions["go"].params["mu"] != 450


def test_jitter_no_config_no_jitter():
    """When between_subject_jitter has all zeros, no jitter is applied."""
    config_data = {
        "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "response_distributions": {
            "go": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
        },
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.85},
        "navigation": {"phases": []},
        "task_specific": {},
    }
    config = TaskConfig.from_dict(config_data)
    rng = np.random.default_rng(42)
    jittered = jitter_distributions(config, rng)
    # With zero jitter, mu should stay at 450
    assert jittered.response_distributions["go"].params["mu"] == 450
```

- [ ] **Step 2: Run tests — expect failure**

Run: `uv run python -m pytest tests/test_distributions.py::test_jitter_no_config_no_jitter -v`
Expected: FAIL — jitter still uses hardcoded constants

- [ ] **Step 3: Refactor jitter_distributions**

Update `jitter_distributions()` to read from `config.between_subject_jitter`:

```python
def jitter_distributions(config: TaskConfig, rng: np.random.Generator) -> TaskConfig:
    config = copy.deepcopy(config)
    bsj = config.between_subject_jitter

    # Skip jitter entirely if not configured
    if bsj.rt_mean_sd_ms == 0 and bsj.accuracy_sd == 0:
        return config

    shared_mu_shift = rng.normal(0, bsj.rt_mean_sd_ms) if bsj.rt_mean_sd_ms > 0 else 0.0
    for dist in config.response_distributions.values():
        if dist.distribution == "ex_gaussian":
            dist.params["mu"] += shared_mu_shift + (rng.normal(0, bsj.rt_condition_sd_ms) if bsj.rt_condition_sd_ms > 0 else 0.0)
            lo, hi = bsj.sigma_tau_range
            if lo != hi:
                dist.params["sigma"] *= rng.uniform(lo, hi)
                dist.params["tau"] *= rng.uniform(lo, hi)

    if bsj.accuracy_sd > 0:
        for cond, acc_base in config.performance.accuracy.items():
            config.performance.accuracy[cond] = float(
                np.clip(acc_base + rng.normal(0, bsj.accuracy_sd), 0.60, 0.995)
            )

    if bsj.omission_sd > 0:
        for cond, om_base in config.performance.omission_rate.items():
            config.performance.omission_rate[cond] = float(
                np.clip(om_base + rng.normal(0, bsj.omission_sd), 0.0, 0.10)
            )

    return config
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run python -m pytest tests/test_distributions.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/distributions.py tests/test_distributions.py
git commit -m "refactor: jitter_distributions reads magnitudes from config"
```

---

### Task 6: Refactor TaskExecutor to use config-driven slowing

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `tests/test_executor.py`

- [ ] **Step 1: Write failing tests**

Update tests in `tests/test_executor.py`:

```python
def test_post_error_slowing_reads_from_config():
    """Post-error slowing magnitude comes from temporal_effects config."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    # Should reference config, not hardcoded uniform(20, 60)
    assert "post_error_slowing" in source
    assert "post_interrupt_slowing" in source


def test_executor_sampler_receives_temporal_effects():
    """Executor passes temporal_effects to ResponseSampler."""
    config_data = dict(SAMPLE_CONFIG)
    config_data["temporal_effects"] = {
        "autocorrelation": {"enabled": True, "phi": 0.3, "rationale": "test"},
    }
    config = TaskConfig.from_dict(config_data)
    executor = TaskExecutor(config, seed=42)
    assert executor._sampler._effects.autocorrelation.phi == 0.3


def test_post_interrupt_skips_condition_repetition():
    """When post-interrupt slowing fires, condition_repetition is suppressed."""
    import inspect
    source = inspect.getsource(TaskExecutor._execute_trial)
    assert "skip_condition_repetition" in source
```

- [ ] **Step 2: Run tests — expect failures**

Run: `uv run python -m pytest tests/test_executor.py -v`
Expected: FAIL

- [ ] **Step 3: Update TaskExecutor**

In `src/experiment_bot/core/executor.py`:

1. Change the `ResponseSampler` construction in `__init__`:

```python
self._sampler = ResponseSampler(
    config.response_distributions,
    config.temporal_effects,
    floor_ms=config.runtime.timing.rt_floor_ms,
    seed=seed,
)
```

2. Replace hardcoded post-error/post-interrupt slowing in `_execute_trial`:

```python
# Sequential slowing effects (mutually exclusive — most specific wins)
te = self._config.temporal_effects
skip_cond_rep = False
if self._prev_interrupt_detected and te.post_interrupt_slowing.enabled:
    rt_ms += self._rng.uniform(
        te.post_interrupt_slowing.slowing_ms_min,
        te.post_interrupt_slowing.slowing_ms_max,
    )
    skip_cond_rep = True  # Suppress condition_repetition on this trial
elif self._prev_trial_error and te.post_error_slowing.enabled:
    rt_ms += self._rng.uniform(
        te.post_error_slowing.slowing_ms_min,
        te.post_error_slowing.slowing_ms_max,
    )
```

3. Pass `skip_condition_repetition` through to `sample_rt_with_fallback`:

The `skip_cond_rep` flag must be passed to `self._sampler.sample_rt_with_fallback(rt_condition, skip_condition_repetition=skip_cond_rep)` so the sampler knows to suppress the Gratton effect on post-interrupt trials. This implements the spec's effect interaction rule.

4. Also update `tests/test_executor.py::test_sampler_fallback_to_first_distribution` to use the new `ResponseSampler` constructor signature (pass a `TemporalEffectsConfig` instead of individual params).

- [ ] **Step 4: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "refactor: executor reads post-error/post-interrupt slowing from config"
```

---

## Chunk 3: Prompt, Scripts, Docs, Data

### Task 7: Restructure prompts/system.md — technical vs. behavioral split

**Files:**
- Modify: `src/experiment_bot/prompts/system.md`

- [ ] **Step 1: Rewrite system.md**

Restructure into two clearly labeled sections:

**Section A — Technical Instructions:** Keep all current content about detection methods, JS expressions, navigation, response key resolution, data capture, attention checks, timing config, advance behavior. Add documentation for the `temporal_effects` schema slots (what each field means mechanically, not what values to use). Add documentation for `between_subject_jitter`.

**Section B — Behavioral Instructions:** Replace the current behavioral hints with the open-ended version from the spec:

> "You are analyzing a cognitive experiment. Based on the task source code and your knowledge of the cognitive psychology literature:
> 1. Identify the cognitive constructs being measured and the relevant literature
> 2. Determine appropriate response time distributions (ex-Gaussian: mu, sigma, tau) for each condition, informed by published findings for this paradigm
> 3. Set per-condition accuracy and omission rate targets consistent with the literature
> 4. Decide which temporal effects to enable and parameterize, with rationale citing relevant studies
> 5. If the task involves any form of response suppression or signal-based interruption, configure the trial_interrupt parameters based on the relevant theoretical framework, citing your reasoning
> 6. Configure between-subject jitter parameters based on known individual differences in the literature
>
> Your behavioral parameters should reflect what a typical healthy adult participant would produce. Cite your reasoning in the rationale fields."

Remove: specific parameter ranges, hints about which effects for which task types, platform-specific behavioral guidance.

- [ ] **Step 2: Commit**

```bash
git add src/experiment_bot/prompts/system.md
git commit -m "refactor: split prompt into technical vs. behavioral sections"
```

---

### Task 8: Move human data, deprecate old scripts, create analysis notebook

**Files:**
- Create: `data/human/` (move CSVs)
- Create: `scripts/__deprecated__/` (move old scripts)
- Create: `scripts/analysis.ipynb`

- [ ] **Step 1: Move human data files**

```bash
mkdir -p data/human
git mv stop_signal.csv data/human/stop_signal.csv
git mv stroop.csv data/human/stroop.csv
```

- [ ] **Step 2: Deprecate old scripts**

```bash
mkdir -p scripts/__deprecated__
git mv scripts/check_data.py scripts/__deprecated__/check_data.py
git mv scripts/check_data.ipynb scripts/__deprecated__/check_data.ipynb
git mv scripts/verify_humanlike.py scripts/__deprecated__/verify_humanlike.py
```

- [ ] **Step 3: Create analysis.ipynb**

Create `scripts/analysis.ipynb` with these sections:

1. **Setup** — imports (pandas, numpy, pathlib, json, matplotlib), path constants, helper to load bot runs
2. **Load Human Data** — read CSVs, filter three exclusion columns to "Include", show sample counts
3. **Load Bot Data** — scan `output/` dirs, load bot_log.json + experiment_data per run, parse into DataFrames
4. **Stop Signal Metrics** — mean go RT (test trials only for ExpFactory), go accuracy, go omission, stop failure RT, stop accuracy, SSD, SSRT. Side-by-side human vs. bot table.
5. **Stroop Metrics** — congruent/incongruent RT and accuracy, omission rates, Stroop effect. Side-by-side table.
6. **Cross-Platform Comparison** — same metrics for STOP-IT and cognition.run runs

Each section has a markdown cell explaining what's being computed and why. Filtering logic is explicit and commented.

- [ ] **Step 4: Commit**

```bash
git add data/human/ scripts/__deprecated__/ scripts/analysis.ipynb
git commit -m "feat: consolidate scripts, move human data, create analysis notebook"
```

---

### Task 9: Rewrite docs/how-it-works.md

**Files:**
- Modify: `docs/how-it-works.md`

- [ ] **Step 1: Rewrite the document**

Follow the structure from the spec:

1. **Overview** — single sentence + zero-shot philosophy
2. **Information Flow — What the Bot Knows and When** — build time (mechanisms), config generation (Claude infers), runtime (executes config)
3. **Config Generation Pipeline** — Scrape → Claude → Cache → Jitter → Execute, with prompt split explained
4. **TaskConfig Schema** — full reference including temporal_effects, between_subject_jitter, marked as "Claude-determined"
5. **Response Time Modeling** — ex-Gaussian methodology, temporal effects as optional layers
6. **Trial Execution** — stimulus detection, phase detection, accuracy/omission, interrupt handling
7. **Data Output** — what gets saved, where, format
8. **Validation Approach** — mean-metric comparison, analysis notebook

- [ ] **Step 2: Commit**

```bash
git add docs/how-it-works.md
git commit -m "docs: rewrite how-it-works as methods section with information flow"
```

---

### Task 10: Regenerate cached configs

**Files:**
- Modify: `cache/*/config.json` (all four)

- [ ] **Step 1: Delete existing cached configs**

```bash
rm cache/expfactory_stop_signal/config.json
rm cache/expfactory_stroop/config.json
rm cache/stopit_stop_signal/config.json
rm cache/cognitionrun_stroop/config.json
```

- [ ] **Step 2: Regenerate each config**

Run the bot with `--regenerate-config` for each experiment URL. The bot will scrape the source, call Claude with the updated prompt/schema, and cache the result.

```bash
uv run experiment-bot <expfactory-stop-signal-url> --label expfactory_stop_signal --regenerate-config --headless
uv run experiment-bot <expfactory-stroop-url> --label expfactory_stroop --regenerate-config --headless
uv run experiment-bot <stopit-stop-signal-url> --label stopit_stop_signal --regenerate-config --headless
uv run experiment-bot <cognitionrun-stroop-url> --label cognitionrun_stroop --regenerate-config --headless
```

Note: Use `Ctrl+C` after config generation if you don't want to run the full task — the config is cached after the Claude call but before execution.

- [ ] **Step 3: Review generated configs**

Check each `cache/*/config.json` for:
- `temporal_effects` block is present with rationales
- `between_subject_jitter` block is present
- No hardcoded values from old schema remain
- RT distribution parameters are reasonable for the task
- Accuracy targets are reasonable for the task

- [ ] **Step 4: Commit**

```bash
git add cache/
git commit -m "feat: regenerate cached configs with Claude-determined temporal effects"
```

---

### Task 11: Final integration test

- [ ] **Step 1: Run full test suite**

```bash
uv run python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: Verify bot runs end-to-end**

Run against one cached experiment to confirm the full pipeline works:

```bash
uv run experiment-bot <expfactory-stroop-url> --label expfactory_stroop --headless
```

Verify output appears in `output/` with trial logs and experiment data.

- [ ] **Step 3: Run analysis notebook**

```bash
uv run jupyter execute scripts/analysis.ipynb
```

Or open in Jupyter and run all cells. Verify human data loads, bot data loads (if available), and metrics compute without errors.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final integration verification"
```

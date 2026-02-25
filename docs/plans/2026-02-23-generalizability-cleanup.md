# Generalizability Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all hardcoded, platform-specific logic from the executor and move it into config-driven behavior, so any new task/platform works by generating a config — no code changes needed.

**Architecture:** The executor becomes a pure config interpreter. Platform adapters become thin shells. Claude's analyzer produces richer configs that encode all platform-specific behavior (phase detection, timing, advance keys, paradigm rules). A platform registry replaces if/else chains.

**Tech Stack:** Python 3.12, Playwright, dataclasses, existing test infrastructure

---

### Task 1: Extend TaskConfig with platform-agnostic runtime fields

**Files:**
- Modify: `src/experiment_bot/core/config.py`
- Test: `tests/test_config.py`

Add new config sections that replace hardcoded behavior. These fields will be populated by Claude's analyzer when generating configs.

**Step 1: Write the failing test**

```python
def test_runtime_config_from_dict():
    """RuntimeConfig parses from JSON with all new fields."""
    data = {
        "phase_detection": {
            "method": "js_eval",
            "complete": "typeof psy_experiment_done !== 'undefined' && psy_experiment_done",
            "test": "true",
            "loading": "document.body.textContent.includes('Click to start')"
        },
        "timing": {
            "poll_interval_ms": 20,
            "max_no_stimulus_polls": 2000,
            "stuck_timeout_s": 10.0,
            "completion_wait_ms": 5000,
            "feedback_delay_ms": 2000,
            "omission_wait_ms": 2000,
            "stop_success_wait_ms": 1500,
            "rt_floor_ms": 150,
            "rt_cap_fraction": 0.90,
            "viewport": {"width": 1280, "height": 800}
        },
        "advance_behavior": {
            "pre_keypress_js": "psy_expect_keyboard()",
            "advance_keys": [" "],
            "exit_pager_key": "q",
            "advance_interval_polls": 100,
            "feedback_selectors": ["button"],
            "feedback_fallback_keys": [" ", "Enter"]
        },
        "paradigm": {
            "type": "stop_signal",
            "stop_condition": "stop",
            "stop_failure_rt_key": "stop_failure",
            "stop_rt_cap_fraction": 0.85
        }
    }
    from experiment_bot.core.config import RuntimeConfig
    rc = RuntimeConfig.from_dict(data)
    assert rc.timing.poll_interval_ms == 20
    assert rc.advance_behavior.exit_pager_key == "q"
    assert rc.paradigm.type == "stop_signal"
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_config.py::test_runtime_config_from_dict -v`
Expected: FAIL — `RuntimeConfig` does not exist yet

**Step 3: Implement RuntimeConfig and sub-dataclasses**

Add to `config.py`:

```python
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
```

Add `runtime` field to `TaskConfig`:

```python
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
            ...existing fields...,
            runtime=RuntimeConfig.from_dict(d.get("runtime", {})),
        )

    def to_dict(self) -> dict:
        result = {
            ...existing fields...,
        }
        runtime_dict = self.runtime.to_dict()
        if any(v for v in runtime_dict.values()):
            result["runtime"] = runtime_dict
        return result
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/config.py tests/test_config.py
git commit -m "feat: add RuntimeConfig for config-driven executor behavior"
```

---

### Task 2: Make phase detection config-driven

**Files:**
- Modify: `src/experiment_bot/platforms/expfactory.py`
- Modify: `src/experiment_bot/platforms/psytoolkit.py`
- Modify: `src/experiment_bot/platforms/base.py`
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_expfactory.py`
- Test: `tests/test_psytoolkit.py`

Move all hardcoded phase detection JavaScript and selectors into config. The platform's `detect_task_phase` method will evaluate JS expressions from `runtime.phase_detection`.

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_config_driven_phase_detection():
    """Phase detection uses JS expressions from config when provided."""
    from experiment_bot.core.config import TaskPhase, RuntimeConfig, PhaseDetectionConfig
    from experiment_bot.platforms.base import Platform

    config = RuntimeConfig(
        phase_detection=PhaseDetectionConfig(
            method="js_eval",
            complete="document.title === 'Done'",
            test="true",
        )
    )
    # The platform should use config expressions instead of hardcoded logic
    # when a runtime config is provided
```

**Step 2: Run test to verify it fails**

**Step 3: Add `detect_task_phase_from_config` to Platform base class**

In `base.py`, add a shared method that evaluates `runtime.phase_detection` JS expressions. Platform subclasses call this first; only fall back to hardcoded logic if no config expressions are provided (backward compat).

```python
class Platform(ABC):
    async def detect_task_phase_from_config(
        self, page: Page, phase_config: PhaseDetectionConfig
    ) -> TaskPhase | None:
        """Evaluate config-driven phase detection. Returns None if no match."""
        if not phase_config.complete and not phase_config.loading:
            return None  # No config — let subclass handle it

        for phase_name, js_expr in [
            ("complete", phase_config.complete),
            ("loading", phase_config.loading),
            ("instructions", phase_config.instructions),
            ("attention_check", phase_config.attention_check),
            ("feedback", phase_config.feedback),
            ("practice", phase_config.practice),
        ]:
            if js_expr:
                try:
                    result = await page.evaluate(f"(() => {{ try {{ return {js_expr}; }} catch(e) {{ return false; }} }})()")
                    if result:
                        return TaskPhase(phase_name)
                except Exception:
                    continue

        if phase_config.test:
            return TaskPhase.TEST
        return None
```

Update `expfactory.py` and `psytoolkit.py` `detect_task_phase` to check config first:

```python
async def detect_task_phase(self, page: Page, runtime_config=None) -> TaskPhase:
    if runtime_config and runtime_config.phase_detection.complete:
        result = await self.detect_task_phase_from_config(page, runtime_config.phase_detection)
        if result:
            return result
    # Fall back to existing hardcoded logic for backward compatibility
    ...
```

**Step 4: Run tests**

**Step 5: Commit**

```bash
git add src/experiment_bot/platforms/ tests/
git commit -m "feat: config-driven phase detection with platform fallback"
```

---

### Task 3: Replace platform if/else chain with registry

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Create: `src/experiment_bot/platforms/registry.py`
- Test: `tests/test_platforms_base.py`

**Step 1: Write the failing test**

```python
def test_platform_registry():
    from experiment_bot.platforms.registry import get_platform
    platform = get_platform("expfactory")
    assert isinstance(platform, ExpFactoryPlatform)

    platform = get_platform("psytoolkit")
    assert isinstance(platform, PsyToolkitPlatform)

    with pytest.raises(KeyError):
        get_platform("unknown_platform")
```

**Step 2: Run test to verify it fails**

**Step 3: Implement registry**

```python
# src/experiment_bot/platforms/registry.py
from experiment_bot.platforms.base import Platform
from experiment_bot.platforms.expfactory import ExpFactoryPlatform
from experiment_bot.platforms.psytoolkit import PsyToolkitPlatform

_REGISTRY: dict[str, type[Platform]] = {
    "expfactory": ExpFactoryPlatform,
    "psytoolkit": PsyToolkitPlatform,
}

def get_platform(name: str) -> Platform:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown platform: {name}. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]()
```

Update `cli.py` to use it:
```python
from experiment_bot.platforms.registry import get_platform
platform = get_platform(platform_name)
```

**Step 4: Run tests**

**Step 5: Commit**

```bash
git add src/experiment_bot/platforms/registry.py src/experiment_bot/cli.py tests/
git commit -m "refactor: replace platform if/else with registry"
```

---

### Task 4: Replace executor timing magic numbers with RuntimeConfig

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `src/experiment_bot/core/distributions.py`
- Test: `tests/test_executor.py`

Replace every magic number in executor.py with reads from `self._config.runtime.timing`. The TimingConfig has sensible defaults so existing configs without `runtime` continue to work.

**Step 1: Write the failing test**

```python
def test_executor_uses_runtime_timing():
    """Executor reads timing from runtime config, not hardcoded values."""
    config = _build_config()
    config.runtime.timing.poll_interval_ms = 50
    config.runtime.timing.max_no_stimulus_polls = 1000
    executor = TaskExecutor(config, platform_name="test")
    # Verify executor stored the config (implementation detail test)
    assert executor._config.runtime.timing.poll_interval_ms == 50
```

**Step 2: Run test to verify it fails**

**Step 3: Replace all magic numbers in executor.py**

Replace line by line:
- `StuckDetector(timeout_seconds=10.0)` → `StuckDetector(timeout_seconds=self._config.runtime.timing.stuck_timeout_s)`
- `max_no_stimulus_polls = 2000 if ... else 500` → `max_no_stimulus_polls = self._config.runtime.timing.max_no_stimulus_polls`
- `poll_interval = 0.02` → `poll_interval = self._config.runtime.timing.poll_interval_ms / 1000.0`
- `asyncio.sleep(2.0)` in omission → `asyncio.sleep(self._config.runtime.timing.omission_wait_ms / 1000.0)`
- `asyncio.sleep(1.5)` in stop success → `asyncio.sleep(self._config.runtime.timing.stop_success_wait_ms / 1000.0)`
- `max_response_ms * 0.90` → `max_response_ms * self._config.runtime.timing.rt_cap_fraction`
- `max_response_ms * 0.85` → `max_response_ms * self._config.runtime.paradigm.stop_rt_cap_fraction`
- `asyncio.sleep(35)` and `asyncio.sleep(5)` → `asyncio.sleep(self._config.runtime.timing.completion_wait_ms / 1000.0)`
- `viewport={"width": 1280, "height": 800}` → `viewport=self._config.runtime.timing.viewport`
- `floor_ms=150.0` in ResponseSampler → `floor_ms=self._config.runtime.timing.rt_floor_ms`

Also update `distributions.py`:
```python
class ResponseSampler:
    def __init__(self, distributions, floor_ms=150.0, seed=None):
```
The floor_ms is passed from executor using config value.

**Step 4: Run all tests**

Run: `uv run python -m pytest tests/ -v`
Expected: ALL PASS (defaults match current hardcoded values)

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py src/experiment_bot/core/distributions.py tests/
git commit -m "refactor: replace timing magic numbers with RuntimeConfig"
```

---

### Task 5: Remove platform name checks from executor

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_executor.py`

After Tasks 1-4, the executor should no longer need `self._platform_name`. All platform-specific behavior is in config.

**Step 1: Write the failing test**

```python
def test_executor_no_platform_name_dependency():
    """Executor should not branch on platform name."""
    import inspect
    from experiment_bot.core.executor import TaskExecutor
    source = inspect.getsource(TaskExecutor)
    # No remaining platform_name conditionals in the executor logic
    assert 'platform_name == "psytoolkit"' not in source
    assert 'platform_name == "expfactory"' not in source
```

**Step 2: Run test to verify it fails**

**Step 3: Replace all `self._platform_name` checks with config-driven behavior**

- `max_no_stimulus_polls = 2000 if self._platform_name == "psytoolkit" else 500`
  → Already replaced in Task 4 with `self._config.runtime.timing.max_no_stimulus_polls`

- `if self._platform_name == "psytoolkit": await self._psytoolkit_reenable_keyboard(page)`
  → Replace with: `if self._config.runtime.advance_behavior.pre_keypress_js: await page.evaluate(self._config.runtime.advance_behavior.pre_keypress_js)`

- PsyToolkit Q key exit:
  → Replace with: `if self._config.runtime.advance_behavior.exit_pager_key: await page.keyboard.press(self._config.runtime.advance_behavior.exit_pager_key)`

- `if self._platform_name == "expfactory": await asyncio.sleep(35)`
  → Already replaced in Task 4 with `self._config.runtime.timing.completion_wait_ms`

- Remove `_psytoolkit_reenable_keyboard` method entirely

- Keep `self._platform_name` only in `__init__` for metadata/logging (output directory naming). Do not use it for control flow.

**Step 4: Run tests**

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/
git commit -m "refactor: remove all platform name conditionals from executor"
```

---

### Task 6: Generalize key mapping resolution

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: cached configs to include direct key mappings
- Test: `tests/test_executor.py`

Replace the hardcoded `_resolve_key_mapping` method (which knows about stop signal group indices and task switching parity/magnitude) with a generic approach: the config's `task_specific.key_map` provides direct condition→key mappings. Claude's analyzer populates this when generating configs.

**Step 1: Write the failing test**

```python
def test_direct_key_map_from_config():
    """Key map uses task_specific.key_map directly when present."""
    config = _build_config()
    config.task_specific = {
        "key_map": {
            "go_left": "b",
            "go_right": "n",
            "parity_even": "z",
            "parity_odd": "m",
        }
    }
    executor = TaskExecutor(config, platform_name="test")
    assert executor._key_map == config.task_specific["key_map"]
```

**Step 2: Run test to verify it fails**

**Step 3: Simplify `_resolve_key_mapping`**

```python
@staticmethod
def _resolve_key_mapping(config: TaskConfig) -> dict[str, str]:
    """Resolve key mappings from config."""
    ts = config.task_specific
    # Prefer direct key_map if provided
    if "key_map" in ts:
        return dict(ts["key_map"])
    # Legacy: resolve from group-based mappings (backward compat)
    return TaskExecutor._resolve_key_mapping_legacy(config)

@staticmethod
def _resolve_key_mapping_legacy(config: TaskConfig) -> dict[str, str]:
    """Legacy key mapping resolution for older configs."""
    # ... move existing code here unchanged ...
```

**Step 4: Run tests**

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/
git commit -m "refactor: support direct key_map in config, keep legacy fallback"
```

---

### Task 7: Make feedback and advance behavior config-driven

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_executor.py`

Replace hardcoded feedback selectors (`"button"`, `"#jspsych-instructions-next"`, `".jspsych-btn"`) and fallback keys (`" "`, `"Enter"`) with reads from `runtime.advance_behavior`.

**Step 1: Write the failing test**

```python
def test_feedback_uses_config_selectors():
    """_handle_feedback uses config selectors, not hardcoded jsPsych ones."""
    config = _build_config()
    config.runtime.advance_behavior.feedback_selectors = ["button.custom"]
    config.runtime.advance_behavior.feedback_fallback_keys = ["Enter"]
    # Verify config is accessible (unit test; integration test would use mock page)
    assert config.runtime.advance_behavior.feedback_selectors == ["button.custom"]
```

**Step 2: Run test to verify it fails**

**Step 3: Update `_handle_feedback` and advance logic**

```python
async def _handle_feedback(self, page: Page) -> None:
    ab = self._config.runtime.advance_behavior
    await asyncio.sleep(self._config.runtime.timing.feedback_delay_ms / 1000.0)

    for selector in ab.feedback_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                return
        except Exception:
            continue

    for key in ab.feedback_fallback_keys:
        await page.keyboard.press(key)
        await asyncio.sleep(0.5)
```

Update the between-block advance logic in `_trial_loop`:
```python
if consecutive_misses % ab.advance_interval_polls == 0:
    if ab.pre_keypress_js:
        try:
            await page.evaluate(ab.pre_keypress_js)
        except Exception:
            pass
    for key in ab.advance_keys:
        await page.keyboard.press(key)
    if ab.exit_pager_key and consecutive_misses % (ab.advance_interval_polls * 2) == 0:
        await asyncio.sleep(0.5)
        if ab.pre_keypress_js:
            try:
                await page.evaluate(ab.pre_keypress_js)
            except Exception:
                pass
        await page.keyboard.press(ab.exit_pager_key)
```

**Step 4: Run tests**

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/
git commit -m "refactor: config-driven feedback selectors and advance keys"
```

---

### Task 8: Make stop signal paradigm config-driven

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_executor.py`

Replace hardcoded `"stop"` condition checks and `"stop_failure"` distribution names with reads from `runtime.paradigm`.

**Step 1: Write the failing test**

```python
def test_paradigm_config_controls_stop_handling():
    """Stop signal condition names come from paradigm config."""
    config = _build_config()
    config.runtime.paradigm.type = "stop_signal"
    config.runtime.paradigm.stop_condition = "inhibit"
    config.runtime.paradigm.stop_failure_rt_key = "inhibit_failure"
    executor = TaskExecutor(config, platform_name="test")
    # _get_stop_signal_selector should look for "inhibit" not "stop"
    # (add a stimulus with condition="inhibit" to verify)
```

**Step 2: Run test to verify it fails**

**Step 3: Update stop signal methods to use paradigm config**

```python
def _get_stop_signal_selector(self) -> str | None:
    if self._config.runtime.paradigm.type != "stop_signal":
        return None
    stop_cond = self._config.runtime.paradigm.stop_condition
    for stim in self._config.stimuli:
        if stim.response.condition == stop_cond:
            return stim.detection.selector
    return None
```

In `_execute_trial`, replace:
- `self._should_respond_correctly("stop")` → `self._should_respond_correctly(paradigm.stop_condition)`
- `self._sampler.sample_rt_with_fallback("stop_failure")` → `self._sampler.sample_rt_with_fallback(paradigm.stop_failure_rt_key)`
- `max_response_ms * 0.85` → `max_response_ms * paradigm.stop_rt_cap_fraction`

**Step 4: Run tests**

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/
git commit -m "refactor: config-driven stop signal paradigm parameters"
```

---

### Task 9: Update cached configs with runtime sections

**Files:**
- Modify: `cache/expfactory/2/config.json`
- Modify: `cache/expfactory/9/config.json`
- Modify: `cache/psytoolkit/stopsignal/config.json`
- Modify: `cache/psytoolkit/taskswitching_cued/config.json`

Add `runtime` sections to all cached configs encoding the platform-specific behavior that was previously hardcoded.

**Step 1: Add runtime to PsyToolkit stopsignal config**

```json
"runtime": {
  "phase_detection": {
    "method": "js_eval",
    "complete": "(typeof psy_experiment_done !== 'undefined' && psy_experiment_done) || (typeof current_task !== 'undefined' && current_task === '' && general_trial_counter > 0)",
    "loading": "document.body.textContent.includes('Click to start')",
    "test": "typeof general_trial_counter !== 'undefined'"
  },
  "timing": {
    "poll_interval_ms": 20,
    "max_no_stimulus_polls": 2000,
    "completion_wait_ms": 5000,
    "rt_cap_fraction": 0.90
  },
  "advance_behavior": {
    "pre_keypress_js": "psy_expect_keyboard()",
    "advance_keys": [" "],
    "exit_pager_key": "q",
    "advance_interval_polls": 100,
    "feedback_selectors": [],
    "feedback_fallback_keys": [" ", "Enter"]
  },
  "paradigm": {
    "type": "stop_signal",
    "stop_condition": "stop",
    "stop_failure_rt_key": "stop_failure",
    "stop_rt_cap_fraction": 0.85
  }
}
```

**Step 2: Add runtime to PsyToolkit taskswitching_cued config**

Same `phase_detection`, `timing`, and `advance_behavior` as stopsignal (PsyToolkit defaults). Paradigm type = "simple".

**Step 3: Add runtime to ExpFactory configs**

```json
"runtime": {
  "phase_detection": {
    "method": "dom_query",
    "complete": "document.querySelector('#completion_msg') !== null || ['finished','complete','done','thank you'].some(w => document.body.textContent.toLowerCase().includes(w))",
    "loading": "document.querySelector('button#jspsych-fullscreen-btn') !== null",
    "instructions": "document.querySelector('button#jspsych-instructions-next') !== null",
    "attention_check": "document.querySelector('#jspsych-attention-check-rdoc-stimulus') !== null"
  },
  "timing": {
    "max_no_stimulus_polls": 500,
    "completion_wait_ms": 35000
  },
  "advance_behavior": {
    "feedback_selectors": ["button", "#jspsych-instructions-next", ".jspsych-btn"],
    "feedback_fallback_keys": ["Enter"]
  },
  "paradigm": {
    "type": "simple"
  }
}
```

**Step 4: Run smoke tests to verify configs still work**

Run each smoke test briefly (first few trials) to confirm behavior is unchanged.

**Step 5: Commit**

```bash
git add cache/
git commit -m "feat: add runtime config sections to all cached configs"
```

---

### Task 10: Update analyzer prompt to generate runtime config

**Files:**
- Modify: `src/experiment_bot/core/analyzer.py`
- Modify: prompt template files if they exist

Update Claude's analysis prompt to include `runtime` section generation. The analyzer should instruct Claude to produce phase_detection JS expressions, timing parameters, advance behavior, and paradigm type appropriate for the specific task and platform.

**Step 1: Read current analyzer prompt**

**Step 2: Add runtime section to the expected output schema in the prompt**

Add to the prompt template:
```
"runtime": {
  "phase_detection": { JS expressions for detecting each task phase },
  "timing": { timing parameters specific to this task },
  "advance_behavior": { how to advance between blocks/instructions },
  "paradigm": { "type": "simple" | "stop_signal" | "go_nogo", ... }
}
```

**Step 3: Update analyzer to parse and validate runtime section**

**Step 4: Test with a manual analysis run**

**Step 5: Commit**

```bash
git add src/experiment_bot/core/analyzer.py
git commit -m "feat: analyzer generates runtime config section"
```

---

### Task 11: Clean up dead code and add integration test

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `src/experiment_bot/platforms/expfactory.py`
- Modify: `src/experiment_bot/platforms/psytoolkit.py`
- Test: `tests/test_integration.py`

Remove:
- `_psytoolkit_reenable_keyboard` method
- Legacy key mapping code (keep `_resolve_key_mapping_legacy` but mark as deprecated)
- Any remaining hardcoded selectors that are now in config

Add an integration test that verifies a config with `runtime` section constructs a working executor without any platform-specific code paths.

**Step 1: Write the integration test**

```python
def test_executor_works_with_runtime_config_only():
    """Executor works purely from config, no platform-specific code needed."""
    config_dict = {
        "task": {"name": "Test Task", "platform": "generic", "constructs": [], "reference_literature": []},
        "stimuli": [
            {"id": "s1", "description": "test", "detection": {"method": "js_eval", "selector": "true"},
             "response": {"key": "a", "condition": "go"}}
        ],
        "response_distributions": {
            "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 400, "sigma": 50, "tau": 60}}
        },
        "performance": {"go_accuracy": 0.95, "stop_accuracy": 0.5, "omission_rate": 0.02, "practice_accuracy": 0.9},
        "navigation": {"phases": []},
        "runtime": {
            "timing": {"max_no_stimulus_polls": 100, "completion_wait_ms": 1000},
            "advance_behavior": {"advance_keys": [" "], "feedback_selectors": ["button"]},
            "paradigm": {"type": "simple"}
        }
    }
    config = TaskConfig.from_dict(config_dict)
    executor = TaskExecutor(config, platform_name="generic")
    assert executor._config.runtime.timing.max_no_stimulus_polls == 100
```

**Step 2: Run test**

**Step 3: Remove dead code**

**Step 4: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ tests/
git commit -m "refactor: remove dead platform code, add runtime config integration test"
```

---

### Task 12: Run full smoke tests to verify no regressions

**Files:** None modified — verification only

**Step 1: Run unit tests**
```bash
uv run python -m pytest tests/ -v
```
Expected: ALL PASS

**Step 2: Run ExpFactory stop signal smoke test**
```bash
uv run experiment-bot expfactory --task 9 -v
```
Expected: Completes with ~66 trials

**Step 3: Run PsyToolkit stopsignal smoke test**
```bash
uv run experiment-bot psytoolkit --task stopsignal -v
```
Expected: Completes with ~66 trials, race model passes

**Step 4: Run PsyToolkit taskswitching_cued smoke test**
```bash
uv run experiment-bot psytoolkit --task taskswitching_cued -v
```
Expected: Completes with ~60-100 trials

**Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "test: verify all smoke tests pass after generalizability refactor"
```

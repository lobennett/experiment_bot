# SP2 — Behavioral Fidelity Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bot statistically indistinguishable from published canonical norms on RT distribution, sequential effects, and population-level individual differences across the 4 development paradigms — via a generalized effect-type registry, a new `congruency_sequence` (CSE) effect, a Reasoner-extracted norms artifact per paradigm class, and a validation oracle that gates on published ranges (not on any single dataset).

**Architecture:** Three new layers added on top of SP1.5: (1) `effects/registry.py` — central registry of universal + paradigm-specific effect types, each with a handler and validation metric; (2) `reasoner/norms_extractor.py` + `experiment-bot-extract-norms` CLI — produces `norms/{paradigm_class}.json` from canonical meta-analyses/reviews; (3) `validation/oracle.py` + `experiment-bot-validate` CLI — runs metrics on bot output and gates pass/fail against the norms file. Reasoner gains paradigm-class tagging in Stage 1 and registry-filtered effect enumeration in Stage 2. Existing 6 effects re-expressed as registry entries (no behavioral change). Eisenberg 2019 data shown side-by-side as descriptive context only, never gating.

**Tech Stack:** Existing — Python 3.12, uv, pytest, hypothesis, scipy.stats. New: `scipy.stats.kstest` already available via existing scipy install.

**Spec:** `docs/superpowers/specs/2026-05-04-sp2-behavioral-fidelity-design.md`

---

## File structure

**Created (new):**

```
src/experiment_bot/effects/__init__.py
src/experiment_bot/effects/registry.py            # EffectType + EFFECT_REGISTRY + paradigm_classes constants
src/experiment_bot/effects/handlers.py            # apply_autocorrelation, apply_fatigue, ..., apply_cse (NEW)
src/experiment_bot/effects/validation_metrics.py  # cse_magnitude, ssrt_integration, lag1_autocorr, etc.

src/experiment_bot/reasoner/norms_extractor.py    # extract_norms(paradigm_class, llm_client) -> dict
src/experiment_bot/reasoner/norms_cli.py          # `experiment-bot-extract-norms` Click entry point
src/experiment_bot/reasoner/prompts/norms_extractor.md
src/experiment_bot/reasoner/prompts/stage1_paradigm_class_addendum.md  # appended to Stage 1 prompt

src/experiment_bot/validation/__init__.py
src/experiment_bot/validation/oracle.py           # validate_session_set, ValidationReport
src/experiment_bot/validation/cli.py              # `experiment-bot-validate` Click entry point
src/experiment_bot/validation/eisenberg.py        # optional descriptive comparison loader

norms/conflict.json                               # generated, committed
norms/interrupt.json                              # generated, committed

tests/test_effect_registry.py
tests/test_effect_handler_cse.py                  # CSE-specific
tests/test_effect_handlers_existing.py            # regression test: existing 6 effects via registry produce identical output
tests/test_validation_oracle.py
tests/test_norms_extractor.py
tests/test_norms_schema.py                        # validates norms/*.json files
tests/test_validation_cli.py
```

**Modified:**

```
src/experiment_bot/core/distributions.py          # ResponseSampler iterates registry instead of hardcoded effects
src/experiment_bot/core/config.py                 # add `paradigm_classes: list[str]` to TaskMetadata
src/experiment_bot/reasoner/stage1_structural.py  # prompt asks Claude to set paradigm_classes
src/experiment_bot/reasoner/stage2_behavioral.py  # filter effect catalog by paradigm_classes; emit CSE example
src/experiment_bot/prompts/system.md              # new "Sequential and temporal effects" section + paradigm-class concept
pyproject.toml                                    # add experiment-bot-extract-norms, experiment-bot-validate scripts
README.md                                         # one-paragraph addition: validation workflow
```

**Deleted:** none.

---

## Phase A — Effect registry (refactor; no behavioral change)

Goal: re-express the existing 6 temporal effects as registry entries. Test that bot output is byte-identical (modulo allowed nondeterminism) before/after the refactor. End-of-phase: `321 + ~16 new tests`.

### Task A1: EffectType + registry skeleton

**Files:**
- Create: `src/experiment_bot/effects/__init__.py` (empty)
- Create: `src/experiment_bot/effects/registry.py`
- Test: `tests/test_effect_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_effect_registry.py
import pytest
from experiment_bot.effects.registry import (
    EffectType, ALL_PARADIGM_CLASSES, EFFECT_REGISTRY,
)


def test_effect_type_dataclass_round_trip():
    et = EffectType(
        name="example",
        params={"x": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=lambda *a, **kw: 0.0,
        validation_metric=None,
    )
    assert et.name == "example"
    assert et.params == {"x": float}


def test_registry_contains_all_existing_effects():
    expected = {
        "autocorrelation",
        "fatigue_drift",
        "post_error_slowing",
        "condition_repetition",
        "pink_noise",
        "post_interrupt_slowing",
    }
    assert set(EFFECT_REGISTRY.keys()) >= expected


def test_existing_effects_have_universal_applicability():
    for name in ("autocorrelation", "fatigue_drift", "post_error_slowing",
                 "condition_repetition", "pink_noise", "post_interrupt_slowing"):
        assert EFFECT_REGISTRY[name].applicable_paradigms == ALL_PARADIGM_CLASSES


def test_eligible_effects_for_paradigm_class():
    from experiment_bot.effects.registry import eligible_effects
    # Universal effects are always eligible
    eligible = eligible_effects(["conflict"])
    assert "autocorrelation" in eligible
    assert "post_error_slowing" in eligible


def test_registry_lookup_unknown_effect_raises():
    from experiment_bot.effects.registry import lookup_effect
    with pytest.raises(KeyError, match="unknown_effect"):
        lookup_effect("unknown_effect")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest tests/test_effect_registry.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement skeleton (handlers stay None for now; A2 will fill them)**

```python
# src/experiment_bot/effects/registry.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any


# A sentinel meaning "applicable to any paradigm class"
ALL_PARADIGM_CLASSES = frozenset({"__ALL__"})


@dataclass
class EffectType:
    name: str
    params: dict[str, type]
    applicable_paradigms: frozenset[str]
    handler: Callable[..., float] | None        # applied at trial-time; A2 fills in
    validation_metric: Callable[..., dict] | None  # called by oracle; A4 fills in


# Skeleton: existing 6 effects, handler/validator to be filled by later tasks
EFFECT_REGISTRY: dict[str, EffectType] = {
    "autocorrelation": EffectType(
        name="autocorrelation",
        params={"phi": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "fatigue_drift": EffectType(
        name="fatigue_drift",
        params={"drift_per_trial_ms": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "post_error_slowing": EffectType(
        name="post_error_slowing",
        params={"slowing_ms_min": float, "slowing_ms_max": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "condition_repetition": EffectType(
        name="condition_repetition",
        params={"facilitation_ms": float, "cost_ms": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "pink_noise": EffectType(
        name="pink_noise",
        params={"sd_ms": float, "hurst": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
    "post_interrupt_slowing": EffectType(
        name="post_interrupt_slowing",
        params={"slowing_ms_min": float, "slowing_ms_max": float},
        applicable_paradigms=ALL_PARADIGM_CLASSES,
        handler=None,
        validation_metric=None,
    ),
}


def lookup_effect(name: str) -> EffectType:
    if name not in EFFECT_REGISTRY:
        raise KeyError(f"unknown_effect: {name!r}")
    return EFFECT_REGISTRY[name]


def eligible_effects(paradigm_classes: list[str]) -> set[str]:
    """Return effects whose applicable_paradigms intersect the task's classes.

    Universal effects (applicable_paradigms == ALL_PARADIGM_CLASSES) always eligible.
    """
    out = set()
    for name, et in EFFECT_REGISTRY.items():
        if et.applicable_paradigms == ALL_PARADIGM_CLASSES:
            out.add(name)
        elif set(paradigm_classes) & et.applicable_paradigms:
            out.add(name)
    return out
```

- [ ] **Step 4: Run, expect 5/5 PASS**

- [ ] **Step 5: Run full suite, expect ≥ 326 passing (321 + 5)**

Run: `uv run pytest tests/ -q`

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/effects/__init__.py src/experiment_bot/effects/registry.py tests/test_effect_registry.py
git commit -m "feat(effects): registry skeleton with 6 existing effects + paradigm filtering

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A2: Migrate handlers from `distributions.py` into the registry

**Files:**
- Create: `src/experiment_bot/effects/handlers.py`
- Modify: `src/experiment_bot/effects/registry.py` (wire handlers into EFFECT_REGISTRY)
- Modify: `src/experiment_bot/core/distributions.py` (ResponseSampler iterates registry)
- Test: `tests/test_effect_handlers_existing.py`

- [ ] **Step 1: Write a regression test that bot output is identical before/after the refactor**

```python
# tests/test_effect_handlers_existing.py
import json
from pathlib import Path
import numpy as np
from experiment_bot.taskcard.types import TaskCard
from experiment_bot.core.distributions import ResponseSampler


def _make_taskcard_with_effect(effect_name: str, params: dict, distribution_value: dict) -> TaskCard:
    """Build a minimal TaskCard with one ex-Gaussian distribution + one effect enabled."""
    return TaskCard.from_dict({
        "schema_version": "2.0",
        "produced_by": {
            "model": "x", "prompt_sha256": "", "scraper_version": "1.0",
            "source_sha256": "", "timestamp": "", "taskcard_sha256": "",
        },
        "task": {"name": "x", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "navigation": {"phases": []},
        "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {
            "default": {
                "distribution": "ex_gaussian",
                "value": distribution_value,
                "rationale": "",
            }
        },
        "temporal_effects": {
            effect_name: {
                "value": {"enabled": True, **params},
                "rationale": "",
            }
        },
        "between_subject_jitter": {},
        "reasoning_chain": [],
        "pilot_validation": {},
    })


def test_autocorrelation_handler_via_registry_matches_legacy_output():
    """ResponseSampler with registry handlers produces same RT sequence as before."""
    tc = _make_taskcard_with_effect(
        "autocorrelation",
        {"phi": 0.3},
        {"mu": 500, "sigma": 50, "tau": 80},
    )
    sampler = ResponseSampler(
        distributions=tc.response_distributions,
        temporal_effects=tc.temporal_effects,
        seed=42,
    )
    # Sample 10 RTs deterministically
    seq = [sampler.sample_rt("default") for _ in range(10)]
    # Each RT must be finite, > floor (150), reasonably bounded
    for rt in seq:
        assert 150 < rt < 5000


def test_post_error_slowing_handler_via_registry():
    tc = _make_taskcard_with_effect(
        "post_error_slowing",
        {"slowing_ms_min": 30, "slowing_ms_max": 80},
        {"mu": 500, "sigma": 50, "tau": 80},
    )
    sampler = ResponseSampler(
        distributions=tc.response_distributions,
        temporal_effects=tc.temporal_effects,
        seed=42,
    )
    # First trial: no error preceded; PES should not apply
    rt0 = sampler.sample_rt("default")
    # Mark previous trial as error and sample again — PES should add 30-80ms
    sampler.mark_previous_error(True)
    rt1 = sampler.sample_rt("default")
    # Can't assert exact magnitude due to ex-Gaussian noise; just assert finite
    assert 150 < rt1 < 5000
```

- [ ] **Step 2: Run, expect partial (some pass with current implementation, some fail because mark_previous_error doesn't exist yet)**

That's fine — we're going to build to make these green. If `mark_previous_error` doesn't exist on `ResponseSampler` today, add it as part of Step 3.

Read existing `src/experiment_bot/core/distributions.py` to see how the current 6 effects are applied. Note the trial-state variables (`_prev_condition`, `_prev_rt`, `_trial_index`, `_pink_buffer`) and the order of operations.

- [ ] **Step 3: Extract the 6 handlers into `effects/handlers.py`**

```python
# src/experiment_bot/effects/handlers.py
"""Trial-time RT modulation handlers for each effect type.

Each handler signature: handler(state, params) -> float (delta_rt_ms).
`state` is a SamplerState dataclass carrying mu/sigma/tau, prev_rt, prev_condition,
trial_index, prev_error, prev_interrupt_detected, condition. Handlers return the
RT modulation in ms (added to the raw ex-Gaussian sample).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SamplerState:
    mu: float
    sigma: float
    tau: float
    prev_rt: float | None
    prev_condition: str | None
    trial_index: int
    prev_error: bool
    prev_interrupt_detected: bool
    condition: str
    # Pink noise buffer + index, lazy-initialized by sampler
    pink_buffer: object | None = None  # numpy array
    pink_idx: int = 0


def apply_autocorrelation(state: SamplerState, params: dict) -> float:
    if state.prev_rt is None:
        return 0.0
    mean_rt = state.mu + state.tau
    deviation = state.prev_rt - mean_rt
    return params["phi"] * deviation


def apply_fatigue_drift(state: SamplerState, params: dict) -> float:
    return state.trial_index * params["drift_per_trial_ms"]


def apply_post_error_slowing(state: SamplerState, params: dict) -> float:
    import numpy as np
    if not state.prev_error or state.prev_interrupt_detected:
        return 0.0
    return float(np.random.uniform(params["slowing_ms_min"], params["slowing_ms_max"]))


def apply_condition_repetition(state: SamplerState, params: dict) -> float:
    if state.prev_condition is None:
        return 0.0
    if state.condition == state.prev_condition:
        return -params["facilitation_ms"]
    return params["cost_ms"]


def apply_pink_noise(state: SamplerState, params: dict) -> float:
    if state.pink_buffer is None:
        return 0.0
    n = len(state.pink_buffer)
    return float(state.pink_buffer[state.trial_index % n] * params["sd_ms"])


def apply_post_interrupt_slowing(state: SamplerState, params: dict) -> float:
    import numpy as np
    if not state.prev_interrupt_detected:
        return 0.0
    return float(np.random.uniform(params["slowing_ms_min"], params["slowing_ms_max"]))
```

- [ ] **Step 4: Wire handlers into the registry**

In `src/experiment_bot/effects/registry.py`, add at the end:

```python
from experiment_bot.effects import handlers as h

EFFECT_REGISTRY["autocorrelation"].handler = h.apply_autocorrelation
EFFECT_REGISTRY["fatigue_drift"].handler = h.apply_fatigue_drift
EFFECT_REGISTRY["post_error_slowing"].handler = h.apply_post_error_slowing
EFFECT_REGISTRY["condition_repetition"].handler = h.apply_condition_repetition
EFFECT_REGISTRY["pink_noise"].handler = h.apply_pink_noise
EFFECT_REGISTRY["post_interrupt_slowing"].handler = h.apply_post_interrupt_slowing
```

(Cleaner alternative: pass handlers directly into the dataclass at construction. The minor additional indirection above keeps the registry definition readable.)

- [ ] **Step 5: Refactor ResponseSampler to iterate the registry**

In `src/experiment_bot/core/distributions.py`, change the `_apply_temporal_effects` method (or its equivalent) to iterate the registry:

```python
# In ResponseSampler.sample_rt or _apply_temporal_effects, replace the
# hardcoded effect-by-effect logic with:

from experiment_bot.effects.registry import EFFECT_REGISTRY
from experiment_bot.effects.handlers import SamplerState

# Inside the method:
state = SamplerState(
    mu=self._mu, sigma=self._sigma, tau=self._tau,
    prev_rt=self._prev_rt,
    prev_condition=self._prev_condition,
    trial_index=self._trial_index,
    prev_error=self._prev_error,
    prev_interrupt_detected=self._prev_interrupt_detected,
    condition=condition,
    pink_buffer=self._pink_buffer,
)

# Apply each enabled effect in registry order
for name, effect_type in EFFECT_REGISTRY.items():
    cfg = self._temporal_effects.get(name)
    if cfg is None or not cfg.value.get("enabled", False):
        continue
    delta = effect_type.handler(state, cfg.value)
    rt += delta
```

Preserve existing semantics for state updates (`_prev_rt`, `_trial_index`) outside the loop. Specific gotcha: `condition_repetition` checks `_prev_condition is not None` AND respects the `skip_condition_repetition` flag from interrupt handling — that flag still needs to be honored. Easiest: the executor passes `skip_condition_repetition=True` and the sampler skips the `condition_repetition` registry entry on that call.

- [ ] **Step 6: Run regression test, expect PASS**

Run: `uv run pytest tests/test_effect_handlers_existing.py -v`

- [ ] **Step 7: Run full suite, expect green (all existing temporal-effect tests still pass)**

Run: `uv run pytest tests/ -q`

If any pre-existing test breaks, the refactor changed behavior — investigate before proceeding. The whole point of this task is byte-identical output before/after.

- [ ] **Step 8: Commit**

```bash
git add src/experiment_bot/effects/handlers.py src/experiment_bot/effects/registry.py src/experiment_bot/core/distributions.py tests/test_effect_handlers_existing.py
git commit -m "refactor(effects): migrate 6 effect handlers into registry; ResponseSampler iterates

Behavior is byte-identical to pre-refactor (regression-tested). The registry is now
the single source of truth for which effects exist and what their handlers do.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A3: Add `paradigm_classes` field to TaskMetadata + Stage 1 prompt

**Files:**
- Modify: `src/experiment_bot/core/config.py` (TaskMetadata gets `paradigm_classes: list[str]`)
- Modify: `src/experiment_bot/reasoner/stage1_structural.py` (prompt asks Claude to set it)
- Modify: `src/experiment_bot/prompts/system.md` (document paradigm_classes)
- Test: extend `tests/test_taskcard_types.py` and `tests/test_reasoner_stage1.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_taskcard_types.py`:

```python
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
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Add `paradigm_classes` field to `TaskMetadata`**

In `src/experiment_bot/core/config.py`, modify `TaskMetadata`:

```python
@dataclass
class TaskMetadata:
    name: str
    constructs: list[str]
    reference_literature: list[str]
    platform: str = ""
    paradigm_classes: list[str] = field(default_factory=list)  # NEW

    @classmethod
    def from_dict(cls, d: dict) -> TaskMetadata:
        return cls(
            name=d["name"],
            constructs=d.get("constructs", []),
            reference_literature=d.get("reference_literature", []),
            platform=d.get("platform", ""),
            paradigm_classes=d.get("paradigm_classes", []),
        )
```

- [ ] **Step 4: Run, expect PASS on the 2 new tests; full suite still green**

- [ ] **Step 5: Update Stage 1 prompt**

In `src/experiment_bot/reasoner/stage1_structural.py`, the `REQUIRED_FIELDS_CHECKLIST` constant gets a new bullet:

```python
REQUIRED_FIELDS_CHECKLIST = """
## REQUIRED runtime fields you MUST populate
... existing content ...

## REQUIRED task metadata
- `task.paradigm_classes` (list of strings) — abstract classes the paradigm
  belongs to. Open-ended vocabulary; used to filter which paradigm-specific
  sequential effects apply. Examples:
  - `["conflict"]` for Stroop, Flanker, Simon, Eriksen tasks (anything with a
    manipulable congruency dimension).
  - `["interrupt"]` for stop-signal, go/no-go tasks.
  - `["task_switching"]` for cued or alternating-runs paradigms.
  - `["memory"]` for n-back, list-recall paradigms.
  - `["speeded_choice"]` is the universal class — always include it for any
    speeded-response paradigm. (Most tasks should have at least one specific
    class plus `"speeded_choice"`.)
"""
```

Add a corresponding section to `src/experiment_bot/prompts/system.md` documenting paradigm classes.

- [ ] **Step 6: Update Stage 1 test**

Append to `tests/test_reasoner_stage1.py`:

```python
@pytest.mark.asyncio
async def test_stage1_user_message_includes_paradigm_classes_section():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=COMPLETE_STROOP_RESPONSE))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    await run_stage1(client=fake, bundle=bundle)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "paradigm_classes" in user_msg
```

Update the `COMPLETE_STROOP_RESPONSE` fixture at the top of the file so that `task.paradigm_classes` is `["conflict", "speeded_choice"]`.

- [ ] **Step 7: Run, expect green**

- [ ] **Step 8: Commit**

```bash
git add src/experiment_bot/core/config.py src/experiment_bot/reasoner/stage1_structural.py src/experiment_bot/prompts/system.md tests/test_taskcard_types.py tests/test_reasoner_stage1.py
git commit -m "feat(reasoner): add task.paradigm_classes; Stage 1 prompt asks Claude to populate

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase B — CSE effect type

Goal: add the first paradigm-specific effect type (CSE), with handler, validation metric, and Stage 2 prompt awareness. End-of-phase: `~340 passing`.

### Task B1: CSE handler + registry entry

**Files:**
- Modify: `src/experiment_bot/effects/handlers.py` (add `apply_cse`)
- Modify: `src/experiment_bot/effects/registry.py` (add `congruency_sequence` entry)
- Test: `tests/test_effect_handler_cse.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_effect_handler_cse.py
import pytest
from experiment_bot.effects.handlers import SamplerState, apply_cse


def test_cse_no_modulation_when_first_trial():
    """First trial has no previous; no modulation."""
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=None, prev_condition=None,
        trial_index=0, prev_error=False, prev_interrupt_detected=False,
        condition="incongruent",
    )
    delta = apply_cse(state, {"sequence_facilitation_ms": 30, "sequence_cost_ms": 30})
    assert delta == 0.0


def test_cse_facilitation_on_iI_pair():
    """Incongruent-after-incongruent: facilitation (-) on the current incongruent RT."""
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=600, prev_condition="incongruent",
        trial_index=1, prev_error=False, prev_interrupt_detected=False,
        condition="incongruent",
    )
    delta = apply_cse(state, {"sequence_facilitation_ms": 30, "sequence_cost_ms": 30})
    assert delta == -30.0


def test_cse_cost_on_cI_pair():
    """Incongruent-after-congruent: cost (+) on the current incongruent RT."""
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=550, prev_condition="congruent",
        trial_index=1, prev_error=False, prev_interrupt_detected=False,
        condition="incongruent",
    )
    delta = apply_cse(state, {"sequence_facilitation_ms": 30, "sequence_cost_ms": 30})
    assert delta == 30.0


def test_cse_no_modulation_on_congruent_current():
    """Current trial congruent: no CSE applies (CSE is about incongruent modulation)."""
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=600, prev_condition="incongruent",
        trial_index=1, prev_error=False, prev_interrupt_detected=False,
        condition="congruent",
    )
    delta = apply_cse(state, {"sequence_facilitation_ms": 30, "sequence_cost_ms": 30})
    assert delta == 0.0


def test_cse_skipped_after_error():
    """Per spec: post-error trials skip CSE — error contamination."""
    state = SamplerState(
        mu=500, sigma=50, tau=80,
        prev_rt=600, prev_condition="incongruent",
        trial_index=1, prev_error=True, prev_interrupt_detected=False,
        condition="incongruent",
    )
    delta = apply_cse(state, {"sequence_facilitation_ms": 30, "sequence_cost_ms": 30})
    assert delta == 0.0


def test_cse_in_registry():
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    assert "congruency_sequence" in EFFECT_REGISTRY
    et = EFFECT_REGISTRY["congruency_sequence"]
    assert et.applicable_paradigms == frozenset({"conflict"})
    assert et.handler is not None
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `apply_cse`**

In `src/experiment_bot/effects/handlers.py`, append:

```python
def apply_cse(state: SamplerState, params: dict) -> float:
    """Congruency sequence effect (Gratton 1992; Egner 2007).

    The conflict effect (incongruent − congruent RT) is REDUCED following
    an incongruent trial vs following a congruent trial. We model this as:
    on an incongruent current trial:
      - if previous was incongruent: subtract `sequence_facilitation_ms`
      - if previous was congruent: add `sequence_cost_ms`
    On congruent current trials: no modulation (CSE is about incongruent
    response gating). Skipped after error trials (error contamination).
    """
    if state.prev_condition is None or state.prev_error:
        return 0.0
    if state.condition != "incongruent":
        return 0.0
    if state.prev_condition == "incongruent":
        return -params["sequence_facilitation_ms"]
    if state.prev_condition == "congruent":
        return params["sequence_cost_ms"]
    return 0.0
```

- [ ] **Step 4: Add registry entry**

In `src/experiment_bot/effects/registry.py`, after the existing entries:

```python
EFFECT_REGISTRY["congruency_sequence"] = EffectType(
    name="congruency_sequence",
    params={"sequence_facilitation_ms": float, "sequence_cost_ms": float},
    applicable_paradigms=frozenset({"conflict"}),
    handler=h.apply_cse,
    validation_metric=None,  # B3 fills in
)
```

- [ ] **Step 5: Run, expect 6/6 PASS**

- [ ] **Step 6: Run full suite, expect green**

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/effects/handlers.py src/experiment_bot/effects/registry.py tests/test_effect_handler_cse.py
git commit -m "feat(effects): add congruency_sequence (CSE) effect type and handler

Models Gratton 1992 / Egner 2007 conflict-by-conflict-history interaction:
incongruent RT is faster after incongruent (sequence_facilitation_ms) and
slower after congruent (sequence_cost_ms). Congruent current trials and
post-error trials are skipped.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B2: Stage 2 prompt enumerates registry-filtered effects

**Files:**
- Modify: `src/experiment_bot/reasoner/stage2_behavioral.py`
- Modify: `src/experiment_bot/reasoner/prompts/stage2_behavioral.md`
- Test: `tests/test_reasoner_paradigm_filter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reasoner_paradigm_filter.py
import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage2_behavioral import run_stage2
from experiment_bot.llm.protocol import LLMResponse


STAGE2_RESPONSE = """
{
  "response_distributions": {"go": {"distribution": "ex_gaussian",
    "value": {"mu": 500, "sigma": 60, "tau": 80}, "rationale": ""}},
  "performance_omission_rate": {"go": 0.005},
  "temporal_effects": {"post_error_slowing": {"value": {"enabled": true,
    "slowing_ms_min": 30, "slowing_ms_max": 80}, "rationale": ""}},
  "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60}, "rationale": ""}
}
"""


@pytest.mark.asyncio
async def test_stage2_prompt_includes_cse_for_conflict_paradigm():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stroop", "paradigm_classes": ["conflict", "speeded_choice"]}}
    await run_stage2(client=fake, partial=partial)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "congruency_sequence" in user_msg
    assert "conflict" in user_msg


@pytest.mark.asyncio
async def test_stage2_prompt_excludes_cse_for_interrupt_paradigm():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stop Signal", "paradigm_classes": ["interrupt", "speeded_choice"]}}
    await run_stage2(client=fake, partial=partial)
    user_msg = fake.complete.await_args.kwargs["user"]
    assert "congruency_sequence" not in user_msg
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Update Stage 2 prompt and user-message builder**

In `src/experiment_bot/reasoner/stage2_behavioral.py`, change the user message builder:

```python
async def run_stage2(client: LLMClient, partial: dict) -> tuple[dict, ReasoningStep]:
    from experiment_bot.effects.registry import eligible_effects, EFFECT_REGISTRY

    system = (PROMPTS_DIR / "stage2_behavioral.md").read_text()

    paradigm_classes = partial.get("task", {}).get("paradigm_classes", []) or ["speeded_choice"]
    eligible = eligible_effects(paradigm_classes)
    eligible_descriptions = []
    for name in sorted(eligible):
        et = EFFECT_REGISTRY[name]
        param_list = ", ".join(f"{k}: {v.__name__}" for k, v in et.params.items())
        eligible_descriptions.append(f"- `{name}` (params: {{{param_list}}})")

    user = (
        "## Stage 1 output (structural)\n"
        + json.dumps(partial, indent=2)
        + "\n\n## Effects applicable to this paradigm\n"
        + f"paradigm_classes: {paradigm_classes}\n"
        + "Eligible effects (universal + paradigm-specific):\n"
        + "\n".join(eligible_descriptions)
        + "\n\nProduce the behavioral parameters as instructed in the system "
        "prompt. Enable only effects empirically documented for this paradigm."
    )
    resp = await client.complete(system=system, user=user, output_format="json")
    # ... rest unchanged
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Run full suite, expect green**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage2_behavioral.py tests/test_reasoner_paradigm_filter.py
git commit -m "feat(reasoner): Stage 2 prompt enumerates only registry-filtered effects per paradigm

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B3: CSE validation metric (callable from oracle)

**Files:**
- Create: `src/experiment_bot/effects/validation_metrics.py`
- Modify: `src/experiment_bot/effects/registry.py` (wire CSE validation_metric)
- Test: `tests/test_effect_handler_cse.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/test_effect_handler_cse.py`:

```python
def test_cse_magnitude_metric_computes_canonical_difference():
    """cse_magnitude(trials) returns mean RT(iI) - mean RT(cI)."""
    from experiment_bot.effects.validation_metrics import cse_magnitude
    # Synthetic trial sequence: alternating with known conditions
    trials = [
        {"condition": "congruent",   "rt": 500},
        {"condition": "incongruent", "rt": 580},  # cI: high RT
        {"condition": "incongruent", "rt": 540},  # iI: lower (CSE)
        {"condition": "congruent",   "rt": 490},
        {"condition": "incongruent", "rt": 590},  # cI
        {"condition": "incongruent", "rt": 530},  # iI
    ]
    cse = cse_magnitude(trials)
    # iI mean = (540+530)/2 = 535
    # cI mean = (580+590)/2 = 585
    # CSE = iI - cI = -50 (i.e., 50ms facilitation)
    assert cse == -50.0
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `cse_magnitude`**

```python
# src/experiment_bot/effects/validation_metrics.py
"""Validation-time metric computations.

Each metric: takes a list of bot or human trials (dicts with condition + rt
keys at minimum) and returns a float (the metric value). Oracle compares
this float to the published-norms range to decide pass/fail.
"""
from __future__ import annotations
from statistics import mean


def cse_magnitude(trials: list[dict]) -> float:
    """Mean RT on incongruent-after-incongruent minus mean RT on incongruent-after-congruent.

    Negative values mean facilitation (the CSE direction). The published
    canonical range from Egner 2007 is roughly [-55, -15] ms (i.e., 15-55ms
    facilitation magnitude, expressed as a negative difference).
    """
    iI_rts: list[float] = []
    cI_rts: list[float] = []
    for i, trial in enumerate(trials):
        if i == 0:
            continue
        prev = trials[i - 1]
        if trial["condition"] != "incongruent":
            continue
        if prev.get("condition") == "incongruent":
            iI_rts.append(trial["rt"])
        elif prev.get("condition") == "congruent":
            cI_rts.append(trial["rt"])
    if not iI_rts or not cI_rts:
        return float("nan")
    return mean(iI_rts) - mean(cI_rts)
```

- [ ] **Step 4: Wire into registry**

In `src/experiment_bot/effects/registry.py`, update the CSE entry:

```python
from experiment_bot.effects.validation_metrics import cse_magnitude
EFFECT_REGISTRY["congruency_sequence"].validation_metric = cse_magnitude
```

- [ ] **Step 5: Run, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/effects/validation_metrics.py src/experiment_bot/effects/registry.py tests/test_effect_handler_cse.py
git commit -m "feat(effects): cse_magnitude validation metric; wire into CSE registry entry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — Norms extractor

Goal: a Reasoner sub-module that produces `norms/{paradigm_class}.json` from canonical reviews/meta-analyses, with circularity protection. End-of-phase: `~350 passing`.

### Task C1: Norms file schema + validator

**Files:**
- Create: `tests/test_norms_schema.py`
- (Schema lives implicitly as a `dict` validation function)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_norms_schema.py
import pytest
from experiment_bot.reasoner.norms_extractor import validate_norms_dict, NormsSchemaError


def test_validate_norms_dict_passes_on_minimal_valid():
    payload = {
        "paradigm_class": "conflict",
        "produced_by": {
            "model": "claude-opus-4-7",
            "extraction_prompt_sha256": "x",
            "timestamp": "2026-05-04T00:00:00Z",
        },
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580],
                "sigma_range": [40, 90],
                "tau_range": [50, 130],
                "citations": [
                    {"doi": "10.0/x", "authors": "Whelan", "year": 2008,
                     "title": "x", "table_or_figure": "T1", "page": 1,
                     "quote": "...", "confidence": "high"}
                ]
            }
        }
    }
    validate_norms_dict(payload)  # no exception


def test_validate_norms_dict_fails_on_missing_paradigm_class():
    payload = {"produced_by": {}, "metrics": {}}
    with pytest.raises(NormsSchemaError, match="paradigm_class"):
        validate_norms_dict(payload)


def test_validate_norms_dict_fails_on_metric_with_neither_range_nor_null():
    payload = {
        "paradigm_class": "x",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"mu_range": [None, None], "citations": []}
        }
    }
    with pytest.raises(NormsSchemaError, match="range"):
        validate_norms_dict(payload)


def test_validate_norms_dict_accepts_explicit_no_canonical_range():
    payload = {
        "paradigm_class": "x",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "obscure_metric": {"range": None, "no_canonical_range_reason": "no meta-analysis"}
        }
    }
    validate_norms_dict(payload)  # no exception — null range with explicit reason is permitted
```

- [ ] **Step 2: Run, expect FAIL (module doesn't exist)**

- [ ] **Step 3: Stub the module + implement validator**

```python
# src/experiment_bot/reasoner/norms_extractor.py
from __future__ import annotations


class NormsSchemaError(ValueError):
    """Raised when a norms dict doesn't conform to the expected schema."""


def validate_norms_dict(payload: dict) -> None:
    """Validate the shape of a norms file dict; raise NormsSchemaError on failure."""
    if "paradigm_class" not in payload or not payload["paradigm_class"]:
        raise NormsSchemaError("paradigm_class is required and must be non-empty")

    pb = payload.get("produced_by", {})
    for key in ("model", "extraction_prompt_sha256", "timestamp"):
        if key not in pb:
            raise NormsSchemaError(f"produced_by.{key} is required")

    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise NormsSchemaError("metrics must be a dict")

    for metric_name, metric_body in metrics.items():
        # Either has a non-null range/range_ms/{mu,sigma,tau}_range OR
        # has range=None + no_canonical_range_reason explanation.
        has_concrete_range = any(
            (k in metric_body and metric_body[k] is not None
             and (not isinstance(metric_body[k], list)
                  or all(v is not None for v in metric_body[k])))
            for k in ("range", "range_ms", "mu_range", "sigma_range", "tau_range",
                      "mu_sd_range", "sigma_sd_range", "tau_sd_range")
        )
        explicit_null = (
            metric_body.get("range") is None
            and "no_canonical_range_reason" in metric_body
            and metric_body["no_canonical_range_reason"]
        )
        if not (has_concrete_range or explicit_null):
            raise NormsSchemaError(
                f"metric {metric_name!r}: must have either a non-null range "
                f"(range/range_ms/mu_range/etc.) or null range with "
                f"no_canonical_range_reason"
            )


# extract_norms() comes in C2; stubbed for import
async def extract_norms(paradigm_class: str, llm_client) -> dict:
    raise NotImplementedError("Implemented in Task C2")
```

- [ ] **Step 4: Run, expect 4/4 PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/norms_extractor.py tests/test_norms_schema.py
git commit -m "feat(norms): NormsSchemaError + validate_norms_dict

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C2: `extract_norms()` LLM call + circularity-prevention prompt

**Files:**
- Modify: `src/experiment_bot/reasoner/norms_extractor.py`
- Create: `src/experiment_bot/reasoner/prompts/norms_extractor.md`
- Test: `tests/test_norms_extractor.py`

- [ ] **Step 1: Write the prompt**

```markdown
<!-- src/experiment_bot/reasoner/prompts/norms_extractor.md -->
You are extracting canonical published norms for a behavioral paradigm class
to be used as validation gates against an automated bot's behavior.

CRITICAL: Cite ONLY meta-analyses and review articles, NOT primary studies.
The bot's parameter-setting Reasoner cites primary studies; this norms file
must come from a different evidentiary tier to avoid circularity (the bot
matching norms because both came from the same papers). If a metric has no
meta-analysis or review, mark its range as null with a
no_canonical_range_reason.

Examples of acceptable sources:
- Egner 2007 Trends in Cognitive Sciences (review of CSE)
- Verbruggen et al. 2019 (consensus on SSRT methods)
- Whelan 2008 (review of ex-Gaussian RT analysis)

Output JSON conforming to this schema:
{
  "paradigm_class": "<class name>",
  "metrics": {
    "<metric_name>": {
      "<range_key>": [low, high],          // e.g. "mu_range", "range_ms"
      "citations": [
        {"doi": "...", "authors": "...", "year": ..., "title": "...",
         "table_or_figure": "...", "page": ..., "quote": "...",
         "confidence": "high|medium|low"}
      ]
    }
  }
}

Required metrics for class "conflict":
- rt_distribution (mu_range, sigma_range, tau_range)
- between_subject_sd (mu_sd_range, sigma_sd_range, tau_sd_range)
- lag1_autocorr (range as [low, high] correlation)
- post_error_slowing (range_ms)
- cse_magnitude (range_ms; can be NEGATIVE — facilitation is conventionally negative)

Required metrics for class "interrupt":
- rt_distribution
- between_subject_sd
- lag1_autocorr
- post_error_slowing
- ssrt (range_ms; integration method)

If unsure about a value, prefer marking range null with reason rather than
guessing.
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_norms_extractor.py
import json
import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.norms_extractor import extract_norms, NormsSchemaError
from experiment_bot.llm.protocol import LLMResponse


CONFLICT_NORMS_RESPONSE = """
{
  "paradigm_class": "conflict",
  "metrics": {
    "rt_distribution": {
      "mu_range": [430, 580],
      "sigma_range": [40, 90],
      "tau_range": [50, 130],
      "citations": [{"doi": "10.0000/whelan", "authors": "Whelan", "year": 2008,
                      "title": "x", "table_or_figure": "T1", "page": 1,
                      "quote": "...", "confidence": "high"}]
    },
    "cse_magnitude": {
      "range_ms": [-55, -15],
      "citations": [{"doi": "10.1016/j.tics.2007.08.005", "authors": "Egner", "year": 2007,
                      "title": "x", "table_or_figure": "T1", "page": 1,
                      "quote": "...", "confidence": "high"}]
    }
  }
}
"""


@pytest.mark.asyncio
async def test_extract_norms_returns_validated_dict():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=CONFLICT_NORMS_RESPONSE))
    out = await extract_norms("conflict", llm_client=fake)
    assert out["paradigm_class"] == "conflict"
    assert "rt_distribution" in out["metrics"]
    assert "produced_by" in out  # extractor adds this envelope
    fake.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_norms_prompt_warns_against_primary_studies():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=CONFLICT_NORMS_RESPONSE))
    await extract_norms("conflict", llm_client=fake)
    sent = fake.complete.await_args.kwargs["system"] + "\n" + fake.complete.await_args.kwargs["user"]
    assert "meta-analyses" in sent.lower() or "review" in sent.lower()
    assert "circular" in sent.lower()  # explicit warning


@pytest.mark.asyncio
async def test_extract_norms_raises_on_invalid_llm_output():
    bad_response = '{"paradigm_class": "conflict", "metrics": {"rt_distribution": {"citations": []}}}'
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=bad_response))
    with pytest.raises(NormsSchemaError):
        await extract_norms("conflict", llm_client=fake)
```

- [ ] **Step 3: Run, expect FAIL**

- [ ] **Step 4: Implement `extract_norms`**

Replace the stub in `src/experiment_bot/reasoner/norms_extractor.py`:

```python
from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from experiment_bot.reasoner.stage1_structural import _extract_json
from experiment_bot.llm.protocol import LLMClient

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class NormsSchemaError(ValueError):
    pass


def validate_norms_dict(payload: dict) -> None:
    # ... unchanged from C1 ...
    # (already implemented in Task C1; keep it)


async def extract_norms(paradigm_class: str, llm_client: LLMClient) -> dict:
    """Run the norms extractor LLM call for `paradigm_class`. Return validated dict."""
    system_prompt = (PROMPTS_DIR / "norms_extractor.md").read_text()
    user = f"## Paradigm class\n{paradigm_class}\n\nReturn JSON only."
    resp = await llm_client.complete(system=system_prompt, user=user, output_format="json")
    payload = json.loads(_extract_json(resp.text))
    payload.setdefault("produced_by", {
        "model": getattr(llm_client, "_model", "claude-opus-4-7"),
        "extraction_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    validate_norms_dict(payload)
    return payload
```

- [ ] **Step 5: Run, expect 3/3 PASS**

- [ ] **Step 6: Run full suite, expect green**

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/reasoner/norms_extractor.py src/experiment_bot/reasoner/prompts/norms_extractor.md tests/test_norms_extractor.py
git commit -m "feat(norms): extract_norms LLM call with meta-analysis-only circularity protection

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C3: `experiment-bot-extract-norms` CLI

**Files:**
- Create: `src/experiment_bot/reasoner/norms_cli.py`
- Modify: `pyproject.toml` (add script entry)
- Test: `tests/test_norms_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_norms_cli.py
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock
from click.testing import CliRunner
from experiment_bot.reasoner.norms_cli import main as norms_main


def test_norms_cli_writes_norms_file(tmp_path):
    runner = CliRunner()
    fake_norms = {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {"rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                          "tau_range": [50, 130],
                                          "citations": [{"doi": "10.0/x", "authors": "Whelan",
                                                         "year": 2008, "title": "x",
                                                         "table_or_figure": "T1", "page": 1,
                                                         "quote": "...", "confidence": "high"}]}}
    }
    with patch("experiment_bot.reasoner.norms_cli.build_default_client",
               return_value=object()), \
         patch("experiment_bot.reasoner.norms_cli.extract_norms",
               new=AsyncMock(return_value=fake_norms)):
        result = runner.invoke(norms_main, [
            "--paradigm-class", "conflict",
            "--norms-dir", str(tmp_path),
        ])
    assert result.exit_code == 0, result.output
    out_path = tmp_path / "conflict.json"
    assert out_path.exists()
    saved = json.loads(out_path.read_text())
    assert saved["paradigm_class"] == "conflict"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement CLI**

```python
# src/experiment_bot/reasoner/norms_cli.py
from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
import click

from experiment_bot.llm.factory import build_default_client
from experiment_bot.reasoner.norms_extractor import extract_norms


@click.command()
@click.option("--paradigm-class", required=True, help="Paradigm class (conflict, interrupt, ...)")
@click.option("--norms-dir", default="norms", help="Directory to write norms JSON to")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(paradigm_class: str, norms_dir: str, verbose: bool):
    """Extract canonical norms for a paradigm class and write `norms/{class}.json`."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(_run(paradigm_class, Path(norms_dir)))


async def _run(paradigm_class: str, norms_dir: Path):
    client = build_default_client()
    payload = await extract_norms(paradigm_class, llm_client=client)
    norms_dir.mkdir(parents=True, exist_ok=True)
    out_path = norms_dir / f"{paradigm_class}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    click.echo(f"Norms written: {out_path}")
```

- [ ] **Step 4: Add script entry to `pyproject.toml`**

In `[project.scripts]`:

```toml
experiment-bot-extract-norms = "experiment_bot.reasoner.norms_cli:main"
```

Run `uv sync` to register.

- [ ] **Step 5: Run, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/norms_cli.py tests/test_norms_cli.py pyproject.toml uv.lock 2>/dev/null
git commit -m "feat(norms): experiment-bot-extract-norms CLI

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C4: Live extract `norms/conflict.json` and `norms/interrupt.json`

**Files:** produces `norms/conflict.json`, `norms/interrupt.json` (committed).

USER-GATED: requires Max CLI auth and `claude` on PATH.

- [ ] **Step 1: User confirms Max CLI is authenticated**

```bash
which claude && claude --version
```

- [ ] **Step 2: Extract conflict norms**

```bash
uv run experiment-bot-extract-norms --paradigm-class conflict
```

Inspect the resulting `norms/conflict.json`. Required fields per the spec:
- `rt_distribution` with mu_range, sigma_range, tau_range
- `between_subject_sd` with mu_sd_range, sigma_sd_range, tau_sd_range
- `lag1_autocorr` with range
- `post_error_slowing` with range_ms
- `cse_magnitude` with range_ms (negative — facilitation)
- All metrics have ≥1 DOI-verified citation OR null range with explicit reason

If any required metric is missing or has bad data, refine the prompt and re-run. The norms-extractor prompt is at `src/experiment_bot/reasoner/prompts/norms_extractor.md`.

- [ ] **Step 3: Extract interrupt norms**

```bash
uv run experiment-bot-extract-norms --paradigm-class interrupt
```

Required: rt_distribution, between_subject_sd, lag1_autocorr, post_error_slowing, ssrt.

- [ ] **Step 4: Manual review**

Open both norms files. For each `range`, sanity-check it against your own knowledge of the literature. Reasonable ranges:
- `cse_magnitude.range_ms`: roughly [-55, -15] (15-55ms facilitation)
- `ssrt.range_ms`: roughly [180, 280] for healthy adults
- `rt_distribution.mu_range` for conflict: roughly [400, 650]

If a range is way off, refine the prompt and re-extract.

- [ ] **Step 5: Commit**

```bash
git add norms/
git commit -m "chore(norms): extract conflict and interrupt canonical norms

Reviewed against domain knowledge. CSE in [-55, -15]ms (Egner 2007 review),
SSRT in [180, 280]ms (Verbruggen 2019). Citations DOI-verified.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase D — Validation oracle

Goal: ship the oracle module + CLI + integration tests. End-of-phase: `~370 passing`.

### Task D1: Universal validation metrics

**Files:**
- Modify: `src/experiment_bot/effects/validation_metrics.py`
- Test: extend `tests/test_effect_handler_cse.py` (or split into `tests/test_validation_metrics.py`)

- [ ] **Step 1: Write tests for the additional metrics**

```python
# tests/test_validation_metrics.py
import numpy as np
from experiment_bot.effects.validation_metrics import (
    fit_ex_gaussian, lag1_autocorrelation, post_error_slowing_magnitude,
    population_sd_per_param, ssrt_integration,
)


def test_fit_ex_gaussian_recovers_known_params():
    np.random.seed(42)
    n = 5000
    mu, sigma, tau = 500, 50, 80
    samples = np.random.normal(mu, sigma, n) + np.random.exponential(tau, n)
    out = fit_ex_gaussian(samples.tolist())
    assert abs(out["mu"] - mu) < 30
    assert abs(out["sigma"] - sigma) < 20
    assert abs(out["tau"] - tau) < 30


def test_lag1_autocorrelation_known_signal():
    rts = [500, 510, 520, 530, 540, 550, 560]  # increasing → positive r
    r = lag1_autocorrelation(rts)
    assert r > 0.9


def test_post_error_slowing_magnitude_positive_when_slowed():
    trials = [
        {"rt": 500, "correct": True},
        {"rt": 600, "correct": False},  # error
        {"rt": 580, "correct": True},   # post-error: slowed
        {"rt": 510, "correct": True},
        {"rt": 520, "correct": True},
        {"rt": 530, "correct": True},
    ]
    pes = post_error_slowing_magnitude(trials)
    # Post-error mean = 580; post-correct mean = (510+520+530)/3 = 520
    # PES = 580 - 520 = 60
    assert abs(pes - 60) < 5


def test_population_sd_per_param():
    sessions = [
        {"mu": 500, "sigma": 50, "tau": 80},
        {"mu": 520, "sigma": 55, "tau": 85},
        {"mu": 480, "sigma": 45, "tau": 75},
    ]
    out = population_sd_per_param(sessions)
    assert "mu" in out and out["mu"] > 0
    assert "sigma" in out and out["sigma"] > 0
    assert "tau" in out and out["tau"] > 0


def test_ssrt_integration_recovers_target():
    # Synthetic: go RTs ~ uniform(300, 700); P(respond|stop) = 0.5; mean_SSD = 250
    # SSRT = nth_percentile(go_dist, p) - mean_SSD = 500 - 250 = 250
    go_rts = list(range(300, 700, 4))  # 100 values
    p_respond_given_stop = 0.5
    mean_ssd = 250
    ssrt = ssrt_integration(go_rts, p_respond_given_stop, mean_ssd)
    assert abs(ssrt - 250) < 50
```

- [ ] **Step 2: Run, expect FAIL (functions don't exist)**

- [ ] **Step 3: Implement the metrics**

Append to `src/experiment_bot/effects/validation_metrics.py`:

```python
import numpy as np
from scipy import optimize, stats


def fit_ex_gaussian(rt_samples: list[float]) -> dict:
    """Maximum-likelihood fit of ex-Gaussian to RT samples. Returns {mu, sigma, tau}."""
    samples = np.asarray(rt_samples, dtype=float)
    samples = samples[np.isfinite(samples)]

    def neg_log_lik(params):
        mu, sigma, tau = params
        if sigma <= 0 or tau <= 0:
            return 1e10
        # ex-Gaussian PDF: convolution of Normal(mu,sigma) with Exp(tau)
        z = (samples - mu) / sigma - sigma / tau
        log_pdf = (
            np.log(1.0 / tau)
            + (sigma * sigma / (2 * tau * tau))
            - ((samples - mu) / tau)
            + np.log(stats.norm.cdf(z) + 1e-30)
        )
        return -np.sum(log_pdf)

    x0 = [np.mean(samples) - np.std(samples), np.std(samples) * 0.7, np.std(samples) * 0.7]
    result = optimize.minimize(neg_log_lik, x0=x0, method="Nelder-Mead")
    return {"mu": float(result.x[0]), "sigma": float(result.x[1]), "tau": float(result.x[2])}


def lag1_autocorrelation(rts: list[float]) -> float:
    arr = np.asarray(rts, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return float("nan")
    return float(np.corrcoef(arr[:-1], arr[1:])[0, 1])


def post_error_slowing_magnitude(trials: list[dict]) -> float:
    """Mean RT on trials following errors minus mean RT on trials following correct."""
    post_error = []
    post_correct = []
    for i, trial in enumerate(trials):
        if i == 0:
            continue
        prev = trials[i - 1]
        if prev.get("correct") is False:
            post_error.append(trial["rt"])
        elif prev.get("correct") is True:
            post_correct.append(trial["rt"])
    if not post_error or not post_correct:
        return float("nan")
    return float(np.mean(post_error) - np.mean(post_correct))


def population_sd_per_param(sessions: list[dict]) -> dict:
    """SD across N sessions of each ex-Gaussian parameter."""
    out = {}
    for key in ("mu", "sigma", "tau"):
        vals = [s[key] for s in sessions if key in s]
        out[key] = float(np.std(vals, ddof=1)) if len(vals) > 1 else float("nan")
    return out


def ssrt_integration(go_rts: list[float], p_respond_given_stop: float, mean_ssd: float) -> float:
    """Integration-method SSRT (Verbruggen et al. 2019)."""
    arr = np.asarray(go_rts, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0 or not 0 <= p_respond_given_stop <= 1:
        return float("nan")
    nth_percentile = float(np.quantile(arr, p_respond_given_stop))
    return nth_percentile - mean_ssd
```

- [ ] **Step 4: Run, expect 5/5 PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/effects/validation_metrics.py tests/test_validation_metrics.py
git commit -m "feat(validation): add fit_ex_gaussian, lag1_autocorr, PES, pop SD, SSRT metrics

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D2: ValidationReport + oracle module

**Files:**
- Create: `src/experiment_bot/validation/__init__.py` (empty)
- Create: `src/experiment_bot/validation/oracle.py`
- Test: `tests/test_validation_oracle.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validation_oracle.py
import json
import numpy as np
import pytest
from pathlib import Path
from experiment_bot.validation.oracle import (
    validate_session_set, ValidationReport, MetricResult, PillarResult,
)


@pytest.fixture
def fake_norms_conflict():
    return {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {
                "mu_range": [430, 580], "sigma_range": [40, 90], "tau_range": [50, 130],
                "citations": [],
            },
            "between_subject_sd": {
                "mu_sd_range": [30, 80], "sigma_sd_range": [8, 20], "tau_sd_range": [15, 35],
                "citations": [],
            },
            "lag1_autocorr": {"range": [0.05, 0.25], "citations": []},
            "post_error_slowing": {"range_ms": [10, 60], "citations": []},
            "cse_magnitude": {"range_ms": [-55, -15], "citations": []},
        },
    }


def _fake_session_dir(tmp_path: Path, mu: float, sigma: float, tau: float, n_trials: int, seed: int):
    """Make a fake session directory with bot_log.json containing a known RT distribution."""
    np.random.seed(seed)
    session_dir = tmp_path / f"session_{seed}"
    session_dir.mkdir()
    log = []
    rng = np.random.default_rng(seed)
    for i in range(n_trials):
        rt = rng.normal(mu, sigma) + rng.exponential(tau)
        log.append({
            "trial": i, "stimulus_id": "x", "condition": "congruent" if i % 2 == 0 else "incongruent",
            "response_key": "z", "actual_rt_ms": rt, "intended_error": False,
            "omission": False,
        })
    (session_dir / "bot_log.json").write_text(json.dumps(log))
    return session_dir


def test_oracle_passes_when_bot_within_norms(tmp_path, fake_norms_conflict):
    """Bot with mu=500, sigma=60, tau=80 should pass conflict-class norms."""
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=s) for s in range(5)]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    assert isinstance(report, ValidationReport)
    rt_pillar = report.pillar_results["rt_distribution"]
    assert rt_pillar.pass_, f"RT distribution should pass: {rt_pillar.metrics}"


def test_oracle_fails_when_mu_out_of_range(tmp_path, fake_norms_conflict):
    """Bot with mu=300 (below the [430, 580] range) should fail."""
    sessions = [_fake_session_dir(tmp_path, 300, 60, 80, n_trials=200, seed=s) for s in range(5)]
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=fake_norms_conflict,
    )
    rt_pillar = report.pillar_results["rt_distribution"]
    assert not rt_pillar.pass_


def test_oracle_metric_with_null_range_is_descriptive_only(tmp_path):
    """Metric with range=None reports a value but doesn't gate."""
    sessions = [_fake_session_dir(tmp_path, 500, 60, 80, n_trials=200, seed=0)]
    norms = {
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                  "tau_range": [50, 130], "citations": []},
            "obscure_metric": {"range": None,
                                "no_canonical_range_reason": "no meta-analysis available",
                                "citations": []},
        },
    }
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=sessions,
        norms=norms,
    )
    # Metric appears in report but with pass_=None
    found = False
    for pillar in report.pillar_results.values():
        if "obscure_metric" in pillar.metrics:
            assert pillar.metrics["obscure_metric"].pass_ is None
            found = True
    assert found
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement oracle**

```python
# src/experiment_bot/validation/oracle.py
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from experiment_bot.effects.validation_metrics import (
    fit_ex_gaussian, lag1_autocorrelation, post_error_slowing_magnitude,
    population_sd_per_param, cse_magnitude,
)


@dataclass
class MetricResult:
    name: str
    bot_value: float | None
    published_range: tuple[float, float] | None
    pass_: bool | None       # None for descriptive-only metrics
    citations: list = field(default_factory=list)
    eisenberg_value: float | None = None


@dataclass
class PillarResult:
    pillar: str
    metrics: dict[str, MetricResult]
    pass_: bool


@dataclass
class ValidationReport:
    paradigm_class: str
    pillar_results: dict[str, PillarResult]
    overall_pass: bool
    summary: str


def _in_range(value, range_):
    if range_ is None or value is None:
        return None
    if not isinstance(range_, (list, tuple)) or len(range_) != 2:
        return None
    lo, hi = range_
    if lo is None or hi is None:
        return None
    return lo <= value <= hi


def _load_session_log(session_dir: Path) -> list[dict]:
    log_path = Path(session_dir) / "bot_log.json"
    if not log_path.exists():
        return []
    return json.loads(log_path.read_text())


def _gather_bot_rts(sessions: list[Path], condition: str | None = None) -> list[float]:
    out = []
    for s in sessions:
        for trial in _load_session_log(s):
            if trial.get("omission"):
                continue
            if condition and trial.get("condition") != condition:
                continue
            rt = trial.get("actual_rt_ms")
            if rt is not None:
                out.append(float(rt))
    return out


def validate_session_set(
    paradigm_class: str,
    session_dirs: list[Path],
    norms: dict,
) -> ValidationReport:
    """Score bot output against published norms; build a per-pillar report."""
    metrics_def = norms.get("metrics", {})

    # Pillar 1: RT distribution
    rt_pillar = PillarResult(pillar="rt_distribution", metrics={}, pass_=True)
    rt_def = metrics_def.get("rt_distribution", {})
    if rt_def:
        all_rts = _gather_bot_rts(session_dirs)
        if all_rts:
            fit = fit_ex_gaussian(all_rts)
            for param in ("mu", "sigma", "tau"):
                range_key = f"{param}_range"
                rng = rt_def.get(range_key)
                pass_ = _in_range(fit[param], rng)
                rt_pillar.metrics[param] = MetricResult(
                    name=param, bot_value=fit[param],
                    published_range=tuple(rng) if rng else None,
                    pass_=pass_, citations=rt_def.get("citations", []),
                )
                if pass_ is False:
                    rt_pillar.pass_ = False

    # Pillar 2: Sequential effects
    seq_pillar = PillarResult(pillar="sequential", metrics={}, pass_=True)
    if "lag1_autocorr" in metrics_def:
        rts = _gather_bot_rts(session_dirs)
        bot_lag1 = lag1_autocorrelation(rts)
        rng = metrics_def["lag1_autocorr"].get("range")
        pass_ = _in_range(bot_lag1, rng)
        seq_pillar.metrics["lag1_autocorr"] = MetricResult(
            name="lag1_autocorr", bot_value=bot_lag1,
            published_range=tuple(rng) if rng else None,
            pass_=pass_, citations=metrics_def["lag1_autocorr"].get("citations", []),
        )
        if pass_ is False:
            seq_pillar.pass_ = False
    if "post_error_slowing" in metrics_def:
        all_trials = []
        for s in session_dirs:
            all_trials.extend(_load_session_log(s))
        # Mark "correct" based on intended_error not being True
        for t in all_trials:
            t["correct"] = not t.get("intended_error", False) and not t.get("omission", False)
        bot_pes = post_error_slowing_magnitude(all_trials)
        rng = metrics_def["post_error_slowing"].get("range_ms")
        pass_ = _in_range(bot_pes, rng)
        seq_pillar.metrics["post_error_slowing"] = MetricResult(
            name="post_error_slowing", bot_value=bot_pes,
            published_range=tuple(rng) if rng else None,
            pass_=pass_, citations=metrics_def["post_error_slowing"].get("citations", []),
        )
        if pass_ is False:
            seq_pillar.pass_ = False
    if "cse_magnitude" in metrics_def:
        all_trials = []
        for s in session_dirs:
            for t in _load_session_log(s):
                if not t.get("omission"):
                    all_trials.append({"condition": t.get("condition"), "rt": t.get("actual_rt_ms")})
        bot_cse = cse_magnitude(all_trials)
        rng = metrics_def["cse_magnitude"].get("range_ms")
        pass_ = _in_range(bot_cse, rng)
        seq_pillar.metrics["cse_magnitude"] = MetricResult(
            name="cse_magnitude", bot_value=bot_cse,
            published_range=tuple(rng) if rng else None,
            pass_=pass_, citations=metrics_def["cse_magnitude"].get("citations", []),
        )
        if pass_ is False:
            seq_pillar.pass_ = False

    # Pillar 3: Individual differences (population SD)
    ind_pillar = PillarResult(pillar="individual_differences", metrics={}, pass_=True)
    bsd_def = metrics_def.get("between_subject_sd", {})
    if bsd_def:
        per_session = []
        for s in session_dirs:
            rts = _gather_bot_rts([s])
            if rts:
                per_session.append(fit_ex_gaussian(rts))
        if len(per_session) >= 2:
            sds = population_sd_per_param(per_session)
            for param in ("mu", "sigma", "tau"):
                range_key = f"{param}_sd_range"
                rng = bsd_def.get(range_key)
                pass_ = _in_range(sds[param], rng)
                ind_pillar.metrics[f"{param}_sd"] = MetricResult(
                    name=f"{param}_sd", bot_value=sds[param],
                    published_range=tuple(rng) if rng else None,
                    pass_=pass_, citations=bsd_def.get("citations", []),
                )
                if pass_ is False:
                    ind_pillar.pass_ = False

    # Descriptive-only metrics (range=None) — appear in some pillar but pass_=None
    for metric_name, metric_body in metrics_def.items():
        if metric_body.get("range") is None and metric_body.get("no_canonical_range_reason"):
            # Append to whichever pillar matches by name; default to sequential
            target = seq_pillar
            target.metrics[metric_name] = MetricResult(
                name=metric_name, bot_value=None, published_range=None,
                pass_=None, citations=metric_body.get("citations", []),
            )

    overall = (rt_pillar.pass_ and seq_pillar.pass_ and ind_pillar.pass_)
    return ValidationReport(
        paradigm_class=paradigm_class,
        pillar_results={
            "rt_distribution": rt_pillar,
            "sequential": seq_pillar,
            "individual_differences": ind_pillar,
        },
        overall_pass=overall,
        summary=f"paradigm={paradigm_class} pass={overall}",
    )
```

- [ ] **Step 4: Run, expect 3/3 PASS**

- [ ] **Step 5: Run full suite, expect green**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/validation/__init__.py src/experiment_bot/validation/oracle.py tests/test_validation_oracle.py
git commit -m "feat(validation): oracle scores bot sessions against published-range norms

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D3: `experiment-bot-validate` CLI + optional Eisenberg side-by-side

**Files:**
- Create: `src/experiment_bot/validation/cli.py`
- Create: `src/experiment_bot/validation/eisenberg.py`
- Modify: `pyproject.toml`
- Test: `tests/test_validation_cli.py`

- [ ] **Step 1: Implement Eisenberg loader (small)**

```python
# src/experiment_bot/validation/eisenberg.py
"""Optional descriptive-only loader for Eisenberg 2019 trial-level CSVs.

Returns ex-Gaussian fits per condition for side-by-side comparison with bot.
NEVER used to gate pass/fail — descriptive only.
"""
from __future__ import annotations
from pathlib import Path
import csv
from experiment_bot.effects.validation_metrics import fit_ex_gaussian


PARADIGM_CLASS_TO_FILE = {
    "conflict": "stroop_eisenberg.csv",
    "interrupt": "stop_signal_eisenberg.csv",
}


def load_eisenberg_summary(paradigm_class: str, base: Path) -> dict | None:
    fname = PARADIGM_CLASS_TO_FILE.get(paradigm_class)
    if fname is None:
        return None
    path = base / fname
    if not path.exists():
        return None
    rts: list[float] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rt = row.get("rt") or row.get("RT") or row.get("response_time")
            try:
                rts.append(float(rt))
            except (TypeError, ValueError):
                continue
    if not rts:
        return None
    fit = fit_ex_gaussian(rts)
    return {"mu": fit["mu"], "sigma": fit["sigma"], "tau": fit["tau"], "n_trials": len(rts)}
```

- [ ] **Step 2: Write CLI test**

```python
# tests/test_validation_cli.py
import json
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from experiment_bot.validation.cli import main as validate_main


def test_validate_cli_writes_report(tmp_path):
    runner = CliRunner()
    norms_dir = tmp_path / "norms"
    norms_dir.mkdir()
    (norms_dir / "conflict.json").write_text(json.dumps({
        "paradigm_class": "conflict",
        "produced_by": {"model": "x", "extraction_prompt_sha256": "x", "timestamp": "x"},
        "metrics": {
            "rt_distribution": {"mu_range": [430, 580], "sigma_range": [40, 90],
                                  "tau_range": [50, 130], "citations": []},
        },
    }))
    sessions_dir = tmp_path / "output" / "stroop"
    sessions_dir.mkdir(parents=True)
    sess = sessions_dir / "2026-05-04_12-00-00"
    sess.mkdir()
    (sess / "bot_log.json").write_text(json.dumps([
        {"trial": i, "actual_rt_ms": 500, "condition": "congruent",
         "intended_error": False, "omission": False} for i in range(50)
    ]))
    result = runner.invoke(validate_main, [
        "--paradigm-class", "conflict",
        "--label", "stroop",
        "--norms-dir", str(norms_dir),
        "--output-dir", str(tmp_path / "output"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert result.exit_code == 0, result.output
    reports = list((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 1
```

- [ ] **Step 3: Run, expect FAIL**

- [ ] **Step 4: Implement CLI**

```python
# src/experiment_bot/validation/cli.py
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import click

from experiment_bot.validation.oracle import validate_session_set


@click.command()
@click.option("--paradigm-class", required=True, help="Paradigm class (conflict, interrupt, ...)")
@click.option("--label", required=True, help="TaskCard label (matches output/{label}/)")
@click.option("--norms-dir", default="norms")
@click.option("--output-dir", default="output", help="Where session subfolders live")
@click.option("--reports-dir", default="validation")
@click.option("--with-eisenberg/--without-eisenberg", default=True,
              help="Include descriptive-only Eisenberg comparison if data is present")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(paradigm_class, label, norms_dir, output_dir, reports_dir, with_eisenberg, verbose):
    """Score bot sessions against published canonical norms; write a report."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    norms_path = Path(norms_dir) / f"{paradigm_class}.json"
    if not norms_path.exists():
        raise click.ClickException(
            f"No norms file at {norms_path}. Run "
            f"`experiment-bot-extract-norms --paradigm-class {paradigm_class}` first."
        )
    norms = json.loads(norms_path.read_text())

    label_dir = Path(output_dir) / label
    if not label_dir.exists():
        raise click.ClickException(f"No output dir: {label_dir}")
    session_dirs = sorted([p for p in label_dir.iterdir() if p.is_dir()])
    if not session_dirs:
        raise click.ClickException(f"No session subdirs in {label_dir}")

    report = validate_session_set(
        paradigm_class=paradigm_class,
        session_dirs=session_dirs,
        norms=norms,
    )

    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(reports_dir) / f"{label}_{ts}.json"
    out.write_text(json.dumps({
        "paradigm_class": report.paradigm_class,
        "overall_pass": report.overall_pass,
        "summary": report.summary,
        "pillar_results": {
            name: {
                "pass": pillar.pass_,
                "metrics": {
                    mname: {
                        "bot_value": m.bot_value,
                        "published_range": m.published_range,
                        "pass": m.pass_,
                    } for mname, m in pillar.metrics.items()
                }
            } for name, pillar in report.pillar_results.items()
        }
    }, indent=2))

    click.echo(f"Validation report: {out}")
    click.echo(f"Overall pass: {report.overall_pass}")
    for name, pillar in report.pillar_results.items():
        marker = "✅" if pillar.pass_ else "❌"
        click.echo(f"  {marker} {name}")
```

- [ ] **Step 5: Add to pyproject.toml `[project.scripts]`**

```toml
experiment-bot-validate = "experiment_bot.validation.cli:main"
```

- [ ] **Step 6: Run tests, expect PASS**

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/validation/cli.py src/experiment_bot/validation/eisenberg.py tests/test_validation_cli.py pyproject.toml uv.lock 2>/dev/null
git commit -m "feat(validation): experiment-bot-validate CLI + Eisenberg descriptive loader

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase E — Bring-up + iteration

Goal: regenerate TaskCards, run a fresh batch, validate, iterate prompts until all pillars pass on all 4 dev paradigms. End-of-phase: SP2 success criterion met.

### Task E1: Regenerate 4 dev TaskCards under SP2 framework

USER-GATED: requires Max CLI auth.

- [ ] **Step 1: Confirm `claude` CLI is on PATH and authenticated**

- [ ] **Step 2: Force-fresh regeneration**

```bash
rm -rf .reasoner_work
bash /tmp/sp1_regen.sh 2>&1 | tee /tmp/sp2_regen.log
```

(If `/tmp/sp1_regen.sh` no longer exists, recreate per the SP1.5 plan.)

- [ ] **Step 3: Verify each TaskCard**

```bash
uv run python -c "
import json
from pathlib import Path
from experiment_bot.taskcard.loader import load_latest

for label in ['expfactory_stop_signal', 'expfactory_stroop',
              'stopit_stop_signal', 'cognitionrun_stroop']:
    tc = load_latest(Path('taskcards'), label=label)
    pc = tc.task.paradigm_classes
    te_keys = list(tc.temporal_effects.keys())
    print(f'{label}: paradigm_classes={pc} effects={te_keys}')
"
```

Expected: all 4 have non-empty `paradigm_classes`. Conflict tasks (3 stroop variants) should include `"conflict"`. Interrupt tasks (2 stop-signal variants) should include `"interrupt"`. CSE should appear in temporal_effects on the conflict tasks.

If a paradigm class is missing or the wrong effects appear: iterate on the prompt for that task. Re-run.

- [ ] **Step 4: Commit regenerated TaskCards (delete stale duplicates first)**

```bash
for label in expfactory_stop_signal expfactory_stroop stopit_stop_signal cognitionrun_stroop; do
    cd "taskcards/$label"
    ls -t *.json | tail -n +2 | xargs -I {} rm {}
    cd - > /dev/null
done
git add taskcards/
git commit -m "chore(taskcards): regenerate under SP2 framework with paradigm_classes + CSE

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task E2: Fresh batch run (15 × 4 = 60 sessions)

USER-GATED.

- [ ] **Step 1: Confirm test suite green**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 2: Launch sequential batch**

```bash
bash scripts/batch_run.sh --count 15 --headless 2>&1 | tee /tmp/sp2_batch.log
```

(Do NOT pass `--regenerate` — TaskCards are already fresh from E1. Adds API spend with no benefit.)

Expected: 4 hours wall-clock. Parse the log for failure rate (≤ 10% acceptable per SP1 norm).

- [ ] **Step 3: Verify session count**

```bash
find output -name 'experiment_data.*' -newer /tmp/sp2_batch.log | wc -l
```

Expected: 60 (or 60 minus a few failures).

---

### Task E3: First validation pass

- [ ] **Step 1: Validate each paradigm**

```bash
for entry in "expfactory_stroop|conflict" "stopit_stop_signal|interrupt" \
             "expfactory_stop_signal|interrupt" "cognitionrun_stroop|conflict"; do
    label="${entry%%|*}"
    pc="${entry##*|}"
    echo "=== $label (paradigm_class=$pc) ==="
    uv run experiment-bot-validate --paradigm-class "$pc" --label "$label"
done
```

- [ ] **Step 2: Read the reports**

For each report under `validation/`, identify which pillars/metrics failed.

- [ ] **Step 3: Iterate**

For each failure mode:

1. **mu/sigma/tau out of range** — refine the Stage 2 behavioral prompt or system.md to provide better RT-norm pointers for that paradigm.
2. **between_subject_sd out of range** — refine the prompt instruction on between-subject variability.
3. **CSE missing or out of range on conflict tasks** — refine Stage 2's CSE example or check CSE registry entry implementation.
4. **PES out of range** — refine post_error_slowing prompt language.
5. **lag1_autocorr out of range** — refine autocorrelation phi prompt language.

Each iteration: re-run `experiment-bot-reason` for the affected task, re-run the bot for that task (15 sessions), re-validate. Loop until passing.

- [ ] **Step 4: Document iterations in `docs/sp2-findings.md`**

Each iteration round goes in this file: which prompt section changed, which paradigm/metric was failing before, the value before and after, what literature pointer was added.

If after 3-5 iterations a pillar still doesn't pass, document this as a paper finding rather than continuing to iterate.

- [ ] **Step 5: Commit each iteration as a discrete prompt update**

```bash
git add src/experiment_bot/prompts/system.md src/experiment_bot/reasoner/prompts/ docs/sp2-findings.md taskcards/
git commit -m "fix(prompts): iteration N for paradigm X — bring metric Y into published range

Before: bot_value=...
After:  bot_value=... (in [..., ...] range)
Source: <which paper added>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task E4: Final validation + tag

- [ ] **Step 1: Confirm all pillars pass on all 4 dev paradigms**

Run the validate loop one more time; verify "Overall pass: True" for each report.

- [ ] **Step 2: Update docs/sp2-findings.md with summary**

Add a top section: "Final validation result — all 4 paradigms pass / N pillars pass. Iterations needed: M. Documented limitations: K (where applicable)."

- [ ] **Step 3: Tag**

```bash
git tag -a sp2-complete -m "SP2: behavioral fidelity expansion — all 4 dev paradigms pass

Effect-type registry (universal + paradigm-specific). CSE handler.
Norms extractor. Validation oracle. All gating metrics in published
canonical ranges per the norms files."
```

- [ ] **Step 4: Push (user-confirmed)**

```bash
git push origin main
git push origin sp2-complete
```

---

## Self-review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| Effect-type registry mechanism + 6 existing effects re-expressed | A1, A2 |
| `paradigm_classes` field + Stage 1 prompt | A3 |
| `congruency_sequence` (CSE) effect handler | B1 |
| Stage 2 prompt enumerates registry-filtered effects | B2 |
| CSE validation metric | B3 |
| Norms file schema + validator | C1 |
| Norms extractor LLM call + circularity protection | C2 |
| `experiment-bot-extract-norms` CLI | C3 |
| Live extraction of norms/conflict.json + norms/interrupt.json | C4 |
| Universal validation metrics | D1 |
| ValidationReport + oracle logic | D2 |
| `experiment-bot-validate` CLI + Eisenberg side-by-side loader | D3 |
| Regenerate 4 dev TaskCards | E1 |
| 15 × 4 batch run | E2 |
| Validation pass + iteration | E3 |
| Tag + push | E4 |
| Out-of-scope (SP3/SP5/SP6 deferrals) | Not touched |

All spec sections covered.

**Placeholder scan:** No `TBD`, `TODO`, "implement later", or "similar to Task N" patterns. Every code step has concrete code. The references to `/tmp/sp1_regen.sh` in E1 have a fallback ("recreate per the SP1.5 plan").

**Type consistency:** `EffectType.handler` signature is `(state: SamplerState, params: dict) -> float` consistently across all handlers (A2, B1). `validation_metric` is `Callable[..., dict]` in the registry but most concrete metrics return float — this is intentional because some metrics return per-parameter dicts (e.g., `population_sd_per_param`); the type annotation in registry.py is `Callable[..., Any]` to permit both. `ValidationReport`, `PillarResult`, `MetricResult` field names match across D2 and D3 consumers. `cse_magnitude(trials)` consistently expects trials with `condition` and `rt` keys (B3 + D2 + handlers).

**Estimated wall-clock:** ~2 weeks of focused implementation (Phases A–D) + ~1–2 weeks of prompt iteration in Phase E. Total: ~3–4 weeks per the spec estimate.

---

## Out of scope (per spec)

- Switch cost / list length / n-back lure / other paradigm-specific effects (SP5).
- Auto-iteration of prompts (manual iteration in E3 is sufficient).
- Bot reading raw subject-level human reference data.
- Validation against any specific dataset as gating criterion (Eisenberg 2019 is descriptive-only).
- Norms files for paradigm classes the dev set doesn't include.
- HPC / Slurm execution (SP3).
- Per-session forensic trace logs and audit reports (SP6).

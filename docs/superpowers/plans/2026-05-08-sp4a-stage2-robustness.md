# SP4a — Stage 2 robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three Tier 1 fixes from `docs/sp4-stage2-robustness.md` (envelope contradiction, schema-derived prompt examples with drift-protection test, refinement-loop slot preservation), and re-run SP3 against Flanker + n-back as descriptive evidence about the framework's generalization curve.

**Architecture:** Five touch-points concentrated in Stage 2 of the Reasoner, each addressed by one task pair (test then implementation). New helpers landed via TDD; existing code paths preserved (existing TaskCards keep validating; bare numbers and envelopes both accepted via `oneOf`).

**Tech Stack:** Python 3.12 / uv; jsonschema; pytest; same Reasoner pipeline as SP3.

Reference: spec at `docs/superpowers/specs/2026-05-08-sp4a-stage2-robustness-design.md`. SP3 background: `docs/sp3-heldout-results.md` (failure modes), `docs/sp4-stage2-robustness.md` (the full backlog from which Tier 1 is drawn).

**Held-out policy reminder:** the SP3 re-run (Tasks 11-12) is the descriptive evidence that builds the project's generalization claim. If the re-run reveals a fifth failure mode beyond the four documented Tier 1 modes, that becomes the next SP's input — SP4a does not expand to chase it.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/experiment_bot/prompts/schema.json` | Stage 2 contract | Modified — add `oneOf` for `performance.{accuracy,omission_rate,practice_accuracy}` (Task 2) |
| `src/experiment_bot/reasoner/validate.py` | Schema validator | Modified — generalize envelope unwrap to handle `{value: number}` (Task 3) |
| `src/experiment_bot/core/config.py` | TaskCard loader | Modified — `PerformanceConfig.from_dict` unwraps envelopes (Task 4) |
| `src/experiment_bot/reasoner/prompts/stage2_behavioral.md` | Stage 2 LLM prompt | Modified — add `## Concrete shape examples` section (Task 5) |
| `tests/test_prompt_schema_consistency.py` | New invariant test | Created (Task 6) |
| `src/experiment_bot/reasoner/stage2_behavioral.py` | Refinement loop | Modified — new helpers + slot-locked refinement (Tasks 7, 8, 9) |
| `tests/fixtures/stage2/sp3_flanker_attempt3.json` | Captured failure fixture | Created (Task 1) |
| `tests/fixtures/stage2/sp3_nback_attempt3.json` | Captured failure fixture | Created (Task 1) |
| `tests/test_stage2_envelope.py` | New | Created (Tasks 2-4) |
| `tests/test_stage2_refinement_locks.py` | New | Created (Tasks 7-9) |
| `tests/test_stage2_behavioral.py` | Existing or new | Extended for slot-locked loop coverage (Task 9) |
| `docs/sp4a-results.md` | Held-out re-run report | Created (Task 13) |
| `CLAUDE.md` | Sub-project history | Modified (Task 14) |

---

## Task 0: Set up SP4a worktree

**Files:**
- Worktree: `.worktrees/sp4a` on branch `sp4a/stage2-robustness`, branched off tag `sp3-complete`

The sp4a branch additionally cherry-picks the SP4a spec and this plan from `sp3/heldout-validation`, so both docs are present in the working tree alongside the SP4 backlog and SP3 results docs (which are already on `sp3-complete`).

Steps 1-3 below have already been executed by the controller before plan execution begins. Subsequent tasks assume the worktree exists at `.worktrees/sp4a` and the engineer is operating inside it.

- [x] **Step 1: `git worktree add .worktrees/sp4a -b sp4a/stage2-robustness sp3-complete`** (controller)
- [x] **Step 2: Cherry-pick SP4a spec + this plan onto sp4a branch** (controller)
- [x] **Step 3: `uv sync` and verify clean baseline** (controller)

- [ ] **Step 4: Verify the worktree's clean state**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp4a
git status
git log --oneline -5
```

Expected: clean working tree on `sp4a/stage2-robustness`; recent log shows the two cherry-picked docs commits on top of `sp3-complete` (`404773d`).

- [ ] **Step 5: Verify tests pass on this branch**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: `468 passed, 1 skipped` (matches `sp3-complete` state — SP3 added no test code).

---

## Task 1: Capture SP3 failure fixtures

**Files:**
- Create: `tests/fixtures/stage2/sp3_flanker_attempt3.json`
- Create: `tests/fixtures/stage2/sp3_nback_attempt3.json`

The fixtures capture the **shape of LLM outputs** that produced each of the four documented Stage 2 failure modes from SP3. They are hand-crafted (the original LLM responses are not preserved verbatim in `.reasoner-logs`; only the schema errors are). Each fixture reproduces the failure modes documented in `docs/sp3-heldout-results.md` so subsequent tests can verify our fixes work on representative malformed input.

- [ ] **Step 1: Create the fixtures directory**

```bash
mkdir -p tests/fixtures/stage2
```

- [ ] **Step 2: Write the Flanker failure fixture**

Reproduces the four observed failures from `docs/sp3-heldout-results.md`:
- post_event_slowing trigger as bare string
- lag1 modulation_table with `prev_condition`/`curr_condition`/`rt_offset_ms` field-name vocabulary
- performance.accuracy.incongruent as `null`

Create `tests/fixtures/stage2/sp3_flanker_attempt3.json`:

```json
{
  "task": {"name": "attention_network_test_flanker", "paradigm_classes": ["conflict"]},
  "stimuli": [],
  "response_distributions": {
    "congruent": {
      "distribution": "ex_gaussian",
      "value": {"mu": 420, "sigma": 35, "tau": 90},
      "rationale": "Population norms for congruent flanker trials."
    },
    "incongruent": {
      "distribution": "ex_gaussian",
      "value": {"mu": 480, "sigma": 40, "tau": 110},
      "rationale": "Population norms for incongruent flanker trials."
    }
  },
  "performance": {
    "accuracy": {"congruent": 0.97, "incongruent": null},
    "omission_rate": {"congruent": 0.01, "incongruent": 0.02},
    "practice_accuracy": 0.95
  },
  "temporal_effects": {
    "lag1_pair_modulation": {
      "value": {
        "enabled": true,
        "modulation_table": [
          {"prev_condition": "incongruent", "curr_condition": "incongruent", "rt_offset_ms": -25},
          {"prev_condition": "congruent", "curr_condition": "incongruent", "rt_offset_ms": 0}
        ]
      },
      "rationale": "Conflict adaptation effect."
    },
    "post_event_slowing": {
      "value": {
        "enabled": true,
        "triggers": ["error"]
      },
      "rationale": "Post-error slowing on conflict tasks."
    }
  },
  "between_subject_jitter": {
    "value": {
      "rt_mean_sd_ms": 50,
      "rt_condition_sd_ms": 30,
      "sigma_tau_range": [0.8, 1.2],
      "accuracy_sd": 0.02,
      "omission_sd": 0.01,
      "accuracy_clip_range": [0.85, 1.0],
      "omission_clip_range": [0.0, 0.1]
    }
  }
}
```

- [ ] **Step 3: Write the n-back failure fixture**

Reproduces the n-back-specific failures:
- post_event_slowing trigger as bare string (same as Flanker)
- performance.accuracy.mismatch as `{value, rationale}` envelope
- task_specific.key_map.rationale rationale leakage

Create `tests/fixtures/stage2/sp3_nback_attempt3.json`:

```json
{
  "task": {"name": "n_back_rdoc", "paradigm_classes": ["working_memory"]},
  "stimuli": [],
  "response_distributions": {
    "match": {
      "distribution": "ex_gaussian",
      "value": {"mu": 540, "sigma": 50, "tau": 130},
      "rationale": "Population norms for match trials."
    },
    "mismatch": {
      "distribution": "ex_gaussian",
      "value": {"mu": 580, "sigma": 55, "tau": 140},
      "rationale": "Population norms for mismatch trials."
    }
  },
  "performance": {
    "accuracy": {
      "match": 0.86,
      "mismatch": {"target": 0.93, "rationale": "Correct rejection rates on non-match trials."}
    },
    "omission_rate": {"match": 0.02, "mismatch": 0.01},
    "practice_accuracy": 0.85
  },
  "temporal_effects": {
    "post_event_slowing": {
      "value": {
        "enabled": true,
        "triggers": ["error"]
      },
      "rationale": "Post-error slowing on n-back."
    }
  },
  "task_specific": {
    "key_map": {
      "match": ".",
      "mismatch": ",",
      "rationale": "Match/mismatch key assignment is counterbalanced across participants via window.efVars.group_index. The assignment is materialized at trial start in window.possibleResponses; response_key_js reads the live mapping."
    }
  },
  "between_subject_jitter": {
    "value": {
      "rt_mean_sd_ms": 60,
      "rt_condition_sd_ms": 35,
      "sigma_tau_range": [0.8, 1.2],
      "accuracy_sd": 0.03,
      "omission_sd": 0.01,
      "accuracy_clip_range": [0.7, 1.0],
      "omission_clip_range": [0.0, 0.1]
    }
  }
}
```

- [ ] **Step 4: Sanity-check that current validator rejects each fixture as documented**

```bash
uv run python << 'PY'
import json
from experiment_bot.reasoner.validate import validate_stage2_schema, Stage2SchemaError

for label, path in [
    ("flanker", "tests/fixtures/stage2/sp3_flanker_attempt3.json"),
    ("nback",   "tests/fixtures/stage2/sp3_nback_attempt3.json"),
]:
    with open(path) as f:
        partial = json.load(f)
    try:
        validate_stage2_schema(partial)
    except Stage2SchemaError as e:
        print(f"[{label}] failures (expected):")
        for p, m in e.errors:
            print(f"  - {p}: {m[:80]}")
PY
```

Expected: Flanker emits errors at `temporal_effects.lag1_pair_modulation.value.modulation_table.0/.1` (extra props), `temporal_effects.post_event_slowing.value.triggers.0` (not object), `performance.accuracy.incongruent` (not number). N-back emits errors at `temporal_effects.post_event_slowing.value.triggers.0`, `performance.accuracy.mismatch` (not number), `task_specific.key_map.rationale` (too long).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/stage2/
git commit -m "test(sp4a): captured SP3 Stage 2 failure fixtures

Hand-crafted fixtures reproducing the four documented failure modes
from docs/sp3-heldout-results.md: post_event_slowing trigger shape,
lag1 modulation_table field-name vocabulary, performance.accuracy
envelope contradiction, key_map.rationale leak."
```

---

## Task 2: Schema accepts envelope shape for `performance.*`

**Files:**
- Modify: `src/experiment_bot/prompts/schema.json:62-72`
- Test: `tests/test_stage2_envelope.py` (new)

The `oneOf` lets either bare numbers or `{value, rationale}` envelopes validate. Existing TaskCards (bare numbers) keep working without migration.

- [ ] **Step 1: Write failing test for envelope acceptance**

Create `tests/test_stage2_envelope.py`:

```python
"""Schema and loader accept both bare-number and envelope shapes for
performance.{accuracy,omission_rate,practice_accuracy}. Backwards-compatible
with existing TaskCards (bare numbers); forward-compatible with Stage 2
LLM outputs that wrap each numeric in a {value, rationale} envelope."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from experiment_bot.reasoner.validate import (
    Stage2SchemaError, validate_stage2_schema,
)


def _minimal_partial(**overrides) -> dict:
    """Build a Stage 2 partial whose other fields are valid; tests
    isolate the field they care about via overrides."""
    base = {
        "task": {"name": "test_task"},
        "stimuli": [],
        "response_distributions": {
            "go": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 50, "tau": 100},
                "rationale": "test",
            }
        },
        "performance": {
            "accuracy": {"go": 0.95},
            "omission_rate": {"go": 0.02},
            "practice_accuracy": 0.9,
        },
        "temporal_effects": {},
        "between_subject_jitter": {"value": {}},
    }
    for path, value in overrides.items():
        node = base
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return base


def test_schema_accepts_bare_number_accuracy():
    partial = _minimal_partial()
    validate_stage2_schema(partial)  # no raise


def test_schema_accepts_envelope_accuracy():
    partial = _minimal_partial(**{
        "performance.accuracy": {"go": {"value": 0.95, "rationale": "test"}},
    })
    validate_stage2_schema(partial)  # no raise


def test_schema_rejects_null_accuracy():
    """Null accuracy was an SP3 Flanker failure mode — it must still fail."""
    partial = _minimal_partial(**{
        "performance.accuracy": {"go": None},
    })
    with pytest.raises(Stage2SchemaError) as ei:
        validate_stage2_schema(partial)
    paths = [p for p, _ in ei.value.errors]
    assert any("accuracy" in p for p in paths), f"expected accuracy error, got {paths}"


def test_schema_accepts_envelope_omission_rate():
    partial = _minimal_partial(**{
        "performance.omission_rate": {"go": {"value": 0.02, "rationale": "test"}},
    })
    validate_stage2_schema(partial)  # no raise


def test_schema_accepts_envelope_practice_accuracy():
    partial = _minimal_partial(**{"performance.practice_accuracy": {"value": 0.9, "rationale": "x"}})
    validate_stage2_schema(partial)  # no raise
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
uv run pytest tests/test_stage2_envelope.py -v 2>&1 | tail -20
```

Expected: `test_schema_accepts_envelope_accuracy`, `test_schema_accepts_envelope_omission_rate`, `test_schema_accepts_envelope_practice_accuracy` FAIL (current schema rejects envelopes).

- [ ] **Step 3: Update the schema**

Edit `src/experiment_bot/prompts/schema.json`. Replace the `performance` block (currently at L58-74) with:

```json
"performance": {
  "type": "object",
  "required": ["accuracy", "omission_rate", "practice_accuracy"],
  "properties": {
    "accuracy": {
      "type": "object",
      "additionalProperties": {
        "oneOf": [
          {"type": "number", "minimum": 0, "maximum": 1},
          {
            "type": "object",
            "properties": {
              "value": {"type": "number", "minimum": 0, "maximum": 1},
              "rationale": {"type": "string"}
            },
            "required": ["value"],
            "additionalProperties": false
          }
        ]
      },
      "description": "Per-condition accuracy (0-1). Keys are condition names from stimuli. Each value is either a bare number or a {value, rationale} envelope."
    },
    "omission_rate": {
      "type": "object",
      "additionalProperties": {
        "oneOf": [
          {"type": "number", "minimum": 0, "maximum": 1},
          {
            "type": "object",
            "properties": {
              "value": {"type": "number", "minimum": 0, "maximum": 1},
              "rationale": {"type": "string"}
            },
            "required": ["value"],
            "additionalProperties": false
          }
        ]
      },
      "description": "Per-condition omission rate (0-1). Keys are condition names. Each value is either a bare number or a {value, rationale} envelope."
    },
    "practice_accuracy": {
      "oneOf": [
        {"type": "number", "minimum": 0, "maximum": 1},
        {
          "type": "object",
          "properties": {
            "value": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"}
          },
          "required": ["value"],
          "additionalProperties": false
        }
      ]
    }
  }
}
```

- [ ] **Step 4: Run the tests to confirm pass**

```bash
uv run pytest tests/test_stage2_envelope.py -v 2>&1 | tail -10
```

Expected: all five `test_schema_*` tests PASS.

- [ ] **Step 5: Confirm full suite still passes (no schema regressions)**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 473 passed, 1 skipped (468 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/prompts/schema.json tests/test_stage2_envelope.py
git commit -m "feat(schema): performance.* accepts oneOf bare-number-or-envelope

Resolves the SP3-surfaced contradiction where the Stage 2 prompt
instructed the LLM to wrap numeric parameters in {value, rationale}
envelopes, but the schema for performance.{accuracy,omission_rate,
practice_accuracy} required bare numbers. Both shapes now validate;
existing TaskCards (bare numbers) need no migration."
```

---

## Task 3: Validator unwraps `{value: number}` envelopes

**Files:**
- Modify: `src/experiment_bot/reasoner/validate.py:36-44`
- Test: `tests/test_stage2_envelope.py` (extend)

The current `_value_only` helper only unwraps `{value: dict}`. The Task 2 schema accepts both bare numbers and envelopes via `oneOf`, so the validator's path doesn't strictly need to unwrap (the `oneOf` handles it). But other code paths in `validate.py` (e.g., the `performance.*` validation block at L132-146) iterate over the dict and apply jsonschema directly; if those paths unwrap before validating they get cleaner error messages. This task generalizes the helper for future-proofing and consistent behavior.

- [ ] **Step 1: Write failing test for the unwrap helper**

Add to `tests/test_stage2_envelope.py`:

```python
def test_value_only_unwraps_dict_envelope():
    from experiment_bot.reasoner.validate import _value_only
    assert _value_only({"value": {"a": 1}, "rationale": "x"}) == {"a": 1}


def test_value_only_unwraps_number_envelope():
    """SP4a addition: envelope with bare-number value (e.g., performance.accuracy)."""
    from experiment_bot.reasoner.validate import _value_only
    assert _value_only({"value": 0.95, "rationale": "x"}) == 0.95


def test_value_only_passthrough_for_non_envelope():
    from experiment_bot.reasoner.validate import _value_only
    assert _value_only({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    assert _value_only(0.95) == 0.95
    assert _value_only("plain string") == "plain string"
```

- [ ] **Step 2: Run tests to confirm `test_value_only_unwraps_number_envelope` fails**

```bash
uv run pytest tests/test_stage2_envelope.py::test_value_only_unwraps_number_envelope -v 2>&1 | tail -10
```

Expected: FAIL — current `_value_only` only unwraps when `node["value"]` is a dict.

- [ ] **Step 3: Generalize `_value_only`**

Edit `src/experiment_bot/reasoner/validate.py`. Replace the `_value_only` function (currently at L36-44) with:

```python
def _value_only(node):
    """Stage 2 wraps each parameter in a {value: <inner>, rationale, ...}
    envelope. Some envelopes wrap dict values (temporal_effects.*); some
    wrap bare numbers (performance.*) — both are valid since SP4a's
    schema generalization. This helper unwraps either shape; non-envelope
    nodes pass through unchanged so the validator can still apply.
    """
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
uv run pytest tests/test_stage2_envelope.py -v 2>&1 | tail -10
```

Expected: all `test_value_only_*` tests PASS.

- [ ] **Step 5: Confirm full suite still passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 476 passed, 1 skipped (473 + 3 new). If anything previously relied on `_value_only` returning the envelope when value is non-dict, that's a bug being uncovered — investigate the failure case before patching.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/validate.py tests/test_stage2_envelope.py
git commit -m "fix(validate): _value_only unwraps both dict and number envelopes

Generalizes the envelope unwrap to handle performance.* envelope
shapes (bare-number value) in addition to temporal_effects.*
envelopes (dict value). Aligns with the SP4a schema generalization."
```

---

## Task 4: Loader unwraps envelopes in `PerformanceConfig.from_dict`

**Files:**
- Modify: `src/experiment_bot/core/config.py:287-307`
- Test: `tests/test_stage2_envelope.py` (extend)

`PerformanceConfig.from_dict` currently passes the input dict's `accuracy` mapping through unchanged, so envelope-shaped values would arrive as `{value: 0.95, rationale: "..."}` instead of `0.95`, breaking the `dict[str, float]` contract. This task adds the unwrap at load time.

- [ ] **Step 1: Write failing test for loader unwrap**

Add to `tests/test_stage2_envelope.py`:

```python
def test_performance_config_loads_bare_number():
    from experiment_bot.core.config import PerformanceConfig
    cfg = PerformanceConfig.from_dict({
        "accuracy": {"go": 0.95, "stop": 0.85},
        "omission_rate": {"go": 0.02},
        "practice_accuracy": 0.9,
    })
    assert cfg.accuracy["go"] == 0.95
    assert cfg.accuracy["stop"] == 0.85
    assert cfg.omission_rate["go"] == 0.02
    assert cfg.practice_accuracy == 0.9


def test_performance_config_loads_envelope():
    """SP4a addition: loader unwraps {value, rationale} envelopes."""
    from experiment_bot.core.config import PerformanceConfig
    cfg = PerformanceConfig.from_dict({
        "accuracy": {
            "go": {"value": 0.95, "rationale": "test"},
            "stop": 0.85,  # mixed shapes in the same map are fine
        },
        "omission_rate": {"go": {"value": 0.02, "rationale": "test"}},
        "practice_accuracy": {"value": 0.9, "rationale": "test"},
    })
    assert cfg.accuracy["go"] == 0.95
    assert cfg.accuracy["stop"] == 0.85
    assert cfg.omission_rate["go"] == 0.02
    assert cfg.practice_accuracy == 0.9
```

- [ ] **Step 2: Run tests to confirm `test_performance_config_loads_envelope` fails**

```bash
uv run pytest tests/test_stage2_envelope.py::test_performance_config_loads_envelope -v 2>&1 | tail -10
```

Expected: FAIL with `AssertionError: cfg.accuracy["go"] == 0.95` — actual value is the dict.

- [ ] **Step 3: Add the unwrap helper and use it in `from_dict`**

Edit `src/experiment_bot/core/config.py`. In the `PerformanceConfig` block (currently L287-307), replace `from_dict` with:

```python
    @classmethod
    def from_dict(cls, d: dict) -> PerformanceConfig:
        return cls(
            accuracy={k: _unwrap_value(v) for k, v in d["accuracy"].items()},
            omission_rate={k: _unwrap_value(v) for k, v in d.get("omission_rate", {}).items()},
            practice_accuracy=_unwrap_value(d.get("practice_accuracy")),
        )
```

And add this module-level helper near the top of `config.py` (alongside other private helpers):

```python
def _unwrap_value(v):
    """Unwrap a Stage 2 {value, rationale} envelope to its inner value.
    Bare numbers and None pass through unchanged. Handles both dict
    envelopes (temporal_effects style) and number envelopes
    (performance.* style under SP4a's schema generalization).
    """
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
uv run pytest tests/test_stage2_envelope.py -v 2>&1 | tail -10
```

Expected: all `test_performance_config_*` tests PASS.

- [ ] **Step 5: Confirm full suite still passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 478 passed, 1 skipped (476 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/core/config.py tests/test_stage2_envelope.py
git commit -m "fix(loader): PerformanceConfig.from_dict unwraps envelope values

TaskCards produced under SP4a's schema may carry {value, rationale}
envelopes for performance.{accuracy,omission_rate,practice_accuracy}.
Loader normalizes to bare floats at construction time so the
PerformanceConfig dataclass's float contract holds."
```

---

## Task 5: Add `## Concrete shape examples` section to Stage 2 prompt

**Files:**
- Modify: `src/experiment_bot/reasoner/prompts/stage2_behavioral.md`

The new section gives the LLM literal examples of the shapes the schema expects (and explicit anti-examples for the SP3-observed failures). Each example block is fenced with a tagged class the invariant test (Task 6) will recognize.

- [ ] **Step 1: Append the new section to `stage2_behavioral.md`**

Append the following to the end of `src/experiment_bot/reasoner/prompts/stage2_behavioral.md`:

```markdown

## Concrete shape examples (read carefully — schema rejects variants)

The schema validator strictly enforces the exact field names and types shown below. Variants like alternate field names or extra properties cause refinement loops. Use these examples verbatim as templates.

### temporal_effects.post_event_slowing.triggers[]

Each item must be an object with an `event` enum, two numeric bounds, and an optional exclusivity flag.

```json schema-example: temporal_effects.post_event_slowing.triggers[]
{"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}
```

```json schema-example: temporal_effects.post_event_slowing.triggers[]
{"event": "interrupt", "slowing_ms_min": 80, "slowing_ms_max": 140, "exclusive_with_prior_triggers": true}
```

Do NOT emit:

```json schema-anti-example: temporal_effects.post_event_slowing.triggers[]
"error"
```

```json schema-anti-example: temporal_effects.post_event_slowing.triggers[]
{"slowing_ms": 50}
```

### temporal_effects.lag1_pair_modulation.modulation_table[]

Each item names the condition transition with `prev` and `curr` (NOT `prev_condition` / `curr_condition`), plus a delta. Use either a fixed `delta_ms` or a uniform-random `delta_ms_min`/`delta_ms_max` pair.

```json schema-example: temporal_effects.lag1_pair_modulation.modulation_table[]
{"prev": "incongruent", "curr": "incongruent", "delta_ms": -25}
```

```json schema-example: temporal_effects.lag1_pair_modulation.modulation_table[]
{"prev": "congruent", "curr": "incongruent", "delta_ms_min": 5, "delta_ms_max": 30}
```

Do NOT emit:

```json schema-anti-example: temporal_effects.lag1_pair_modulation.modulation_table[]
{"prev_condition": "incongruent", "curr_condition": "incongruent", "rt_offset_ms": -25}
```

### performance.accuracy.<condition>

Each per-condition value may be either a bare number OR a `{value, rationale}` envelope. Both are accepted; pick one.

```json schema-example: performance.accuracy.<condition>
0.95
```

```json schema-example: performance.accuracy.<condition>
{"value": 0.95, "rationale": "Population mean for go-condition accuracy."}
```

Do NOT emit `null`. If the literature does not give a clean point estimate, choose the midpoint of the reported range.

```json schema-anti-example: performance.accuracy.<condition>
null
```

The same rule applies to `performance.omission_rate.<condition>` and `performance.practice_accuracy`.

### task_specific.key_map

A flat condition→key map. Each value is a literal Playwright key, the sentinel `"dynamic"`, or a withhold sentinel like `"withhold"`/`"null"`. Do NOT include rationale fields, prose, or parentheticals — the executor presses the value as a literal key.

```json schema-example: task_specific.key_map
{"congruent": "f", "incongruent": "j"}
```

```json schema-example: task_specific.key_map
{"go": "Space", "stop": "withhold"}
```

Do NOT emit:

```json schema-anti-example: task_specific.key_map
{"match": ".", "mismatch": ",", "rationale": "Counterbalanced across participants..."}
```

If you need to document how the key mapping is resolved, place the rationale in the per-stimulus `response_key_js` or in the parent's `rationale` field — never as a value inside `key_map`.
```

- [ ] **Step 2: Verify the prompt file parses as expected length**

```bash
wc -l src/experiment_bot/reasoner/prompts/stage2_behavioral.md
```

Expected: ~80-100 lines (was 37 before; the addendum is ~50-60 lines).

- [ ] **Step 3: Commit (test for invariant lands in Task 6)**

```bash
git add src/experiment_bot/reasoner/prompts/stage2_behavioral.md
git commit -m "feat(prompt): Stage 2 prompt has concrete shape examples

Adds explicit good/bad examples for the four SP3-documented Stage 2
failure modes: post_event_slowing trigger shape, lag1
modulation_table field-name vocabulary, performance.* envelope
shape, and task_specific.key_map (anti-rationale-leakage).

Each fenced block carries a 'schema-example: <path>' or
'schema-anti-example: <path>' tag that the invariant test (next
commit) uses to assert prompt-schema consistency at CI time."
```

---

## Task 6: Prompt-schema invariant test

**Files:**
- Create: `tests/test_prompt_schema_consistency.py`

Extracts every fenced block tagged `json schema-example: <path>` and `json schema-anti-example: <path>` from `stage2_behavioral.md`. For each, validates the JSON against the schema sub-tree at `<path>`. Schema-example blocks must validate; schema-anti-example blocks must fail validation. Catches drift between prompt examples and schema at CI time.

- [ ] **Step 1: Write the test**

Create `tests/test_prompt_schema_consistency.py`:

```python
"""Invariant test: every JSON example in the Stage 2 prompt must
validate against the schema sub-tree the example claims to illustrate.
Anti-examples must fail to validate. Catches prompt-schema drift."""
from __future__ import annotations
import json
import re
from pathlib import Path

import jsonschema
import pytest


PROMPT_PATH = Path("src/experiment_bot/reasoner/prompts/stage2_behavioral.md")
SCHEMA_PATH = Path("src/experiment_bot/prompts/schema.json")

# Fenced block format:
#   ```json schema-example: <path>
#   <json>
#   ```
# Path uses dot-segments; "[]" suffix means "the array's items schema".
_BLOCK_RE = re.compile(
    r"^```json\s+(schema-example|schema-anti-example):\s*([^\n]+?)\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def _resolve_schema_path(schema: dict, path: str) -> dict:
    """Resolve a dot/[]-segment path to the schema sub-tree at that location.
    Examples:
      "performance.accuracy.<condition>"
        → schema.properties.performance.properties.accuracy.additionalProperties
      "temporal_effects.post_event_slowing.triggers[]"
        → ...properties.triggers.items
      "task_specific.key_map"
        → ...properties.task_specific.properties.key_map.additionalProperties
        (special case: key_map's values are validated by additionalProperties,
        but a whole key_map dict is validated by the key_map schema itself).
    """
    node = schema
    if "properties" in node:
        node = node["properties"]
    segments = path.split(".")
    for seg in segments:
        # Handle <placeholder> segments (e.g., "<condition>"):
        # they mean "additionalProperties" — i.e., per-key schema.
        if seg.startswith("<") and seg.endswith(">"):
            node = node["additionalProperties"]
            continue
        # Handle "[]" suffix on a segment (e.g., "triggers[]"):
        # strip and recurse into items after.
        items_after = seg.endswith("[]")
        if items_after:
            seg = seg[:-2]
        if seg in node:
            node = node[seg]
        elif "properties" in node and seg in node["properties"]:
            node = node["properties"][seg]
        else:
            raise KeyError(f"Schema path segment {seg!r} not found in node keys {sorted(node.keys())}")
        if items_after:
            node = node["items"]
        elif "properties" in node:
            # Auto-descend into properties on the next iteration unless
            # the next segment is a placeholder.
            pass
    return node


def _extract_blocks(text: str):
    """Yield (kind, path, parsed_json) for each fenced example block."""
    for m in _BLOCK_RE.finditer(text):
        kind, path, body = m.group(1), m.group(2), m.group(3)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Prompt example at {path!r} is not valid JSON: {e}"
            )
        yield kind, path, data


def test_prompt_schema_consistency():
    schema = json.loads(SCHEMA_PATH.read_text())
    prompt = PROMPT_PATH.read_text()

    blocks = list(_extract_blocks(prompt))
    assert blocks, "No schema-example blocks found in stage2_behavioral.md — has the addendum been removed?"

    for kind, path, data in blocks:
        try:
            sub_schema = _resolve_schema_path(schema, path)
        except KeyError as e:
            pytest.fail(f"schema path resolution failed for {path!r}: {e}")
        try:
            jsonschema.validate(data, sub_schema)
            example_validated = True
        except jsonschema.ValidationError as e:
            example_validated = False
            ve_msg = e.message
        if kind == "schema-example":
            assert example_validated, (
                f"prompt example at {path!r} should validate but did not: {ve_msg}\n"
                f"data: {json.dumps(data)}"
            )
        elif kind == "schema-anti-example":
            assert not example_validated, (
                f"prompt anti-example at {path!r} unexpectedly validates against the schema. "
                f"Either the schema accepts it (anti-example is wrong) or the schema is too permissive. "
                f"data: {json.dumps(data)}"
            )


def test_extract_blocks_finds_all_paths():
    """At least these four paths must have at least one example block.
    They correspond to the four SP3-documented failure modes."""
    prompt = PROMPT_PATH.read_text()
    blocks = list(_extract_blocks(prompt))
    paths_seen = {path for _, path, _ in blocks}
    expected_subset = {
        "temporal_effects.post_event_slowing.triggers[]",
        "temporal_effects.lag1_pair_modulation.modulation_table[]",
        "performance.accuracy.<condition>",
        "task_specific.key_map",
    }
    missing = expected_subset - paths_seen
    assert not missing, f"missing prompt examples for paths: {missing}"
```

- [ ] **Step 2: Run the test to confirm it passes against the current prompt**

```bash
uv run pytest tests/test_prompt_schema_consistency.py -v 2>&1 | tail -15
```

Expected: both tests PASS.

- [ ] **Step 3: Verify the test catches drift (sanity check)**

Make a temporary change to the prompt that breaks an example, run the test, confirm it fails, revert.

```bash
# Temporary break: rename a "prev" to "prev_condition" in a good example.
sed -i.bak 's/"prev": "incongruent", "curr": "incongruent", "delta_ms": -25/"prev_condition": "incongruent", "curr": "incongruent", "delta_ms": -25/' src/experiment_bot/reasoner/prompts/stage2_behavioral.md
uv run pytest tests/test_prompt_schema_consistency.py::test_prompt_schema_consistency -v 2>&1 | tail -8
# Expected: FAIL with "prompt example at temporal_effects.lag1_pair_modulation.modulation_table[] should validate but did not"
mv src/experiment_bot/reasoner/prompts/stage2_behavioral.md.bak src/experiment_bot/reasoner/prompts/stage2_behavioral.md
uv run pytest tests/test_prompt_schema_consistency.py -v 2>&1 | tail -5
# Expected: PASS again
```

- [ ] **Step 4: Confirm full suite passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 480 passed, 1 skipped (478 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_schema_consistency.py
git commit -m "test(prompt): invariant — Stage 2 prompt examples validate against schema

Extracts schema-example/schema-anti-example fenced blocks from
stage2_behavioral.md and asserts schema-example blocks validate, anti-
example blocks fail. Drift between prompt and schema is now a CI
failure rather than a silent regression."
```

---

## Task 7: `_extract_failing_slots` helper

**Files:**
- Modify: `src/experiment_bot/reasoner/stage2_behavioral.py` (add helper)
- Create: `tests/test_stage2_refinement_locks.py`

The helper walks a `Stage2SchemaError.errors` list and produces a deduped, sorted list of slot keys at the granularity errors actually surface. Slot rule per the spec:

- `temporal_effects.<mech>.value.<inner>` → `temporal_effects.<mech>`
- `performance.<sub>.<cond>` → `performance.<sub>`
- `task_specific.<key>.<inner>` → `task_specific.<key>`
- `between_subject_jitter.value.<inner>` → `between_subject_jitter`
- `response_distributions.<cond>.<inner>` → `response_distributions.<cond>`

- [ ] **Step 1: Write failing test for the helper**

Create `tests/test_stage2_refinement_locks.py`:

```python
"""Tests for the slot-locked Stage 2 refinement loop. Verify the slot
extractor maps failing error paths to the right level of granularity,
and the refinement merge logic preserves validated slots."""
from __future__ import annotations
import json
from pathlib import Path

import pytest


def test_extract_failing_slots_temporal_effects():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("temporal_effects.post_event_slowing.value.triggers.0", "msg"),
        ("temporal_effects.lag1_pair_modulation.value.modulation_table.3", "msg"),
        ("temporal_effects.lag1_pair_modulation.value.modulation_table.5", "msg"),  # dup slot
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "temporal_effects.lag1_pair_modulation",
        "temporal_effects.post_event_slowing",
    ]


def test_extract_failing_slots_performance():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("performance.accuracy.incongruent", "msg"),
        ("performance.accuracy.congruent", "msg"),
        ("performance.omission_rate.go", "msg"),
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "performance.accuracy",
        "performance.omission_rate",
    ]


def test_extract_failing_slots_task_specific():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [("task_specific.key_map.rationale", "too long")]
    slots = _extract_failing_slots(errors)
    assert slots == ["task_specific.key_map"]


def test_extract_failing_slots_between_subject_jitter():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [("between_subject_jitter.value.rt_mean_sd_ms", "negative")]
    slots = _extract_failing_slots(errors)
    assert slots == ["between_subject_jitter"]


def test_extract_failing_slots_response_distributions():
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("response_distributions.go.value.mu", "negative"),
        ("response_distributions.stop.distribution", "unknown"),
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "response_distributions.go",
        "response_distributions.stop",
    ]


def test_extract_failing_slots_mixed_dedupe_and_sort():
    """Multiple errors at different granularities — final list is sorted unique."""
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots
    errors = [
        ("temporal_effects.post_event_slowing.value.triggers.0", "a"),
        ("performance.accuracy.incongruent", "b"),
        ("temporal_effects.post_event_slowing.value.triggers.1", "c"),
        ("performance.accuracy.congruent", "d"),
    ]
    slots = _extract_failing_slots(errors)
    assert slots == [
        "performance.accuracy",
        "temporal_effects.post_event_slowing",
    ]


def test_flanker_fixture_yields_three_slots():
    """End-to-end: feed the captured Flanker fixture's errors through
    the helper; expect three slots (lag1, post_event_slowing, performance.accuracy)."""
    from experiment_bot.reasoner.validate import (
        validate_stage2_schema, Stage2SchemaError,
    )
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots

    partial = json.loads(Path("tests/fixtures/stage2/sp3_flanker_attempt3.json").read_text())
    with pytest.raises(Stage2SchemaError) as ei:
        validate_stage2_schema(partial)
    slots = _extract_failing_slots(ei.value.errors)
    assert slots == [
        "performance.accuracy",
        "temporal_effects.lag1_pair_modulation",
        "temporal_effects.post_event_slowing",
    ]


def test_nback_fixture_yields_three_slots():
    """End-to-end: n-back fixture errors → slot list."""
    from experiment_bot.reasoner.validate import (
        validate_stage2_schema, Stage2SchemaError,
    )
    from experiment_bot.reasoner.stage2_behavioral import _extract_failing_slots

    partial = json.loads(Path("tests/fixtures/stage2/sp3_nback_attempt3.json").read_text())
    with pytest.raises(Stage2SchemaError) as ei:
        validate_stage2_schema(partial)
    slots = _extract_failing_slots(ei.value.errors)
    # Note: with the SP4a schema generalization, performance.accuracy.mismatch
    # (which uses {value, rationale} envelope) NO LONGER fails. So the n-back
    # fixture under SP4a's schema has only two failing slots.
    assert slots == [
        "task_specific.key_map",
        "temporal_effects.post_event_slowing",
    ]
```

- [ ] **Step 2: Run tests to confirm they fail (helper not yet defined)**

```bash
uv run pytest tests/test_stage2_refinement_locks.py -v 2>&1 | tail -15
```

Expected: all 8 tests FAIL with `ImportError: cannot import name '_extract_failing_slots'`.

- [ ] **Step 3: Add the helper to `stage2_behavioral.py`**

Edit `src/experiment_bot/reasoner/stage2_behavioral.py`. Add this function near the top of the module (after the `STAGE2_MAX_REFINEMENTS` constant, before `run_stage2`):

```python
# Slot-extraction rule for refinement preservation. Each top-level path
# in Stage2SchemaError.errors collapses to one of these slot patterns;
# refinement re-prompts only the failing slots and locks the rest.
_SLOT_RULES: list[tuple[str, int]] = [
    # (path-prefix-after-split, depth-of-slot-segments)
    ("temporal_effects", 2),       # temporal_effects.<mech>
    ("performance", 2),            # performance.<sub>
    ("task_specific", 2),          # task_specific.<key>
    ("response_distributions", 2), # response_distributions.<cond>
    ("between_subject_jitter", 1), # between_subject_jitter (whole)
]


def _extract_failing_slots(errors: list[tuple[str, str]]) -> list[str]:
    """Map a list of (path, message) validation errors to the deduped,
    sorted set of slot keys whose contents need regeneration.

    See the SP4a spec's slot-extraction rule. Multiple errors within
    one slot collapse to a single slot entry.
    """
    slots: set[str] = set()
    for path, _ in errors:
        segments = path.split(".")
        if not segments:
            continue
        head = segments[0]
        depth = next(
            (d for prefix, d in _SLOT_RULES if prefix == head),
            1,  # default: collapse to top-level segment
        )
        slot = ".".join(segments[:depth])
        slots.add(slot)
    return sorted(slots)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
uv run pytest tests/test_stage2_refinement_locks.py -v 2>&1 | tail -15
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Confirm full suite still passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 488 passed, 1 skipped (480 + 8 new).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage2_behavioral.py tests/test_stage2_refinement_locks.py
git commit -m "feat(stage2): _extract_failing_slots helper for slot-locked refinement

Maps Stage2SchemaError.errors paths to the slot granularity at which
the LLM regenerates content during refinement. Five slot patterns
cover all current Stage 2 fields. Tested end-to-end against the
captured SP3 Flanker and n-back failure fixtures."
```

---

## Task 8: `_render_slot_refinement_prompt` helper

**Files:**
- Modify: `src/experiment_bot/reasoner/stage2_behavioral.py`
- Test: `tests/test_stage2_refinement_locks.py` (extend)

Builds the slot-specific refinement prompt: a "previously-validated context (do NOT modify)" section, a list of failing slots, and per-slot guidance pulled from the existing schema example blocks in the prompt addendum.

- [ ] **Step 1: Write failing test for the prompt renderer**

Append to `tests/test_stage2_refinement_locks.py`:

```python
def test_render_slot_refinement_prompt_includes_failing_slots():
    from experiment_bot.reasoner.stage2_behavioral import _render_slot_refinement_prompt
    partial = {
        "task": {"name": "x"},
        "response_distributions": {"go": {"distribution": "ex_gaussian", "value": {"mu": 500, "sigma": 50, "tau": 100}}},
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.9},
        "temporal_effects": {"post_event_slowing": {"value": {"enabled": True, "triggers": ["error"]}}},
        "between_subject_jitter": {"value": {}},
    }
    failing_slots = ["temporal_effects.post_event_slowing"]
    errors = [("temporal_effects.post_event_slowing.value.triggers.0", "'error' is not of type 'object'")]
    prompt = _render_slot_refinement_prompt(partial, failing_slots, errors)

    # Sanity checks: the rendered prompt should mention failing slots and the error.
    assert "temporal_effects.post_event_slowing" in prompt
    assert "'error' is not of type 'object'" in prompt
    # Should reference previously-validated context (a marker like "do NOT modify"):
    assert "do NOT modify" in prompt or "do not modify" in prompt.lower()


def test_render_slot_refinement_prompt_locks_validated_slots():
    """Validated slots appear in the prompt as locked context;
    failing slots appear as targets for regeneration."""
    from experiment_bot.reasoner.stage2_behavioral import _render_slot_refinement_prompt
    partial = {
        "response_distributions": {"go": {"distribution": "ex_gaussian", "value": {"mu": 500, "sigma": 50, "tau": 100}}},
        "performance": {"accuracy": {"go": 0.95}},
        "temporal_effects": {"post_event_slowing": {"value": {"enabled": True, "triggers": ["error"]}}},
    }
    failing_slots = ["temporal_effects.post_event_slowing"]
    prompt = _render_slot_refinement_prompt(partial, failing_slots, [])

    # The validated content must appear in the locked-context section.
    assert "response_distributions" in prompt
    assert "performance" in prompt
```

- [ ] **Step 2: Run tests to confirm they fail (function not defined)**

```bash
uv run pytest tests/test_stage2_refinement_locks.py::test_render_slot_refinement_prompt_includes_failing_slots -v 2>&1 | tail -10
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `_render_slot_refinement_prompt`**

Add to `src/experiment_bot/reasoner/stage2_behavioral.py` (after `_extract_failing_slots`):

```python
def _render_slot_refinement_prompt(
    partial: dict,
    failing_slots: list[str],
    errors: list[tuple[str, str]],
) -> str:
    """Build the refinement prompt for slot-locked refinement.

    Sections:
    1. Previously-validated context (locked): every top-level partial
       field, except those listed in failing_slots, serialized as JSON.
       The LLM is instructed not to modify these.
    2. Failing slots: one line per slot, with the validation error
       messages that surfaced for that slot.
    3. Schema reminder: re-iterates that the prompt's existing
       'Concrete shape examples' section is the canonical source for
       the failing slots' shapes.
    """
    locked_partial = _strip_failing_slots(partial, failing_slots)
    locked_json = json.dumps(locked_partial, indent=2, sort_keys=True)

    error_lines = []
    for slot in failing_slots:
        slot_errors = [
            (p, m) for p, m in errors
            if p.startswith(slot + ".") or p == slot
        ]
        for path, msg in slot_errors:
            error_lines.append(f"  - {path}: {msg}")

    return (
        "## Previously-validated context (do NOT modify)\n"
        "These fields already passed schema validation. Treat them as fixed; "
        "do NOT regenerate them in your response. Your response should "
        "contain ONLY the failing slots listed below.\n\n"
        "```json\n" + locked_json + "\n```\n\n"
        "## Failing slots to fix\n"
        "Regenerate these top-level slots (and only these slots) in your "
        "response. The schema validator's diagnostics for each:\n\n"
        + "\n".join(f"### {slot}" for slot in failing_slots)
        + "\n\nValidation errors:\n"
        + "\n".join(error_lines)
        + "\n\n## Schema reminder\n"
        "The shape requirements for each failing slot are documented in "
        "the 'Concrete shape examples' section of the system prompt. "
        "Use the schema-example blocks verbatim as templates; do NOT "
        "emit any of the schema-anti-example shapes.\n\n"
        "Return a JSON object containing only the failing slots, each "
        "at the same nesting level it appears in the partial above:\n\n"
        "```json\n"
        "{\n"
        + ",\n".join(f'  "{slot.split(".")[0]}": {{ ... }}' for slot in failing_slots[:1])
        + "\n}\n"
        "```\n"
    )


def _strip_failing_slots(partial: dict, failing_slots: list[str]) -> dict:
    """Return a deep copy of partial with each failing slot replaced
    by a placeholder marker (so the LLM sees the slot's location
    without the previous failed content)."""
    out = copy.deepcopy(partial)
    for slot in failing_slots:
        segments = slot.split(".")
        node = out
        for k in segments[:-1]:
            if k not in node or not isinstance(node[k], dict):
                # Slot not present in partial — nothing to strip.
                node = None
                break
            node = node[k]
        if node is None:
            continue
        last = segments[-1]
        if last in node:
            node[last] = "<<TO BE REGENERATED — see failing slots below>>"
    return out
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
uv run pytest tests/test_stage2_refinement_locks.py -v 2>&1 | tail -10
```

Expected: all tests PASS (8 from Task 7 + 2 new = 10).

- [ ] **Step 5: Confirm full suite passes**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 490 passed, 1 skipped (488 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage2_behavioral.py tests/test_stage2_refinement_locks.py
git commit -m "feat(stage2): _render_slot_refinement_prompt for slot-locked refinement

Builds the refinement prompt with three sections: locked validated
context (LLM instructed not to modify), failing slot list with
per-error diagnostics, and a schema reminder pointing at the prompt's
canonical shape examples. Validated slots are preserved as-is in the
prompt so the LLM sees them but does not regenerate them."
```

---

## Task 9: Wire up slot-locked refinement in `run_stage2`

**Files:**
- Modify: `src/experiment_bot/reasoner/stage2_behavioral.py:74-136`
- Test: `tests/test_stage2_refinement_locks.py` (extend)

The refinement loop currently regenerates the entire Stage 2 output on each retry. This task replaces that with the slot-locked approach using the helpers from Tasks 7-8.

- [ ] **Step 1: Write integration test using a stub LLM client**

Append to `tests/test_stage2_refinement_locks.py`:

```python
class _StubClient:
    """Returns scripted text responses; tracks user prompts received."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts_received: list[str] = []

    async def complete(self, system, user, output_format=None):
        from types import SimpleNamespace
        self.prompts_received.append(user)
        if not self._responses:
            raise AssertionError("StubClient: out of scripted responses")
        return SimpleNamespace(text=self._responses.pop(0))


@pytest.mark.asyncio
async def test_stage2_slot_locked_refinement_converges():
    """Initial response has a failing post_event_slowing trigger;
    refinement response fixes only that slot. The merged partial
    validates."""
    import json
    from experiment_bot.reasoner.stage2_behavioral import run_stage2

    initial = {
        "response_distributions": {
            "go": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 50, "tau": 100},
                "rationale": "norms",
            }
        },
        "performance_omission_rate": {"go": 0.02},
        "temporal_effects": {
            "post_event_slowing": {
                "value": {"enabled": True, "triggers": ["error"]},  # invalid: bare string
                "rationale": "PES",
            }
        },
        "between_subject_jitter": {"value": {}},
    }
    refinement = {
        "temporal_effects": {
            "post_event_slowing": {
                "value": {
                    "enabled": True,
                    "triggers": [{"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}],
                },
                "rationale": "PES",
            }
        }
    }
    client = _StubClient([json.dumps(initial), json.dumps(refinement)])

    stage1_partial = {
        "task": {"name": "test", "paradigm_classes": ["conflict"]},
        "stimuli": [],
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.9},
    }
    result, step = await run_stage2(client, stage1_partial)

    # Validation should have passed on attempt 2.
    assert result["temporal_effects"]["post_event_slowing"]["value"]["triggers"][0]["event"] == "error"
    # Refinement prompt should mention the locked context (e.g.,
    # response_distributions present in second prompt).
    assert "response_distributions" in client.prompts_received[1]
    assert "do NOT modify" in client.prompts_received[1]


@pytest.mark.asyncio
async def test_stage2_slot_locked_refinement_does_not_reprompt_passing_slots():
    """If a slot validates on attempt 1, attempt 2's refinement prompt
    should not list that slot as a failing slot."""
    import json
    from experiment_bot.reasoner.stage2_behavioral import run_stage2

    # Initial: post_event_slowing is wrong; performance.accuracy is FINE.
    initial = {
        "response_distributions": {
            "go": {
                "distribution": "ex_gaussian",
                "value": {"mu": 500, "sigma": 50, "tau": 100},
                "rationale": "norms",
            }
        },
        "performance_omission_rate": {"go": 0.02},
        "temporal_effects": {
            "post_event_slowing": {
                "value": {"enabled": True, "triggers": ["error"]},
                "rationale": "PES",
            }
        },
        "between_subject_jitter": {"value": {}},
    }
    refinement = {
        "temporal_effects": {
            "post_event_slowing": {
                "value": {
                    "enabled": True,
                    "triggers": [{"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}],
                },
                "rationale": "PES",
            }
        }
    }
    client = _StubClient([json.dumps(initial), json.dumps(refinement)])

    stage1_partial = {
        "task": {"name": "test", "paradigm_classes": ["conflict"]},
        "stimuli": [],
        "performance": {"accuracy": {"go": 0.95}, "omission_rate": {"go": 0.02}, "practice_accuracy": 0.9},
    }
    await run_stage2(client, stage1_partial)

    # The second prompt's "Failing slots to fix" section must NOT list performance.accuracy.
    refine_prompt = client.prompts_received[1]
    failing_section = refine_prompt.split("## Failing slots to fix", 1)[1].split("## Schema reminder", 1)[0]
    assert "performance.accuracy" not in failing_section
    assert "temporal_effects.post_event_slowing" in failing_section
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
uv run pytest tests/test_stage2_refinement_locks.py::test_stage2_slot_locked_refinement_converges -v 2>&1 | tail -10
```

Expected: FAIL — current `run_stage2` re-prompts the whole Stage 2, not slot-locked.

- [ ] **Step 3: Refactor `run_stage2`'s refinement loop**

Edit `src/experiment_bot/reasoner/stage2_behavioral.py`. Replace the contents of the `for attempt in range(...)` loop (currently L74-136) with the slot-locked version. The full replacement of the loop body:

```python
    n_refinements = 0
    last_errors: list[tuple[str, str]] = []
    candidate: dict | None = None
    for attempt in range(1, STAGE2_MAX_REFINEMENTS + 1):
        resp = await client.complete(system=system, user=user_msg, output_format="json")
        try:
            response_json = json.loads(_extract_json(resp.text))
        except json.JSONDecodeError as e:
            n_refinements = attempt
            if attempt == STAGE2_MAX_REFINEMENTS:
                logger.warning(
                    "Stage 2 still produced unparseable JSON after %d "
                    "attempts; surfacing error.", attempt,
                )
                raise
            logger.info(
                "Stage 2 attempt %d returned non-parseable JSON; refining. "
                "Error: %s", attempt, e,
            )
            user_msg = (
                user
                + "\n\n## Parse error from previous attempt\n"
                "Your previous output could not be parsed as JSON: "
                f"`{e.msg}` at line {e.lineno}, column {e.colno}. "
                "Regenerate the complete Stage 2 JSON, ensuring valid "
                "syntax (no trailing commas, all strings closed, no "
                "unterminated objects/arrays).\n"
            )
            continue

        if attempt == 1:
            # First pass: response is the full Stage 2 output. Build
            # the full candidate partial.
            candidate = copy.deepcopy(partial)
            candidate["response_distributions"] = response_json["response_distributions"]
            candidate["temporal_effects"] = response_json.get("temporal_effects", {})
            candidate["between_subject_jitter"] = response_json.get("between_subject_jitter", {})
            # performance_omission_rate is folded back into performance
            # block at the end of run_stage2 (existing convention).
            om = response_json.get("performance_omission_rate", {})
            candidate.setdefault("performance", {})["omission_rate"] = om
        else:
            # Refinement pass: response contains ONLY the failing slots.
            # Merge each into the previous candidate.
            assert candidate is not None
            for slot in _extract_failing_slots(last_errors):
                head, _, sub = slot.partition(".")
                if sub:
                    candidate.setdefault(head, {})[sub] = response_json.get(head, {}).get(sub)
                else:
                    candidate[head] = response_json.get(head)

        try:
            validate_stage2_schema(candidate)
            # Validation passed.
            break
        except Stage2SchemaError as e:
            n_refinements = attempt
            last_errors = e.errors
            if attempt == STAGE2_MAX_REFINEMENTS:
                logger.warning(
                    "Stage 2 still has schema violations after %d refinement "
                    "attempts; surfacing error.", attempt,
                )
                raise
            failing_slots = _extract_failing_slots(e.errors)
            logger.info(
                "Stage 2 attempt %d failed schema validation; refining "
                "%d slot(s): %s. Errors:\n%s",
                attempt, len(failing_slots), failing_slots, str(e),
            )
            user_msg = _render_slot_refinement_prompt(
                candidate, failing_slots, e.errors,
            )
            continue
```

Note: this drops the previous `behavioral` local variable in favor of `response_json`; the post-loop code that reads `behavioral.get(...)` (currently L139-150) needs corresponding edits — replace with reads from `candidate` directly. Specifically:

```python
    # After the loop, candidate holds the validated partial.
    result = candidate

    n_conditions = len(candidate.get("response_distributions", {}))
    n_effects_enabled = sum(
        1 for e in candidate.get("temporal_effects", {}).values()
        if (e.get("value", {}) if isinstance(e.get("value"), dict) else {}).get("enabled")
    )
    inference = (
        f"Produced ex-Gaussian (mu/sigma/tau) parameters for {n_conditions} "
        f"conditions; enabled {n_effects_enabled} temporal effects."
    )
```

- [ ] **Step 4: Run all Stage 2 tests to confirm pass**

```bash
uv run pytest tests/test_stage2_refinement_locks.py tests/test_stage2_envelope.py tests/test_prompt_schema_consistency.py -v 2>&1 | tail -25
```

Expected: all pass.

- [ ] **Step 5: Confirm full suite passes (likely catches a regression in existing test_stage2_behavioral.py if any)**

```bash
uv run pytest 2>&1 | tail -3
```

Expected: 492 passed, 1 skipped (490 + 2 new). If existing `test_stage2_behavioral.py` tests fail, inspect — they may be asserting the old re-prompt-everything behavior and need updating to the new slot-locked behavior.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage2_behavioral.py tests/test_stage2_refinement_locks.py
git commit -m "feat(stage2): slot-locked refinement loop in run_stage2

Replaces full-Stage-2 regeneration on each refinement attempt with a
slot-locked approach: validated slots appear as 'do NOT modify'
context in the refinement prompt; the LLM regenerates only the
failing slots; results are merged into the candidate. Eliminates
the cross-attempt regression observed in SP3 (where attempt 2 fixed
A and B, then attempt 3 regressed A while leaving C broken)."
```

---

## Task 10: Full-suite regression check

**Files:**
- None modified

Final pre-re-run sanity check. Confirms no regressions in the existing 468 tests after Tasks 2-9 land.

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest 2>&1 | tail -10
```

Expected: 492 passed, 1 skipped, no failures. If anything fails, fix before continuing — re-running SP3 with broken tests would muddy the held-out evidence.

- [ ] **Step 2: Confirm `git status` is clean**

```bash
git status
```

Expected: nothing to commit, working tree clean. (No artifacts from test runs should be committed.)

- [ ] **Step 3: No commit needed (verification only)**

---

## Task 11: Re-run SP3 — Flanker

**Files:**
- Working: `.reasoner-logs/sp4a_flanker_regen.log`
- Output (on success): `taskcards/expfactory_flanker/<hash>.json` + `pilot.md`

Same command as SP3 Task 2; same held-out URL. The held-out policy still applies: do NOT modify the prompt/schema/refinement-loop reactively. If this re-run still fails, document the new failure mode and let the next SP address it.

- [ ] **Step 1: Confirm clean state**

```bash
ls taskcards/expfactory_flanker/ 2>&1 || echo "(no taskcards yet — expected)"
ls .reasoner_work/expfactory_flanker/ 2>&1 || echo "(no stage partials)"
```

Expected: both absent. (Fresh sp4a worktree has no carryover from SP3.)

- [ ] **Step 2: Run the Reasoner**

```bash
mkdir -p .reasoner-logs
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/3/" \
  --label expfactory_flanker --pilot-max-retries 3 -v \
  > .reasoner-logs/sp4a_flanker_regen.log 2>&1
echo "exit=$?"
```

Wall time: 5–25 min same as SP3. Run as a background job in execution if available.

- [ ] **Step 3: Capture outcome**

```bash
echo "=== Flanker outcome ===" 
ls taskcards/expfactory_flanker/ 2>&1 || echo "(no TaskCard produced)"
echo "---"
grep -E "Stage [0-9]+ attempt|Stage2SchemaError|PilotValidationError" \
  .reasoner-logs/sp4a_flanker_regen.log | tail -30
echo "---"
grep -cE "Stage 2 attempt" .reasoner-logs/sp4a_flanker_regen.log | xargs -I{} echo "Stage 2 refinement attempts: {}"
```

The output goes into Task 13's report. Three possible outcomes:
- **Success:** TaskCard produced; Reasoner exits 0; ready for sessions (deferred to a future SP).
- **Stage 2 still fails with the same modes:** Tier 1 fixes did not resolve the failure modes — investigate (likely a missed edge case in slot logic or merge).
- **Stage 2 still fails with NEW modes:** held-out re-run surfaced a fifth failure mode beyond Tier 1's coverage. Document and let next SP address; do NOT iterate in SP4a.

- [ ] **Step 4: No commit yet** — combined commit happens after the n-back re-run (Task 12).

---

## Task 12: Re-run SP3 — n-back

**Files:**
- Working: `.reasoner-logs/sp4a_nback_regen.log`
- Output (on success): `taskcards/expfactory_n_back/<hash>.json` + `pilot.md`

Same command as SP3 Task 7.

- [ ] **Step 1: Run the Reasoner**

```bash
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/5/" \
  --label expfactory_n_back --pilot-max-retries 3 -v \
  > .reasoner-logs/sp4a_nback_regen.log 2>&1
echo "exit=$?"
```

- [ ] **Step 2: Capture outcome**

```bash
echo "=== n-back outcome ===" 
ls taskcards/expfactory_n_back/ 2>&1 || echo "(no TaskCard produced)"
echo "---"
grep -E "Stage [0-9]+ attempt|Stage2SchemaError|PilotValidationError" \
  .reasoner-logs/sp4a_nback_regen.log | tail -30
```

- [ ] **Step 3: Commit any TaskCards that were produced**

```bash
if compgen -G "taskcards/expfactory_*/*.json" >/dev/null; then
  git add taskcards/
  git commit -m "chore(sp4a): held-out TaskCards from re-run after Tier 1 fixes

Whichever paradigms produced a TaskCard during the SP4a re-run.
Provenance: post-SP4a-Tier-1 framework; same URLs as SP3."
fi
```

If no TaskCards were produced (both paradigms still fail), no commit yet. The failure trail is captured in `.reasoner-logs/sp4a_*_regen.log` (gitignored) and summarized in Task 13's report.

---

## Task 13: Write `docs/sp4a-results.md`

**Files:**
- Create: `docs/sp4a-results.md`

Descriptive report on the held-out re-run. Mirrors the structure of `docs/sp3-heldout-results.md` but covers SP4a's outcome.

- [ ] **Step 1: Gather data**

```bash
echo "=== SP4a re-run summary ===" 
for label in flanker nback; do
  log=".reasoner-logs/sp4a_${label}_regen.log"
  if [ ! -f "$log" ]; then continue; fi
  echo "[$label]"
  echo "  Stage 2 attempts: $(grep -c 'Stage 2 attempt' "$log")"
  echo "  Final outcome: $(grep -E 'Stage2SchemaError|exit=|PilotValidationError' "$log" | tail -1)"
  taskcard_dir="taskcards/expfactory_${label/nback/n_back}"
  if [ -d "$taskcard_dir" ]; then
    echo "  TaskCard: produced ($(ls "$taskcard_dir"/*.json 2>/dev/null | head -1))"
  else
    echo "  TaskCard: not produced"
  fi
done
```

- [ ] **Step 2: Write the report**

Create `docs/sp4a-results.md` with the structure below. The `<...>` placeholders are filled from Step 1's output and the actual `.reasoner-logs/` content.

```markdown
# SP4a — Stage 2 robustness held-out re-run results

**Date:** 2026-05-08 (or actual run date)
**Spec:** `docs/superpowers/specs/2026-05-08-sp4a-stage2-robustness-design.md`
**Branch:** `sp4a/stage2-robustness`
**Tag (after this report lands):** `sp4a-complete`

## Goal

Re-run the SP3 protocol (Flanker + n-back held-out paradigms) against the framework after Tier 1 fixes (envelope contradiction, schema-derived prompt examples, refinement-loop slot preservation) to provide descriptive evidence about whether the targeted Stage 2 failure modes are resolved.

## Procedure

1. Same URLs as SP3 (Flanker `https://deploy.expfactory.org/preview/3/`; n-back `https://deploy.expfactory.org/preview/5/`).
2. Same Reasoner command (`experiment-bot-reason --pilot-max-retries 3`).
3. No prompt or schema edits between SP3 and SP4a beyond the three Tier 1 fixes shipped in this branch.

## Outcome

| Paradigm | Stage 2 attempts | TaskCard produced? | Notes |
|---|---|---|---|
| Flanker | <count> | <yes/no> | <one-line summary of attempt-1 errors → attempt-N outcome> |
| n-back  | <count> | <yes/no> | <same> |

## Comparison vs SP3

| Failure mode | SP3 outcome | SP4a outcome |
|---|---|---|
| post_event_slowing trigger shape | persistent across 3 attempts in both paradigms | <resolved / persists / partial> |
| lag1 modulation_table field-name vocabulary (Flanker) | persistent | <resolved / persists> |
| performance.accuracy envelope contradiction (both) | persistent across 3 attempts | <resolved / persists> |
| key_map.rationale leak (n-back) | persistent across 3 attempts | <resolved / persists> |
| Cross-attempt regression in refinement loop | observed in both | <observed / not observed> |

## Reading

[Fill in: which Tier 1 fix appeared to do most of the work; which residual modes (if any) need future SP work; whether the held-out paradigms now operationally pass.]

## Residual gaps (next SP backlog candidates)

[List any new failure modes surfaced. If none, write: "No new failure modes; SP4a's Tier 1 fixes appear sufficient for both held-out paradigms."]

## Status

Internal CI gate: [PASS/FAIL — refer to test suite outcome at the SP4a-complete tag commit]. The four documented Tier 1 failure modes have unit-test coverage proving the fix on captured fixtures.

External descriptive evidence: see Outcome table above. Held-out generalization claim is [strengthened/unchanged/further weakened] by this re-run.

Tag `sp4a-complete` on this commit. Next sub-project (if needed) addresses any residual gaps surfaced here.
```

Replace each `<placeholder>` with the actual numbers and prose from the runs. Replace `[Fill in: ...]` sections with paragraph-form discussion.

- [ ] **Step 3: Sanity-check no placeholders remain**

```bash
grep -nE "<count>|<yes/no>|<resolved|<observed|\[Fill in" docs/sp4a-results.md
```

Expected: no output. If any remain, fill them in.

- [ ] **Step 4: Commit**

```bash
git add docs/sp4a-results.md
git commit -m "docs(sp4a): held-out re-run results after Tier 1 fixes

Descriptive report on SP3 re-run outcome. Per the SP4a spec, the
held-out outcome is the scientific contribution about generalization,
not the engineering gate."
```

---

## Task 14: Tag, push, update CLAUDE.md

**Files:**
- Tag: `sp4a-complete`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify clean state**

```bash
git status
uv run pytest 2>&1 | tail -3
```

Expected: clean working tree, all tests passing.

- [ ] **Step 2: Tag the milestone**

```bash
git tag -a sp4a-complete -m "$(cat <<'EOF'
SP4a (Stage 2 robustness, Tier 1) — milestone tag

Three Tier 1 fixes from docs/sp4-stage2-robustness.md shipped:
1.1 refinement-loop preserves validated slots (slot-locked
    refinement; eliminates cross-attempt regression)
1.2 schema-derived prompt examples + invariant test for drift
    protection (anti-examples cover the four SP3 failure modes)
1.3 performance.* envelope contradiction resolved (schema accepts
    oneOf bare-number-or-envelope; loader and validator unwrap)

Internal: 22 new tests covering envelopes, prompt-schema invariants,
slot extraction, slot-locked refinement.

External: SP3 re-run on Flanker + n-back. Outcome reported in
docs/sp4a-results.md as descriptive evidence about generalization.
EOF
)"
```

- [ ] **Step 3: Push branch + tag**

```bash
git push -u origin sp4a/stage2-robustness
git push origin sp4a-complete
```

- [ ] **Step 4: Update CLAUDE.md sub-project history**

Edit `CLAUDE.md`. Find the SP4 entry (added in SP3's CLAUDE.md update — currently says "(planned)") and replace with:

```markdown
- **SP4a**: Stage 2 robustness Tier 1 — refinement-loop slot
  preservation, schema-derived prompt examples with invariant test,
  performance.* envelope contradiction resolved. Held-out re-run
  results in `docs/sp4a-results.md`. ✓ Complete.
- **SP4** (continuing): backlog at `docs/sp4-stage2-robustness.md`.
  Tier 2/3 items (canonicalization layer, two-pass Stage 2 split,
  schema-as-canonical autogeneration) remain. Each is its own
  brainstorm/spec/plan cycle when prioritized.
```

- [ ] **Step 5: Commit and push CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): mark SP4a complete; SP4 continuing backlog

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Self-review checklist

- **Spec § Goal**: Tasks 2-9 ship the three Tier 1 fixes; Tasks 11-12 re-run SP3.
- **Spec § Success criterion (internal)**: each of the four failure modes has unit-test coverage in `test_stage2_envelope.py` (envelope), `test_prompt_schema_consistency.py` (post_event_slowing/lag1/key_map example shapes), `test_stage2_refinement_locks.py` (slot extraction + locked refinement). All four covered.
- **Spec § Success criterion (external)**: Tasks 11-12 + Task 13 produce `docs/sp4a-results.md`.
- **Spec § Architecture**: schema (Task 2), validator (Task 3), loader (Task 4), prompt (Task 5), invariant test (Task 6), refinement-loop helpers (Tasks 7-8), wired-up loop (Task 9). All five touch-points addressed.
- **Spec § Test strategy**: four files match the four-test-file plan in the spec — `test_stage2_envelope.py` (Tasks 2-4), `test_prompt_schema_consistency.py` (Task 6), `test_stage2_refinement_locks.py` (Tasks 7-9). Existing `test_stage2_behavioral.py` is run via the full-suite check (Task 10).
- **Spec § Out of scope**: no tasks for canonicalization layer, two-pass split, autogeneration, divergence-aware budget, or new held-out paradigms. ✓
- **Spec § Sub-project boundary check**: deliverables match spec; one bounded change set; one pre-defined success criterion; clear "next SP for new modes" rule. ✓

---

## Notes for the implementing engineer

- Held-out policy is binding: if Tasks 11-12 reveal a fifth failure mode beyond the four documented Tier 1 modes, write it up in Task 13's report and stop. Do NOT iterate on the prompt or schema in SP4a to chase a held-out pass.
- The slot-extraction rule in Task 7 has five patterns covering the entire current schema. If the schema grows new top-level fields in the future, `_SLOT_RULES` needs corresponding entries — this is a known maintenance touchpoint, not a one-time fix.
- The Reasoner runs in Tasks 11-12 take 5–25 min wall time each. Budget accordingly when executing; running both in parallel (different Reasoner labels can coexist) is safe but typically not necessary for SP4a.
- The fixtures in Task 1 are hand-crafted, not LLM outputs. They reproduce the failure SHAPES from `docs/sp3-heldout-results.md`. If the actual SP3 LLM outputs become available later (e.g., from a re-run with response logging), they can replace the hand-crafted fixtures in a future maintenance commit.

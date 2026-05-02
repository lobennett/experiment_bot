# SP1 — TaskCard + Reasoner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1 `cache/{label}/config.json` artifact with a peer-reviewable `taskcards/{label}/{hash}.json` artifact, produce it via a 5-stage Reasoner that uses Claude Max CLI by default with API-key fallback, and migrate the 4 existing development tasks to v2 TaskCards.

**Architecture:** Layered. `LLMClient` Protocol with two implementations (CLI subprocess via `claude --print`, and `anthropic.AsyncAnthropic`). Reasoner is 5 chained stages (structural → behavioral → citations → DOI verify → sensitivity), each appending to a partial TaskCard with `--resume` semantics. Executor adaptation is minimal: `taskcard_loader.py` replaces `cache.py`; `sample_session_params(taskcard, seed)` replaces `jitter_distributions(config)` for distributional parameters. The legacy `between_subject_jitter` for orthogonal effects (accuracy, omission, sigma_tau scaling) stays.

**Tech Stack:** Python 3.12, uv, anthropic SDK, claude CLI, httpx (for OpenAlex), pytest, hypothesis. Existing 232-test suite stays green throughout; expected end-state ~280 tests.

**Spec:** `docs/superpowers/specs/2026-04-23-taskcard-reasoner-design.md`

---

## File structure

**Created (new):**

```
src/experiment_bot/taskcard/__init__.py
src/experiment_bot/taskcard/types.py             # Dataclasses: Citation, ParameterValue, ReasoningStep, ProducedBy, TaskCard
src/experiment_bot/taskcard/hashing.py           # canonical_json_dumps, taskcard_sha256
src/experiment_bot/taskcard/loader.py            # load_latest, load_by_hash, save (replaces core/cache.py)
src/experiment_bot/taskcard/sampling.py          # sample_session_params(taskcard, seed)

src/experiment_bot/llm/__init__.py
src/experiment_bot/llm/protocol.py               # LLMClient Protocol + LLMResponse
src/experiment_bot/llm/api_client.py             # ClaudeAPIClient
src/experiment_bot/llm/cli_client.py             # ClaudeCLIClient
src/experiment_bot/llm/factory.py                # build_default_client()

src/experiment_bot/reasoner/__init__.py
src/experiment_bot/reasoner/openalex.py          # verify_doi(doi) → bool, dict
src/experiment_bot/reasoner/stage1_structural.py # produces stimuli/navigation/runtime
src/experiment_bot/reasoner/stage2_behavioral.py # produces value/accuracy/temporal_effects
src/experiment_bot/reasoner/stage3_citations.py  # produces citations + ranges + SDs
src/experiment_bot/reasoner/stage4_doi_verify.py # marks doi_verified
src/experiment_bot/reasoner/stage5_sensitivity.py# tags sensitivity per parameter
src/experiment_bot/reasoner/pipeline.py          # orchestrates stages with resume
src/experiment_bot/reasoner/cli.py               # `experiment-bot-reason` entry point
src/experiment_bot/reasoner/prompts/stage2_behavioral.md
src/experiment_bot/reasoner/prompts/stage3_citations.md
src/experiment_bot/reasoner/prompts/stage5_sensitivity.md

tests/test_taskcard_types.py
tests/test_taskcard_hashing.py
tests/test_taskcard_loader.py
tests/test_taskcard_sampling.py
tests/test_llm_protocol.py
tests/test_llm_api_client.py
tests/test_llm_cli_client.py
tests/test_llm_factory.py
tests/test_reasoner_openalex.py
tests/test_reasoner_stage1.py
tests/test_reasoner_stage2.py
tests/test_reasoner_stage3.py
tests/test_reasoner_stage4.py
tests/test_reasoner_stage5.py
tests/test_reasoner_pipeline.py
tests/test_reasoner_cli.py
tests/fixtures/fake_llm_responses.py             # canned LLM responses for staged tests
```

**Modified:**

```
src/experiment_bot/cli.py                        # use taskcard_loader instead of ConfigCache
src/experiment_bot/core/executor.py              # accept TaskCard; sample via sample_session_params
src/experiment_bot/core/distributions.py         # carve out distributional jitter into sample_session_params
src/experiment_bot/core/analyzer.py              # delegated to reasoner.pipeline; remains for compat
pyproject.toml                                   # add httpx (likely already transitive)
```

**Deleted:**

```
src/experiment_bot/core/cache.py                 # replaced by taskcard/loader.py
cache/cognitionrun_stroop/config.json            # regenerated as taskcards/cognitionrun_stroop/{hash}.json
cache/expfactory_stop_signal/config.json         # regenerated
cache/expfactory_stroop/config.json              # regenerated
cache/stopit_stop_signal/config.json             # regenerated
```

---

## Phase A — Foundation (no live LLM)

Goal: types, hashing, sampling, LLM clients, OpenAlex verifier, all unit-tested. Test suite at end of phase: ~232 + ~30 new = 262 passing.

### Task A1: TaskCard type definitions

**Files:**
- Create: `src/experiment_bot/taskcard/__init__.py` (empty)
- Create: `src/experiment_bot/taskcard/types.py`
- Test: `tests/test_taskcard_types.py`

- [ ] **Step 1: Write the failing test for Citation round-trip**

```python
# tests/test_taskcard_types.py
from experiment_bot.taskcard.types import Citation


def test_citation_round_trip():
    data = {
        "doi": "10.1016/j.cognition.2008.07.011",
        "authors": "Whelan, R.",
        "year": 2008,
        "title": "Effective analysis of reaction time data",
        "table_or_figure": "Table 2",
        "page": 481,
        "quote": "Healthy adults on go trials: mu=460 ms",
        "confidence": "high",
        "doi_verified": False,
        "doi_verified_at": None,
    }
    c = Citation.from_dict(data)
    assert c.to_dict() == data
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/test_taskcard_types.py::test_citation_round_trip -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement Citation**

```python
# src/experiment_bot/taskcard/types.py
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
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/test_taskcard_types.py::test_citation_round_trip -v`
Expected: PASS.

- [ ] **Step 5: Add tests for ParameterValue, ReasoningStep, ProducedBy**

```python
# tests/test_taskcard_types.py (append)
from experiment_bot.taskcard.types import ParameterValue, ReasoningStep, ProducedBy


def test_parameter_value_round_trip():
    data = {
        "value": {"mu": 480, "sigma": 60, "tau": 80},
        "literature_range": {"mu": [430, 530], "sigma": [40, 80], "tau": [50, 110]},
        "between_subject_sd": {"mu": 50, "sigma": 10, "tau": 20},
        "citations": [],
        "rationale": "Whelan 2008 norms",
        "sensitivity": "high",
    }
    pv = ParameterValue.from_dict(data)
    rt = pv.to_dict()
    assert rt["value"] == data["value"]
    assert rt["literature_range"] == data["literature_range"]
    assert rt["sensitivity"] == "high"


def test_reasoning_step_round_trip():
    data = {
        "step": "task_identification",
        "input_hash": "abc",
        "inference": "this is a stop-signal task",
        "evidence_lines": ["main.js line 47"],
        "confidence": "high",
    }
    rs = ReasoningStep.from_dict(data)
    assert rs.to_dict() == data


def test_produced_by_round_trip():
    data = {
        "model": "claude-opus-4-7",
        "prompt_sha256": "deadbeef",
        "scraper_version": "1.2.0",
        "source_sha256": "feedface",
        "timestamp": "2026-04-23T12:00:00Z",
        "taskcard_sha256": "789xyz",
    }
    pb = ProducedBy.from_dict(data)
    assert pb.to_dict() == data
```

- [ ] **Step 6: Implement ParameterValue, ReasoningStep, ProducedBy**

```python
# src/experiment_bot/taskcard/types.py (append)
@dataclass
class ParameterValue:
    value: dict
    literature_range: dict | None = None
    between_subject_sd: dict | None = None
    citations: list[Citation] = field(default_factory=list)
    rationale: str = ""
    sensitivity: Literal["high", "medium", "low", "unknown"] = "unknown"

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
```

- [ ] **Step 7: Add tests for TaskCard top-level round-trip**

```python
# tests/test_taskcard_types.py (append)
from experiment_bot.taskcard.types import TaskCard


def _minimal_taskcard_dict() -> dict:
    return {
        "schema_version": "2.0",
        "produced_by": {
            "model": "claude-opus-4-7",
            "prompt_sha256": "x",
            "scraper_version": "1.0.0",
            "source_sha256": "y",
            "timestamp": "2026-04-23T12:00:00Z",
            "taskcard_sha256": "",
        },
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "navigation": {"phases": []},
        "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {},
        "temporal_effects": {},
        "between_subject_jitter": {},
        "reasoning_chain": [],
        "pilot_validation": {"passed": True, "iterations": 0, "trials_completed": 0},
    }


def test_taskcard_round_trip_minimal():
    data = _minimal_taskcard_dict()
    tc = TaskCard.from_dict(data)
    out = tc.to_dict()
    assert out["schema_version"] == "2.0"
    assert out["produced_by"]["model"] == "claude-opus-4-7"
```

- [ ] **Step 8: Implement TaskCard top-level**

```python
# src/experiment_bot/taskcard/types.py (append)
from experiment_bot.core.config import (
    TaskMetadata, StimulusConfig, NavigationConfig, RuntimeConfig,
    PerformanceConfig, TemporalEffectsConfig, BetweenSubjectJitterConfig,
    PilotConfig,
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
    """Wrap a v1 DistributionConfig dict into a ParameterValue with empty provenance."""
    return ParameterValue(
        value=d.get("params", {}),
        literature_range=None,
        between_subject_sd=None,
        citations=[],
        rationale="",
        sensitivity="unknown",
    )


def _wrap_legacy_effect(d: dict) -> ParameterValue:
    """Wrap a v1 temporal-effect dict into a ParameterValue."""
    return ParameterValue(
        value={k: v for k, v in d.items() if k not in ("rationale",)},
        literature_range=None,
        between_subject_sd=None,
        citations=[],
        rationale=d.get("rationale", ""),
        sensitivity="unknown",
    )
```

- [ ] **Step 9: Run all type tests**

Run: `uv run pytest tests/test_taskcard_types.py -v`
Expected: 4 tests pass.

- [ ] **Step 10: Commit**

```bash
git add src/experiment_bot/taskcard/__init__.py src/experiment_bot/taskcard/types.py tests/test_taskcard_types.py
git commit -m "feat(taskcard): add TaskCard, ParameterValue, Citation, ReasoningStep, ProducedBy types

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A2: TaskCard canonical hashing

**Files:**
- Create: `src/experiment_bot/taskcard/hashing.py`
- Test: `tests/test_taskcard_hashing.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_taskcard_hashing.py
from experiment_bot.taskcard.hashing import canonical_json_dumps, taskcard_sha256


def test_canonical_json_stable_across_key_order():
    a = {"b": 1, "a": 2, "c": [1, 2, 3]}
    b = {"a": 2, "c": [1, 2, 3], "b": 1}
    assert canonical_json_dumps(a) == canonical_json_dumps(b)


def test_canonical_json_strips_extra_whitespace():
    a = canonical_json_dumps({"a": 1})
    assert "\n" not in a
    assert "  " not in a


def test_taskcard_sha256_excludes_hash_field():
    base = {"schema_version": "2.0", "produced_by": {"taskcard_sha256": "OLDHASH"}}
    h1 = taskcard_sha256(base)
    base["produced_by"]["taskcard_sha256"] = "DIFFERENTHASH"
    h2 = taskcard_sha256(base)
    assert h1 == h2  # hash field itself not part of hash


def test_taskcard_sha256_changes_on_content_change():
    a = {"schema_version": "2.0", "produced_by": {"taskcard_sha256": ""}, "task": {"name": "stroop"}}
    b = {"schema_version": "2.0", "produced_by": {"taskcard_sha256": ""}, "task": {"name": "flanker"}}
    assert taskcard_sha256(a) != taskcard_sha256(b)
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest tests/test_taskcard_hashing.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/taskcard/hashing.py
from __future__ import annotations
import copy
import hashlib
import json


def canonical_json_dumps(obj: dict) -> str:
    """Stable serialization: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def taskcard_sha256(taskcard_dict: dict) -> str:
    """sha256 over canonicalized TaskCard, with produced_by.taskcard_sha256 zeroed."""
    cloned = copy.deepcopy(taskcard_dict)
    cloned.setdefault("produced_by", {})["taskcard_sha256"] = ""
    payload = canonical_json_dumps(cloned).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest tests/test_taskcard_hashing.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/taskcard/hashing.py tests/test_taskcard_hashing.py
git commit -m "feat(taskcard): canonical JSON dumps and content-addressed hashing

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A3: TaskCard loader

**Files:**
- Create: `src/experiment_bot/taskcard/loader.py`
- Test: `tests/test_taskcard_loader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_taskcard_loader.py
import json
from pathlib import Path
import pytest
from experiment_bot.taskcard.loader import save_taskcard, load_latest, load_by_hash
from experiment_bot.taskcard.types import TaskCard


@pytest.fixture
def minimal_taskcard_dict():
    return {
        "schema_version": "2.0",
        "produced_by": {
            "model": "claude-opus-4-7",
            "prompt_sha256": "p",
            "scraper_version": "1.0.0",
            "source_sha256": "s",
            "timestamp": "2026-04-23T12:00:00Z",
            "taskcard_sha256": "",
        },
        "task": {"name": "stroop", "constructs": [], "reference_literature": []},
        "stimuli": [],
        "navigation": {"phases": []},
        "runtime": {},
        "task_specific": {},
        "performance": {"accuracy": {"default": 0.95}},
        "response_distributions": {},
        "temporal_effects": {},
        "between_subject_jitter": {},
        "reasoning_chain": [],
        "pilot_validation": {},
    }


def test_save_writes_hashed_filename(tmp_path, minimal_taskcard_dict):
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    path = save_taskcard(tc, tmp_path / "taskcards", label="stroop")
    assert path.exists()
    assert path.parent == tmp_path / "taskcards" / "stroop"
    assert path.suffix == ".json"
    # filename is first 8 chars of hash
    assert len(path.stem) == 8


def test_save_updates_taskcard_sha256(tmp_path, minimal_taskcard_dict):
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    assert tc.produced_by.taskcard_sha256 == ""
    path = save_taskcard(tc, tmp_path / "taskcards", label="stroop")
    loaded = json.loads(path.read_text())
    assert loaded["produced_by"]["taskcard_sha256"] != ""
    assert path.stem == loaded["produced_by"]["taskcard_sha256"][:8]


def test_load_latest_returns_most_recent(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    p1 = save_taskcard(tc, base, label="stroop")
    minimal_taskcard_dict["task"]["name"] = "stroop_v2"
    tc2 = TaskCard.from_dict(minimal_taskcard_dict)
    p2 = save_taskcard(tc2, base, label="stroop")
    latest = load_latest(base, label="stroop")
    assert latest.task.name == "stroop_v2"


def test_load_by_hash(tmp_path, minimal_taskcard_dict):
    base = tmp_path / "taskcards"
    tc = TaskCard.from_dict(minimal_taskcard_dict)
    path = save_taskcard(tc, base, label="stroop")
    loaded = load_by_hash(base, label="stroop", hash_prefix=path.stem)
    assert loaded.schema_version == "2.0"


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest(tmp_path / "taskcards", label="nonexistent")
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/taskcard/loader.py
from __future__ import annotations
import json
from pathlib import Path
from experiment_bot.taskcard.hashing import taskcard_sha256
from experiment_bot.taskcard.types import TaskCard


def save_taskcard(tc: TaskCard, base_dir: Path, label: str) -> Path:
    """Compute hash, name file by first 8 hex chars, write JSON."""
    out_dir = base_dir / label
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = tc.to_dict()
    h = taskcard_sha256(payload)
    payload["produced_by"]["taskcard_sha256"] = h
    out_path = out_dir / f"{h[:8]}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def load_latest(base_dir: Path, label: str) -> TaskCard:
    """Load most recently modified TaskCard for a label."""
    out_dir = base_dir / label
    if not out_dir.exists():
        raise FileNotFoundError(f"No TaskCards directory for label '{label}' at {out_dir}")
    candidates = sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No TaskCards in {out_dir}")
    return TaskCard.from_dict(json.loads(candidates[0].read_text()))


def load_by_hash(base_dir: Path, label: str, hash_prefix: str) -> TaskCard:
    """Load TaskCard by hash prefix (typically the first 8 hex chars)."""
    candidates = list((base_dir / label).glob(f"{hash_prefix}*.json"))
    if not candidates:
        raise FileNotFoundError(f"No TaskCard matching {hash_prefix} in {base_dir / label}")
    if len(candidates) > 1:
        raise ValueError(f"Multiple TaskCards match {hash_prefix}: {candidates}")
    return TaskCard.from_dict(json.loads(candidates[0].read_text()))
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/taskcard/loader.py tests/test_taskcard_loader.py
git commit -m "feat(taskcard): hash-named loader with save/load_latest/load_by_hash

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A4: sample_session_params

**Files:**
- Create: `src/experiment_bot/taskcard/sampling.py`
- Test: `tests/test_taskcard_sampling.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_taskcard_sampling.py
import numpy as np
from experiment_bot.taskcard.sampling import sample_session_params


def _tc_dict_with_dist(value, lit_range, sd):
    return {
        "response_distributions": {
            "go": {
                "value": value,
                "literature_range": lit_range,
                "between_subject_sd": sd,
            }
        }
    }


def test_sample_returns_value_when_sd_zero():
    tc = _tc_dict_with_dist(
        value={"mu": 480, "sigma": 60, "tau": 80},
        lit_range=None,
        sd=None,
    )
    out = sample_session_params(tc, seed=42)
    assert out["go"]["mu"] == 480.0
    assert out["go"]["sigma"] == 60.0
    assert out["go"]["tau"] == 80.0


def test_sample_is_deterministic_for_seed():
    tc = _tc_dict_with_dist(
        value={"mu": 480, "sigma": 60, "tau": 80},
        lit_range=None,
        sd={"mu": 50, "sigma": 10, "tau": 20},
    )
    a = sample_session_params(tc, seed=42)
    b = sample_session_params(tc, seed=42)
    assert a == b


def test_sample_clips_to_literature_range():
    tc = _tc_dict_with_dist(
        value={"mu": 480, "sigma": 60, "tau": 80},
        lit_range={"mu": [470, 490], "sigma": [55, 65], "tau": [75, 85]},
        sd={"mu": 1000, "sigma": 1000, "tau": 1000},  # huge SD, will overshoot
    )
    out = sample_session_params(tc, seed=0)
    assert 470 <= out["go"]["mu"] <= 490
    assert 55 <= out["go"]["sigma"] <= 65
    assert 75 <= out["go"]["tau"] <= 85


def test_sample_handles_missing_param():
    tc = {"response_distributions": {"go": {"value": {"mu": 480}}}}  # only mu
    out = sample_session_params(tc, seed=0)
    assert out["go"] == {"mu": 480.0}
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/taskcard/sampling.py
from __future__ import annotations
import numpy as np


def sample_session_params(taskcard: dict, seed: int) -> dict:
    """Draw per-session distributional parameters from TaskCard.

    For each condition's distribution, draw a single value per parameter
    (mu, sigma, tau, ...) from N(value, between_subject_sd**2), clipped to
    literature_range when provided. Output is fed to the executor's
    ResponseSampler instead of the static config values.
    """
    rng = np.random.default_rng(seed)
    sampled: dict = {}
    for cond, dist in taskcard.get("response_distributions", {}).items():
        v = dist.get("value", {})
        r = dist.get("literature_range") or {}
        sd = dist.get("between_subject_sd") or {}
        sampled[cond] = {}
        for param, mean in v.items():
            spread = float(sd.get(param, 0))
            draw = rng.normal(float(mean), spread) if spread > 0 else float(mean)
            if param in r:
                lo, hi = r[param]
                draw = float(np.clip(draw, lo, hi))
            sampled[cond][param] = float(draw)
    return sampled
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Add Hypothesis property test**

Add to `pyproject.toml` if not present:

```toml
[tool.uv.dev-dependencies]
hypothesis = "*"
```

```python
# tests/test_taskcard_sampling.py (append)
from hypothesis import given, strategies as st


@given(
    mu=st.floats(min_value=200, max_value=1000),
    sigma=st.floats(min_value=10, max_value=200),
    tau=st.floats(min_value=10, max_value=300),
    sd_mu=st.floats(min_value=0, max_value=200),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_sample_property_finite_and_deterministic(mu, sigma, tau, sd_mu, seed):
    tc = {
        "response_distributions": {
            "go": {
                "value": {"mu": mu, "sigma": sigma, "tau": tau},
                "between_subject_sd": {"mu": sd_mu, "sigma": 0, "tau": 0},
            }
        }
    }
    a = sample_session_params(tc, seed=seed)
    b = sample_session_params(tc, seed=seed)
    assert a == b
    for k, v in a["go"].items():
        assert v == v  # not NaN
        assert v != float("inf") and v != float("-inf")
```

- [ ] **Step 6: Run, expect PASS**

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/taskcard/sampling.py tests/test_taskcard_sampling.py
git commit -m "feat(taskcard): sample_session_params with deterministic seeding and range clipping

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A5: LLMClient protocol + APIClient

**Files:**
- Create: `src/experiment_bot/llm/__init__.py` (empty)
- Create: `src/experiment_bot/llm/protocol.py`
- Create: `src/experiment_bot/llm/api_client.py`
- Test: `tests/test_llm_protocol.py`
- Test: `tests/test_llm_api_client.py`

- [ ] **Step 1: Write protocol structure test**

```python
# tests/test_llm_protocol.py
from experiment_bot.llm.protocol import LLMClient, LLMResponse


def test_llm_client_is_a_protocol():
    # Just import and confirm the surface is what callers expect.
    assert hasattr(LLMClient, "complete")


def test_llm_response_is_a_dataclass():
    r = LLMResponse(text="hi", stop_reason="end_turn")
    assert r.text == "hi"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement protocol**

```python
# src/experiment_bot/llm/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class LLMResponse:
    text: str
    stop_reason: str = "end_turn"


class LLMClient(Protocol):
    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
    ) -> LLMResponse:
        ...
```

- [ ] **Step 4: Write APIClient tests with mocked anthropic**

```python
# tests/test_llm_api_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from experiment_bot.llm.api_client import ClaudeAPIClient


@pytest.mark.asyncio
async def test_api_client_calls_anthropic_messages_create():
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text="response text")],
            stop_reason="end_turn",
        )
    )
    client = ClaudeAPIClient(client=fake, model="claude-opus-4-7")
    result = await client.complete(system="sys", user="usr")
    fake.messages.create.assert_called_once()
    kwargs = fake.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "usr"}]
    assert result.text == "response text"
```

- [ ] **Step 5: Implement APIClient**

```python
# src/experiment_bot/llm/api_client.py
from __future__ import annotations
from typing import Literal
from experiment_bot.llm.protocol import LLMResponse


class ClaudeAPIClient:
    def __init__(self, client, model: str = "claude-opus-4-7"):
        self._client = client
        self._model = model

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
    ) -> LLMResponse:
        # output_format is informational only for the API path; the prompt
        # itself instructs Claude to return JSON when desired.
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text
        return LLMResponse(text=text, stop_reason=getattr(resp, "stop_reason", "end_turn"))
```

- [ ] **Step 6: Run all LLM tests, expect PASS**

Run: `uv run pytest tests/test_llm_protocol.py tests/test_llm_api_client.py -v`

- [ ] **Step 7: Commit**

```bash
git add src/experiment_bot/llm/__init__.py src/experiment_bot/llm/protocol.py src/experiment_bot/llm/api_client.py tests/test_llm_protocol.py tests/test_llm_api_client.py
git commit -m "feat(llm): LLMClient protocol and ClaudeAPIClient implementation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A6: ClaudeCLIClient (subprocess to `claude --print`)

**Files:**
- Create: `src/experiment_bot/llm/cli_client.py`
- Test: `tests/test_llm_cli_client.py`

- [ ] **Step 1: Write tests with mocked subprocess**

```python
# tests/test_llm_cli_client.py
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.llm.cli_client import ClaudeCLIClient


@pytest.mark.asyncio
async def test_cli_client_invokes_claude_with_print_and_json_output():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(
            json.dumps({"result": "response text", "stop_reason": "end_turn"}).encode(),
            b"",
        )
    )
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        client = ClaudeCLIClient(claude_binary="claude")
        result = await client.complete(system="sys", user="usr", output_format="json")
        args, _ = mock_exec.call_args
        assert "claude" in args[0]
        assert "--print" in args
        assert "--output-format" in args
        assert "json" in args
        assert result.text == "response text"


@pytest.mark.asyncio
async def test_cli_client_quota_exceeded_signals_clearly():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(b"", b"Error: usage limit reached. Reset in 4h.")
    )
    proc.returncode = 1
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        client = ClaudeCLIClient(claude_binary="claude")
        with pytest.raises(RuntimeError, match="usage limit"):
            await client.complete(system="sys", user="usr")


@pytest.mark.asyncio
async def test_cli_client_includes_model_flag_when_specified():
    proc = MagicMock()
    proc.communicate = AsyncMock(
        return_value=(json.dumps({"result": "ok"}).encode(), b"")
    )
    proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        client = ClaudeCLIClient(claude_binary="claude", model="claude-opus-4-7")
        await client.complete(system="sys", user="usr")
        args, _ = mock_exec.call_args
        assert "--model" in args
        assert "claude-opus-4-7" in args
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/llm/cli_client.py
from __future__ import annotations
import asyncio
import json
import logging
from typing import Literal
from experiment_bot.llm.protocol import LLMResponse

logger = logging.getLogger(__name__)


class ClaudeCLIClient:
    """LLM client that shells out to the `claude --print` CLI.

    Uses the user's existing Max subscription via `claude login`.
    No API key required.
    """

    def __init__(
        self,
        claude_binary: str = "claude",
        model: str = "claude-opus-4-7",
        timeout_s: float = 600.0,
    ):
        self._binary = claude_binary
        self._model = model
        self._timeout_s = timeout_s

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
    ) -> LLMResponse:
        # Combine system + user in the prompt body. CLI doesn't separate them;
        # convention: prepend system as a labeled section.
        prompt = f"[SYSTEM]\n{system}\n[/SYSTEM]\n\n{user}"
        args = [
            self._binary,
            "--print",
            "--output-format",
            "json",
            "--model",
            self._model,
            prompt,
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"claude CLI timed out after {self._timeout_s}s")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            if "usage limit" in err.lower() or "quota" in err.lower():
                raise RuntimeError(f"claude CLI: usage limit reached: {err.strip()}")
            raise RuntimeError(f"claude CLI failed (rc={proc.returncode}): {err.strip()}")

        out = stdout.decode("utf-8", errors="replace")
        try:
            data = json.loads(out)
            text = data.get("result") or data.get("text") or ""
            stop_reason = data.get("stop_reason", "end_turn")
        except json.JSONDecodeError:
            text = out
            stop_reason = "end_turn"
        return LLMResponse(text=text, stop_reason=stop_reason)
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/llm/cli_client.py tests/test_llm_cli_client.py
git commit -m "feat(llm): ClaudeCLIClient wrapping `claude --print` for Max subscription auth

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A7: LLMClient factory

**Files:**
- Create: `src/experiment_bot/llm/factory.py`
- Test: `tests/test_llm_factory.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_llm_factory.py
import os
import pytest
from unittest.mock import patch
from experiment_bot.llm.factory import build_default_client
from experiment_bot.llm.cli_client import ClaudeCLIClient
from experiment_bot.llm.api_client import ClaudeAPIClient


def test_factory_picks_cli_when_env_var_says_cli():
    with patch.dict(os.environ, {"EXPERIMENT_BOT_LLM_CLIENT": "cli"}):
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            client = build_default_client()
            assert isinstance(client, ClaudeCLIClient)


def test_factory_picks_api_when_env_var_says_api():
    with patch.dict(os.environ, {
        "EXPERIMENT_BOT_LLM_CLIENT": "api",
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }):
        client = build_default_client()
        assert isinstance(client, ClaudeAPIClient)


def test_factory_default_picks_cli_if_claude_on_path():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXPERIMENT_BOT_LLM_CLIENT", None)
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            client = build_default_client()
            assert isinstance(client, ClaudeCLIClient)


def test_factory_falls_back_to_api_if_no_claude_cli():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
        os.environ.pop("EXPERIMENT_BOT_LLM_CLIENT", None)
        with patch("shutil.which", return_value=None):
            client = build_default_client()
            assert isinstance(client, ClaudeAPIClient)


def test_factory_raises_if_no_path_available():
    with patch.dict(os.environ, {}, clear=True):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="no LLM client available"):
                build_default_client()
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/llm/factory.py
from __future__ import annotations
import os
import shutil
from experiment_bot.llm.cli_client import ClaudeCLIClient
from experiment_bot.llm.api_client import ClaudeAPIClient


def build_default_client():
    """Pick LLM client based on environment.

    Resolution order:
      1. EXPERIMENT_BOT_LLM_CLIENT="cli" → CLI (require claude on PATH)
      2. EXPERIMENT_BOT_LLM_CLIENT="api" → API (require ANTHROPIC_API_KEY)
      3. Default: CLI if claude on PATH, else API if key present, else raise.
    """
    explicit = os.environ.get("EXPERIMENT_BOT_LLM_CLIENT", "").lower()
    has_cli = shutil.which("claude") is not None
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if explicit == "cli":
        if not has_cli:
            raise RuntimeError("EXPERIMENT_BOT_LLM_CLIENT=cli but `claude` not on PATH")
        return ClaudeCLIClient()
    if explicit == "api":
        if not has_api_key:
            raise RuntimeError("EXPERIMENT_BOT_LLM_CLIENT=api but ANTHROPIC_API_KEY unset")
        return _build_api_client()

    if has_cli:
        return ClaudeCLIClient()
    if has_api_key:
        return _build_api_client()
    raise RuntimeError("no LLM client available: neither `claude` on PATH nor ANTHROPIC_API_KEY set")


def _build_api_client() -> ClaudeAPIClient:
    from anthropic import AsyncAnthropic
    api_key = os.environ["ANTHROPIC_API_KEY"]
    return ClaudeAPIClient(client=AsyncAnthropic(api_key=api_key))
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/llm/factory.py tests/test_llm_factory.py
git commit -m "feat(llm): factory selects CLI or API client by env var with sensible defaults

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task A8: OpenAlex DOI verifier

**Files:**
- Create: `src/experiment_bot/reasoner/__init__.py` (empty)
- Create: `src/experiment_bot/reasoner/openalex.py`
- Test: `tests/test_reasoner_openalex.py`

- [ ] **Step 1: Write tests with mocked httpx**

```python
# tests/test_reasoner_openalex.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from experiment_bot.reasoner.openalex import verify_doi


@pytest.mark.asyncio
async def test_verify_doi_returns_true_on_match():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "title": "Effective analysis of reaction time data",
        "publication_year": 2008,
        "authorships": [{"author": {"display_name": "Robert Whelan"}}],
    })
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, meta = await verify_doi(
            doi="10.1016/j.cognition.2008.07.011",
            expected_authors="Whelan, R.",
            expected_year=2008,
        )
    assert ok is True
    assert meta["title"] == "Effective analysis of reaction time data"


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_404():
    fake_response = MagicMock()
    fake_response.status_code = 404
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, meta = await verify_doi("10.0000/nonexistent", "Anyone", 2020)
    assert ok is False


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_year_mismatch():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "title": "Some paper",
        "publication_year": 1999,
        "authorships": [{"author": {"display_name": "Jane Doe"}}],
    })
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, _ = await verify_doi("10.0000/x", "Doe, J.", 2020)
    assert ok is False


@pytest.mark.asyncio
async def test_verify_doi_returns_false_on_network_error():
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(side_effect=Exception("network down"))
    with patch("httpx.AsyncClient", return_value=fake_client):
        ok, meta = await verify_doi("10.0000/x", "Anyone", 2020)
    assert ok is False
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/reasoner/openalex.py
from __future__ import annotations
import logging
import httpx

logger = logging.getLogger(__name__)

OPENALEX_URL = "https://api.openalex.org/works/doi:{doi}"


async def verify_doi(doi: str, expected_authors: str, expected_year: int) -> tuple[bool, dict]:
    """Verify a DOI exists and metadata loosely matches the citation.

    Returns (ok, metadata). ok=True iff:
      - HTTP 200 from OpenAlex
      - publication_year matches expected_year (exact)
      - At least one OpenAlex author display_name shares a surname token with expected_authors

    Network errors and 404s return (False, {}).
    """
    url = OPENALEX_URL.format(doi=doi.strip())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return False, {}
        meta = resp.json()
    except Exception as e:
        logger.warning("OpenAlex verify failed for %s: %s", doi, e)
        return False, {}

    if meta.get("publication_year") != expected_year:
        return False, meta

    expected_surnames = {
        tok.strip(",.").lower()
        for tok in expected_authors.split()
        if len(tok) > 2 and tok[0].isupper()
    }
    actual_authors = " ".join(
        a["author"]["display_name"]
        for a in meta.get("authorships", [])
    ).lower()
    if expected_surnames and not any(s in actual_authors for s in expected_surnames):
        return False, meta

    return True, meta
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/__init__.py src/experiment_bot/reasoner/openalex.py tests/test_reasoner_openalex.py
git commit -m "feat(reasoner): OpenAlex DOI verifier with author/year cross-check

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase B — Reasoner

Goal: 5 stages + pipeline + CLI, fed by fake LLM in tests, capable of producing TaskCards from a SourceBundle when run live. Test suite at end of phase: ~262 + ~25 = ~287 passing (live tests skipped by default).

### Task B1: Reasoner Stage 1 — structural inference

**Files:**
- Create: `src/experiment_bot/reasoner/stage1_structural.py`
- Test: `tests/test_reasoner_stage1.py`
- Test fixture: `tests/fixtures/fake_llm_responses.py`

- [ ] **Step 1: Add fake LLM fixtures**

```python
# tests/fixtures/fake_llm_responses.py
"""Canned LLM responses for reasoner stage tests."""

STAGE1_STROOP_RESPONSE = """
{
  "task": {"name": "Stroop", "constructs": ["cognitive control"], "reference_literature": []},
  "stimuli": [
    {"id": "stroop_congruent", "description": "color matches word",
     "detection": {"method": "dom_query", "selector": ".congruent"},
     "response": {"key": null, "condition": "congruent", "response_key_js": "..."}}
  ],
  "navigation": {"phases": []},
  "runtime": {},
  "task_specific": {"key_map": {"red": "r", "blue": "b"}},
  "performance": {"accuracy": {"congruent": 0.97, "incongruent": 0.92}},
  "pilot_validation_config": {"min_trials": 20, "target_conditions": ["congruent", "incongruent"]}
}
"""
```

- [ ] **Step 2: Write Stage 1 tests with fake client**

```python
# tests/test_reasoner_stage1.py
import json
import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage1_structural import run_stage1
from experiment_bot.llm.protocol import LLMResponse
from experiment_bot.core.config import SourceBundle
from tests.fixtures.fake_llm_responses import STAGE1_STROOP_RESPONSE


@pytest.mark.asyncio
async def test_stage1_returns_partial_taskcard():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE1_STROOP_RESPONSE))
    bundle = SourceBundle(
        url="http://example.com/stroop",
        source_files={"main.js": "..."},
        description_text="<html>...</html>",
    )
    partial = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"
    assert "stroop_congruent" in {s["id"] for s in partial["stimuli"]}
    assert partial["performance"]["accuracy"]["congruent"] == 0.97
    fake.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_stage1_extracts_json_from_markdown_fence():
    fake = AsyncMock()
    wrapped = "```json\n" + STAGE1_STROOP_RESPONSE + "\n```"
    fake.complete = AsyncMock(return_value=LLMResponse(text=wrapped))
    bundle = SourceBundle(url="x", source_files={}, description_text="")
    partial = await run_stage1(client=fake, bundle=bundle)
    assert partial["task"]["name"] == "Stroop"
```

- [ ] **Step 3: Run, expect FAIL**

- [ ] **Step 4: Implement Stage 1**

```python
# src/experiment_bot/reasoner/stage1_structural.py
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _extract_json(text: str) -> str:
    """Strip markdown fences and locate first JSON object."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        return text[first:last + 1]
    return text


def _build_stage1_prompt(bundle: SourceBundle) -> str:
    parts = [f"## Experiment URL: {bundle.url}"]
    if bundle.hint:
        parts.append(f"## Hint: {bundle.hint}")
    parts.append(f"## Page HTML\n{bundle.description_text[:5000]}")
    for fname, content in bundle.source_files.items():
        parts.append(f"## File: {fname}\n{content[:60000]}")
    parts.append(
        "Produce ONLY the structural fields of a TaskConfig: task, stimuli, "
        "navigation, runtime, task_specific (with key_map and trial_timing if "
        "applicable), performance.accuracy/omission, and a pilot_validation_config "
        "block. Do NOT produce response_distributions, temporal_effects, or any "
        "behavioral parameters yet — those come in stage 2. Return JSON only."
    )
    return "\n\n".join(parts)


async def run_stage1(client: LLMClient, bundle: SourceBundle) -> dict:
    """Stage 1 of the Reasoner: produce structural TaskConfig fields."""
    system_prompt = (PROMPTS_DIR / "system.md").read_text()
    user = _build_stage1_prompt(bundle)
    resp = await client.complete(system=system_prompt, user=user, output_format="json")
    return json.loads(_extract_json(resp.text))
```

- [ ] **Step 5: Run, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage1_structural.py tests/test_reasoner_stage1.py tests/fixtures/fake_llm_responses.py
git commit -m "feat(reasoner): stage 1 structural inference (stimuli/navigation/runtime)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B2: Reasoner Stage 2 — behavioral inference

**Files:**
- Create: `src/experiment_bot/reasoner/stage2_behavioral.py`
- Create: `src/experiment_bot/reasoner/prompts/stage2_behavioral.md`
- Test: `tests/test_reasoner_stage2.py`

- [ ] **Step 1: Write the prompt file**

```markdown
<!-- src/experiment_bot/reasoner/prompts/stage2_behavioral.md -->
You are a cognitive psychology expert producing behavioral parameters for a bot
that mimics a typical healthy adult on this task. Given the structural fields
below (already produced in stage 1), produce:

1. response_distributions[<condition>].value = {mu, sigma, tau} per condition,
   informed by published norms.
2. performance.omission_rate per condition.
3. temporal_effects[<effect>].value with `enabled` boolean and parameters,
   only enabling effects empirically documented for this paradigm.
4. between_subject_jitter.value with rt_mean_sd_ms, rt_condition_sd_ms,
   sigma_tau_range, accuracy_sd, omission_sd.

For each numeric parameter, also include a `rationale` string. Citations come
in stage 3 — do NOT include them yet.

Return ONLY a JSON object with these keys:
{
  "response_distributions": {<cond>: {"distribution": "ex_gaussian",
                                       "value": {"mu": ..., "sigma": ..., "tau": ...},
                                       "rationale": "..."}},
  "performance_omission_rate": {<cond>: <fraction>, ...},
  "temporal_effects": {<effect>: {"value": {"enabled": ..., ...},
                                   "rationale": "..."}},
  "between_subject_jitter": {"value": {...}, "rationale": "..."}
}
```

- [ ] **Step 2: Write tests**

```python
# tests/test_reasoner_stage2.py
import json
import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage2_behavioral import run_stage2
from experiment_bot.llm.protocol import LLMResponse


STAGE2_RESPONSE = """
{
  "response_distributions": {
    "congruent": {"distribution": "ex_gaussian",
                  "value": {"mu": 580, "sigma": 80, "tau": 100},
                  "rationale": "Stroop congruent norms"},
    "incongruent": {"distribution": "ex_gaussian",
                    "value": {"mu": 650, "sigma": 95, "tau": 130},
                    "rationale": "Stroop interference effect"}
  },
  "performance_omission_rate": {"congruent": 0.005, "incongruent": 0.005},
  "temporal_effects": {
    "post_error_slowing": {"value": {"enabled": true, "slowing_ms_min": 30, "slowing_ms_max": 80},
                           "rationale": "Rabbitt 1966"}
  },
  "between_subject_jitter": {"value": {"rt_mean_sd_ms": 60, "accuracy_sd": 0.02},
                              "rationale": "individual differences"}
}
"""


@pytest.mark.asyncio
async def test_stage2_appends_behavioral_to_partial():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE2_RESPONSE))
    partial = {"task": {"name": "Stroop"}, "performance": {"accuracy": {"congruent": 0.97}}}
    out = await run_stage2(client=fake, partial=partial)
    assert out["response_distributions"]["congruent"]["value"]["mu"] == 580
    assert out["temporal_effects"]["post_error_slowing"]["value"]["enabled"] is True
    # partial is preserved
    assert out["task"]["name"] == "Stroop"
    # omission rates merged into performance
    assert out["performance"]["omission_rate"]["congruent"] == 0.005
```

- [ ] **Step 3: Run, expect FAIL**

- [ ] **Step 4: Implement Stage 2**

```python
# src/experiment_bot/reasoner/stage2_behavioral.py
from __future__ import annotations
import copy
import json
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import _extract_json

PROMPTS_DIR = Path(__file__).parent / "prompts"


async def run_stage2(client: LLMClient, partial: dict) -> dict:
    """Stage 2: behavioral parameters as point estimates with rationale."""
    system = (PROMPTS_DIR / "stage2_behavioral.md").read_text()
    user = (
        "## Stage 1 output (structural)\n"
        + json.dumps(partial, indent=2)
        + "\n\nProduce the behavioral parameters as instructed in the system prompt."
    )
    resp = await client.complete(system=system, user=user, output_format="json")
    behavioral = json.loads(_extract_json(resp.text))

    result = copy.deepcopy(partial)
    result["response_distributions"] = behavioral["response_distributions"]
    result["temporal_effects"] = behavioral.get("temporal_effects", {})
    result["between_subject_jitter"] = behavioral.get("between_subject_jitter", {})
    om = behavioral.get("performance_omission_rate", {})
    result.setdefault("performance", {})["omission_rate"] = om
    return result
```

- [ ] **Step 5: Run, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage2_behavioral.py src/experiment_bot/reasoner/prompts/stage2_behavioral.md tests/test_reasoner_stage2.py
git commit -m "feat(reasoner): stage 2 behavioral inference (point estimates + rationale)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B3: Reasoner Stage 3 — citation production (batched)

**Files:**
- Create: `src/experiment_bot/reasoner/stage3_citations.py`
- Create: `src/experiment_bot/reasoner/prompts/stage3_citations.md`
- Test: `tests/test_reasoner_stage3.py`

- [ ] **Step 1: Write prompt**

```markdown
<!-- src/experiment_bot/reasoner/prompts/stage3_citations.md -->
You will receive a list of behavioral parameter point estimates for a cognitive
task. For EACH parameter, produce:

1. `citations`: a non-empty list of objects {doi, authors, year, title,
   table_or_figure, page, quote, confidence}. Citations must be real published
   work; if you are not confident, set confidence="low".
2. `literature_range`: empirically observed range across studies, as
   {param_name: [low, high]}.
3. `between_subject_sd`: SD of inter-subject variability for each numeric
   sub-parameter.

Return a JSON object keyed by `<section>/<key>/<param>`:
{
  "response_distributions/congruent/mu": {
    "citations": [...],
    "literature_range": {"mu": [560, 620]},
    "between_subject_sd": {"mu": 40}
  },
  ...
}
```

- [ ] **Step 2: Write tests**

```python
# tests/test_reasoner_stage3.py
import json
import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage3_citations import run_stage3
from experiment_bot.llm.protocol import LLMResponse


STAGE3_RESPONSE = """
{
  "response_distributions/congruent/mu": {
    "citations": [{"doi": "10.0000/test", "authors": "Smith, J.", "year": 2020,
                   "title": "x", "table_or_figure": "T1", "page": 1,
                   "quote": "mu=580 ms", "confidence": "high"}],
    "literature_range": {"mu": [560, 620]},
    "between_subject_sd": {"mu": 40}
  }
}
"""


@pytest.mark.asyncio
async def test_stage3_attaches_citations_and_ranges():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text=STAGE3_RESPONSE))
    partial = {
        "response_distributions": {
            "congruent": {
                "distribution": "ex_gaussian",
                "value": {"mu": 580, "sigma": 80, "tau": 100},
                "rationale": "stroop congruent",
            }
        },
        "temporal_effects": {},
        "between_subject_jitter": {},
    }
    out = await run_stage3(client=fake, partial=partial)
    cong = out["response_distributions"]["congruent"]
    assert cong["citations"]
    assert cong["citations"][0]["doi"] == "10.0000/test"
    assert cong["literature_range"] == {"mu": [560, 620]}
    assert cong["between_subject_sd"] == {"mu": 40}
```

- [ ] **Step 3: Run, expect FAIL**

- [ ] **Step 4: Implement Stage 3 batched**

```python
# src/experiment_bot/reasoner/stage3_citations.py
from __future__ import annotations
import copy
import json
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import _extract_json

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _enumerate_parameters(partial: dict) -> list[str]:
    """Return paths like 'response_distributions/congruent/mu'."""
    paths = []
    for cond, dist in partial.get("response_distributions", {}).items():
        for p in dist.get("value", {}):
            paths.append(f"response_distributions/{cond}/{p}")
    for eff, body in partial.get("temporal_effects", {}).items():
        for p in body.get("value", {}):
            if p == "enabled":
                continue
            paths.append(f"temporal_effects/{eff}/{p}")
    bsj = partial.get("between_subject_jitter", {}).get("value", {})
    for p in bsj:
        paths.append(f"between_subject_jitter/_/{p}")
    return paths


async def run_stage3(client: LLMClient, partial: dict) -> dict:
    """Stage 3: citations + literature_range + between_subject_sd per parameter (batched)."""
    system = (PROMPTS_DIR / "stage3_citations.md").read_text()
    paths = _enumerate_parameters(partial)
    user = (
        "## Parameters needing citations\n"
        + json.dumps({"paths": paths, "current_values": partial}, indent=2)
    )
    resp = await client.complete(system=system, user=user, output_format="json")
    citations_map = json.loads(_extract_json(resp.text))

    result = copy.deepcopy(partial)
    for path, body in citations_map.items():
        section, key, _param = path.split("/", 2)
        if section == "response_distributions":
            target = result["response_distributions"][key]
        elif section == "temporal_effects":
            target = result["temporal_effects"][key]
        elif section == "between_subject_jitter":
            target = result["between_subject_jitter"]
        else:
            continue
        # Merge — accumulate citations across params for the same key
        target.setdefault("citations", []).extend(body.get("citations", []))
        if body.get("literature_range") is not None:
            target.setdefault("literature_range", {}).update(body["literature_range"])
        if body.get("between_subject_sd") is not None:
            target.setdefault("between_subject_sd", {}).update(body["between_subject_sd"])
    return result
```

- [ ] **Step 5: Run, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage3_citations.py src/experiment_bot/reasoner/prompts/stage3_citations.md tests/test_reasoner_stage3.py
git commit -m "feat(reasoner): stage 3 citation production with literature_range and between_subject_sd

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B4: Reasoner Stage 4 — DOI verification

**Files:**
- Create: `src/experiment_bot/reasoner/stage4_doi_verify.py`
- Test: `tests/test_reasoner_stage4.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_reasoner_stage4.py
import pytest
from unittest.mock import patch, AsyncMock
from experiment_bot.reasoner.stage4_doi_verify import run_stage4


@pytest.mark.asyncio
async def test_stage4_marks_verified_on_success():
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {"mu": 580},
                "citations": [{"doi": "10.0000/x", "authors": "Smith, J.", "year": 2020,
                               "title": "x", "table_or_figure": "T1", "page": 1,
                               "quote": "...", "confidence": "high"}],
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(True, {"title": "x"}))):
        out = await run_stage4(partial)
    cit = out["response_distributions"]["congruent"]["citations"][0]
    assert cit["doi_verified"] is True
    assert "doi_verified_at" in cit


@pytest.mark.asyncio
async def test_stage4_marks_unverified_on_failure():
    partial = {
        "response_distributions": {
            "congruent": {
                "value": {"mu": 580},
                "citations": [{"doi": "10.0000/y", "authors": "Doe", "year": 2000,
                               "title": "y", "table_or_figure": "T2", "page": 2,
                               "quote": "...", "confidence": "low"}]
            }
        }
    }
    with patch("experiment_bot.reasoner.stage4_doi_verify.verify_doi",
               new=AsyncMock(return_value=(False, {}))):
        out = await run_stage4(partial)
    cit = out["response_distributions"]["congruent"]["citations"][0]
    assert cit["doi_verified"] is False
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
# src/experiment_bot/reasoner/stage4_doi_verify.py
from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
from experiment_bot.reasoner.openalex import verify_doi


def _iter_citations(partial: dict):
    for section in ("response_distributions", "temporal_effects"):
        for k, v in partial.get(section, {}).items():
            for cit in v.get("citations", []):
                yield cit
    for cit in partial.get("between_subject_jitter", {}).get("citations", []):
        yield cit


async def run_stage4(partial: dict) -> dict:
    """Stage 4: verify each citation's DOI via OpenAlex."""
    result = copy.deepcopy(partial)

    async def _verify_one(cit: dict):
        ok, _meta = await verify_doi(
            doi=cit["doi"],
            expected_authors=cit["authors"],
            expected_year=int(cit["year"]),
        )
        cit["doi_verified"] = bool(ok)
        cit["doi_verified_at"] = datetime.now(timezone.utc).isoformat()

    citations = list(_iter_citations(result))
    if citations:
        await asyncio.gather(*[_verify_one(c) for c in citations])
    return result
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/stage4_doi_verify.py tests/test_reasoner_stage4.py
git commit -m "feat(reasoner): stage 4 DOI verification via OpenAlex

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B5: Reasoner Stage 5 — sensitivity tagging

**Files:**
- Create: `src/experiment_bot/reasoner/stage5_sensitivity.py`
- Create: `src/experiment_bot/reasoner/prompts/stage5_sensitivity.md`
- Test: `tests/test_reasoner_stage5.py`

- [ ] **Step 1: Write prompt**

```markdown
<!-- src/experiment_bot/reasoner/prompts/stage5_sensitivity.md -->
You will receive a TaskCard's behavioral parameters. For each parameter,
classify how strongly it affects the bot's observable output (mean RT,
accuracy, distributional shape, sequential effects).

Output a JSON object keyed by parameter path, value in
{"high", "medium", "low"}:

{
  "response_distributions/congruent/mu": "high",
  "response_distributions/congruent/sigma": "medium",
  ...
}
```

- [ ] **Step 2: Write tests**

```python
# tests/test_reasoner_stage5.py
import pytest
from unittest.mock import AsyncMock
from experiment_bot.reasoner.stage5_sensitivity import run_stage5
from experiment_bot.llm.protocol import LLMResponse


@pytest.mark.asyncio
async def test_stage5_tags_each_parameter():
    fake = AsyncMock()
    fake.complete = AsyncMock(return_value=LLMResponse(text="""
    {
      "response_distributions/congruent/mu": "high",
      "response_distributions/congruent/sigma": "medium",
      "response_distributions/congruent/tau": "medium"
    }
    """))
    partial = {
        "response_distributions": {
            "congruent": {"value": {"mu": 580, "sigma": 80, "tau": 100}}
        }
    }
    out = await run_stage5(client=fake, partial=partial)
    cong = out["response_distributions"]["congruent"]
    assert cong["sensitivity"] == {"mu": "high", "sigma": "medium", "tau": "medium"}
```

- [ ] **Step 3: Run, expect FAIL**

- [ ] **Step 4: Implement**

```python
# src/experiment_bot/reasoner/stage5_sensitivity.py
from __future__ import annotations
import copy
import json
from pathlib import Path
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import _extract_json

PROMPTS_DIR = Path(__file__).parent / "prompts"


async def run_stage5(client: LLMClient, partial: dict) -> dict:
    """Stage 5: sensitivity tags."""
    system = (PROMPTS_DIR / "stage5_sensitivity.md").read_text()
    user = "## Behavioral parameters\n" + json.dumps(partial, indent=2)
    resp = await client.complete(system=system, user=user, output_format="json")
    tags_map = json.loads(_extract_json(resp.text))

    result = copy.deepcopy(partial)
    for path, level in tags_map.items():
        section, key, param = path.split("/", 2)
        if section == "response_distributions":
            target = result["response_distributions"].get(key, {})
        elif section == "temporal_effects":
            target = result["temporal_effects"].get(key, {})
        elif section == "between_subject_jitter":
            target = result["between_subject_jitter"]
        else:
            continue
        target.setdefault("sensitivity", {})[param] = level
    return result
```

- [ ] **Step 5: Run, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/stage5_sensitivity.py src/experiment_bot/reasoner/prompts/stage5_sensitivity.md tests/test_reasoner_stage5.py
git commit -m "feat(reasoner): stage 5 sensitivity tagging per parameter

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B6: Reasoner pipeline orchestration with --resume

**Files:**
- Create: `src/experiment_bot/reasoner/pipeline.py`
- Test: `tests/test_reasoner_pipeline.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_reasoner_pipeline.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from experiment_bot.reasoner.pipeline import ReasonerPipeline
from experiment_bot.core.config import SourceBundle


@pytest.fixture
def bundle():
    return SourceBundle(url="http://example.com", source_files={"main.js": "//"},
                        description_text="<html></html>")


@pytest.mark.asyncio
async def test_pipeline_runs_all_5_stages(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work")
    with patch("experiment_bot.reasoner.pipeline.run_stage1",
               new=AsyncMock(return_value={"task": {"name": "x"}, "stimuli": [],
                                           "navigation": {"phases": []}, "runtime": {},
                                           "task_specific": {}, "performance": {"accuracy": {"d": 0.9}}})), \
         patch("experiment_bot.reasoner.pipeline.run_stage2",
               new=AsyncMock(side_effect=lambda client, partial: {**partial,
                   "response_distributions": {"d": {"value": {"mu": 500}, "rationale": ""}},
                   "temporal_effects": {}, "between_subject_jitter": {}})), \
         patch("experiment_bot.reasoner.pipeline.run_stage3",
               new=AsyncMock(side_effect=lambda client, partial: partial)), \
         patch("experiment_bot.reasoner.pipeline.run_stage4",
               new=AsyncMock(side_effect=lambda partial: partial)), \
         patch("experiment_bot.reasoner.pipeline.run_stage5",
               new=AsyncMock(side_effect=lambda client, partial: partial)):
        result = await pipe.run(bundle, label="test")
    assert result["task"]["name"] == "x"


@pytest.mark.asyncio
async def test_pipeline_writes_partial_after_each_stage(tmp_path, bundle):
    fake = AsyncMock()
    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work")

    async def stage1(client, b):
        return {"_stage": 1}

    async def stage2(client, p):
        return {**p, "_stage": 2}

    with patch("experiment_bot.reasoner.pipeline.run_stage1", new=stage1), \
         patch("experiment_bot.reasoner.pipeline.run_stage2", new=stage2), \
         patch("experiment_bot.reasoner.pipeline.run_stage3", new=AsyncMock(side_effect=Exception("boom"))):
        with pytest.raises(Exception, match="boom"):
            await pipe.run(bundle, label="test")
    # Stage 2 partial saved
    saved = json.loads((tmp_path / "work" / "test" / "stage2.json").read_text())
    assert saved["_stage"] == 2


@pytest.mark.asyncio
async def test_pipeline_resumes_from_stage(tmp_path, bundle):
    fake = AsyncMock()
    work = tmp_path / "work" / "test"
    work.mkdir(parents=True)
    (work / "stage2.json").write_text('{"_stage": 2}')

    async def stage3(client, p):
        return {**p, "_stage": 3}

    async def stage4(p):
        return {**p, "_stage": 4}

    async def stage5(client, p):
        return {**p, "_stage": 5}

    pipe = ReasonerPipeline(client=fake, work_dir=tmp_path / "work")
    with patch("experiment_bot.reasoner.pipeline.run_stage3", new=stage3), \
         patch("experiment_bot.reasoner.pipeline.run_stage4", new=stage4), \
         patch("experiment_bot.reasoner.pipeline.run_stage5", new=stage5):
        result = await pipe.run(bundle, label="test", resume=True)
    assert result["_stage"] == 5
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement pipeline**

```python
# src/experiment_bot/reasoner/pipeline.py
from __future__ import annotations
import json
from pathlib import Path
from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.stage1_structural import run_stage1
from experiment_bot.reasoner.stage2_behavioral import run_stage2
from experiment_bot.reasoner.stage3_citations import run_stage3
from experiment_bot.reasoner.stage4_doi_verify import run_stage4
from experiment_bot.reasoner.stage5_sensitivity import run_stage5


class ReasonerPipeline:
    """Runs stages 1-5, persisting partial state after each so --resume works."""

    def __init__(self, client: LLMClient, work_dir: Path):
        self._client = client
        self._work_dir = Path(work_dir)

    def _stage_path(self, label: str, stage_n: int) -> Path:
        return self._work_dir / label / f"stage{stage_n}.json"

    def _save(self, label: str, stage_n: int, partial: dict) -> None:
        path = self._stage_path(label, stage_n)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(partial, indent=2))

    def _resume_from(self, label: str) -> tuple[int, dict] | None:
        for n in (4, 3, 2, 1):
            p = self._stage_path(label, n)
            if p.exists():
                return n, json.loads(p.read_text())
        return None

    async def run(self, bundle: SourceBundle, label: str, resume: bool = False) -> dict:
        partial: dict = {}
        start_after = 0

        if resume:
            res = self._resume_from(label)
            if res is not None:
                start_after, partial = res

        if start_after < 1:
            partial = await run_stage1(self._client, bundle)
            self._save(label, 1, partial)
        if start_after < 2:
            partial = await run_stage2(self._client, partial)
            self._save(label, 2, partial)
        if start_after < 3:
            partial = await run_stage3(self._client, partial)
            self._save(label, 3, partial)
        if start_after < 4:
            partial = await run_stage4(partial)
            self._save(label, 4, partial)
        if start_after < 5:
            partial = await run_stage5(self._client, partial)
            self._save(label, 5, partial)
        return partial
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/pipeline.py tests/test_reasoner_pipeline.py
git commit -m "feat(reasoner): pipeline orchestration with stage-level resume

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B7: Reasoner CLI command

**Files:**
- Create: `src/experiment_bot/reasoner/cli.py`
- Modify: `pyproject.toml` (add `experiment-bot-reason` script)
- Test: `tests/test_reasoner_cli.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_reasoner_cli.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from click.testing import CliRunner
from experiment_bot.reasoner.cli import main


def test_reason_cli_writes_taskcard(tmp_path):
    runner = CliRunner()
    fake_partial = {
        "schema_version": "2.0",
        "produced_by": {"model": "claude-opus-4-7", "prompt_sha256": "p",
                        "scraper_version": "1.0.0", "source_sha256": "s",
                        "timestamp": "2026-04-23T12:00:00Z", "taskcard_sha256": ""},
        "task": {"name": "x", "constructs": [], "reference_literature": []},
        "stimuli": [], "navigation": {"phases": []}, "runtime": {},
        "task_specific": {}, "performance": {"accuracy": {"d": 0.9}},
        "response_distributions": {}, "temporal_effects": {},
        "between_subject_jitter": {}, "reasoning_chain": [],
        "pilot_validation": {},
    }
    with patch("experiment_bot.reasoner.cli.scrape_experiment_source",
               new=AsyncMock(return_value=type("B", (), {
                   "url": "http://x", "source_files": {}, "description_text": "",
                   "hint": "", "metadata": {},
               })())), \
         patch("experiment_bot.reasoner.cli.ReasonerPipeline") as Pipe:
        instance = Pipe.return_value
        instance.run = AsyncMock(return_value=fake_partial)
        result = runner.invoke(main, [
            "http://x", "--label", "stroop", "--taskcards-dir", str(tmp_path),
        ])
    assert result.exit_code == 0
    files = list((tmp_path / "stroop").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["task"]["name"] == "x"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement CLI**

```python
# src/experiment_bot/reasoner/cli.py
from __future__ import annotations
import asyncio
import logging
from pathlib import Path

import click

from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.llm.factory import build_default_client
from experiment_bot.reasoner.pipeline import ReasonerPipeline
from experiment_bot.taskcard.loader import save_taskcard
from experiment_bot.taskcard.types import TaskCard


@click.command()
@click.argument("url")
@click.option("--label", required=True, help="Cache label for this task")
@click.option("--hint", default="", help="Optional paradigm hint")
@click.option("--taskcards-dir", default="taskcards", help="Where to write TaskCards")
@click.option("--work-dir", default=".reasoner_work", help="Where stage partials live")
@click.option("--resume", is_flag=True, default=False,
              help="Resume from latest saved stage if present")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(url: str, label: str, hint: str, taskcards_dir: str, work_dir: str,
         resume: bool, verbose: bool):
    """Run the 5-stage Reasoner against URL and produce a TaskCard."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(_run(url, label, hint, Path(taskcards_dir), Path(work_dir), resume))


async def _run(url, label, hint, taskcards_dir, work_dir, resume):
    bundle = await scrape_experiment_source(url=url, hint=hint)
    client = build_default_client()
    pipeline = ReasonerPipeline(client=client, work_dir=work_dir)
    final = await pipeline.run(bundle, label=label, resume=resume)
    if "schema_version" not in final:
        final = _wrap_for_taskcard(final, url)
    tc = TaskCard.from_dict(final)
    out = save_taskcard(tc, taskcards_dir, label=label)
    click.echo(f"TaskCard written: {out}")


def _wrap_for_taskcard(partial: dict, url: str) -> dict:
    """Add the `schema_version`, `produced_by`, and `reasoning_chain` envelope."""
    from datetime import datetime, timezone
    partial.setdefault("schema_version", "2.0")
    partial.setdefault("produced_by", {
        "model": "claude-opus-4-7",
        "prompt_sha256": "",
        "scraper_version": "1.0.0",
        "source_sha256": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "taskcard_sha256": "",
    })
    partial.setdefault("reasoning_chain", [])
    partial.setdefault("pilot_validation", {})
    return partial
```

- [ ] **Step 4: Add script entry to pyproject.toml**

In `pyproject.toml` under `[project.scripts]`:

```toml
[project.scripts]
experiment-bot = "experiment_bot.cli:main"
experiment-bot-reason = "experiment_bot.reasoner.cli:main"
```

Run `uv sync` to register the new script.

- [ ] **Step 5: Run, expect PASS**

Run: `uv run pytest tests/test_reasoner_cli.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/reasoner/cli.py tests/test_reasoner_cli.py pyproject.toml
git commit -m "feat(reasoner): experiment-bot-reason CLI entry point

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — Migration & bring-up

Goal: existing executor reads TaskCards instead of v1 configs; the 4 development tasks regenerated live; v1 cache deleted; test suite stays green throughout.

### Task C1: Executor reads TaskCards via taskcard_loader

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Modify: `src/experiment_bot/core/executor.py:32` (constructor accepts dict from TaskCard or TaskConfig)
- Test: existing `tests/test_executor.py` adjustments

- [ ] **Step 1: Write a passing test that loads a v2 TaskCard and constructs an executor**

```python
# tests/test_executor.py (append; uses _minimal_config_dict helper if present)
def test_executor_constructs_from_taskcard_dict(_minimal_config_dict):
    from experiment_bot.taskcard.types import TaskCard
    from experiment_bot.core.executor import TaskExecutor
    base = _minimal_config_dict()
    base.setdefault("schema_version", "2.0")
    base.setdefault("produced_by", {
        "model": "x", "prompt_sha256": "", "scraper_version": "1.0",
        "source_sha256": "", "timestamp": "2026-04-23T12:00:00Z",
        "taskcard_sha256": "",
    })
    base.setdefault("reasoning_chain", [])
    base.setdefault("pilot_validation", {})
    tc = TaskCard.from_dict(base)
    executor = TaskExecutor(tc)
    assert executor._config.task is not None  # legacy adapter still works
```

- [ ] **Step 2: Run, expect FAIL — TaskExecutor doesn't accept TaskCard yet**

- [ ] **Step 3: Implement: TaskExecutor accepts TaskCard or TaskConfig**

In `src/experiment_bot/core/executor.py`, modify `__init__` to extract a TaskConfig view from a TaskCard if needed:

```python
def __init__(
    self,
    config,  # was TaskConfig; now TaskCard or TaskConfig
    seed: int | None = None,
    headless: bool = False,
):
    # If a TaskCard was passed, view its underlying config-shaped fields
    from experiment_bot.taskcard.types import TaskCard
    if isinstance(config, TaskCard):
        self._taskcard = config
        config = _taskcard_to_config(config)
    else:
        self._taskcard = None
    self._config = config
    # ... rest unchanged
```

Add a helper near the top of the file:

```python
def _taskcard_to_config(tc):
    """Project a TaskCard into a TaskConfig the executor knows how to drive."""
    from experiment_bot.core.config import TaskConfig, DistributionConfig
    cfg = TaskConfig(
        task=tc.task,
        stimuli=tc.stimuli,
        response_distributions={
            k: DistributionConfig(distribution="ex_gaussian", params=v.value)
            for k, v in tc.response_distributions.items()
        },
        performance=tc.performance,
        navigation=tc.navigation,
        task_specific=tc.task_specific,
        runtime=tc.runtime,
    )
    # temporal_effects + between_subject_jitter come from existing config code,
    # but TaskCard stores them as ParameterValue. Project the .value field.
    from experiment_bot.core.config import TemporalEffectsConfig, BetweenSubjectJitterConfig
    te_dict = {k: v.value for k, v in tc.temporal_effects.items()}
    cfg.temporal_effects = TemporalEffectsConfig.from_dict(te_dict)
    bsj_value = (tc.between_subject_jitter or {}).get("value", {})
    cfg.between_subject_jitter = BetweenSubjectJitterConfig.from_dict(bsj_value)
    return cfg
```

- [ ] **Step 4: Run, expect PASS**

Run the full suite: `uv run pytest tests/ -q` → expect green (≥232 + new).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "feat(executor): accept TaskCard, project to legacy TaskConfig view

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C2: cli.py loads TaskCard, samples session params

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Test: `tests/test_cli.py` (existing; update fixtures)

- [ ] **Step 1: Update existing CLI test fixtures**

Inspect `tests/test_cli.py` and update fixture paths so it expects taskcards/ instead of cache/. If test currently mocks `ConfigCache`, replace with mocked `load_latest`.

- [ ] **Step 2: Update cli.py to load TaskCard**

Replace the `cache.load(url, label)` block with:

```python
from experiment_bot.taskcard.loader import load_latest
from experiment_bot.taskcard.sampling import sample_session_params

# ...
try:
    taskcard = load_latest(Path("taskcards"), label=label)
except FileNotFoundError:
    raise click.ClickException(
        f"No TaskCard found for label '{label}'. "
        f"Run `experiment-bot-reason {url} --label {label}` first."
    )

# At session start, draw distributional params
sampled = sample_session_params(taskcard.to_dict(), seed=os.urandom(8).__hash__())
# Stamp sampled values into the TaskCard's response_distributions[*].value
# so the executor's existing ResponseSampler reads them.
for cond, params in sampled.items():
    taskcard.response_distributions[cond].value.update(params)

executor = TaskExecutor(taskcard, headless=headless)
await executor.run(url)
```

Remove the `--regenerate-config` flag (regeneration is now via `experiment-bot-reason`). Remove `cache = ConfigCache()`.

- [ ] **Step 3: Run cli tests, then full suite**

Run: `uv run pytest tests/test_cli.py -v && uv run pytest tests/ -q`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/cli.py tests/test_cli.py
git commit -m "refactor(cli): load TaskCard via taskcard_loader; sample session params at start

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C3: Live regenerate the 4 development tasks

**Files:** none Python; produces `taskcards/{label}/{hash}.json` × 4

- [ ] **Step 1: Confirm `claude` CLI is on PATH and authenticated**

Run: `which claude && claude --version`
Expected: path printed and version (e.g., `1.x.y`).

If not authenticated, run `claude login` interactively (user action — not a script step).

- [ ] **Step 2: Regenerate each task**

For each label/URL pair, run:

```bash
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/9/" --label expfactory_stop_signal
uv run experiment-bot-reason "https://deploy.expfactory.org/preview/10/" --label expfactory_stroop
uv run experiment-bot-reason "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html" --label stopit_stop_signal
uv run experiment-bot-reason "https://strooptest.cognition.run/" --label cognitionrun_stroop
```

Each produces `taskcards/{label}/{hash}.json`. Wall-clock estimate: 5–10 min per task. If a Max window cap is hit, the CLI will raise; rerun with `--resume` once the window resets.

- [ ] **Step 3: Verify all four TaskCards exist**

```bash
ls taskcards/*/*.json | wc -l
```

Expected: `4`.

- [ ] **Step 4: Spot-check one TaskCard's citations**

```bash
python -c "
import json
tc = json.load(open(sorted(__import__('pathlib').Path('taskcards/expfactory_stroop').glob('*.json'))[-1]))
for k, v in tc['response_distributions'].items():
    print(k, len(v.get('citations', [])), 'citations,',
          sum(c.get('doi_verified', False) for c in v.get('citations', [])), 'verified')
"
```

Expected: each condition has ≥1 citation; most are DOI-verified.

- [ ] **Step 5: Commit**

```bash
git add taskcards/
git commit -m "chore: regenerate 4 development tasks as v2 TaskCards via Reasoner

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C4: Delete v1 cache files and `core/cache.py`

**Files:**
- Delete: `src/experiment_bot/core/cache.py`
- Delete: `cache/cognitionrun_stroop/config.json`
- Delete: `cache/expfactory_stop_signal/config.json`
- Delete: `cache/expfactory_stroop/config.json`
- Delete: `cache/stopit_stop_signal/config.json`
- Modify: `tests/test_cache.py` → delete or replace with `tests/test_taskcard_loader.py` if not already done

- [ ] **Step 1: Delete v1 cache directory**

```bash
rm -rf cache/
```

- [ ] **Step 2: Delete cache.py module**

```bash
rm src/experiment_bot/core/cache.py
```

- [ ] **Step 3: Delete or rewrite test_cache.py**

If `tests/test_cache.py` exists, delete it:

```bash
rm tests/test_cache.py
```

(Equivalent coverage now lives in `tests/test_taskcard_loader.py`.)

- [ ] **Step 4: Update existing 4 cached-config contract tests**

Find tests parametrized over `["expfactory_stop_signal", "expfactory_stroop", "stopit_stop_signal", "cognitionrun_stroop"]` in `tests/test_config.py`. Replace `cache/{label}/config.json` with `taskcards/{label}/<hash>.json` lookups using `load_latest`.

Example for `test_cached_config_has_advance_keys`:

```python
@pytest.mark.parametrize("label", [
    "expfactory_stop_signal", "expfactory_stroop",
    "stopit_stop_signal", "cognitionrun_stroop",
])
def test_taskcard_has_advance_keys(label):
    from pathlib import Path
    from experiment_bot.taskcard.loader import load_latest
    if not (Path("taskcards") / label).exists():
        pytest.skip(f"{label} TaskCard not present")
    tc = load_latest(Path("taskcards"), label=label)
    keys = tc.runtime.advance_behavior.advance_keys
    assert keys, f"{label} has empty advance_keys"
```

Apply analogously to `feedback_fallback_keys`, `failure_rt_cap_fraction`, `inhibit_wait_ms`.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/ -q`
Expected: green (~280 tests).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove v1 cache.py and config.json files; tests now read TaskCards

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C5: Live executor smoke against regenerated TaskCards

**Files:** none Python

- [ ] **Step 1: Add a `@pytest.mark.live` test**

Append to `tests/test_executor.py`:

```python
@pytest.mark.live
def test_live_executor_runs_against_regenerated_taskcard():
    """End-to-end smoke against a real Playwright session.

    Skipped by default; run with RUN_LIVE_LLM=1.
    Verifies executor + TaskCard integration on expfactory_stroop.
    """
    import asyncio
    import os
    from pathlib import Path
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.taskcard.loader import load_latest

    if not os.environ.get("RUN_LIVE_LLM"):
        pytest.skip("Set RUN_LIVE_LLM=1 to run")

    tc = load_latest(Path("taskcards"), label="expfactory_stroop")
    ex = TaskExecutor(tc, headless=True)
    asyncio.run(ex.run("https://deploy.expfactory.org/preview/10/"))
```

- [ ] **Step 2: Manually run the live test**

```bash
RUN_LIVE_LLM=1 uv run pytest tests/test_executor.py::test_live_executor_runs_against_regenerated_taskcard -v
```

Expected: completes one full Stroop run, writes `output/stroop_(rdoc)/<timestamp>/experiment_data.csv`. If it crashes, capture the trace and either fix the executor or fix the TaskCard fields the executor reads.

- [ ] **Step 3: Confirm output exists and looks sensible**

```bash
ls -t output/stroop_\(rdoc\)/ | head -1
```

- [ ] **Step 4: Commit the test**

```bash
git add tests/test_executor.py
git commit -m "test(executor): add live smoke against regenerated TaskCard

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C6: Final regression sweep + tag

**Files:** none

- [ ] **Step 1: Final test pass**

```bash
uv run pytest tests/ -q
```

Expected: green. Test count near 280.

- [ ] **Step 2: Run lint / type check (if configured)**

```bash
uv run ruff check src/ tests/ || true
```

Address any new issues introduced by SP1.

- [ ] **Step 3: Tag the commit**

```bash
git tag -a sp1-complete -m "SP1: TaskCard + Reasoner complete; 4 development tasks regenerated"
```

- [ ] **Step 4: Update README briefly**

In `README.md`, replace the "First run (generates config via Claude API)" section with a pointer to `experiment-bot-reason` and the TaskCard concept. Single paragraph; spec doc has the deep details.

```bash
git add README.md
git commit -m "docs: update README to reflect taskcard + reasoner workflow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage check:**

| Spec section | Plan task(s) |
|---|---|
| TaskCard schema (top-level) | A1 |
| Three-tuple parameter representation | A1, A4 |
| Citations (DOI + verification) | A1, A8, B3, B4 |
| Reasoning chain | A1 (types), B6 (carried through pipeline) |
| Sensitivity tags | A1, B5 |
| Versioning + hashing | A2 |
| Reasoner stages 1–5 | B1, B2, B3, B4, B5 |
| LLMClient protocol + 2 implementations | A5, A6 |
| Auth via env var (CLI default, API fallback) | A7 |
| Migration: full regeneration | C3, C4 |
| Performer's TaskCard contract (executor adaptation) | C1, C2 |
| Session-start sampling | A4 |
| Determinism contract | A4 |
| Pilot validation result in TaskCard | A1 (carried via existing config) |
| Test strategy: TDD, unit/integration/regression/e2e gates | every task |
| Live regeneration of 4 development tasks | C3 |
| Out-of-scope items (SP2/SP3/SP4/SP5/SP6/SP7) | NOT touched in plan |

All spec sections covered.

**Placeholder scan:** No `TBD`, `TODO`, "implement later", or "similar to Task N" patterns in the plan body. Every code block is concrete. The two pieces of "edit this file based on what's there" guidance (C2 step 1 and C4 step 4) point to specific existing tests and describe the substitution explicitly.

**Type consistency:** `LLMClient` protocol defined in A5 used in B1–B5 with same signature. `TaskCard.from_dict / to_dict` defined in A1 used consistently. `sample_session_params(taskcard_dict, seed)` accepts a dict (not a TaskCard object) — used consistently in A4 tests and C2 implementation. `ParameterValue` field names (`value`, `literature_range`, `between_subject_sd`, `citations`, `rationale`, `sensitivity`) match across A1, B2, B3, B4, B5.

**Total estimated implementation time:** 8–12 hours of focused engineering, plus 2–3 hours of live regeneration in C3 (clock time, mostly waiting for Claude). Phase A is the longest at ~5–6 hours; Phase B ~3–4; Phase C ~2.

---

## Out of scope (deferred to later sub-projects)

| Deferred to | Items |
|---|---|
| **SP2** | New behavioral effects (CSE, response repetition, etc.); calibrating between_subject_sd against human data; distributional matching tests |
| **SP3** | Slurm scripts, deterministic seed coordination, distributed output, headless cluster runtime, platform-native data capture via network interception |
| **SP4** | Statistical oracles (KS, Anderson-Darling, sequential-effect tests), bot-vs-human comparison reports |
| **SP5** | Acquisition of additional paradigms (n-back, Flanker, etc.), human reference data sourcing |
| **SP6** | Full forensic trace logs, audit reports linking trace → TaskCard → citation, reproducibility verification harness |
| **SP7** | Analysis pipeline refactor; column-level audit per platform |
| **SP1.5** | Curated literature corpus per paradigm (replaces stage-3 training-data-only citations) |

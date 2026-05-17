# SP10 — Driver-based platform architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the bot into a slim paradigm-agnostic core + per-platform drivers. JsPsychDriver hooks the platform's own keyboard-response callback to deliver responses with high fidelity. Reasoner pipeline shrinks (no more brittle JS extraction). Target: per-trial `pressed == platform_recorded` ≥ 90% across all 4 dev paradigms while preserving SP5 + SP6 aggregate validation gates.

**Architecture:** Three-tier separation. `experiment_bot.drivers` package owns all page-touching code (one driver per platform). The executor becomes a slim trial-loop coordinator that calls into the driver. The Reasoner produces simplified TaskCards. The `DiagnosticDriver` fallback writes a structured report when no driver matches an unknown platform or unanchored version.

**Tech Stack:** Python 3.12 / uv; pytest + pytest-asyncio; Playwright (async API); existing effect library and Reasoner stages preserved.

Reference: spec at `docs/superpowers/specs/2026-05-15-sp10-driver-architecture-design.md`. CLAUDE.md edits at `docs/superpowers/specs/2026-05-15-sp10-claude-md-edits.md` (G0 above G1 per user). SP9c findings at `docs/sp9c-investigation.md` carry forward — jsPsych's listener mechanics and `pluginAPI.getKeyboardResponse` interface inform JsPsychDriver's hook strategy.

**Phase gates:** five phases, each independently checkpointable. The plan is structured so abandoning at any phase boundary preserves the prior phase's deliverable. The user reviews between phases.

---

## File Structure

| Path | Role | Action |
|---|---|---|
| `CLAUDE.md` | Project guardrails | Modified — apply Phase 0 edits (Task 1) |
| `docs/reviewer-1-charter.md` | Adversarial-review charter | Modified — Last reviewed at (Task 22) |
| `vendor/LICENSES.md` | Provenance + licenses for vendored sources | Created (Task 2) |
| `vendor/jspsych/<version>/` | Selective jsPsych anchor files | Created (Task 11) |
| `src/experiment_bot/drivers/__init__.py` | Package marker | Created (Task 3) |
| `src/experiment_bot/drivers/base.py` | `PlatformDriver` Protocol + types | Created (Task 3) |
| `src/experiment_bot/drivers/registry.py` | `identify_driver` + REGISTERED_DRIVERS | Created (Task 4) |
| `src/experiment_bot/drivers/diagnostic.py` | DiagnosticDriver | Created (Task 5) |
| `src/experiment_bot/drivers/jspsych/__init__.py` | Subpackage marker | Created (Task 12) |
| `src/experiment_bot/drivers/jspsych/driver.py` | JsPsychDriver class | Created (Task 12) |
| `src/experiment_bot/drivers/jspsych/responses.py` | `pluginAPI.getKeyboardResponse` hook | Created (Task 13) |
| `src/experiment_bot/drivers/jspsych/phases.py` | loop_state from jsPsych state | Created (Task 14) |
| `src/experiment_bot/drivers/jspsych/navigation.py` | Advance instructions, dismiss feedback | Created (Task 15) |
| `src/experiment_bot/drivers/jspsych/data_export.py` | retrieve_data via `jsPsych.data` API | Created (Task 16) |
| `src/experiment_bot/core/executor.py` | Slim trial loop | Heavily modified (Tasks 6–9) |
| `src/experiment_bot/cli.py` | Invoke `identify_driver` | Modified (Task 8) |
| `src/experiment_bot/core/config.py` | TaskConfig schema slimming | Modified (Task 18) |
| `src/experiment_bot/prompts/system.md` | Stage 1 prompt simplification | Modified (Task 18) |
| `src/experiment_bot/reasoner/stage1_structural.py` | Required-fields update | Modified (Task 18) |
| `src/experiment_bot/reasoner/validate.py` | Stage 1 validator update | Modified (Task 18) |
| `src/experiment_bot/reasoner/stage6_pilot.py` | Pilot via driver | Modified (Task 19) |
| `taskcards/*/+.json` | Add `recommended_driver` | Modified (Task 20) |
| `tests/test_drivers_base.py` | Protocol + types tests | Created (Task 3) |
| `tests/test_drivers_registry.py` | identify_driver tests | Created (Task 4) |
| `tests/test_drivers_diagnostic.py` | DiagnosticDriver tests | Created (Task 5) |
| `tests/test_drivers_jspsych.py` | JsPsychDriver tests | Created (Task 12+) |
| `tests/test_executor.py` | Adapt to driver-based flow | Modified (Tasks 6–9) |
| `tests/test_executor_session_agent_integration.py` | Deleted (SP9a obsolete) | Deleted (Task 9) |
| `tests/test_cli.py` | Adapt to driver construction | Modified (Task 8) |
| `tests/test_stage1_*.py` | Adapt to simplified Stage 1 | Modified (Task 18) |
| `output/<paradigm>/<timestamp>/` × 12+ | Empirical run sessions | Generated (Task 21; gitignored) |
| `docs/sp10-investigation.md` | JsPsychDriver hook-strategy notes | Created (Task 17) |
| `docs/sp10-results.md` | Phase 5 empirical results | Created (Task 22) |

---

## Paradigm reference (Phase 5)

Existing TaskCards on the sp8 branch at `b06122e`:

| Label | URL | TaskCard | Driver |
|---|---|---|---|
| `expfactory_stroop` | `https://deploy.expfactory.org/preview/10/` | `f099a88b` | JsPsychDriver |
| `expfactory_n_back` | `https://deploy.expfactory.org/preview/5/` | `8198382d` | JsPsychDriver |
| `expfactory_stop_signal` | `https://deploy.expfactory.org/preview/9/` | `6ccd7d47` | JsPsychDriver |
| `stopit_stop_signal` | `https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html` | `39e97714` | JsPsychDriver |
| `cognitionrun_stroop` | `https://strooptest.cognition.run/` | (no TaskCard) | (deferred) |

---

## Phase 0 — Setup

### Task 0: Tag SP9c work and create SP10 worktree (controller responsibility)

**Files:**
- Tag: `sp9c-investigation-complete` at current `sp9c/layer-d-investigation` HEAD `9886362`
- Worktree: `.worktrees/sp10` on branch `sp10/driver-architecture`, branched off `sp9c-investigation-complete`

The controller performs Steps 1-3 once before dispatching subagents.

- [ ] **Step 1: Tag the SP9c investigation as preserved work**

```bash
git tag sp9c-investigation-complete 9886362
```

- [ ] **Step 2: Create the SP10 worktree**

```bash
git worktree add /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp10 -b sp10/driver-architecture sp9c-investigation-complete
```

- [ ] **Step 3: Cherry-pick the SP10 spec + plan + CLAUDE.md edits doc + Phase B.1 jsPsych source notes (which live in the sp9c branch)**

```bash
cd /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp10
# The SP10 spec + CLAUDE.md edits doc + this plan currently live on sp9b
# branch; cherry-pick onto sp10.
git cherry-pick b58f9ec  # SP10 spec + CLAUDE.md edits
git cherry-pick <plan-commit-sha>  # this plan (commit lands after this plan is written)
uv sync
uv run pytest -q
```

Expected: 564 passed (matches `sp9c-investigation-complete` baseline plus the Phase A+B work).

### Task 1: Apply CLAUDE.md edits (first commit on the SP10 branch)

**Files:**
- Modify: `CLAUDE.md` per `docs/superpowers/specs/2026-05-15-sp10-claude-md-edits.md`

The CLAUDE.md edits are the load-bearing guardrails for SP10 — they land before any code so subsequent task review can rely on them.

- [ ] **Step 1: Apply the proposed diffs from the edits doc**

Open `docs/superpowers/specs/2026-05-15-sp10-claude-md-edits.md` for the verbatim proposed text. Apply each section's "Proposed:" replacement to `CLAUDE.md` in order:

1. Replace "What this project is" section per the edits doc.
2. Replace G1, G2 with G0, G1, G2 per the edits doc. **G0 first** (per user's explicit decision: per-trial fidelity is the highest-priority goal).
3. Append the bot_log diagnostic-only bullet to G4.
4. Add the new "When adding platform support" subsection under "Specific guardrails for code changes".
5. Append the negative-assertion example to "When updating tests".
6. Append the two new operational rules under "Operational rules".
7. Append the SP10 placeholder entry to "Sub-project history".

- [ ] **Step 2: Sanity-check the new CLAUDE.md reads coherently**

```bash
wc -l CLAUDE.md
grep -c "^### G" CLAUDE.md  # should show 6: G0 G1 G2 G3 G4 G5
grep "^### G0\|^### G1\|^### G2" CLAUDE.md  # G0 must be FIRST
```

Expected: line count increased modestly, G0 appears before G1 in the file.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude.md): SP10 guardrails — G0 per-trial fidelity, driver tier

Apply CLAUDE.md edits proposed in
docs/superpowers/specs/2026-05-15-sp10-claude-md-edits.md.

Substantive changes:
- "What this project is" reframed as adversarial-research tool
  demonstrating bot risk to online behavioral-data platforms.
- New G0 (per-trial fidelity to platform data export) as highest-
  priority goal, above G1 generalizability (per user decision).
- G2 expanded: Reasoner does literature thinking, bot library does
  generic mechanics, driver does platform mechanics. Runtime LLM
  intelligence permitted in drivers, not in bot library or Reasoner
  at runtime.
- G4 strengthened: bot_log.json is diagnostic-only; platform export
  is the only analysis input.
- New "When adding platform support" guardrails subsection.
- Operational rules + negative-assertion test guidance updated.
- SP10 sub-project history placeholder added.

These guardrails land FIRST so subsequent SP10 code-review can rely
on them. CLAUDE.md is load-bearing for both SP9a and SP9c rework
analysis (see the edits doc's self-audit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 1 — Driver infrastructure

### Task 2: Create `vendor/` directory + LICENSES.md

**Files:**
- Create: `vendor/LICENSES.md`
- Create: `vendor/.gitkeep`

- [ ] **Step 1: Create the vendor directory structure**

```bash
mkdir -p vendor
touch vendor/.gitkeep
```

- [ ] **Step 2: Write `vendor/LICENSES.md`**

```markdown
# Vendored sources — provenance and licenses

This directory contains selectively-vendored source files from open-source
platforms the bot's drivers reference. Files are vendored per major version
and serve as version-pinned API references for driver code.

## jsPsych

- **License:** MIT — https://github.com/jspsych/jsPsych/blob/main/LICENSE
- **Copyright:** Joshua de Leeuw and contributors.
- **Vendored versions:** see subdirectories under `vendor/jspsych/`.
- **Provenance:** each vendored file's top comment block lists the upstream
  GitHub URL + commit hash + retrieval date.

## Closed-source platforms

Drivers targeting closed-source platforms (e.g., cognition.run) cannot
vendor source. Those drivers live under `src/experiment_bot/drivers/<name>/`
with no corresponding `vendor/<name>/` directory; their `notes.md` documents
observed behavior. The reviewer-1 charter's scope-of-validity section lists
this limitation explicitly.
```

- [ ] **Step 3: Commit**

```bash
git add vendor/LICENSES.md vendor/.gitkeep
git commit -m "$(cat <<'EOF'
chore(vendor): create vendor/ for platform-specific anchor files

Each subdirectory under vendor/<platform>/<version>/ holds the
selective source files a driver references, with provenance comments
preserving upstream URL + commit hash + license. LICENSES.md
documents jsPsych MIT licensing; closed-source platforms (cognition.run)
have no vendor subdir per the documented scope-of-validity limitation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3: Create `drivers/base.py` with Protocol + types + tests

**Files:**
- Create: `src/experiment_bot/drivers/__init__.py`
- Create: `src/experiment_bot/drivers/base.py`
- Create: `tests/test_drivers_base.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drivers_base.py`:

```python
"""SP10: PlatformDriver Protocol contract + types."""
from __future__ import annotations
import inspect

import pytest

from experiment_bot.drivers.base import (
    DeliveryResult,
    DriverError,
    ExperimentData,
    NavigationOutcome,
    PlatformDriver,
    TrialContext,
    TrialLoopState,
    UnsupportedVersionError,
)


def test_trial_loop_state_has_three_members():
    assert {m.name for m in TrialLoopState} == {
        "NEEDS_NAVIGATION", "READY_FOR_TRIAL", "COMPLETE",
    }


def test_trial_context_required_fields():
    ctx = TrialContext(
        stimulus_id="s1",
        condition="congruent",
        allowed_responses=(",", "."),
        expected_correct=",",
        response_window_ms=None,
    )
    assert ctx.stimulus_id == "s1"
    assert ctx.allowed_responses == (",", ".")
    assert ctx.metadata == {}


def test_delivery_result_required_fields():
    r = DeliveryResult(
        success=True, delivered_at_ms=100.0, actual_rt_ms=350.0,
        method="jspsych_callback_hook",
    )
    assert r.error is None


def test_navigation_outcome_required_fields():
    o = NavigationOutcome(action="advanced_instructions")
    assert o.details == {}


def test_experiment_data_required_fields():
    d = ExperimentData(trials=[{"x": 1}], format="json", raw='[{"x":1}]')
    assert d.metadata == {}


def test_driver_error_carries_structured_info():
    err = DriverError(kind="page_torn_down", context={"url": "x"}, recoverable=True)
    assert err.kind == "page_torn_down"
    assert err.recoverable is True


def test_unsupported_version_error_subclasses_driver_error():
    err = UnsupportedVersionError(
        detected_version="9.0.0",
        supported_versions=("7.3.0", "8.0.0"),
        missing_anchors=["vendor/jspsych/9.0.0/"],
    )
    assert isinstance(err, DriverError)
    assert err.detected_version == "9.0.0"


def test_platform_driver_is_a_protocol():
    """Protocol marker for static typing — concrete drivers don't subclass
    PlatformDriver; they implement its methods. inspect-based smoke check
    that the Protocol has the documented methods."""
    methods = {n for n, _ in inspect.getmembers(PlatformDriver, predicate=inspect.isfunction)}
    expected = {
        "can_handle", "setup", "loop_state", "navigate",
        "get_trial_context", "deliver_response",
        "wait_for_trial_end", "wait_for_completion",
        "retrieve_data", "teardown",
    }
    missing = expected - methods
    assert not missing, f"PlatformDriver missing methods: {missing}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_drivers_base.py -v
```

Expected: ImportError — `experiment_bot.drivers.base` doesn't exist.

- [ ] **Step 3: Create the package marker**

Create `src/experiment_bot/drivers/__init__.py`:

```python
```

(empty file — package marker).

- [ ] **Step 4: Create `base.py`**

Create `src/experiment_bot/drivers/base.py`:

```python
"""SP10 driver base types + Protocol contract.

A PlatformDriver implements the interface the bot library uses to talk to
a specific platform (jsPsych, cognition.run, PsychoJS, ...). Concrete
drivers implement these methods; the bot library never depends on any
specific platform.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

from playwright.async_api import Page


class TrialLoopState(Enum):
    NEEDS_NAVIGATION = "needs_navigation"
    READY_FOR_TRIAL = "ready_for_trial"
    COMPLETE = "complete"


@dataclass(frozen=True)
class TrialContext:
    """Per-trial state the driver hands to the bot library."""
    stimulus_id: str
    condition: str
    allowed_responses: tuple[str, ...]
    expected_correct: str | None
    response_window_ms: int | None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryResult:
    """Telemetry from `deliver_response`."""
    success: bool
    delivered_at_ms: float
    actual_rt_ms: float
    method: str
    error: str | None = None


@dataclass(frozen=True)
class NavigationOutcome:
    """Telemetry from `navigate`."""
    action: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentData:
    """Output of `retrieve_data`. The Oracle reads `trials` for analysis."""
    trials: list[Mapping[str, Any]]
    format: Literal["csv", "json"]
    raw: bytes | str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class DriverError(Exception):
    """Structured error from a driver method.

    `recoverable=True` signals the bot library may retry the operation
    once; `recoverable=False` aborts the session.
    """
    def __init__(
        self, kind: str, context: Mapping[str, Any] | None = None,
        recoverable: bool = False,
    ):
        super().__init__(f"{kind}: {context}")
        self.kind = kind
        self.context = dict(context or {})
        self.recoverable = recoverable


class UnsupportedVersionError(DriverError):
    """Raised by Driver.create() when the live platform version isn't
    anchored. Bot library catches and switches to DiagnosticDriver."""
    def __init__(
        self, detected_version: str, supported_versions: tuple[str, ...],
        missing_anchors: list[str],
    ):
        super().__init__(
            kind="unsupported_version",
            context={
                "detected_version": detected_version,
                "supported_versions": supported_versions,
                "missing_anchors": missing_anchors,
            },
            recoverable=False,
        )
        self.detected_version = detected_version
        self.supported_versions = supported_versions
        self.missing_anchors = missing_anchors


@runtime_checkable
class PlatformDriver(Protocol):
    """Contract every platform driver implements.

    Methods are async. Concrete drivers may also expose driver-specific
    init logic (e.g., `JsPsychDriver.create(page)` classmethod for the
    version-check construction path).
    """

    @classmethod
    async def can_handle(cls, page: Page) -> bool:
        """Cheap DOM/window inspection. No LLM, no side effects."""
        ...

    async def setup(self, page: Page) -> None:
        """One-time per-session driver init. May install runtime hooks
        (e.g., monkey-patch the platform's keyboard handler), set focus."""
        ...

    async def loop_state(self, page: Page) -> TrialLoopState:
        """Polled by the bot library's outer loop. Cheap."""
        ...

    async def navigate(self, page: Page) -> NavigationOutcome:
        """When loop_state == NEEDS_NAVIGATION, advance the page state.
        May click instructions, dismiss feedback, respond to attention
        checks. Returns telemetry."""
        ...

    async def get_trial_context(self, page: Page) -> TrialContext:
        """When READY_FOR_TRIAL, return the active trial's context."""
        ...

    async def deliver_response(
        self, page: Page, response: str | None, rt_ms: float | None,
    ) -> DeliveryResult:
        """Make the platform record (response, rt_ms). response=None
        means withhold."""
        ...

    async def wait_for_trial_end(self, page: Page) -> None:
        """Block until the platform has moved past the current trial."""
        ...

    async def wait_for_completion(self, page: Page) -> None:
        """Block until the experiment is over."""
        ...

    async def retrieve_data(self, page: Page) -> ExperimentData:
        """Pull the platform's exported data."""
        ...

    async def teardown(self, page: Page) -> None:
        """Pre-close cleanup. Often no-op."""
        ...
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_drivers_base.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/experiment_bot/drivers/__init__.py src/experiment_bot/drivers/base.py tests/test_drivers_base.py
git commit -m "$(cat <<'EOF'
feat(drivers): PlatformDriver Protocol + types

Phase 1 of SP10. Defines the contract every platform driver implements:
can_handle, setup, loop_state, navigate, get_trial_context,
deliver_response, wait_for_trial_end, wait_for_completion,
retrieve_data, teardown. Types: TrialContext, DeliveryResult,
NavigationOutcome, ExperimentData, TrialLoopState.

Error hierarchy: DriverError with recoverable flag; subclass
UnsupportedVersionError carries detected/supported version info for
the DiagnosticDriver version-mismatch path.

No concrete drivers yet; that's Tasks 4 (registry), 5 (diagnostic),
12+ (JsPsychDriver).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4: Create `drivers/registry.py` with `identify_driver` + tests

**Files:**
- Create: `src/experiment_bot/drivers/registry.py`
- Create: `tests/test_drivers_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drivers_registry.py`:

```python
"""SP10: identify_driver picks the first matching registered driver,
falls back to DiagnosticDriver on no match or unsupported version."""
from __future__ import annotations
from unittest.mock import AsyncMock

import pytest

from experiment_bot.drivers.base import (
    DriverError, PlatformDriver, UnsupportedVersionError,
)
from experiment_bot.drivers.registry import identify_driver


class _MockDriver:
    """Test double for a registered driver."""
    _can_handle_value: bool = False
    _create_raises: Exception | None = None

    def __init__(self, name: str):
        self._name = name

    @classmethod
    async def can_handle(cls, page) -> bool:
        return cls._can_handle_value

    @classmethod
    async def create(cls, page):
        if cls._create_raises is not None:
            raise cls._create_raises
        return cls(name=cls.__name__)


class _AcceptingDriver(_MockDriver):
    _can_handle_value = True


class _RejectingDriver(_MockDriver):
    _can_handle_value = False


class _UnsupportedVersionDriver(_MockDriver):
    _can_handle_value = True
    _create_raises = UnsupportedVersionError(
        detected_version="9.0",
        supported_versions=("7.3", "8.0"),
        missing_anchors=["vendor/x/9.0/"],
    )


@pytest.mark.asyncio
async def test_identify_driver_picks_first_match(monkeypatch):
    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_RejectingDriver, _AcceptingDriver],
    )
    driver = await identify_driver(page)
    assert driver._name == "_AcceptingDriver"


@pytest.mark.asyncio
async def test_identify_driver_falls_back_to_diagnostic_on_no_match(monkeypatch):
    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_RejectingDriver],
    )
    page.url = "http://example.com/test"
    page.title = AsyncMock(return_value="Unknown")
    page.evaluate = AsyncMock(return_value={"jspsych_keys": [], "ids": [], "classes": []})
    page.screenshot = AsyncMock(return_value=b"")
    driver = await identify_driver(page)
    # DiagnosticDriver instance
    assert driver.__class__.__name__ == "DiagnosticDriver"


@pytest.mark.asyncio
async def test_identify_driver_falls_back_on_unsupported_version(monkeypatch):
    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_UnsupportedVersionDriver],
    )
    page.url = "http://example.com/test"
    page.title = AsyncMock(return_value="Unknown")
    page.evaluate = AsyncMock(return_value={"jspsych_keys": [], "ids": [], "classes": []})
    page.screenshot = AsyncMock(return_value=b"")
    driver = await identify_driver(page)
    assert driver.__class__.__name__ == "DiagnosticDriver"
    assert getattr(driver, "_mode", None) == "version_mismatch"


@pytest.mark.asyncio
async def test_identify_driver_skips_drivers_whose_can_handle_raises(monkeypatch):
    class _ExplodingDriver(_MockDriver):
        @classmethod
        async def can_handle(cls, page):
            raise RuntimeError("boom")

    page = AsyncMock()
    monkeypatch.setattr(
        "experiment_bot.drivers.registry.REGISTERED_DRIVERS",
        [_ExplodingDriver, _AcceptingDriver],
    )
    driver = await identify_driver(page)
    assert driver._name == "_AcceptingDriver"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_drivers_registry.py -v
```

Expected: ImportError — `experiment_bot.drivers.registry` doesn't exist.

- [ ] **Step 3: Create `registry.py`**

```python
"""SP10 driver registry — picks the right driver at session start."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from playwright.async_api import Page

from experiment_bot.drivers.base import (
    PlatformDriver, UnsupportedVersionError,
)
from experiment_bot.drivers.diagnostic import DiagnosticDriver

logger = logging.getLogger(__name__)


# Order matters: specific drivers first. DiagnosticDriver is NOT in this
# list — the bot library invokes it directly on no-match or version-
# mismatch.
REGISTERED_DRIVERS: list[type[PlatformDriver]] = [
    # JsPsychDriver added in Task 12
    # CognitionRunDriver added when needed
]


async def identify_driver(page: Page) -> PlatformDriver:
    """Pick the first registered driver whose `can_handle` returns True.

    On UnsupportedVersionError during driver.create(): switch to
    DiagnosticDriver.for_version_mismatch.

    On no driver matching at all: DiagnosticDriver.for_unknown_platform.
    """
    for driver_cls in REGISTERED_DRIVERS:
        try:
            matches = await driver_cls.can_handle(page)
        except Exception as e:
            logger.warning(
                "%s.can_handle raised; skipping: %s", driver_cls.__name__, e,
            )
            continue
        if not matches:
            continue
        try:
            return await driver_cls.create(page)
        except UnsupportedVersionError as e:
            return await DiagnosticDriver.for_version_mismatch(page, e)
    return await DiagnosticDriver.for_unknown_platform(page)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_drivers_registry.py -v
```

Expected: all 4 tests pass (one depends on DiagnosticDriver existing — see Task 5; if Task 5 hasn't landed yet, expect ImportError and proceed to Task 5).

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/drivers/registry.py tests/test_drivers_registry.py
git commit -m "$(cat <<'EOF'
feat(drivers): identify_driver registry + fallback chain

Iterates REGISTERED_DRIVERS in declaration order. First driver whose
can_handle returns True wins; UnsupportedVersionError during create()
routes to DiagnosticDriver.for_version_mismatch. No match → 
DiagnosticDriver.for_unknown_platform.

Drivers whose can_handle raises are skipped with a warning, not
fatal — preserves resilience when a driver's heuristic depends on
features that might not be present on every page.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5: Create `drivers/diagnostic.py` (DiagnosticDriver) + tests

**Files:**
- Create: `src/experiment_bot/drivers/diagnostic.py`
- Create: `tests/test_drivers_diagnostic.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drivers_diagnostic.py`:

```python
"""SP10: DiagnosticDriver writes structured reports for unknown
platforms or unsupported versions; raises DriverError on any
operational method (setup, loop_state, etc.)."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from experiment_bot.drivers.base import DriverError, UnsupportedVersionError
from experiment_bot.drivers.diagnostic import DiagnosticDriver


def _fake_page(url="http://example.com/test"):
    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value="Unknown Task")
    page.evaluate = AsyncMock(return_value={
        "jspsych_keys": [], "ids": ["main", "content"], "classes": ["wrapper"],
    })
    page.screenshot = AsyncMock(return_value=b"\x89PNG-fake")
    return page


@pytest.mark.asyncio
async def test_for_unknown_platform_builds_a_report():
    page = _fake_page()
    driver = await DiagnosticDriver.for_unknown_platform(page)
    assert driver._mode == "unknown_platform"
    assert "Unknown Task" in driver._report
    assert "main" in driver._report
    assert "wrapper" in driver._report


@pytest.mark.asyncio
async def test_for_version_mismatch_builds_a_report():
    page = _fake_page()
    err = UnsupportedVersionError(
        detected_version="9.0",
        supported_versions=("7.3", "8.0"),
        missing_anchors=["vendor/jspsych/9.0/"],
    )
    driver = await DiagnosticDriver.for_version_mismatch(page, err)
    assert driver._mode == "version_mismatch"
    assert "9.0" in driver._report
    assert "7.3" in driver._report
    assert "vendor/jspsych/9.0/" in driver._report


@pytest.mark.asyncio
async def test_setup_raises_driver_error_so_executor_aborts_cleanly(tmp_path):
    page = _fake_page()
    driver = await DiagnosticDriver.for_unknown_platform(page)
    driver._report_dir = tmp_path  # write the report into the tmp dir
    with pytest.raises(DriverError) as excinfo:
        await driver.setup(page)
    assert excinfo.value.kind in ("diagnostic_unknown_platform", "diagnostic_version_mismatch")
    # Report was written
    report_files = list(tmp_path.glob("driver_*.md"))
    assert len(report_files) == 1


@pytest.mark.asyncio
async def test_operational_methods_raise_driver_error():
    page = _fake_page()
    driver = await DiagnosticDriver.for_unknown_platform(page)
    for method_name in ("loop_state", "navigate", "get_trial_context"):
        method = getattr(driver, method_name)
        with pytest.raises(DriverError):
            await method(page)


@pytest.mark.asyncio
async def test_can_handle_returns_false_so_diagnostic_never_matches_in_registry():
    # DiagnosticDriver is not in REGISTERED_DRIVERS; this is a safety check.
    assert await DiagnosticDriver.can_handle(_fake_page()) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_drivers_diagnostic.py -v
```

Expected: ImportError — `experiment_bot.drivers.diagnostic` doesn't exist.

- [ ] **Step 3: Create `diagnostic.py`**

```python
"""SP10 DiagnosticDriver — fallback when no platform driver matches."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from playwright.async_api import Page

from experiment_bot.drivers.base import (
    DeliveryResult, DriverError, ExperimentData, NavigationOutcome,
    TrialContext, TrialLoopState, UnsupportedVersionError,
)

logger = logging.getLogger(__name__)


_FINGERPRINT_JS = """
(() => {
  const out = {
    jspsych_keys: Object.keys(window).filter(k =>
      /jspsych|psychojs|cognition|response|trial|stimulus|experiment/i.test(k)
    ).slice(0, 50),
    ids: Array.from(document.querySelectorAll('[id]')).map(e => e.id).slice(0, 30),
    classes: (() => {
      const s = new Set();
      document.querySelectorAll('[class]').forEach(e => {
        e.className.split(/\\s+/).forEach(c => { if (c) s.add(c); });
      });
      return Array.from(s).slice(0, 30);
    })(),
  };
  return out;
})()
"""


class DiagnosticDriver:
    """Last-resort fallback. Writes a structured report and aborts."""

    def __init__(self, report: str, mode: str):
        self._report = report
        self._mode = mode
        # Set by the executor BEFORE setup() is called, pointing at the
        # session output dir. Defaults to cwd for tests that don't set it.
        self._report_dir: Path = Path.cwd()

    @classmethod
    async def can_handle(cls, page: Page) -> bool:
        # Never matches via the registry — invoked directly as a fallback.
        return False

    @classmethod
    async def for_unknown_platform(cls, page: Page) -> "DiagnosticDriver":
        report = await cls._build_unknown_platform_report(page)
        return cls(report=report, mode="unknown_platform")

    @classmethod
    async def for_version_mismatch(
        cls, page: Page, err: UnsupportedVersionError,
    ) -> "DiagnosticDriver":
        report = await cls._build_version_mismatch_report(page, err)
        return cls(report=report, mode="version_mismatch")

    @staticmethod
    async def _fingerprint(page: Page) -> Mapping[str, Any]:
        try:
            return await page.evaluate(_FINGERPRINT_JS)
        except Exception as e:
            logger.warning("DiagnosticDriver fingerprint failed: %s", e)
            return {"jspsych_keys": [], "ids": [], "classes": []}

    @classmethod
    async def _build_unknown_platform_report(cls, page: Page) -> str:
        url = getattr(page, "url", "<unknown>")
        title = await page.title()
        fp = await cls._fingerprint(page)
        return f"""# Driver needed — unknown platform

The bot encountered a page that no registered driver claimed via
`can_handle`. Below is a fingerprint of the page; use it to write a
new driver under `src/experiment_bot/drivers/<platform_name>/`.

## Page

- URL: `{url}`
- Title: `{title}`

## window.* keys matching /jspsych|psychojs|cognition|response|trial|stimulus|experiment/i

```
{json.dumps(fp.get("jspsych_keys", []), indent=2)}
```

## Top DOM IDs

```
{json.dumps(fp.get("ids", []), indent=2)}
```

## Top class tokens

```
{json.dumps(fp.get("classes", []), indent=2)}
```

## Next steps

1. Identify the platform: jsPsych, cognition.run, PsychoJS, or custom.
2. Create `src/experiment_bot/drivers/<platform>/` and implement
   `PlatformDriver` (see `drivers/base.py` for the contract).
3. Vendor selective source files under `vendor/<platform>/<version>/`
   if the platform is open source. Update `vendor/LICENSES.md`.
4. Register the new driver class in
   `src/experiment_bot/drivers/registry.py`'s `REGISTERED_DRIVERS`
   list (specific drivers first).
5. Re-run the bot against this URL.
"""

    @classmethod
    async def _build_version_mismatch_report(
        cls, page: Page, err: UnsupportedVersionError,
    ) -> str:
        url = getattr(page, "url", "<unknown>")
        title = await page.title()
        return f"""# Driver needed — unsupported platform version

A registered driver matched this page's platform but does not have
anchored support for the platform's current version. Add the missing
anchors and update the driver's compatibility table.

## Page

- URL: `{url}`
- Title: `{title}`

## Version mismatch

- Detected: `{err.detected_version}`
- Supported by current driver: `{", ".join(err.supported_versions)}`
- Missing anchor files: `{", ".join(err.missing_anchors)}`

## Next steps

1. Vendor the missing anchor files for the new version (typically
   the keyboard listener API, plugin lifecycle, and data export
   modules from the platform's source).
2. Update the driver's version-compatibility table to include the
   new version.
3. Add tests covering any API differences from previously-supported
   versions.
4. Re-run the bot against this URL.
"""

    async def setup(self, page: Page) -> None:
        """Write the diagnostic report to disk and raise. The executor's
        catch block aborts the session cleanly."""
        report_filename = (
            "driver_needed.md" if self._mode == "unknown_platform"
            else "driver_version_needed.md"
        )
        path = self._report_dir / report_filename
        path.write_text(self._report)
        logger.warning(
            "DiagnosticDriver wrote %s; aborting session.", path,
        )
        kind = f"diagnostic_{self._mode}"
        raise DriverError(
            kind=kind,
            context={"report_path": str(path), "mode": self._mode},
            recoverable=False,
        )

    # All operational methods raise DriverError. setup() is the only
    # method the executor calls before discovering the diagnostic mode.

    async def loop_state(self, page: Page) -> TrialLoopState:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def navigate(self, page: Page) -> NavigationOutcome:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def get_trial_context(self, page: Page) -> TrialContext:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def deliver_response(
        self, page: Page, response: str | None, rt_ms: float | None,
    ) -> DeliveryResult:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def wait_for_trial_end(self, page: Page) -> None:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def wait_for_completion(self, page: Page) -> None:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def retrieve_data(self, page: Page) -> ExperimentData:
        raise DriverError(kind="diagnostic_mode", recoverable=False)

    async def teardown(self, page: Page) -> None:
        # No-op — safe to call even after setup raised.
        return None
```

- [ ] **Step 4: Run tests to verify they pass + the registry tests**

```bash
uv run pytest tests/test_drivers_diagnostic.py tests/test_drivers_registry.py -v
```

Expected: all diagnostic + registry tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/drivers/diagnostic.py tests/test_drivers_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(drivers): DiagnosticDriver fallback writes structured reports

Two construction paths: for_unknown_platform and for_version_mismatch.
Each builds a markdown report describing what's needed for a new
driver (or new version anchor) and writes it to the session's run dir
during setup(), then raises DriverError to abort the session cleanly.

Operational methods (loop_state, navigate, etc.) also raise — the
DiagnosticDriver never runs trials. This is the contribution path
when the bot encounters a platform it can't handle: read the report,
write a new driver, register it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Bot library refactor

Most of the current 1066-line `core/executor.py` becomes obsolete because the driver subsumes its concerns. Phase 2 slims `__init__`, replaces the trial loop with the driver-based version, updates cli.py, and deletes the SP9a agent package and obsolete tests.

### Task 6: Slim `TaskExecutor.__init__` + add `_run_session`

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `src/experiment_bot/output/writer.py` (add `save_experiment_data`)
- Modify: `tests/test_executor.py` (add `_run_session` test)

Replace the SP9a-era `__init__` (lines ~63-132) with a slim version that keeps only `_taskcard`, `_config`, `_headless`, `_session_seed`, `_session_params`, `_rng`, `_py_rng`, `_sampler`, `_writer`, `_trial_count`, `_recent_errors`. Drop the `session_agent` kwarg.

Delete from the executor file: `_resolve_key_mapping` (static), `_KEY_ALIASES`, `_normalize_key`, `_WITHHOLD_SENTINELS`, `_is_withhold_sentinel`, `_resolve_response_key`, `_is_trial_stimulus`, `_should_respond_correctly`, `_should_omit`, `_pick_wrong_key`, `_resolve_rt_distribution_key`, `_install_keydown_listener`, `_drain_keydown_log`, `_log_trial_with_keypress_diag`, `_invoke_session_agent`, `_handle_attention_check`, `_wait_for_completion`, `_wait_for_trial_end`, `_stimulus_detection_js`, `_build_interrupt_check_js`. Also remove `_lookup`, `_navigator`, `_seen_response_keys`, `_key_map`, `_stimulus_detection_js_cache`, `_interrupt_js`, `_navigation_condition_name`, `_attention_check_conditions`, `_session_agent`, `_runtime_key_mapping`, `_session_agent_directive` from `__init__`.

Add the new `_run_session(self, page, driver)`:

```python
    async def _run_session(self, page, driver) -> None:
        """SP10 driver-based trial loop."""
        from experiment_bot.drivers.base import TrialLoopState
        await driver.setup(page)
        history: list[dict] = []
        while True:
            state = await driver.loop_state(page)
            if state == TrialLoopState.COMPLETE:
                break
            if state == TrialLoopState.NEEDS_NAVIGATION:
                outcome = await driver.navigate(page)
                self._writer.log_trial({
                    "type": "navigation",
                    "action": outcome.action,
                    "details": dict(outcome.details),
                })
                continue
            ctx = await driver.get_trial_context(page)
            rt = self._sampler.sample(ctx.condition, history=history)
            intended_correct = self._py_rng.random() < self._config.performance.get_accuracy(ctx.condition)
            response = _resolve_response(ctx, intended_correct, self._py_rng, self._taskcard)
            result = await driver.deliver_response(page, response, rt)
            self._writer.log_trial({
                "type": "trial",
                "trial_index": self._trial_count,
                "stimulus_id": ctx.stimulus_id,
                "condition": ctx.condition,
                "intended_correct": intended_correct,
                "response_key": response,
                "rt_ms": rt,
                "delivery": {
                    "success": result.success, "method": result.method,
                    "actual_rt_ms": result.actual_rt_ms, "error": result.error,
                },
            })
            history.append({
                "condition": ctx.condition,
                "intended_correct": intended_correct,
                "rt": rt,
            })
            self._recent_errors.appendleft(not intended_correct)
            self._trial_count += 1
            await driver.wait_for_trial_end(page)
        await driver.wait_for_completion(page)
        data = await driver.retrieve_data(page)
        self._writer.save_experiment_data(data)
```

And the module-level helper `_resolve_response`:

```python
def _resolve_response(ctx, intended_correct, rng, taskcard):
    """SP10 response-key resolution.
    Priority: ctx.expected_correct > legacy taskcard.task_specific.key_map > random.
    None means withhold.
    """
    if ctx.expected_correct is None and not ctx.allowed_responses:
        return None
    correct = ctx.expected_correct
    if correct is None and taskcard is not None:
        legacy = (taskcard.task_specific or {}).get("key_map", {}) if hasattr(taskcard, "task_specific") else {}
        cand = legacy.get(ctx.condition)
        if cand and cand not in ("dynamic", "dynamic_mapping"):
            correct = cand
    if correct is None:
        return rng.choice(list(ctx.allowed_responses)) if ctx.allowed_responses else None
    if intended_correct:
        return correct
    wrong = [k for k in ctx.allowed_responses if k != correct]
    return rng.choice(wrong) if wrong else None
```

Add `save_experiment_data` to `src/experiment_bot/output/writer.py`:

```python
    def save_experiment_data(self, data) -> None:
        """SP10: persist the driver-retrieved platform data export."""
        if not self._run_dir:
            return
        path = self._run_dir / f"experiment_data.{data.format}"
        if isinstance(data.raw, bytes):
            path.write_bytes(data.raw)
        else:
            path.write_text(data.raw)
```

Add a test that `_run_session` dispatches NEEDS_NAVIGATION → READY_FOR_TRIAL → COMPLETE with a MagicMock driver. Commit:

```bash
git commit -am "feat(executor): SP10 slim __init__ + _run_session + writer.save_experiment_data"
```

### Task 7: Replace `TaskExecutor.run()` body with driver-based flow

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `tests/test_executor.py`

Add imports:

```python
from experiment_bot.drivers.diagnostic import DiagnosticDriver
from experiment_bot.drivers.registry import identify_driver
```

Replace `run()`:

```python
    async def run(self, task_url: str) -> None:
        task_name = self._config.task.name.replace(" ", "_").lower()
        run_dir = self._writer.create_run(task_name, self._config)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport=self._config.runtime.timing.viewport,
            )
            page = await context.new_page()
            session_status = "ok"
            diagnostic_path = None
            try:
                await page.goto(task_url, wait_until="networkidle")
                driver = await identify_driver(page)
                if isinstance(driver, DiagnosticDriver):
                    driver._report_dir = run_dir
                try:
                    await self._run_session(page, driver)
                finally:
                    try:
                        await driver.teardown(page)
                    except Exception as e:
                        logger.warning("driver.teardown raised: %s", e)
            except Exception as e:
                from experiment_bot.drivers.base import DriverError
                if isinstance(e, DriverError) and e.kind.startswith("diagnostic_"):
                    session_status = "diagnostic_mode"
                    diagnostic_path = e.context.get("report_path")
                    logger.warning("Session aborted: %s", e.kind)
                else:
                    session_status = "error"
                    logger.error("Task execution failed: %s", e)
                    try:
                        screenshot = await page.screenshot(type="png")
                        self._writer.save_screenshot(screenshot, "error.png")
                    except Exception:
                        pass
                    raise
            finally:
                metadata = {
                    "task_name": task_name, "task_url": task_url,
                    "total_trials": self._trial_count, "headless": self._headless,
                    "session_seed": self._session_seed,
                    "session_params": self._session_params,
                    "status": session_status,
                }
                if diagnostic_path is not None:
                    metadata["diagnostic_report_path"] = diagnostic_path
                if self._taskcard is not None:
                    pb = getattr(self._taskcard, "produced_by", None)
                    metadata["taskcard_sha256"] = getattr(pb, "taskcard_sha256", "") if pb else ""
                self._writer.save_metadata(metadata)
                self._writer.finalize()
                await browser.close()
```

Add a test using `monkeypatch` to inject a fake driver + fake `async_playwright`. Verify `identify_driver` is called and `_run_session` is dispatched. Commit.

### Task 8: Update `cli.py` — drop SP9a SessionAgent

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Modify: `tests/test_cli.py`

Delete the SP9a imports and `_build_session_agent()`. In `_run_task`, drop the `session_agent = _build_session_agent()` line and the `session_agent=session_agent` kwarg.

In `tests/test_cli.py`: delete `test_cli_passes_session_agent_to_executor` and `test_cli_proceeds_when_session_agent_unavailable`. Add a regression test that `session_agent` is NOT in the kwargs passed to TaskExecutor. Commit.

### Task 9: Delete obsolete tests + the `agent/` package

```bash
git rm -r src/experiment_bot/agent/
git rm tests/test_session_agent.py
git rm tests/test_executor_session_agent_integration.py
git rm tests/test_executor_keypress_diagnostic.py
```

In `tests/test_executor.py`: remove tests referencing deleted methods (`_resolve_response_key`, `_pick_wrong_key`, `_resolve_rt_distribution_key`, `_install_keydown_listener`, `_navigator`, `_handle_attention_check`, `task_specific`, `key_map`). Keep tests for `__init__`, `_run_session`, `run()`.

Run the suite — expect zero failures, lower total count. Commit.

---

## Phase 3 — JsPsychDriver

Builds the first real driver. Vendored anchor files for one jsPsych version; driver implements every PlatformDriver method by hooking the platform's own response-handler.

### Task 10: Identify jsPsych version on the deployed expfactory tasks

**Files:** none (research task)

Run a small live-page probe to identify the jsPsych version used by the expfactory deployment:

```bash
uv run python <<'EOF'
import asyncio
from playwright.async_api import async_playwright

async def probe(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2)
        info = await page.evaluate("""(() => ({
          version: (window.jsPsych && window.jsPsych.version) ? window.jsPsych.version() : null,
          hasPluginAPI: typeof window.jsPsych?.pluginAPI !== 'undefined',
          pluginAPIKeys: Object.keys(window.jsPsych?.pluginAPI || {}).slice(0, 20),
        }))()""")
        print(url, info)
        await browser.close()

async def main():
    for u in [
        "https://deploy.expfactory.org/preview/10/",   # stroop
        "https://deploy.expfactory.org/preview/5/",    # n-back
        "https://deploy.expfactory.org/preview/9/",    # stop-signal
        "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html",
    ]:
        await probe(u)

asyncio.run(main())
EOF
```

Record the detected version per URL in `docs/sp10-investigation.md` (created in Task 17). Likely all expfactory pages use the same jsPsych version; kywch stop-it might differ.

### Task 11: Vendor jsPsych anchor files

**Files:**
- Create: `vendor/jspsych/<version>/KeyboardListenerAPI.ts`
- Create: `vendor/jspsych/<version>/plugin-html-keyboard-response.ts`
- Create: `vendor/jspsych/<version>/data-export-notes.md` (since data export is across multiple files)

WebFetch each file from the jsPsych GitHub repo at the tag matching the detected version. Prepend each vendored file with a provenance comment:

```
// SOURCE: https://github.com/jspsych/jsPsych/blob/<commit>/<path>
// COMMIT: <sha>
// LICENSE: MIT (see vendor/LICENSES.md)
// RETRIEVED: 2026-05-15
```

Commit:

```bash
git add vendor/jspsych/
git commit -m "vendor(jspsych): selective anchor files for <version>"
```

### Task 12: JsPsychDriver — `can_handle`, `create`, `setup` skeleton

**Files:**
- Create: `src/experiment_bot/drivers/jspsych/__init__.py`
- Create: `src/experiment_bot/drivers/jspsych/driver.py`
- Create: `tests/test_drivers_jspsych.py`

Create the subpackage. `JsPsychDriver.can_handle`:

```python
    @classmethod
    async def can_handle(cls, page) -> bool:
        try:
            return await page.evaluate("typeof window.jsPsych !== 'undefined'")
        except Exception:
            return False
```

`JsPsychDriver.create`:

```python
    @classmethod
    async def create(cls, page):
        version = await page.evaluate("window.jsPsych?.version?.() ?? null")
        if version not in cls.SUPPORTED_VERSIONS:
            raise UnsupportedVersionError(
                detected_version=str(version),
                supported_versions=cls.SUPPORTED_VERSIONS,
                missing_anchors=[f"vendor/jspsych/{version}/"],
            )
        return cls(version=version)
```

`SUPPORTED_VERSIONS` is a class attribute populated from Task 10's findings — initially a single version tuple like `("7.3.0",)`.

`setup(page)` installs the response hook (Task 13) and tracks teardown handles.

Add tests against a stubbed page with `evaluate` returning a fake jsPsych version. Commit.

### Task 13: JsPsychDriver — response delivery via `pluginAPI.getKeyboardResponse` hook

**Files:**
- Create: `src/experiment_bot/drivers/jspsych/responses.py`
- Modify: `tests/test_drivers_jspsych.py`

The hook strategy: monkey-patch `jsPsych.pluginAPI.getKeyboardResponse` at session start so each call captures the `{callback_function, valid_responses, persist}` args into a JS-side registry. The driver's `deliver_response(page, key, rt)` invokes the captured callback with `{key, rt}` after waiting `rt_ms` of simulated time.

```python
# responses.py
INSTALL_HOOK_JS = """
(() => {
  if (window.__bot_hook_installed) return;
  window.__bot_hook_installed = true;
  window.__bot_hook = { current: null, history: [] };
  const orig = window.jsPsych.pluginAPI.getKeyboardResponse;
  window.jsPsych.pluginAPI.getKeyboardResponse = function(params) {
    window.__bot_hook.current = {
      callback_function: params.callback_function,
      valid_responses: params.valid_responses,
      persist: params.persist,
      rt_method: params.rt_method,
      registered_at: performance.now(),
    };
    // Still call the original so jsPsych's own listeners are also
    // installed — keeps the trial behavior consistent if a real user
    // happened to press a key.
    return orig.call(this, params);
  };
})()
"""

DELIVER_JS_TEMPLATE = """
(() => {
  const hook = window.__bot_hook;
  if (!hook || !hook.current) return { ok: false, reason: 'no_active_listener' };
  const info = { rt: %(rt)s, key: %(key_js)s };
  hook.current.callback_function(info);
  hook.history.push({...info, delivered_at: performance.now()});
  hook.current = null;
  return { ok: true };
})()
"""

async def install_hook(page):
    await page.evaluate(INSTALL_HOOK_JS)

async def deliver(page, key, rt_ms):
    import json
    js = DELIVER_JS_TEMPLATE % {"rt": rt_ms, "key_js": json.dumps(key)}
    return await page.evaluate(js)
```

Driver method:

```python
    async def deliver_response(self, page, response, rt_ms):
        from time import perf_counter
        if response is None:
            # Withhold trial — do nothing; trial will time out naturally.
            return DeliveryResult(
                success=True, delivered_at_ms=0.0, actual_rt_ms=rt_ms or 0.0,
                method="withhold_no_op",
            )
        start = perf_counter()
        result = await deliver(page, response, rt_ms or 0.0)
        elapsed = (perf_counter() - start) * 1000
        return DeliveryResult(
            success=bool(result.get("ok")),
            delivered_at_ms=elapsed,
            actual_rt_ms=rt_ms or 0.0,
            method="jspsych_callback_hook",
            error=result.get("reason"),
        )
```

Add tests with stubbed `page.evaluate` returning the simulated hook result. Commit.

### Task 14: JsPsychDriver — `loop_state`, `get_trial_context`

**Files:**
- Create: `src/experiment_bot/drivers/jspsych/phases.py`
- Modify: `src/experiment_bot/drivers/jspsych/driver.py`
- Modify: `tests/test_drivers_jspsych.py`

`loop_state` inspects `window.jsPsych.getCurrentTrial?.()`:

```python
LOOP_STATE_JS = """
(() => {
  if (!window.jsPsych) return { state: 'unknown' };
  if (window.jsPsych.progress?.()?.percent_complete >= 100) return { state: 'complete' };
  const t = window.jsPsych.getCurrentTrial?.();
  if (!t) return { state: 'unknown' };
  const type_name = (t.type?.info?.name) || t.type?.name || String(t.type || 'unknown');
  // Keyboard-response trials → READY_FOR_TRIAL when hook is active.
  if (/keyboard-response/.test(type_name)) {
    if (window.__bot_hook?.current) return { state: 'ready_for_trial', type: type_name };
    return { state: 'needs_navigation', type: type_name, reason: 'hook_not_yet_armed' };
  }
  // Everything else (instructions, button-response, html-display, etc.) is
  // navigation.
  return { state: 'needs_navigation', type: type_name };
})()
"""
```

Driver method:

```python
    async def loop_state(self, page):
        from experiment_bot.drivers.base import TrialLoopState
        info = await page.evaluate(LOOP_STATE_JS)
        s = info.get("state")
        if s == "complete":
            return TrialLoopState.COMPLETE
        if s == "ready_for_trial":
            return TrialLoopState.READY_FOR_TRIAL
        return TrialLoopState.NEEDS_NAVIGATION
```

`get_trial_context` reads the captured hook state + `getCurrentTrial`:

```python
GET_CTX_JS = """
(() => {
  const trial = window.jsPsych.getCurrentTrial?.();
  const hook = window.__bot_hook?.current;
  if (!trial || !hook) return null;
  return {
    stimulus_id: String(trial.data?.stimulus_id ?? trial.stimulus ?? 'unknown'),
    condition: String(trial.data?.condition ?? trial.condition ?? 'default'),
    allowed_responses: hook.valid_responses,
    expected_correct: trial.data?.correct_response ?? trial.correct_response ?? null,
    response_window_ms: trial.trial_duration ?? null,
    metadata: { type_name: trial.type?.info?.name ?? null },
  };
})()
"""

    async def get_trial_context(self, page):
        from experiment_bot.drivers.base import TrialContext
        info = await page.evaluate(GET_CTX_JS)
        if info is None:
            from experiment_bot.drivers.base import DriverError
            raise DriverError(kind="no_active_trial", recoverable=True)
        return TrialContext(
            stimulus_id=info["stimulus_id"],
            condition=info["condition"],
            allowed_responses=tuple(info["allowed_responses"] or ()),
            expected_correct=info.get("expected_correct"),
            response_window_ms=info.get("response_window_ms"),
            metadata=info.get("metadata", {}),
        )
```

Note: the exact field names (`trial.data?.condition`, etc.) may vary by paradigm — these are heuristics. Phase 5 empirical runs will surface any per-paradigm adjustments; the driver can be refined when surfaced. Commit.

### Task 15: JsPsychDriver — `navigate`, `wait_for_trial_end`, `wait_for_completion`

**Files:**
- Create: `src/experiment_bot/drivers/jspsych/navigation.py`
- Modify: `src/experiment_bot/drivers/jspsych/driver.py`
- Modify: `tests/test_drivers_jspsych.py`

`navigate(page)` advances the current jsPsych trial. For instructions plugin, press Space; for button-response, click the first button; for html-display with a "continue" prompt, press Space; otherwise sleep briefly to let the page settle.

```python
NAVIGATE_JS = """
(() => {
  const trial = window.jsPsych.getCurrentTrial?.();
  if (!trial) return { action: 'no_op', reason: 'no_current_trial' };
  const type_name = (trial.type?.info?.name) || trial.type?.name || 'unknown';
  // Click first visible button if button-response
  if (/button-response/.test(type_name)) {
    const btn = document.querySelector('#jspsych-display-element button');
    if (btn) { btn.click(); return { action: 'clicked_button', type: type_name }; }
  }
  // For instructions / html-display with key advance: dispatch Space to root
  if (/instructions|html-/.test(type_name)) {
    const root = document.querySelector('#jspsych-display-element') || document.body;
    const init = { key: ' ', code: 'Space', bubbles: true, cancelable: true };
    root.dispatchEvent(new KeyboardEvent('keydown', init));
    root.dispatchEvent(new KeyboardEvent('keyup', init));
    return { action: 'dispatched_space', type: type_name };
  }
  return { action: 'noop', type: type_name };
})()
"""

    async def navigate(self, page):
        from experiment_bot.drivers.base import NavigationOutcome
        info = await page.evaluate(NAVIGATE_JS)
        # Brief pause so jsPsych can transition to the next trial.
        await asyncio.sleep(0.1)
        return NavigationOutcome(
            action=info.get("action", "noop"),
            details={"jspsych_type": info.get("type")},
        )
```

`wait_for_trial_end` is a no-op for the hook-based delivery — the callback we invoke completes the trial synchronously inside jsPsych. Implementation: `await asyncio.sleep(0.05)` to yield, then return.

`wait_for_completion` polls `progress?.()?.percent_complete >= 100` with a generous timeout. Commit.

### Task 16: JsPsychDriver — `retrieve_data`, `teardown`

**Files:**
- Create: `src/experiment_bot/drivers/jspsych/data_export.py`
- Modify: `src/experiment_bot/drivers/jspsych/driver.py`
- Modify: `tests/test_drivers_jspsych.py`

`retrieve_data` calls `jsPsych.data.get().json()`:

```python
    async def retrieve_data(self, page):
        from experiment_bot.drivers.base import ExperimentData
        raw_json = await page.evaluate("window.jsPsych.data.get().json()")
        import json as _json
        trials = _json.loads(raw_json)
        return ExperimentData(
            trials=trials,
            format="json",
            raw=raw_json,
            metadata={"jspsych_version": self._version},
        )
```

`teardown` removes the monkey-patch via try/except (safe even if hook never installed). Commit.

### Task 17: Register `JsPsychDriver` + smoke run

**Files:**
- Modify: `src/experiment_bot/drivers/registry.py`
- Create: `docs/sp10-investigation.md`

Update `registry.py`:

```python
from experiment_bot.drivers.jspsych.driver import JsPsychDriver

REGISTERED_DRIVERS: list[type[PlatformDriver]] = [
    JsPsychDriver,
]
```

Run one end-to-end smoke session:

```bash
cp /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.worktrees/sp8/taskcards/expfactory_stroop/f099a88b.json taskcards/expfactory_stroop/
set -a && source /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.env && set +a
export EXPERIMENT_BOT_LLM_CLIENT=api
uv run experiment-bot --label expfactory_stroop --seed 9701 https://deploy.expfactory.org/preview/10/ 2>&1 | tail -10
```

Document the result in `docs/sp10-investigation.md`: which hook strategy worked, any per-paradigm adjustments needed in `get_trial_context`, any timing surprises. Commit.

---

## Phase 4 — Reasoner pipeline simplification

### Task 18: Simplify Stage 1 prompt + validator + TaskConfig schema

**Files:**
- Modify: `src/experiment_bot/prompts/system.md`
- Modify: `src/experiment_bot/reasoner/stage1_structural.py`
- Modify: `src/experiment_bot/reasoner/validate.py`
- Modify: `src/experiment_bot/core/config.py`
- Modify: `tests/test_stage1_*.py`

In `prompts/system.md`: drop guidance about `response_key_js`, `navigation.phases`, `phase_detection`, `attention_check`, `advance_behavior`, `data_capture`. Add a new section "Recommended driver" instructing the LLM to examine source for platform markers and emit `recommended_driver: "JsPsychDriver" | "CognitionRunDriver" | "PsychoJsDriver" | "unknown"`.

In `stage1_structural.py`: replace `REQUIRED_FIELDS_CHECKLIST` with a slim version that lists only: task metadata (including paradigm_classes), stimuli (id + condition + description), performance.accuracy/omission, recommended_driver, pilot_validation_config. Update the final prompt sentence to match.

In `reasoner/validate.py`: shrink validator. Required fields: `task`, `stimuli` (each with `id` + `condition`), `performance`, `recommended_driver`. Drop checks for `task_specific.response_key_js`, `navigation.phases`, `runtime.phase_detection`, etc.

In `core/config.py`: add `recommended_driver: str = ""` and `driver_hints: dict = field(default_factory=dict)` to `TaskConfig`. Mark the obsolete blocks (`task_specific`, `navigation`, parts of `runtime` other than `timing.viewport` and `timing.rt_floor_ms`) as kept for backward compat but unused by the new executor.

Update the existing Stage 1 invariant tests (`test_stage1_response_key_js_prompt.py`, etc.) to match the simplified prompt. Delete tests that asserted presence of the dropped sections. Add a new test:

```python
def test_stage1_prompt_includes_recommended_driver_guidance():
    from pathlib import Path
    prompt = Path("src/experiment_bot/prompts/system.md").read_text()
    assert "recommended_driver" in prompt
    assert "JsPsychDriver" in prompt
```

Commit.

### Task 19: Stage 6 pilot → driver-based

**Files:**
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py`
- Modify: `tests/test_pilot.py`

Rewrite Stage 6 pilot. The current 336-line implementation pilots the SP1-era executor; under SP10 pilot becomes: "build a TaskExecutor, call run() against the source URL, verify status='ok' (no diagnostic_mode, no error) and verify retrieved data has ≥ 3 trials."

Most of the old pilot's failure recovery (`pilot_refinement_N.diff`) becomes obsolete because the driver subsumes the brittle bits. Pilot's job is now a thin end-to-end smoke. Keep the structure of producing `pilot.md` documentation alongside the TaskCard. Drop the iterative refinement loop.

Commit.

### Task 20: Migrate existing SP8 TaskCards (one-line `recommended_driver`)

**Files:**
- Modify: `taskcards/expfactory_stroop/f099a88b.json`
- Modify: `taskcards/expfactory_n_back/8198382d.json`
- Modify: `taskcards/expfactory_stop_signal/6ccd7d47.json`
- Modify: `taskcards/stopit_stop_signal/39e97714.json`

For each TaskCard JSON, add a top-level field:

```json
"recommended_driver": "JsPsychDriver"
```

This is a one-line addition; the existing literature-derived fields (`response_distributions`, `temporal_effects`, `performance`, etc.) are preserved.

Sanity-check each modified TaskCard loads cleanly:

```bash
uv run python -c "
from experiment_bot.taskcard.loader import load_latest
from pathlib import Path
for label in ['expfactory_stroop', 'expfactory_n_back', 'expfactory_stop_signal', 'stopit_stop_signal']:
    tc = load_latest(Path('taskcards'), label=label)
    print(label, tc.recommended_driver if hasattr(tc, 'recommended_driver') else '(missing)')
"
```

Expected: each prints `JsPsychDriver`.

Commit:

```bash
git commit -am "chore(taskcards): add recommended_driver=JsPsychDriver to SP8-regen TaskCards"
```

---

## Phase 5 — Empirical validation

### Task 21: 4 paradigms × 3 sessions; audit; hard-gate check

**Files:** sessions are gitignored output; no committed artifacts here.

Run order — stroop first (strongest signal), then n-back (regression check), then stop-signal expfactory, then stop-it.

```bash
set -a && source /Users/lobennett/grants/r01_rdoc/projects/experiment_bot/.env && set +a
export EXPERIMENT_BOT_LLM_CLIENT=api

# Stroop expfactory ×3
for seed in 10001 10002 10003; do
  echo "=== stroop seed $seed ===" && uv run experiment-bot --label expfactory_stroop --seed $seed https://deploy.expfactory.org/preview/10/ 2>&1 | tail -3
done

# N-back expfactory ×3
for seed in 10101 10102 10103; do
  echo "=== n_back seed $seed ===" && uv run experiment-bot --label expfactory_n_back --seed $seed https://deploy.expfactory.org/preview/5/ 2>&1 | tail -3
done

# Stop-signal expfactory ×3
for seed in 10201 10202 10203; do
  echo "=== stop_signal seed $seed ===" && uv run experiment-bot --label expfactory_stop_signal --seed $seed https://deploy.expfactory.org/preview/9/ 2>&1 | tail -3
done

# Stop-it kywch ×3
for seed in 10301 10302 10303; do
  echo "=== stopit seed $seed ===" && uv run experiment-bot --label stopit_stop_signal --seed $seed https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html 2>&1 | tail -3
done
```

Hand-roll the alignment audit (the `scripts/keypress_audit.py` `PLATFORM_ADAPTERS` keys may not match the new task_name values; the audit logic itself is simple):

```bash
uv run python <<'EOF'
import json, csv
from pathlib import Path
from collections import Counter

paradigms = [
    ("expfactory_stroop", {"congruent", "incongruent"}),
    ("expfactory_n_back", {"match_1back", "mismatch_1back", "match_2back", "mismatch_2back"}),
    ("expfactory_stop_signal", {"go", "stop", "stop_signal", "go_signal"}),
    ("stopit_stop_signal", {"go", "stop", "stop_signal", "go_signal"}),
]
for label, conds in paradigms:
    print(f"\n=== {label} ===")
    for ses_dir in sorted(Path(f"output/{label}").glob("2026-*"))[-3:]:
        bot_log = json.loads((ses_dir / "bot_log.json").read_text())
        # Driver retrieved data: experiment_data.{csv,json}
        json_p = ses_dir / "experiment_data.json"
        csv_p = ses_dir / "experiment_data.csv"
        if json_p.exists():
            plat = json.loads(json_p.read_text())
        elif csv_p.exists():
            with csv_p.open() as f:
                plat = list(csv.DictReader(f))
        else:
            print(f"  {ses_dir.name}: NO DATA EXPORT")
            continue
        test_rows = [r for r in plat if r.get("trial_id") in ("test_trial", "stop_signal_trial")]
        bot_trials = [t for t in bot_log if t.get("type") == "trial"]
        n = min(len(bot_trials), len(test_rows))
        c = Counter()
        for i in range(n):
            b = bot_trials[i]
            p = test_rows[i]
            c["pressed==recorded"] += (b.get("response_key") == p.get("response"))
        pct = 100*c["pressed==recorded"]/n if n else 0
        print(f"  {ses_dir.name}: n={n}, pressed==recorded={pct:.1f}%")
EOF
```

For each paradigm, compute mean `pressed==recorded` across the 3 sessions. Check against hard gates from spec §3 Phase 5:

- Stroop: ≥ 90%
- N-back: ≥ 90%
- Stop-signal expfactory: ≥ 90%
- Stop-it: ≥ 90%

Also re-run the SP5 / SP6 validators against the new sessions (Flanker isn't in this set — if Flanker norms-validation is still required, add a Flanker session pair to the run; spec §2's gate references Flanker as the SP5/SP6 anchor):

```bash
uv run python -m experiment_bot.validation.cli --paradigm-class conflict --output-dir output/expfactory_stroop/
```

Document results inline; the results report (Task 22) consolidates.

No commit here — the run output is gitignored.

---

## Phase 6 — Documentation + tag

### Task 22: Write `docs/sp10-results.md` + update CLAUDE.md SP history + charter

**Files:**
- Create: `docs/sp10-results.md`
- Modify: `CLAUDE.md` (replace SP10 placeholder with completion entry)
- Modify: `docs/reviewer-1-charter.md` ("Last reviewed at" + new threat-model probe candidates)

`docs/sp10-results.md` follows the structure used by prior SP results docs (sp5-results.md, sp7-results.md, sp8-results.md):

- Date, spec/plan refs, branch/tag
- Goal restated
- Procedure summary
- Per-paradigm alignment table (before SP9a baseline vs SP10)
- Hard gate pass/fail summary
- Soft gate observations (Gratton effect / SSRT extraction, no visible feedback flicker)
- Comparison to SP5 (Flanker rt_distribution) and SP6 (Flanker PES) gates
- Framework gaps surfaced (SP10 backlog candidates: cognitionrun_stroop driver, PsychoJsDriver, schema migration polish, Stage 6 pilot refinement)
- Status: PASS / MIXED / FAIL

In CLAUDE.md, replace the SP10 placeholder with a real entry summarizing what shipped: test count delta, paradigm-by-paradigm alignment, validation gate status.

In `docs/reviewer-1-charter.md`: bump "Last reviewed at" to `sp10-complete`. Add probe candidates the driver architecture introduces:
- "Does the bot's hook into `pluginAPI.getKeyboardResponse` produce events indistinguishable from real user input, by every test the platform might use?"
- "Does the driver's response delivery handle SSD-adaptive timing in stop-signal correctly?"

Commit, then tag:

```bash
git add docs/sp10-results.md CLAUDE.md docs/reviewer-1-charter.md
git commit -m "$(cat <<'EOF'
docs(sp10): empirical results, CLAUDE.md SP history, charter bump

[1-3 sentence headline summarizing what improved, hard-gate status,
and what's deferred to SP10b or future SPs.]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git tag sp10-complete
```

Push: `git push origin sp10/driver-architecture && git push origin sp10-complete`.

---

## Self-review

**Spec coverage:** Each spec section maps to plan tasks:

- §1 Motivation: covered in plan header.
- §2 Hypothesis: covered by Phase 5 hard gates (Task 21).
- §3 Phase 1: Tasks 2–5.
- §3 Phase 2: Tasks 6–9.
- §3 Phase 3: Tasks 10–17.
- §3 Phase 4: Tasks 18–20.
- §3 Phase 5: Task 21.
- §3 Phase 6: Task 22.
- §4 Out of scope: respected (no cognitionrun driver, no PsychoJsDriver, no multi-browser, no fingerprint stealth).
- §5 Deliverables: all files listed in the File Structure table; all commits described.
- §6 CLAUDE.md edits: applied in Task 1.
- §7 Open questions: deferred to Phase 3 implementation (per-driver decisions) and Phase 5 empirical surfacing.
- §8 Risks: documented in spec; plan does not duplicate.
- §9 Validation philosophy: gates encoded in Task 21.

**Placeholder scan:**
- "1-3 sentence headline" in Task 22's commit message — intentional, filled at SP10-complete time from Phase 5 results.
- Empty-bracket fields in `recommended_driver: "..."` in spec — concrete strings (`"JsPsychDriver"` etc.) in plan.
- Task 10 outputs to `docs/sp10-investigation.md` from a live page probe — concrete script provided; output fills the doc.
- No "TBD" / "implement later" / "handle edge cases" in plan body.

**Type consistency:**
- `PlatformDriver` Protocol method names match across Tasks 3, 6, 12-16: `can_handle`, `setup`, `loop_state`, `navigate`, `get_trial_context`, `deliver_response`, `wait_for_trial_end`, `wait_for_completion`, `retrieve_data`, `teardown`.
- `TrialLoopState` enum members consistent: `NEEDS_NAVIGATION`, `READY_FOR_TRIAL`, `COMPLETE`.
- `TrialContext` fields consistent across Tasks 3, 6, 14: `stimulus_id`, `condition`, `allowed_responses`, `expected_correct`, `response_window_ms`, `metadata`.
- `DeliveryResult`, `NavigationOutcome`, `ExperimentData`, `DriverError`, `UnsupportedVersionError` referenced consistently.
- `identify_driver` signature: `async (page) -> PlatformDriver`. Consistent across Tasks 4, 7.
- `DiagnosticDriver._report_dir` set by executor before `setup()`; same pattern across Tasks 5, 7.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-15-sp10-driver-architecture.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task; spec-compliance review only (skip code-quality reviewer per saved feedback memory); fast iteration in this session. Tasks 0, 10, 17, 21 require live browser sessions or research — these are controller-handled, not subagent-handled.

**2. Inline Execution** — execute here using `superpowers:executing-plans`; batch with checkpoints.

Which approach?






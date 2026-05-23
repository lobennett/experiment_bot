# SP15 — Platform-Aware Stage 1 + Persistent-Session Pilot Walker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Spec-compliance reviewer per task; SKIP the code-quality reviewer (per `feedback_skip_code_quality_reviewer` memory).

**Goal:** Unblock realistic behavioral data on the held-out paradigm by (Part A) backfilling canonical navigation phases at Stage 1 from a per-platform lookup table, and (Part B) replacing Stage 6's per-attempt fresh-browser pattern with one persistent Playwright session that walks the experiment one DOM advance at a time.

**Architecture:** Two surgical changes preserving public contracts. New `reasoner/platform_defaults.py` (Part A) hooks into Stage 1's post-validate path. New `core/pilot_session.py` (Part B) becomes the substrate `PilotRunner.run` uses, with `run_stage6` rewritten as a single-session walker on top. `PilotRunner.run`'s public signature is unchanged; downstream callers (executor, existing pilot tests) see no API churn.

**Tech Stack:** Python 3.12, async Playwright, pytest-asyncio, Claude LLM via `LLMClient` (mocked in tests).

**Spec:** `docs/sp15-spec.md` (commit `b35d744`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/experiment_bot/reasoner/platform_defaults.py` | Create | URL pattern → canonical nav phases lookup; `apply_platform_defaults(partial, url)` |
| `src/experiment_bot/reasoner/stage1_structural.py` | Modify | Call `apply_platform_defaults` after validation, before return |
| `src/experiment_bot/core/pilot_session.py` | Create | `PilotSession` async context manager (try_phase, probe_stimulus, poll_stimuli, dom_snapshot, press, goto) |
| `src/experiment_bot/core/pilot.py` | Modify | `PilotRunner.run` reimplemented via `PilotSession`; signature unchanged |
| `src/experiment_bot/reasoner/stage6_pilot.py` | Modify | Split prompt into nav + stim variants; rewrite `run_stage6` as persistent-session walker |
| `tests/test_platform_defaults.py` | Create | 5 unit tests |
| `tests/test_pilot_session.py` | Create | 6 unit tests against a local HTML fixture |
| `tests/test_pilot.py` | Modify | Verify existing PilotDiagnostics tests still pass (no changes needed in test logic) |
| `tests/test_reasoner_stage6.py` | Modify | Rewrite tests for new walker contract |
| `tests/test_reasoner_stage1.py` | Modify (if exists) or Create | Test Stage 1 platform-defaults integration |
| `docs/sp15-results.md` | Create | Held-out + dev-4 + wall-time outcomes |
| `docs/sp15-heldout-behavior.md` | Create | Behavioral data analysis from executor sessions |
| `docs/pipeline-flow.md` | Modify | Stage 1 platform-defaults + Stage 6 persistent-session callouts |
| `CLAUDE.md` | Modify | SP15 sub-project entry |

---

## Task 1: `platform_defaults.py` module

**Files:**
- Create: `src/experiment_bot/reasoner/platform_defaults.py`
- Create: `tests/test_platform_defaults.py`

**Why:** Encode infrastructure-level navigation patterns for the three platforms we already have working dev TaskCards for, so Stage 1 can backfill nav phases when the LLM under-emits. Derived from committed TaskCards (not invented).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_platform_defaults.py`:

```python
"""Tests for Stage 1 platform-aware nav defaults (SP15 Part A)."""
from experiment_bot.reasoner.platform_defaults import (
    apply_platform_defaults,
    _match_platform,
    PLATFORM_NAV_DEFAULTS,
)


def test_platform_default_matches_expfactory_url():
    d = _match_platform("https://deploy.expfactory.org/preview/80/")
    assert d is not None
    assert d.name == "expfactory"
    # The 10-phase canonical sequence: wait/click/wait/keypress/wait/click/wait/click/wait/keypress
    assert len(d.phases) == 10
    # Anchored: starts with a wait, ends with Enter keypress
    assert d.phases[0]["action"] == "wait"
    assert d.phases[-1]["action"] == "keypress"
    assert d.phases[-1]["key"] == "Enter"


def test_platform_default_matches_cognition_run_url():
    d = _match_platform("https://strooptest.cognition.run/")
    assert d is not None
    assert d.name == "cognition.run"


def test_platform_default_matches_kywch_url():
    d = _match_platform(
        "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html"
    )
    assert d is not None
    assert d.name == "kywch.github.io"


def test_platform_default_no_match_returns_partial_unchanged():
    partial = {"navigation": {"phases": []}}
    out = apply_platform_defaults(partial, "https://example.com/unknown-platform/")
    assert out == partial
    # No match — _match_platform returns None
    assert _match_platform("https://example.com/foo") is None


def test_platform_default_backfills_empty_llm_nav():
    partial = {"navigation": {"phases": []}}
    out = apply_platform_defaults(partial, "https://deploy.expfactory.org/preview/80/")
    assert len(out["navigation"]["phases"]) == 10  # expfactory default
    # Original wasn't mutated (function returns new dict OR mutates; both acceptable
    # but we expect the returned object to have the platform default)
    assert out["navigation"]["phases"][1]["target"] == "#jspsych-fullscreen-btn"


def test_platform_default_does_not_clobber_richer_llm_nav():
    """If LLM emitted MORE phases than the platform default, trust the LLM —
    it may have paradigm-specific knowledge the default doesn't capture."""
    rich_phases = [{"action": "click", "target": f"#x{i}", "key": "", "duration_ms": 0,
                    "phase": "", "steps": []} for i in range(12)]
    partial = {"navigation": {"phases": rich_phases}}
    out = apply_platform_defaults(partial, "https://deploy.expfactory.org/preview/80/")
    assert out["navigation"]["phases"] == rich_phases  # unchanged


def test_platform_default_handles_missing_navigation_key():
    """LLM might not emit a navigation key at all; platform default still applies."""
    partial = {}
    out = apply_platform_defaults(partial, "https://deploy.expfactory.org/preview/80/")
    assert "navigation" in out
    assert len(out["navigation"]["phases"]) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_platform_defaults.py -v`
Expected: 7 FAILED with ImportError (module doesn't exist).

- [ ] **Step 3: Implement `platform_defaults.py`**

Extract the canonical nav phases from these source TaskCards:
- expfactory: `taskcards/expfactory_stroop/f40e356e.json` (10 phases)
- cognition.run: `taskcards/cognitionrun_stroop/e62646a9.json` (the 10-phase Phase-7 fix)
- kywch.github.io: `taskcards/stopit_stop_signal/d930eda9.json` (6 phases)

Read those files; copy the `navigation.phases` arrays verbatim into the module. Module:

```python
"""Platform-aware navigation defaults for Stage 1 (SP15 Part A).

When Stage 1's LLM emits an under-specified navigation.phases array (empty or
shorter than the known canonical sequence for a hosting platform), backfill
with the platform's canonical phases. The defaults are infrastructure
recognition (fullscreen plugin, instructions plugin, etc.) — not paradigm-
specific knowledge — so they generalize across any paradigm on the same
platform without violating G1.

Defaults are derived from committed dev TaskCards that already pass Stage 6.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformDefault:
    name: str
    url_patterns: tuple[str, ...]   # regex patterns matched against URL
    phases: list[dict]              # canonical nav phases (flat schema)


# Extracted from taskcards/expfactory_stroop/f40e356e.json
_EXPFACTORY_PHASES: list[dict] = [
    {"phase": "", "action": "wait",     "target": "",                          "key": "",      "steps": [], "duration_ms": 500},
    {"phase": "", "action": "click",    "target": "#jspsych-fullscreen-btn",   "key": "",      "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                          "key": "",      "steps": [], "duration_ms": 1500},
    {"phase": "", "action": "keypress", "target": "",                          "key": "Enter", "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                          "key": "",      "steps": [], "duration_ms": 3000},
    {"phase": "", "action": "click",    "target": "#jspsych-instructions-next","key": "",      "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                          "key": "",      "steps": [], "duration_ms": 3000},
    {"phase": "", "action": "click",    "target": "#jspsych-instructions-next","key": "",      "steps": [], "duration_ms": 0},
    {"phase": "", "action": "wait",     "target": "",                          "key": "",      "steps": [], "duration_ms": 1000},
    {"phase": "", "action": "keypress", "target": "",                          "key": "Enter", "steps": [], "duration_ms": 0},
]

# Extracted from taskcards/cognitionrun_stroop/e62646a9.json — verbatim copy
# of its navigation.phases array. Use the implementer to read that file and
# splice the EXACT array in here.
_COGNITION_RUN_PHASES: list[dict] = _LOAD_FROM("taskcards/cognitionrun_stroop/e62646a9.json")

# Extracted from taskcards/stopit_stop_signal/d930eda9.json — verbatim copy.
_STOPIT_PHASES: list[dict] = _LOAD_FROM("taskcards/stopit_stop_signal/d930eda9.json")


PLATFORM_NAV_DEFAULTS: tuple[PlatformDefault, ...] = (
    PlatformDefault(
        name="expfactory",
        url_patterns=(r"deploy\.expfactory\.org", r"expfactory\.org/preview/"),
        phases=_EXPFACTORY_PHASES,
    ),
    PlatformDefault(
        name="cognition.run",
        url_patterns=(r"\.cognition\.run",),
        phases=_COGNITION_RUN_PHASES,
    ),
    PlatformDefault(
        name="kywch.github.io",
        url_patterns=(r"kywch\.github\.io",),
        phases=_STOPIT_PHASES,
    ),
)


def _match_platform(url: str) -> PlatformDefault | None:
    for d in PLATFORM_NAV_DEFAULTS:
        for pat in d.url_patterns:
            if re.search(pat, url):
                return d
    return None


def apply_platform_defaults(partial: dict, url: str) -> dict:
    """Backfill canonical platform nav phases when the partial's
    navigation.phases is empty or shorter than the platform default.

    Returns the (possibly modified) partial. Does NOT mutate input.
    """
    default = _match_platform(url)
    if default is None:
        return partial
    nav = partial.get("navigation", {}) or {}
    current_phases = nav.get("phases", []) or []
    if len(current_phases) >= len(default.phases):
        # LLM emitted at least as many phases — trust it; may have paradigm-
        # specific knowledge the platform default doesn't capture.
        return partial
    out = dict(partial)
    out["navigation"] = dict(nav)
    out["navigation"]["phases"] = list(default.phases)
    return out
```

NOTE: `_LOAD_FROM(...)` is pseudocode — the implementer must INLINE the actual phases arrays from the source TaskCards (no I/O at import time). Read each source TaskCard, copy the `navigation.phases` JSON arrays into the file as Python list literals.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_platform_defaults.py -v`
Expected: All 7 pass.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/platform_defaults.py tests/test_platform_defaults.py
git commit -m "$(cat <<'EOF'
feat(sp15-A): platform_defaults.py — backfill canonical nav for known platforms

URL pattern → canonical navigation.phases lookup for expfactory.org,
cognition.run, and kywch.github.io. Defaults derived from committed dev
TaskCards (expfactory_stroop/f40e356e.json, cognitionrun_stroop/
e62646a9.json, stopit_stop_signal/d930eda9.json) that already pass Stage 6.

apply_platform_defaults(partial, url) backfills when LLM-emitted nav is
shorter than the platform default; LLM nav wins if it's at least as long
(assumed paradigm-specific knowledge). +7 tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Hook `apply_platform_defaults` into Stage 1

**Files:**
- Modify: `src/experiment_bot/reasoner/stage1_structural.py` (call after validation, before return)
- Test: append to `tests/test_platform_defaults.py` or `tests/test_reasoner_stage1.py` (create if doesn't exist)

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_platform_defaults.py`:

```python
import pytest
from unittest.mock import AsyncMock

from experiment_bot.core.config import SourceBundle
from experiment_bot.llm.protocol import LLMResponse


@pytest.mark.asyncio
async def test_stage1_applies_platform_default_when_llm_emits_empty_nav():
    """Stage 1: when the LLM emits empty navigation.phases for an expfactory
    URL, platform_defaults backfills the canonical 10-phase sequence."""
    from experiment_bot.reasoner.stage1_structural import run_stage1
    bundle = SourceBundle(
        url="https://deploy.expfactory.org/preview/80/",
        source_files={"experiment.js": "// stub"},
        description_text="<html></html>",
    )
    # LLM returns a minimal valid partial with EMPTY navigation.phases
    llm_output = """{
        "task": {"name": "Test", "constructs": [], "paradigm_classes": ["speeded_choice"]},
        "stimuli": [{"id": "s1", "description": "x",
                    "detection": {"method": "dom_query", "selector": "#s"},
                    "response": {"key": "f", "condition": "c1"}}],
        "navigation": {"phases": []},
        "runtime": {"advance_behavior": {"advance_keys": [" "], "feedback_fallback_keys": ["Enter"],
                                         "feedback_selectors": []},
                    "data_capture": {"method": "js_expression",
                                     "expression": "jsPsych.data.get().json()", "format": "json"}},
        "task_specific": {"key_map": {"c1": "f"}},
        "performance": {"accuracy": {"c1": 0.95}},
        "pilot_validation_config": {"min_trials": 5, "target_conditions": ["c1"]}
    }"""
    client = AsyncMock()
    client.complete = AsyncMock(return_value=LLMResponse(text=llm_output))
    partial, step = await run_stage1(client, bundle)
    # Platform default backfilled
    assert len(partial["navigation"]["phases"]) == 10
    assert partial["navigation"]["phases"][1]["target"] == "#jspsych-fullscreen-btn"
    # Inference text mentions backfill
    assert "platform" in step.inference.lower() or "expfactory" in step.inference.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_platform_defaults.py::test_stage1_applies_platform_default_when_llm_emits_empty_nav -v`
Expected: FAIL (assertion on `len == 10` will see 0).

- [ ] **Step 3: Hook into `stage1_structural.py`**

Add import:
```python
from experiment_bot.reasoner.platform_defaults import apply_platform_defaults, _match_platform
```

Modify the `run_stage1` function body. Find this block (around line 136-152):

```python
            continue
        break

    n_stimuli = len(normalized.get("stimuli", []))
    task_name = normalized.get("task", {}).get("name", "?")
    inference = (
        f"Identified paradigm '{task_name}' with {n_stimuli} stimuli. "
        f"Source files: {', '.join(bundle.source_files.keys())[:200]}."
    )
    if errors:
        inference += f" Validator-retry resolved {len(errors)} prior failure(s)."
```

Replace with:

```python
            continue
        break

    # SP15 Part A: backfill platform-canonical nav phases when LLM under-emits.
    pre_backfill_phase_count = len(normalized.get("navigation", {}).get("phases", []))
    normalized = apply_platform_defaults(normalized, bundle.url)
    post_backfill_phase_count = len(normalized.get("navigation", {}).get("phases", []))
    platform = _match_platform(bundle.url)

    n_stimuli = len(normalized.get("stimuli", []))
    task_name = normalized.get("task", {}).get("name", "?")
    inference = (
        f"Identified paradigm '{task_name}' with {n_stimuli} stimuli. "
        f"Source files: {', '.join(bundle.source_files.keys())[:200]}."
    )
    if platform is not None and post_backfill_phase_count > pre_backfill_phase_count:
        inference += (
            f" Applied {platform.name} platform-default nav phases "
            f"({pre_backfill_phase_count} → {post_backfill_phase_count})."
        )
    if errors:
        inference += f" Validator-retry resolved {len(errors)} prior failure(s)."
```

- [ ] **Step 4: Run all tests; verify**

Run: `uv run pytest tests/test_platform_defaults.py tests/test_reasoner_stage6.py tests/test_pilot.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/stage1_structural.py tests/test_platform_defaults.py
git commit -m "$(cat <<'EOF'
feat(sp15-A): hook apply_platform_defaults into Stage 1 post-validation

After Stage 1 validates the LLM's partial, apply_platform_defaults checks
the URL against known platform patterns and backfills the canonical
nav.phases when the LLM emitted shorter than the platform default. The
ReasoningStep's inference text records when a backfill happened.

+1 integration test verifying expfactory URL + empty-LLM-nav → 10-phase
default applied.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Part A held-out validation

**Files:** None modified; produces artifacts under `taskcards/stop_signal_with_integrated_memory/`.

**Why:** Verify Part A alone unblocks the held-out paradigm. Expected outcome: Stage 6 passes on attempt 1 with the platform-default 10-phase expfactory nav, no walker invocation, one Chromium tab.

- [ ] **Step 1: Clean stale held-out state**

```bash
rm -f taskcards/stop_signal_with_integrated_memory/pilot.md taskcards/stop_signal_with_integrated_memory/pilot_refinement_*.diff
rm -rf .reasoner_work/stop_signal_with_integrated_memory
```

- [ ] **Step 2: Re-run the Reasoner**

```bash
uv run experiment-bot-reason https://deploy.expfactory.org/preview/80/ \
    --label stop_signal_with_integrated_memory \
    --pilot-max-retries 11 \
    2>&1 | tee /tmp/sp15-partA-heldout.log
```

Watch for the inference text in Stage 1 mentioning "Applied expfactory platform-default nav phases (0 → 10)." Then Stage 6 should report "Pilot passed first attempt" if Part A is sufficient.

- [ ] **Step 3: Verify outcome**

Run: `ls taskcards/stop_signal_with_integrated_memory/`
Expected: a `<sha>.json` TaskCard file + `pilot.md`. If Stage 6 passed attempt 1, NO `pilot_refinement_*.diff` files should exist.

```bash
python3 -c "
import json, glob
card = sorted(glob.glob('taskcards/stop_signal_with_integrated_memory/*.json'))[-1]
d = json.load(open(card))
s6 = next((s for s in d.get('reasoning_chain', []) if s.get('step') == 'stage6_pilot'), {})
print(f'TaskCard: {card}')
print(f'Nav phase count: {len(d.get(\"navigation\", {}).get(\"phases\", []))}')
print(f'Stage 6 inference: {s6.get(\"inference\", \"(missing)\")[:200]}')
"
```

- [ ] **Step 4: If Stage 6 passed attempt 1, commit and proceed**

```bash
git add taskcards/stop_signal_with_integrated_memory/
git commit -m "$(cat <<'EOF'
chore(sp15-A): held-out TaskCard generated via platform-default nav

stop_signal_with_integrated_memory Stage 6 PASS on attempt 1 with the
expfactory platform-default 10-phase nav backfilled by Part A. Zero
refinements consumed. One browser tab opened. Held-out unblocked for the
behavioral data run (Task 11).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If Stage 6 did NOT pass attempt 1, document the new failure mode in `/tmp/sp15-partA-heldout.log` and proceed to Part B — the persistent-session walker is the safety net for whatever Part A couldn't resolve.

---

## Task 4: `PilotSession` class

**Files:**
- Create: `src/experiment_bot/core/pilot_session.py`
- Create: `tests/test_pilot_session.py`

**Why:** The persistent-session substrate for the walker. Owns Chromium lifecycle, exposes a small interface (`goto`, `try_phase`, `probe_stimulus`, `poll_stimuli`, `dom_snapshot`, `press`) that both `PilotRunner.run` and `run_stage6` will compose against.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pilot_session.py`:

```python
"""Tests for PilotSession (SP15 Part B substrate).

Uses a local HTML fixture rather than mocking Playwright — the test isolates
session-lifecycle behavior, not Playwright internals.
"""
import pytest
from pathlib import Path

from experiment_bot.core.config import NavigationPhase
from experiment_bot.core.pilot_session import PilotSession


FIXTURE_HTML = """<!DOCTYPE html>
<html><body>
<button id="advance" onclick="document.body.dataset.state='advanced'">Advance</button>
<div id="stim-target" style="display:none">stimulus</div>
<script>
document.body.dataset.state = 'initial';
document.addEventListener('keydown', e => {
  if (e.key === ' ') document.body.dataset.state = 'space-pressed';
});
</script>
</body></html>
"""


@pytest.fixture
def fixture_url(tmp_path):
    p = tmp_path / "fixture.html"
    p.write_text(FIXTURE_HTML)
    return f"file://{p}"


@pytest.mark.asyncio
async def test_pilot_session_opens_and_closes_cleanly(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        dom = await session.dom_snapshot()
        assert "advance" in dom
    # No assertion needed — if __aexit__ raised, the test fails.


@pytest.mark.asyncio
async def test_pilot_session_try_phase_click_succeeds(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "advance", "action": "click", "target": "#advance",
            "key": "", "duration_ms": 0, "steps": [],
        })
        result = await session.try_phase(phase)
        assert result.success is True
        assert result.error is None
        # DOM reflects the click
        assert 'data-state="advanced"' in result.dom_after


@pytest.mark.asyncio
async def test_pilot_session_try_phase_click_times_out_gracefully(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "missing", "action": "click", "target": "#does-not-exist",
            "key": "", "duration_ms": 0, "steps": [],
        })
        result = await session.try_phase(phase)
        assert result.success is False
        assert result.error and "Timeout" in result.error
        # Session is still usable after a failed phase
        dom = await session.dom_snapshot()
        assert dom  # didn't crash


@pytest.mark.asyncio
async def test_pilot_session_try_phase_keypress(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "press", "action": "keypress", "target": "", "key": " ",
            "duration_ms": 0, "steps": [],
        })
        result = await session.try_phase(phase)
        assert result.success is True
        assert 'data-state="space-pressed"' in result.dom_after


@pytest.mark.asyncio
async def test_pilot_session_dom_snapshot_is_stable_when_page_unchanged(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        a = await session.dom_snapshot()
        b = await session.dom_snapshot()
        assert a == b


@pytest.mark.asyncio
async def test_pilot_session_context_manager_cleans_up_on_exception(fixture_url):
    """If the walker body raises mid-session, the browser must still close."""
    raised = False
    try:
        async with PilotSession(headless=True) as session:
            await session.goto(fixture_url)
            raise RuntimeError("simulated walker failure")
    except RuntimeError:
        raised = True
    assert raised
    # No assertion on browser-closed (Playwright cleanup is implicit in __aexit__);
    # this test passes if no resource leak warnings appear.
```

- [ ] **Step 2: Run tests to verify they fail (ImportError)**

Run: `uv run pytest tests/test_pilot_session.py -v`
Expected: 6 FAILED with ImportError.

- [ ] **Step 3: Implement `PilotSession`**

Create `src/experiment_bot/core/pilot_session.py`:

```python
"""Persistent Playwright session for Stage 6's pilot walker (SP15 Part B).

One browser instance lives for the entire walker loop. The walker calls
try_phase / probe_stimulus / poll_stimuli sequentially against the SAME
page, so each LLM refinement applies a delta to the live DOM rather than
re-running all prior phases on a fresh tab.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from playwright.async_api import (
    Browser, BrowserContext, Error as PlaywrightError, Page, async_playwright,
)

from experiment_bot.core.config import NavigationPhase

if TYPE_CHECKING:
    from experiment_bot.core.config import RuntimeConfig

logger = logging.getLogger(__name__)


@dataclass
class PhaseAttempt:
    success: bool
    dom_after: str
    error: str | None


@dataclass
class StimulusProbe:
    """One poll across all stimulus selectors. None if no stimulus matched."""
    match: object | None  # StimulusMatch — imported lazily to avoid circular
    dom_at_probe: str


class PilotSession:
    """Async context manager around a single Playwright browser + page.

    Methods are sequential — caller awaits each completion before issuing
    the next. No concurrency within a session.
    """

    def __init__(self, *, headless: bool = True, viewport: dict | None = None,
                 reading_delay_range: tuple[float, float] = (0.5, 1.0)):
        self._headless = headless
        self._viewport = viewport or {"width": 1280, "height": 800}
        self._reading_delay_range = reading_delay_range
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "PilotSession":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(viewport=self._viewport)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._playwright is not None:
                await self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("PilotSession not entered")
        return self._page

    async def goto(self, url: str) -> str:
        await self.page.goto(url, wait_until="domcontentloaded")
        return await self.dom_snapshot()

    async def dom_snapshot(self, container_selector: str = "body") -> str:
        try:
            html = await self.page.evaluate(
                "(sel) => document.querySelector(sel)?.outerHTML || document.body.outerHTML",
                container_selector,
            )
            return (html or "")[:4000]
        except PlaywrightError:
            return "(snapshot failed)"

    async def press(self, key: str) -> None:
        await self.page.keyboard.press(key)

    async def try_phase(self, phase: NavigationPhase) -> PhaseAttempt:
        """Execute one navigation phase against the live page.

        Returns PhaseAttempt(success=True, dom_after=...) on completion,
        or PhaseAttempt(success=False, error=...) if the action failed
        (timeout, missing target, etc.). The session remains usable.
        """
        try:
            if phase.action == "click":
                await self._inject_reading_delay()
                loc = self.page.locator(phase.target).first
                await loc.wait_for(state="visible", timeout=1500)
                await loc.click()
            elif phase.action in ("press", "keypress"):
                await self._inject_reading_delay()
                await self.page.keyboard.press(phase.key)
            elif phase.action == "wait":
                await asyncio.sleep(phase.duration_ms / 1000.0)
            elif phase.action == "sequence":
                for step in phase.steps:
                    sub = NavigationPhase.from_dict(step)
                    sub_result = await self.try_phase(sub)
                    if not sub_result.success:
                        return PhaseAttempt(
                            success=False,
                            dom_after=await self.dom_snapshot(),
                            error=f"sequence step failed: {sub_result.error}",
                        )
            else:
                logger.info(f"Skipping unknown action: {phase.action}")
        except Exception as e:
            return PhaseAttempt(
                success=False,
                dom_after=await self.dom_snapshot(),
                error=str(e),
            )
        return PhaseAttempt(
            success=True,
            dom_after=await self.dom_snapshot(),
            error=None,
        )

    async def probe_stimulus(self, lookup) -> StimulusProbe:
        """Single poll across all stimulus selectors. Returns match or None."""
        match = await lookup.identify(self.page)
        dom = await self.dom_snapshot()
        return StimulusProbe(match=match, dom_at_probe=dom)

    async def poll_stimuli(
        self, lookup, *, max_polls: int = 100, advance_keys: list[str] | None = None,
        poll_ms: int = 50,
    ) -> dict:
        """Multi-poll loop. Returns a dict with the same fields PilotDiagnostics
        expects: trials_with_stimulus_match, conditions_observed, dom_snapshots,
        selector_results, anomalies, trial_log. Polls until either a match is
        found AND criteria met, OR max_polls consecutive misses occur.

        The caller (PilotRunner.run or run_stage6) assembles a PilotDiagnostics
        from the returned dict.
        """
        # Implementer note: lift the existing polling loop body out of
        # PilotRunner.run (lines 165-302 of the current pilot.py) into here,
        # operating on self.page instead of constructing its own browser.
        # This is mostly a "move code, don't change semantics" refactor.
        raise NotImplementedError  # Implementer: lift PilotRunner.run's loop body here

    async def _inject_reading_delay(self) -> None:
        lo, hi = self._reading_delay_range
        if hi > 0:
            import random
            await asyncio.sleep(random.uniform(lo, hi))
```

NOTE: `poll_stimuli` is the most substantive method — it's a near-verbatim lift of the existing `PilotRunner.run`'s polling loop body. Implementer should read the existing pilot.py (lines 165-302), extract the polling loop, and place it inside `poll_stimuli` operating on `self.page` and `self._page` instead of a locally-created browser. Return shape is a dict; PilotRunner.run will wrap it in `PilotDiagnostics(**result)`.

- [ ] **Step 4: Run tests — all 6 must pass**

Run: `uv run pytest tests/test_pilot_session.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/core/pilot_session.py tests/test_pilot_session.py
git commit -m "$(cat <<'EOF'
feat(sp15-B): PilotSession — persistent Playwright session for Stage 6

Async context manager owning one browser/context/page for the entire walker
loop. Methods: goto, try_phase, probe_stimulus, poll_stimuli, dom_snapshot,
press. try_phase returns PhaseAttempt(success, dom_after, error) — session
remains usable after a failed phase (timeout, missing target, etc.).

+6 unit tests against a local HTML fixture covering open/close, click,
keypress, timeout-graceful-handling, DOM stability, and exception cleanup.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Refactor `PilotRunner.run` via `PilotSession`

**Files:**
- Modify: `src/experiment_bot/core/pilot.py`

**Why:** Backward-compatible refactor. `PilotRunner.run` keeps its signature and return type so all existing callers (executor, existing tests) work unchanged. Internally, it now constructs a `PilotSession`, runs nav phases, then delegates the polling loop to `PilotSession.poll_stimuli`.

- [ ] **Step 1: Verify existing pilot tests pass before the refactor**

Run: `uv run pytest tests/test_pilot.py -v`
Note the count for the post-refactor comparison.

- [ ] **Step 2: Replace `PilotRunner.run` body**

In `src/experiment_bot/core/pilot.py`, replace the body of `PilotRunner.run` with a delegation:

```python
class PilotRunner:
    async def run(self, config: TaskConfig, url: str, headless: bool = False) -> PilotDiagnostics:
        """Backward-compatible facade. Constructs a PilotSession, runs all
        nav phases serially, polls stimuli with the configured criteria, and
        returns a PilotDiagnostics. Equivalent behavior to the pre-SP15
        implementation but uses one persistent browser instance throughout.
        """
        from experiment_bot.core.pilot_session import PilotSession
        from experiment_bot.core.stimulus import StimulusLookup
        lookup = StimulusLookup(config)
        viewport = config.runtime.timing.viewport
        async with PilotSession(headless=headless, viewport=viewport) as session:
            await session.goto(url)
            crash_error: str | None = None
            dom_snapshots: list[dict] = [
                {"trigger": "after_navigation", "html": await session.dom_snapshot(
                    config.pilot.stimulus_container_selector or "body"
                )},
            ]
            # Run nav phases serially
            for phase in config.navigation.phases:
                attempt = await session.try_phase(phase)
                if not attempt.success:
                    crash_error = attempt.error
                    dom_snapshots.append({"trigger": "crash", "html": attempt.dom_after})
                    break
            if crash_error is None:
                # Polling loop
                result = await session.poll_stimuli(
                    lookup,
                    max_polls=_NO_MATCH_EARLY_STOP,
                    advance_keys=config.runtime.advance_behavior.advance_keys,
                )
                # poll_stimuli returns a dict; merge with our nav-phase dom_snapshots
                result_snaps = result.pop("dom_snapshots", [])
                dom_snapshots.extend(result_snaps)
                # Convert conditions_seen → conditions_missing
                target = set(config.pilot.target_conditions)
                conditions_observed = result.get("conditions_observed", [])
                conditions_missing = sorted(target - set(conditions_observed))
                anomalies = result.get("anomalies", [])
                return PilotDiagnostics(
                    trials_completed=result.get("trials_completed", 0),
                    trials_with_stimulus_match=result.get("trials_with_stimulus_match", 0),
                    conditions_observed=conditions_observed,
                    conditions_missing=conditions_missing,
                    selector_results=result.get("selector_results", {}),
                    phase_results=result.get("phase_results", {}),
                    dom_snapshots=dom_snapshots,
                    anomalies=anomalies,
                    trial_log=result.get("trial_log", []),
                )
            # Crash branch
            anomalies = [f"Pilot crashed: {crash_error}"]
            return PilotDiagnostics(
                trials_completed=0,
                trials_with_stimulus_match=0,
                conditions_observed=[],
                conditions_missing=sorted(config.pilot.target_conditions),
                selector_results={},
                phase_results={},
                dom_snapshots=dom_snapshots,
                anomalies=anomalies,
                trial_log=[],
            )
```

The implementer should:
- Verify `PilotSession.poll_stimuli` returns the exact dict shape consumed above.
- Adjust the dict-merging logic to match (this is the contract between Tasks 4 and 5).
- The crash-DOM-capture behavior from SP13 is preserved (now via `attempt.dom_after`).

- [ ] **Step 3: Run all pilot + stage6 tests**

Run: `uv run pytest tests/test_pilot.py tests/test_reasoner_stage6.py tests/test_pilot_session.py -v`
Expected: all pass (same count as before + 6 new pilot_session tests).

- [ ] **Step 4: Commit**

```bash
git add src/experiment_bot/core/pilot.py
git commit -m "$(cat <<'EOF'
refactor(sp15-B): PilotRunner.run via PilotSession; backward-compatible

PilotRunner.run keeps its signature (config, url, headless) → PilotDiagnostics
but is reimplemented as a thin facade: open PilotSession, run nav phases,
delegate to PilotSession.poll_stimuli, assemble diagnostics. One Chromium
instance per pilot run instead of (eventually under SP15-B's walker) one per
attempt.

All existing PilotDiagnostics tests + executor tests pass unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Split `REFINEMENT_PROMPT` into nav + stim variants

**Files:**
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py` (split prompt; add 2 helper functions)
- Modify: `tests/test_reasoner_stage6.py` (update prompt-invariant tests)

**Why:** The walker now applies single-delta refinements (one new nav phase OR one selector update), not full TaskCard edits. Separate prompts give the LLM narrower contracts.

- [ ] **Step 1: Add the two new prompts in `stage6_pilot.py`**

After the existing `REFINEMENT_PROMPT` block, add:

```python
NAVIGATION_REFINEMENT_PROMPT = """\
You are advancing an experiment-bot through one screen of an experiment. The
bot ran all known navigation phases and is now stuck at the screen described
in the DOM snapshot below. Your job: propose ONE additional navigation phase
to APPEND to the current sequence.

## Current DOM (the screen the bot is stuck on)
{dom_snapshot}

## Phases already executed (in order)
{accumulated_phases}

## Prior refinement attempts (chronological)
{prior_diffs_section}

## Instructions

Identify what's blocking THIS specific screen. Propose ONE new navigation
phase that gets the bot off this screen.

[Include the same Navigation phase JSON schema section as the existing
REFINEMENT_PROMPT — flat shape, supported actions, anti-pattern warning,
APPEND-only rule.]

Return ONLY one JSON object matching the flat navigation-phase schema —
the single phase to APPEND to the existing sequence. Do NOT return an
array, do NOT return a full TaskCard edit. Return JSON only.
"""


STIMULUS_REFINEMENT_PROMPT = """\
The bot reached the experiment's trial-rendering phase but none of the
configured stimulus selectors matched the DOM. Propose ONE selector update.

## Current DOM (the trial-rendering screen)
{dom_snapshot}

## Current stimulus configurations (id → selector)
{stim_table}

## Prior refinement attempts (chronological)
{prior_diffs_section}

## Instructions

Examine the DOM. Identify which stimulus is currently rendered (it should
match one of the conditions in the stim table). Propose ONE selector update.

Return ONLY a JSON object: {{"stim_id": "<id>", "new_selector": "<css or js>",
"detection_method": "dom_query" | "js_eval" | "text_content"}}. No preamble.
"""
```

The implementer should COPY the schema/APPEND/anti-pattern sections from the existing `REFINEMENT_PROMPT` into `NAVIGATION_REFINEMENT_PROMPT`. The old `REFINEMENT_PROMPT` can stay defined (for compatibility) but the walker won't use it.

- [ ] **Step 2: Add helper functions**

In `stage6_pilot.py`:

```python
async def _propose_next_phase(
    client: LLMClient, dom: str, accumulated_phases: list[dict],
    prior_diffs: list[str],
) -> dict:
    """Ask the LLM for ONE navigation phase to append. Returns the phase dict."""
    prior_section = (
        "\n\n".join(f"### Attempt {i+1}\n```diff\n{d}\n```"
                    for i, d in enumerate(prior_diffs))
        if prior_diffs else "(none yet — this is the first refinement)"
    )
    user = NAVIGATION_REFINEMENT_PROMPT.format(
        dom_snapshot=dom[:4000],
        accumulated_phases=json.dumps(accumulated_phases, indent=2)[:3000],
        prior_diffs_section=prior_section,
    )
    return await parse_with_retry(
        client, system="", user=user, stage_name="stage6_nav_refinement",
    )


async def _propose_stimulus_update(
    client: LLMClient, dom: str, stimuli: list[dict],
    prior_diffs: list[str],
) -> dict:
    """Ask the LLM for ONE stimulus selector update. Returns dict with
    stim_id + new_selector + detection_method."""
    stim_table = "\n".join(
        f"- {s['id']}: method={s.get('detection', {}).get('method', '?')}, "
        f"selector={s.get('detection', {}).get('selector', '?')[:120]}"
        for s in stimuli
    )
    prior_section = (
        "\n\n".join(f"### Attempt {i+1}\n```diff\n{d}\n```"
                    for i, d in enumerate(prior_diffs))
        if prior_diffs else "(none yet)"
    )
    user = STIMULUS_REFINEMENT_PROMPT.format(
        dom_snapshot=dom[:4000],
        stim_table=stim_table,
        prior_diffs_section=prior_section,
    )
    return await parse_with_retry(
        client, system="", user=user, stage_name="stage6_stim_refinement",
    )
```

- [ ] **Step 3: Add prompt-invariant tests**

Add to `tests/test_reasoner_stage6.py`:

```python
@pytest.mark.asyncio
async def test_navigation_refinement_prompt_has_schema_section():
    from experiment_bot.reasoner.stage6_pilot import NAVIGATION_REFINEMENT_PROMPT
    assert "Navigation phase JSON schema" in NAVIGATION_REFINEMENT_PROMPT
    assert "APPEND" in NAVIGATION_REFINEMENT_PROMPT
    for a in ("click", "keypress", "wait", "sequence"):
        assert f'"action": "{a}"' in NAVIGATION_REFINEMENT_PROMPT


@pytest.mark.asyncio
async def test_stimulus_refinement_prompt_has_expected_fields():
    from experiment_bot.reasoner.stage6_pilot import STIMULUS_REFINEMENT_PROMPT
    assert "stim_id" in STIMULUS_REFINEMENT_PROMPT
    assert "new_selector" in STIMULUS_REFINEMENT_PROMPT
    assert "detection_method" in STIMULUS_REFINEMENT_PROMPT
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_reasoner_stage6.py -v`
Expected: existing tests + 2 new pass.

- [ ] **Step 5: Commit**

```bash
git add src/experiment_bot/reasoner/stage6_pilot.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(sp15-B): split REFINEMENT_PROMPT into navigation + stimulus variants

NAVIGATION_REFINEMENT_PROMPT: given DOM + accumulated phases + prior diffs
→ output ONE phase JSON object to APPEND. Inherits SP14's schema/APPEND
guidance.

STIMULUS_REFINEMENT_PROMPT: given DOM + current stim configs → output ONE
selector update {stim_id, new_selector, detection_method}.

+2 prompt-invariant tests. Old REFINEMENT_PROMPT preserved as a no-op
(walker no longer invokes it).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Rewrite `run_stage6` as persistent-session walker

**Files:**
- Modify: `src/experiment_bot/reasoner/stage6_pilot.py` (`run_stage6` body)

**Why:** The core SP15 Part B change. Walker owns a single `PilotSession` across the entire refinement loop; refinements append one phase or update one selector against the live page; no re-launches.

- [ ] **Step 1: Replace `run_stage6` body**

The full new body is too long to inline here; the implementer should read the existing `run_stage6` (lines 248-336 of `stage6_pilot.py` after SP14) and rewrite per the spec's pseudocode (`docs/sp15-spec.md` § "PART B" §1 and §2). Key constraints:

- Outer `async with PilotSession(...)` owns the browser
- Inner loop: `probe → if matched → poll_stimuli → if passed → success; else if 0 stim matches → stimulus refinement; else nav refinement`
- `accumulated_phases` list mirrors `partial["navigation"]["phases"]`; `save_partial` called after each successful phase append
- `accumulated_stim_overrides: dict[str, str]` tracks in-memory selector updates; on success, splice into the final partial
- Stuck-detection: same SHA-based fingerprint, two-consecutive-identical-non-empty
- Budget: respects `max_retries`

The PASSING branch's ReasoningStep inference text should reflect:
- "Pilot passed first attempt" if no refinements occurred
- "Pilot passed after N navigation refinement(s), M selector update(s)" if any

- [ ] **Step 2: Verify all existing stage6 tests still pass (after appropriate rewrites in Task 8)**

Defer the test rewrites to Task 8 — that task adjusts the mocks for the new walker contract.

- [ ] **Step 3: Commit (with Task 8's test rewrites)**

The Task 7 commit lands together with Task 8 since they're contract-coupled.

---

## Task 8: Update `tests/test_reasoner_stage6.py` for new walker contract

**Files:**
- Modify: `tests/test_reasoner_stage6.py`

The existing tests mock `PilotRunner` to return a `PilotDiagnostics`. The new walker uses `PilotSession` directly. Tests need to mock `PilotSession` instead.

Specifically, the implementer must:

1. Replace `patch("experiment_bot.reasoner.stage6_pilot.PilotRunner")` with `patch("experiment_bot.reasoner.stage6_pilot.PilotSession")` in each test.
2. The mocked `PilotSession` returns from `__aenter__` an AsyncMock whose methods (`goto`, `try_phase`, `probe_stimulus`, `poll_stimuli`, `dom_snapshot`) return scripted values matching the test's intent.
3. Add 2 new tests:
   - `test_walker_navigation_refinement_appends_phase` — first probe fails with no trials and a nav-friendly DOM; LLM proposes a click phase; after `try_phase` succeeds, second probe returns matching stimuli → PASS. Verify `accumulated_phases` ended with the proposed phase.
   - `test_walker_stimulus_refinement_updates_lookup` — first probe shows trials rendering but 0 selector matches; LLM proposes a selector update; second probe matches → PASS. Verify the final partial has the updated selector.

- [ ] **Step 1-3 (combined in one Task 7+8 commit)**: implement Task 7's walker, rewrite Task 8's tests, run full suite green, commit.

```bash
git add src/experiment_bot/reasoner/stage6_pilot.py tests/test_reasoner_stage6.py
git commit -m "$(cat <<'EOF'
feat(sp15-B): run_stage6 as persistent-session walker

run_stage6 now owns a single PilotSession across the entire refinement
loop. Per attempt: probe → if match + passed → SUCCESS; else if trials
rendering with 0 matches → stimulus refinement; else nav refinement.
Accumulated phases + selector overrides applied to the partial only on
success-emitting paths; in-memory until then.

Test mocks switched from PilotRunner to PilotSession. +2 walker-flow
tests covering navigation-refinement-then-pass and stimulus-refinement-
then-pass.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Dev-4 regression

**Files:** None modified; generates new TaskCards.

- [ ] **Step 1: Restore baseline stage5.json for each paradigm** (per `project_reasoner_work_staleness` memory)

```bash
for label in expfactory_stroop expfactory_stop_signal stopit_stop_signal cognitionrun_stroop; do
    python3 - <<PYEOF
import json, glob
tc_glob = sorted(glob.glob(f'taskcards/$label/*.json'))
if not tc_glob: print(f'$label: no taskcards'); exit()
tc = json.load(open(tc_glob[-1]))
stage5 = {k: v for k, v in tc.items() if k not in ('schema_version', 'produced_by', 'taskcard_sha256', 'pilot_validation')}
if 'reasoning_chain' in stage5:
    stage5['_reasoning_chain'] = stage5.pop('reasoning_chain')
stage5['_reasoning_chain'] = [s for s in stage5.get('_reasoning_chain', []) if s.get('step', '').lower() != 'stage6_pilot']
import os; os.makedirs(f'.reasoner_work/$label', exist_ok=True)
with open(f'.reasoner_work/$label/stage5.json', 'w') as f:
    json.dump(stage5, f, indent=2)
print(f'$label: restored from {tc_glob[-1]}')
PYEOF
done
```

- [ ] **Step 2: Re-pilot each paradigm with --resume**

```bash
for label_url in 'expfactory_stroop|https://deploy.expfactory.org/preview/10/' \
                 'expfactory_stop_signal|https://deploy.expfactory.org/preview/9/' \
                 'stopit_stop_signal|https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html' \
                 'cognitionrun_stroop|https://strooptest.cognition.run/'; do
    label="${label_url%|*}"
    url="${label_url#*|}"
    echo "=== $label ==="
    uv run experiment-bot-reason "$url" --label "$label" --resume --pilot-max-retries 11 > "/tmp/sp15-regression-${label}.log" 2>&1
    if [[ $? -eq 0 ]]; then echo "$label: PASS"; else echo "$label: FAIL"; fi
done
```

- [ ] **Step 3: Verify pass + commit new TaskCards**

```bash
git add taskcards/
git commit -m "$(cat <<'EOF'
chore(sp15-B): dev-4 regression — all 4 paradigms PASS under persistent-session walker

Backward compatibility confirmed. Each paradigm's stage5.json restored from
committed TaskCard baseline; --resume re-piloted under SP15 walker. All 4
PASS (3 on first probe, stopit_stop_signal needs its same 1 refinement now
via the new walker).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Held-out paradigm validation under SP15 walker (if Part A didn't already pass)

**Files:** None modified directly.

If Task 3 already produced a passing TaskCard for `stop_signal_with_integrated_memory` via Part A alone, this task is just a confirmation that the persistent-session walker (Part B) doesn't break it. Re-run with `--resume`:

```bash
uv run experiment-bot-reason https://deploy.expfactory.org/preview/80/ --label stop_signal_with_integrated_memory --resume --pilot-max-retries 11
```

Expected: PASS on first probe (no refinements needed).

If Task 3 did NOT pass under Part A alone, this is the real validation: re-run from scratch and observe the walker's behavior. Expected wall time <5 min, ≤2 nav refinements + ≤1 stim refinement.

- [ ] **Step 1: Run; capture log**

- [ ] **Step 2: Commit any new TaskCards/artifacts**

---

## Task 11: Behavioral data run — executor × 5 sessions on the held-out paradigm

**Files:** None modified; produces session output under `output/stop_signal_with_integrated_memory/`.

**Why:** The actual SP15 deliverable. With a working TaskCard, run the executor for 5 sessions, then analyze the resulting behavioral data against published stop-signal + working-memory norms.

- [ ] **Step 1: Run executor × 5 sessions, headless**

```bash
for i in 1 2 3 4 5; do
    echo "=== Session $i ==="
    uv run experiment-bot https://deploy.expfactory.org/preview/80/ \
        --label stop_signal_with_integrated_memory \
        --headless 2>&1 | tail -10
done
```

- [ ] **Step 2: Aggregate behavioral metrics**

```bash
uv run scripts/analyze_sessions.py --label stop_signal_with_integrated_memory --output /tmp/sp15-heldout-behavior.json
```

(If `analyze_sessions.py` doesn't have an adapter for this paradigm, the implementer adds one — small platform-adapter addition under `validation/platform_adapters.py` for the new paradigm's CSV/JSON shape.)

- [ ] **Step 3: Write `docs/sp15-heldout-behavior.md`**

Document per-session and aggregate metrics (SSRT, go-RT, accuracy, working-memory load effects), compare to published norms, surface gaps honestly per [[honest-generalization-findings]] memory.

- [ ] **Step 4: Commit**

```bash
git add docs/sp15-heldout-behavior.md output/stop_signal_with_integrated_memory/
git commit -m "$(cat <<'EOF'
docs(sp15): held-out behavioral data — stop_signal_with_integrated_memory × 5 sessions

[Outcome summary based on actual data]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `docs/sp15-results.md`

Held-out + dev-4 + wall-time benchmarks. Standard SP-results format per `docs/sp12-deliverable.md`, `docs/sp13-results.md` precedents.

---

## Task 13: `docs/pipeline-flow.md` updates

Add a Stage 1 platform-defaults paragraph; update Stage 6 callout for persistent-session walker.

---

## Task 14: `CLAUDE.md` SP15 entry + tag

Append SP15 entry to sub-project history. Tag `sp15-complete`. Push.

```bash
git tag sp15-complete && git push && git push --tags
```

---

## Self-Review (run after writing the plan, fix issues inline)

**1. Spec coverage:**
- Part A: tasks 1, 2, 3 ✓
- Part B PilotSession: tasks 4, 5 ✓
- Part B walker rewrite: tasks 6, 7, 8 ✓
- Validation: tasks 9, 10, 11 ✓
- Docs: tasks 12, 13, 14 ✓

**2. Placeholder scan:** Two intentional bracketed sections in Task 11's commit message ("[Outcome summary]") — filled from actual session data.

**3. Type consistency:**
- `PhaseAttempt` returned from `try_phase` everywhere; fields `success: bool`, `dom_after: str`, `error: str | None`.
- `accumulated_phases: list[dict]` (TaskCard JSON shape).
- `accumulated_stim_overrides: dict[str, str]` (stim_id → new_selector).
- `PilotSession.poll_stimuli` returns `dict` (not `PilotDiagnostics`) — PilotRunner.run + run_stage6 each wrap differently.

**4. Backward compat:** `PilotRunner.run` keeps signature. Executor unchanged. TaskCard schema unchanged. Resume semantics unchanged.

Plan ready.

---

## Execution Handoff

Plan complete. Per `feedback_skip_code_quality_reviewer` memory: use **superpowers:subagent-driven-development** to execute; spec-compliance reviewer between tasks; skip code-quality reviewer.

**Recommended execution order:** 1 → 2 → 3 (Part A complete; held-out unblocked) → 4 → 5 → 6 → 7+8 → 9 → 10 → 11 → 12 → 13 → 14.

If Task 3 (Part A held-out) succeeds with Stage 6 PASS on attempt 1, Tasks 4-10 (Part B) can be deprioritized in favor of getting to Task 11 (the behavioral data run) — but they should still ship because Part B's discreteness benefit applies to all walker invocations, not just this held-out paradigm.

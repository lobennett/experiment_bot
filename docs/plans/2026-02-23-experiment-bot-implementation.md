# Experiment Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python package that executes human-like behavior on web-based cognitive tasks by analyzing source code via Claude API and driving Playwright with literature-based response distributions.

**Architecture:** Analyze-then-Execute pipeline. Platform adapters download source code → Claude Opus 4.6 generates a JSON TaskConfig → TaskExecutor drives Playwright using pre-compiled stimulus-response lookups with ex-Gaussian RT sampling. Stuck-detection fallback uses Haiku.

**Tech Stack:** Python 3.12+, uv, Playwright (async), anthropic SDK, Click, NumPy

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/experiment_bot/__init__.py`
- Create: `.gitignore`
- Create: `.python-version`

**Step 1: Initialize uv project**

```bash
cd /Users/loganbennett/Downloads/experiment_bot
uv init --lib --name experiment_bot
```

**Step 2: Configure pyproject.toml**

Replace the generated `pyproject.toml` with:

```toml
[project]
name = "experiment-bot"
version = "0.1.0"
description = "Human-like behavior executor for web-based cognitive tasks"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.49",
    "anthropic>=0.42",
    "click>=8.1",
    "numpy>=2.0",
]

[project.scripts]
experiment-bot = "experiment_bot.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"

[tool.hatch.build.targets.wheel]
packages = ["src/experiment_bot"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]
```

**Step 3: Set up .gitignore**

```
__pycache__/
*.pyc
.venv/
cache/
output/
dist/
*.egg-info/
.env
```

**Step 4: Set up .python-version**

```
3.12
```

**Step 5: Create package directories and __init__.py files**

```bash
mkdir -p src/experiment_bot/core
mkdir -p src/experiment_bot/platforms
mkdir -p src/experiment_bot/navigation
mkdir -p src/experiment_bot/prompts
mkdir -p src/experiment_bot/output
mkdir -p tests
mkdir -p cache
```

Create `__init__.py` in each:
- `src/experiment_bot/__init__.py` — empty
- `src/experiment_bot/core/__init__.py` — empty
- `src/experiment_bot/platforms/__init__.py` — empty
- `src/experiment_bot/navigation/__init__.py` — empty
- `src/experiment_bot/prompts/__init__.py` — empty
- `src/experiment_bot/output/__init__.py` — empty

**Step 6: Install dependencies**

```bash
uv sync
uv run playwright install chromium
```

**Step 7: Verify setup**

```bash
uv run python -c "import experiment_bot; print('OK')"
```

Expected: `OK`

**Step 8: Commit**

```bash
git add -A
git commit -m "feat: scaffold experiment_bot package with uv"
```

---

### Task 2: Core Data Models (TaskConfig, SourceBundle, TaskPhase)

**Files:**
- Create: `src/experiment_bot/core/config.py`
- Create: `tests/test_config.py`

**Step 1: Write failing tests for data models**

```python
# tests/test_config.py
import json
from experiment_bot.core.config import (
    TaskConfig,
    SourceBundle,
    TaskPhase,
    StimulusConfig,
    DetectionConfig,
    ResponseConfig,
    DistributionConfig,
    PerformanceConfig,
    NavigationPhase,
    TaskMetadata,
)


def test_task_phase_enum():
    assert TaskPhase.LOADING.value == "loading"
    assert TaskPhase.INSTRUCTIONS.value == "instructions"
    assert TaskPhase.PRACTICE.value == "practice"
    assert TaskPhase.FEEDBACK.value == "feedback"
    assert TaskPhase.TEST.value == "test"
    assert TaskPhase.ATTENTION_CHECK.value == "attention_check"
    assert TaskPhase.COMPLETE.value == "complete"


def test_source_bundle_creation():
    bundle = SourceBundle(
        platform="expfactory",
        task_id="9",
        source_files={"experiment.js": "var x = 1;"},
        description_text="A stop signal task.",
        metadata={"url": "https://example.com"},
    )
    assert bundle.platform == "expfactory"
    assert bundle.source_files["experiment.js"] == "var x = 1;"


def test_task_config_from_json():
    raw = {
        "task": {
            "name": "Stop Signal Task",
            "platform": "expfactory",
            "constructs": ["inhibitory_control"],
            "reference_literature": ["Logan et al. 1984"],
        },
        "stimuli": [
            {
                "id": "go_left",
                "description": "Left arrow",
                "detection": {
                    "method": "dom_query",
                    "selector": ".arrow-left",
                    "alt_method": "text_content",
                    "pattern": "←",
                },
                "response": {"key": "z", "condition": "go"},
            }
        ],
        "response_distributions": {
            "go_correct": {
                "distribution": "ex_gaussian",
                "params": {"mu": 450, "sigma": 60, "tau": 80},
                "unit": "ms",
            }
        },
        "performance": {
            "go_accuracy": 0.95,
            "stop_accuracy": 0.50,
            "omission_rate": 0.02,
            "practice_accuracy": 0.85,
        },
        "navigation": {
            "phases": [
                {"phase": "fullscreen", "action": "click", "target": "button.continue"}
            ]
        },
        "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
    }
    config = TaskConfig.from_dict(raw)
    assert config.task.name == "Stop Signal Task"
    assert len(config.stimuli) == 1
    assert config.stimuli[0].detection.selector == ".arrow-left"
    assert config.response_distributions["go_correct"].params["mu"] == 450
    assert config.performance.go_accuracy == 0.95
    assert config.navigation.phases[0].action == "click"
    assert config.task_specific["model"] == "independent_race"


def test_task_config_round_trip_json():
    """Config can be serialized to JSON and deserialized back."""
    raw = {
        "task": {
            "name": "Test",
            "platform": "test",
            "constructs": [],
            "reference_literature": [],
        },
        "stimuli": [],
        "response_distributions": {},
        "performance": {
            "go_accuracy": 0.9,
            "stop_accuracy": 0.5,
            "omission_rate": 0.01,
            "practice_accuracy": 0.8,
        },
        "navigation": {"phases": []},
        "task_specific": {},
    }
    config = TaskConfig.from_dict(raw)
    serialized = json.loads(json.dumps(config.to_dict()))
    config2 = TaskConfig.from_dict(serialized)
    assert config2.task.name == "Test"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'experiment_bot.core.config'`

**Step 3: Implement data models**

```python
# src/experiment_bot/core/config.py
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

    @classmethod
    def from_dict(cls, d: dict) -> NavigationPhase:
        return cls(
            phase=d.get("phase", ""),
            action=d.get("action", ""),
            target=d.get("target", ""),
            key=d.get("key", ""),
            steps=d.get("steps", []),
            duration_ms=d.get("duration_ms", 0),
        )

    def to_dict(self) -> dict:
        return {"phase": self.phase, "action": self.action,
                "target": self.target, "key": self.key,
                "steps": self.steps, "duration_ms": self.duration_ms}


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
class TaskConfig:
    task: TaskMetadata
    stimuli: list[StimulusConfig]
    response_distributions: dict[str, DistributionConfig]
    performance: PerformanceConfig
    navigation: NavigationConfig
    task_specific: dict = field(default_factory=dict)

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
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task.to_dict(),
            "stimuli": [s.to_dict() for s in self.stimuli],
            "response_distributions": {
                k: v.to_dict() for k, v in self.response_distributions.items()
            },
            "performance": self.performance.to_dict(),
            "navigation": self.navigation.to_dict(),
            "task_specific": self.task_specific,
        }
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/config.py tests/test_config.py
git commit -m "feat: add core data models (TaskConfig, SourceBundle, TaskPhase)"
```

---

### Task 3: Response Time Distributions

**Files:**
- Create: `src/experiment_bot/core/distributions.py`
- Create: `tests/test_distributions.py`

**Step 1: Write failing tests**

```python
# tests/test_distributions.py
import numpy as np
from experiment_bot.core.distributions import ExGaussianSampler, ResponseSampler
from experiment_bot.core.config import DistributionConfig


def test_ex_gaussian_sampler_returns_float():
    sampler = ExGaussianSampler(mu=450, sigma=60, tau=80)
    rt = sampler.sample()
    assert isinstance(rt, float)
    assert rt > 0


def test_ex_gaussian_sampler_mean_approx():
    """Mean of ex-Gaussian is mu + tau."""
    sampler = ExGaussianSampler(mu=450, sigma=60, tau=80)
    samples = [sampler.sample() for _ in range(10_000)]
    mean = np.mean(samples)
    # mu + tau = 530, allow generous tolerance
    assert 500 < mean < 560


def test_ex_gaussian_sampler_with_seed():
    s1 = ExGaussianSampler(mu=450, sigma=60, tau=80, seed=42)
    s2 = ExGaussianSampler(mu=450, sigma=60, tau=80, seed=42)
    assert s1.sample() == s2.sample()


def test_response_sampler_floor():
    """Response times should never be below 150ms."""
    config = {
        "go_correct": DistributionConfig(
            distribution="ex_gaussian",
            params={"mu": 100, "sigma": 10, "tau": 10},
        )
    }
    sampler = ResponseSampler(config, floor_ms=150)
    for _ in range(100):
        rt = sampler.sample_rt("go_correct")
        assert rt >= 150


def test_response_sampler_unknown_condition():
    sampler = ResponseSampler({}, floor_ms=150)
    try:
        sampler.sample_rt("nonexistent")
        assert False, "Should raise KeyError"
    except KeyError:
        pass
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_distributions.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement distributions**

```python
# src/experiment_bot/core/distributions.py
from __future__ import annotations

import numpy as np

from experiment_bot.core.config import DistributionConfig


class ExGaussianSampler:
    """Samples from an ex-Gaussian distribution (Gaussian + exponential)."""

    def __init__(self, mu: float, sigma: float, tau: float, seed: int | None = None):
        self.mu = mu
        self.sigma = sigma
        self.tau = tau
        self._rng = np.random.default_rng(seed)

    def sample(self) -> float:
        gaussian = self._rng.normal(self.mu, self.sigma)
        exponential = self._rng.exponential(self.tau)
        return float(gaussian + exponential)


class ResponseSampler:
    """Samples response times for different conditions using configured distributions."""

    def __init__(
        self,
        distributions: dict[str, DistributionConfig],
        floor_ms: float = 150.0,
        seed: int | None = None,
    ):
        self._floor_ms = floor_ms
        self._samplers: dict[str, ExGaussianSampler] = {}
        for condition, dist_config in distributions.items():
            if dist_config.distribution == "ex_gaussian":
                self._samplers[condition] = ExGaussianSampler(
                    mu=dist_config.params["mu"],
                    sigma=dist_config.params["sigma"],
                    tau=dist_config.params["tau"],
                    seed=seed,
                )

    def sample_rt(self, condition: str) -> float:
        if condition not in self._samplers:
            raise KeyError(f"Unknown condition: {condition}")
        rt = self._samplers[condition].sample()
        return max(rt, self._floor_ms)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_distributions.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/distributions.py tests/test_distributions.py
git commit -m "feat: add ex-Gaussian RT distribution sampling"
```

---

### Task 4: Platform Adapter Base Class

**Files:**
- Create: `src/experiment_bot/platforms/base.py`
- Create: `tests/test_platforms_base.py`

**Step 1: Write failing test**

```python
# tests/test_platforms_base.py
from experiment_bot.platforms.base import Platform
from experiment_bot.core.config import SourceBundle, TaskPhase


def test_platform_is_abstract():
    """Platform cannot be instantiated directly."""
    try:
        Platform()
        assert False, "Should raise TypeError"
    except TypeError:
        pass


def test_platform_subclass_must_implement_methods():
    """A subclass that doesn't implement all methods can't be instantiated."""
    class Incomplete(Platform):
        pass

    try:
        Incomplete()
        assert False, "Should raise TypeError"
    except TypeError:
        pass
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_platforms_base.py -v
```

Expected: FAIL

**Step 3: Implement base class**

```python
# src/experiment_bot/platforms/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Page

from experiment_bot.core.config import SourceBundle, TaskPhase


class Platform(ABC):
    """Abstract base class for experiment platform adapters."""

    @abstractmethod
    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        """Download task source code and description text."""

    @abstractmethod
    async def get_task_url(self, task_id: str) -> str:
        """Return the URL to launch the task in a browser."""

    @abstractmethod
    async def detect_task_phase(self, page: Page) -> TaskPhase:
        """Detect the current task phase from the page DOM."""
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_platforms_base.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/platforms/base.py tests/test_platforms_base.py
git commit -m "feat: add abstract Platform adapter base class"
```

---

### Task 5: ExpFactory Platform Adapter

**Files:**
- Create: `src/experiment_bot/platforms/expfactory.py`
- Create: `tests/test_expfactory.py`

**Step 1: Write failing tests**

```python
# tests/test_expfactory.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from experiment_bot.platforms.expfactory import ExpFactoryPlatform


def test_get_task_url():
    platform = ExpFactoryPlatform()
    import asyncio
    url = asyncio.run(platform.get_task_url("9"))
    assert url == "https://deploy.expfactory.org/preview/9/"


def test_parse_script_tags():
    """Extract experiment.js and other script paths from HTML."""
    html = '''
    <html><head>
    <script src="/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/experiment.js"></script>
    <script src="/static/js/jspsych.js"></script>
    <link rel="stylesheet" href="/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/style.css">
    </head></html>
    '''
    platform = ExpFactoryPlatform()
    scripts, styles = platform.parse_resource_tags(html)
    assert any("experiment.js" in s for s in scripts)
    assert any("style.css" in s for s in styles)


def test_build_download_url():
    platform = ExpFactoryPlatform()
    path = "/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/experiment.js"
    url = platform.build_download_url(path)
    assert url == "https://deploy.expfactory.org/deployment/repo/expfactory-experiments-rdoc/abc123/stop_signal_rdoc/experiment.js"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_expfactory.py -v
```

Expected: FAIL

**Step 3: Implement ExpFactory adapter**

```python
# src/experiment_bot/platforms/expfactory.py
from __future__ import annotations

import re
from pathlib import Path
from html.parser import HTMLParser

import httpx

from playwright.async_api import Page

from experiment_bot.core.config import SourceBundle, TaskPhase
from experiment_bot.platforms.base import Platform


BASE_URL = "https://deploy.expfactory.org"


class _ResourceTagParser(HTMLParser):
    """Extract script src and link href from HTML."""

    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self.styles: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_dict = dict(attrs)
        if tag == "script" and attr_dict.get("src"):
            self.scripts.append(attr_dict["src"])
        if tag == "link" and attr_dict.get("rel") == "stylesheet" and attr_dict.get("href"):
            self.styles.append(attr_dict["href"])


class ExpFactoryPlatform(Platform):
    """Adapter for the Experiment Factory platform (jsPsych-based tasks)."""

    async def get_task_url(self, task_id: str) -> str:
        return f"{BASE_URL}/preview/{task_id}/"

    def parse_resource_tags(self, html: str) -> tuple[list[str], list[str]]:
        """Parse HTML and return (script_srcs, stylesheet_hrefs)."""
        parser = _ResourceTagParser()
        parser.feed(html)
        return parser.scripts, parser.styles

    def build_download_url(self, path: str) -> str:
        """Build full URL from a relative resource path."""
        if path.startswith("http"):
            return path
        return f"{BASE_URL}{path}"

    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        url = await self.get_task_url(task_id)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        scripts, styles = self.parse_resource_tags(html)
        source_files: dict[str, str] = {}

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for path in scripts + styles:
                download_url = self.build_download_url(path)
                resp = await client.get(download_url)
                if resp.status_code == 200:
                    filename = path.split("/")[-1]
                    source_files[filename] = resp.text

        # Determine task name from experiment.js path
        task_name = task_id
        for path in scripts:
            if "experiment.js" in path:
                parts = path.strip("/").split("/")
                # Path like: deployment/repo/.../task_name_rdoc/experiment.js
                task_name = parts[-2] if len(parts) >= 2 else task_id
                break

        return SourceBundle(
            platform="expfactory",
            task_id=task_id,
            source_files=source_files,
            description_text=html,
            metadata={"url": url, "task_name": task_name},
        )

    async def detect_task_phase(self, page: Page) -> TaskPhase:
        # Check for completion
        completion_el = await page.query_selector("#completion_msg")
        if completion_el and await completion_el.is_visible():
            return TaskPhase.COMPLETE

        # Check for fullscreen button
        fullscreen_btn = await page.query_selector("button#jspsych-fullscreen-btn")
        if fullscreen_btn:
            return TaskPhase.LOADING

        # Check for instruction navigation buttons
        next_btn = await page.query_selector("button#jspsych-instructions-next")
        if next_btn:
            return TaskPhase.INSTRUCTIONS

        # Check page content for phase cues via evaluate
        phase_text = await page.evaluate("""
            () => {
                const el = document.querySelector('.jspsych-display-element');
                return el ? el.textContent : '';
            }
        """)

        if "practice" in phase_text.lower():
            return TaskPhase.PRACTICE
        if "feedback" in phase_text.lower() or "block" in phase_text.lower():
            return TaskPhase.FEEDBACK
        if "attention" in phase_text.lower():
            return TaskPhase.ATTENTION_CHECK

        return TaskPhase.TEST
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_expfactory.py -v
```

Expected: All PASS

**Step 5: Add httpx dependency**

Add `"httpx>=0.27"` to `pyproject.toml` dependencies and run `uv sync`.

**Step 6: Commit**

```bash
git add src/experiment_bot/platforms/expfactory.py tests/test_expfactory.py pyproject.toml
git commit -m "feat: add ExpFactory platform adapter"
```

---

### Task 6: PsyToolkit Platform Adapter

**Files:**
- Create: `src/experiment_bot/platforms/psytoolkit.py`
- Create: `tests/test_psytoolkit.py`

**Step 1: Write failing tests**

```python
# tests/test_psytoolkit.py
import pytest
import asyncio
from experiment_bot.platforms.psytoolkit import PsyToolkitPlatform


TASK_URLS = {
    "stopsignal": "https://www.psytoolkit.org/experiment-library/stopsignal.html",
    "taskswitching_cued": "https://www.psytoolkit.org/experiment-library/taskswitching_cued.html",
}


def test_get_task_url_stopsignal():
    platform = PsyToolkitPlatform()
    url = asyncio.run(platform.get_task_url("stopsignal"))
    # The demo URL is on a different route; we just need the library page URL
    assert "psytoolkit.org" in url


def test_get_zip_url():
    platform = PsyToolkitPlatform()
    url = platform.get_zip_url("stopsignal")
    assert url == "https://www.psytoolkit.org/doc_exp/stopsignal.zip"


def test_get_library_url():
    platform = PsyToolkitPlatform()
    url = platform.get_library_url("taskswitching_cued")
    assert url == "https://www.psytoolkit.org/experiment-library/taskswitching_cued.html"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_psytoolkit.py -v
```

Expected: FAIL

**Step 3: Implement PsyToolkit adapter**

```python
# src/experiment_bot/platforms/psytoolkit.py
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
from playwright.async_api import Page

from experiment_bot.core.config import SourceBundle, TaskPhase
from experiment_bot.platforms.base import Platform


class PsyToolkitPlatform(Platform):
    """Adapter for PsyToolkit experiment library tasks."""

    def get_zip_url(self, task_id: str) -> str:
        return f"https://www.psytoolkit.org/doc_exp/{task_id}.zip"

    def get_library_url(self, task_id: str) -> str:
        return f"https://www.psytoolkit.org/experiment-library/{task_id}.html"

    async def get_task_url(self, task_id: str) -> str:
        # The demo is launched from the library page; we return the library URL
        # The actual demo URL will be discovered during navigation
        return self.get_library_url(task_id)

    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        source_files: dict[str, str] = {}

        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Download and extract zip
            zip_url = self.get_zip_url(task_id)
            resp = await client.get(zip_url)
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    if not name.endswith("/"):
                        try:
                            source_files[name] = zf.read(name).decode("utf-8", errors="replace")
                        except Exception:
                            pass  # Skip binary files

            # Scrape library page for description
            lib_url = self.get_library_url(task_id)
            resp = await client.get(lib_url)
            resp.raise_for_status()
            description_text = resp.text

        return SourceBundle(
            platform="psytoolkit",
            task_id=task_id,
            source_files=source_files,
            description_text=description_text,
            metadata={"zip_url": self.get_zip_url(task_id)},
        )

    async def detect_task_phase(self, page: Page) -> TaskPhase:
        # PsyToolkit tasks run on a canvas; detect phase via JS state
        # This is a heuristic — the config's navigation instructions are primary
        try:
            phase_info = await page.evaluate("""
                () => {
                    const body = document.body.textContent || '';
                    if (body.includes('Click to start')) return 'loading';
                    if (body.includes('instruction') || body.includes('Instruction')) return 'instructions';
                    if (body.includes('practice') || body.includes('Practice')) return 'practice';
                    if (body.includes('ready') || body.includes('Ready')) return 'feedback';
                    if (body.includes('finished') || body.includes('Finished') || body.includes('Thank you')) return 'complete';
                    return 'test';
                }
            """)
            return TaskPhase(phase_info)
        except Exception:
            return TaskPhase.TEST
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_psytoolkit.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/platforms/psytoolkit.py tests/test_psytoolkit.py
git commit -m "feat: add PsyToolkit platform adapter"
```

---

### Task 7: Prompt Templates & JSON Schema

**Files:**
- Create: `src/experiment_bot/prompts/system.md`
- Create: `src/experiment_bot/prompts/schema.json`

**Step 1: Write the system prompt**

This is the prompt sent to Claude Opus 4.6 when analyzing task source code. Save as `src/experiment_bot/prompts/system.md`:

```markdown
You are a cognitive psychology expert and web developer analyzing experiment source code.

## Your Task

Given the source code and description of a web-based cognitive experiment, produce a JSON configuration file that enables an automated bot to complete the task with human-like behavior.

## What You Must Determine

1. **Task identification**: What cognitive task is this? What constructs does it measure? Cite relevant literature.

2. **Stimulus-response mappings**: For each possible stimulus, what is the correct response? Provide DOM selectors (for jsPsych/HTML tasks) or patterns (for canvas tasks) to detect each stimulus, and the keyboard key to press.

3. **Response time distributions**: Based on published literature for this task type, provide ex-Gaussian distribution parameters (mu, sigma, tau) for each response condition. These should reflect typical healthy adult performance.

4. **Performance targets**: What accuracy, stop accuracy (if applicable), omission rate, and practice accuracy should the bot aim for?

5. **Navigation flow**: How does the participant get from the start screen to the first trial? List every click, keypress, and wait needed to navigate instructions and begin practice/test blocks. Include selectors or patterns for buttons/elements to click.

6. **Task-specific parameters**: For stop signal tasks, specify the independent race model parameters (SSRT target). For task switching, specify expected switch costs and congruency effects.

## Response Format

Return ONLY valid JSON conforming to the schema provided. No markdown, no explanation, just the JSON object.

## Important Guidelines

- DOM selectors must be specific enough to uniquely identify elements. Prefer CSS selectors.
- For jsPsych experiments: stimuli appear inside `.jspsych-display-element` or `#jspsych-content`. Inspect the experiment.js code carefully for how stimuli are rendered (innerHTML, CSS classes, data attributes).
- For PsyToolkit experiments: tasks use a canvas element. Identify the PsyToolkit script variables that control stimulus presentation and response mapping.
- RT parameters should be based on published meta-analyses where possible. Typical healthy adult go RTs: mu=400-500ms, sigma=50-80ms, tau=60-100ms.
- Stop signal: target ~50% stop accuracy, SSRT ~200-280ms (Verbruggen & Logan, 2009).
- Task switching: switch cost ~50-150ms added to mu, congruency effect ~30-80ms (Monsell, 2003).
- For navigation: jsPsych tasks typically start with a fullscreen button, then instructions with Next buttons, then Enter to begin. PsyToolkit tasks start with "Click to start", then spacebar through instructions.
- Identify ALL possible stimulus types. Missing a stimulus type will cause the bot to freeze.
```

**Step 2: Write the JSON schema**

Save as `src/experiment_bot/prompts/schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["task", "stimuli", "response_distributions", "performance", "navigation"],
  "properties": {
    "task": {
      "type": "object",
      "required": ["name", "platform", "constructs", "reference_literature"],
      "properties": {
        "name": {"type": "string"},
        "platform": {"type": "string", "enum": ["expfactory", "psytoolkit"]},
        "constructs": {"type": "array", "items": {"type": "string"}},
        "reference_literature": {"type": "array", "items": {"type": "string"}}
      }
    },
    "stimuli": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "description", "detection", "response"],
        "properties": {
          "id": {"type": "string"},
          "description": {"type": "string"},
          "detection": {
            "type": "object",
            "required": ["method", "selector"],
            "properties": {
              "method": {"type": "string", "enum": ["dom_query", "js_eval", "text_content", "canvas_state"]},
              "selector": {"type": "string"},
              "alt_method": {"type": "string"},
              "pattern": {"type": "string"}
            }
          },
          "response": {
            "type": "object",
            "required": ["condition"],
            "properties": {
              "key": {"type": ["string", "null"]},
              "condition": {"type": "string"}
            }
          }
        }
      }
    },
    "response_distributions": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["distribution", "params"],
        "properties": {
          "distribution": {"type": "string"},
          "params": {"type": "object"},
          "unit": {"type": "string", "default": "ms"}
        }
      }
    },
    "performance": {
      "type": "object",
      "required": ["go_accuracy", "stop_accuracy", "omission_rate", "practice_accuracy"],
      "properties": {
        "go_accuracy": {"type": "number", "minimum": 0, "maximum": 1},
        "stop_accuracy": {"type": "number", "minimum": 0, "maximum": 1},
        "omission_rate": {"type": "number", "minimum": 0, "maximum": 1},
        "practice_accuracy": {"type": "number", "minimum": 0, "maximum": 1}
      }
    },
    "navigation": {
      "type": "object",
      "required": ["phases"],
      "properties": {
        "phases": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "phase": {"type": "string"},
              "action": {"type": "string"},
              "target": {"type": "string"},
              "key": {"type": "string"},
              "steps": {"type": "array"},
              "duration_ms": {"type": "integer"}
            }
          }
        }
      }
    },
    "task_specific": {
      "type": "object"
    }
  }
}
```

**Step 3: Commit**

```bash
git add src/experiment_bot/prompts/system.md src/experiment_bot/prompts/schema.json
git commit -m "feat: add Claude analysis prompt template and JSON schema"
```

---

### Task 8: Claude Analyzer

**Files:**
- Create: `src/experiment_bot/core/analyzer.py`
- Create: `tests/test_analyzer.py`

**Step 1: Write failing tests**

```python
# tests/test_analyzer.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from experiment_bot.core.analyzer import Analyzer
from experiment_bot.core.config import SourceBundle, TaskConfig


MOCK_CONFIG_JSON = json.dumps({
    "task": {
        "name": "Stop Signal",
        "platform": "expfactory",
        "constructs": ["inhibitory_control"],
        "reference_literature": ["Logan 1994"],
    },
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        }
    ],
    "response_distributions": {
        "go_correct": {
            "distribution": "ex_gaussian",
            "params": {"mu": 450, "sigma": 60, "tau": 80},
        }
    },
    "performance": {
        "go_accuracy": 0.95,
        "stop_accuracy": 0.50,
        "omission_rate": 0.02,
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {},
})


@pytest.mark.asyncio
async def test_analyzer_builds_correct_messages():
    """Analyzer sends system prompt + source code to the API."""
    bundle = SourceBundle(
        platform="expfactory",
        task_id="9",
        source_files={"experiment.js": "console.log('test');"},
        description_text="A stop signal task.",
        metadata={},
    )

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=MOCK_CONFIG_JSON)]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    analyzer = Analyzer(client=mock_client)
    config = await analyzer.analyze(bundle)

    assert isinstance(config, TaskConfig)
    assert config.task.name == "Stop Signal"
    assert len(config.stimuli) == 1

    # Verify the API was called with correct model
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_analyzer_retries_on_invalid_json():
    """Analyzer retries once if Claude returns invalid JSON."""
    bundle = SourceBundle(
        platform="expfactory",
        task_id="9",
        source_files={"experiment.js": "x"},
        description_text="test",
        metadata={},
    )

    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.content = [MagicMock(text="not json")]
    good_response = MagicMock()
    good_response.content = [MagicMock(text=MOCK_CONFIG_JSON)]
    mock_client.messages.create = AsyncMock(side_effect=[bad_response, good_response])

    analyzer = Analyzer(client=mock_client)
    config = await analyzer.analyze(bundle)
    assert config.task.name == "Stop Signal"
    assert mock_client.messages.create.call_count == 2
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_analyzer.py -v
```

Expected: FAIL

**Step 3: Implement analyzer**

```python
# src/experiment_bot/core/analyzer.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from experiment_bot.core.config import SourceBundle, TaskConfig

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class Analyzer:
    """Sends task source code to Claude Opus and returns a TaskConfig."""

    def __init__(self, client, model: str = "claude-opus-4-6", max_retries: int = 1):
        self._client = client
        self._model = model
        self._max_retries = max_retries
        self._system_prompt = (PROMPTS_DIR / "system.md").read_text()
        self._schema = json.loads((PROMPTS_DIR / "schema.json").read_text())

    def _build_user_message(self, bundle: SourceBundle) -> str:
        parts = [
            f"## Platform: {bundle.platform}",
            f"## Task ID: {bundle.task_id}",
            "",
            "## Task Description",
            bundle.description_text[:5000],
            "",
        ]
        for filename, content in bundle.source_files.items():
            parts.append(f"## File: {filename}")
            # Truncate very large files to stay within token limits
            parts.append(content[:30000])
            parts.append("")

        parts.append("## Required Output Schema")
        parts.append(json.dumps(self._schema, indent=2))
        return "\n".join(parts)

    async def analyze(self, bundle: SourceBundle) -> TaskConfig:
        user_message = self._build_user_message(bundle)
        attempts = 0

        while attempts <= self._max_retries:
            attempts += 1
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=16384,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            try:
                data = json.loads(raw_text)
                return TaskConfig.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Attempt {attempts} failed to parse config: {e}")
                if attempts > self._max_retries:
                    raise ValueError(f"Failed to get valid config after {attempts} attempts: {e}") from e
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_analyzer.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/analyzer.py tests/test_analyzer.py
git commit -m "feat: add Claude Opus analyzer for task config generation"
```

---

### Task 9: Config Cache Manager

**Files:**
- Create: `src/experiment_bot/core/cache.py`
- Create: `tests/test_cache.py`

**Step 1: Write failing tests**

```python
# tests/test_cache.py
import json
import pytest
from pathlib import Path

from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.config import TaskConfig


SAMPLE_CONFIG_DICT = {
    "task": {"name": "Test", "platform": "test", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_cache_miss(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    result = cache.load("expfactory", "9")
    assert result is None


def test_cache_save_and_load(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    cache.save("expfactory", "9", config)

    loaded = cache.load("expfactory", "9")
    assert loaded is not None
    assert loaded.task.name == "Test"


def test_cache_file_location(tmp_path):
    cache = ConfigCache(cache_dir=tmp_path)
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    cache.save("expfactory", "9", config)

    expected_path = tmp_path / "expfactory" / "9" / "config.json"
    assert expected_path.exists()
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: FAIL

**Step 3: Implement cache**

```python
# src/experiment_bot/core/cache.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "cache"


class ConfigCache:
    """Caches TaskConfig JSON files to avoid repeated API calls."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self._cache_dir = cache_dir

    def _config_path(self, platform: str, task_id: str) -> Path:
        return self._cache_dir / platform / task_id / "config.json"

    def load(self, platform: str, task_id: str) -> TaskConfig | None:
        path = self._config_path(platform, task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TaskConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load cached config: {e}")
            return None

    def save(self, platform: str, task_id: str, config: TaskConfig) -> None:
        path = self._config_path(platform, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config.to_dict(), indent=2))
        logger.info(f"Cached config to {path}")
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/cache.py tests/test_cache.py
git commit -m "feat: add config cache with save/load"
```

---

### Task 10: Instruction Navigator

**Files:**
- Create: `src/experiment_bot/navigation/navigator.py`
- Create: `tests/test_navigator.py`

**Step 1: Write failing tests**

```python
# tests/test_navigator.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from experiment_bot.navigation.navigator import InstructionNavigator
from experiment_bot.core.config import NavigationPhase, NavigationConfig


@pytest.mark.asyncio
async def test_execute_click_action():
    """Navigator clicks the specified target."""
    phase = NavigationPhase(phase="fullscreen", action="click", target="button.continue")
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))

    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_page.locator.return_value = mock_locator
    mock_locator.first = mock_locator
    mock_locator.is_visible = AsyncMock(return_value=True)

    await nav.execute_phase(mock_page, phase)
    mock_page.locator.assert_called_with("button.continue")
    mock_locator.click.assert_called_once()


@pytest.mark.asyncio
async def test_execute_press_action():
    """Navigator presses the specified key."""
    phase = NavigationPhase(phase="start", action="press", key="Enter")
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))

    mock_page = AsyncMock()
    await nav.execute_phase(mock_page, phase)
    mock_page.keyboard.press.assert_called_with("Enter")


@pytest.mark.asyncio
async def test_execute_wait_action():
    """Navigator waits the specified duration."""
    phase = NavigationPhase(phase="reading", action="wait", duration_ms=100)
    nav = InstructionNavigator(reading_delay_range=(0.0, 0.0))

    mock_page = AsyncMock()
    await nav.execute_phase(mock_page, phase)
    # Just verify it completes without error
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_navigator.py -v
```

Expected: FAIL

**Step 3: Implement navigator**

```python
# src/experiment_bot/navigation/navigator.py
from __future__ import annotations

import asyncio
import logging
import random

from playwright.async_api import Page

from experiment_bot.core.config import NavigationConfig, NavigationPhase

logger = logging.getLogger(__name__)


class InstructionNavigator:
    """Navigates instruction screens, practice prompts, and feedback using config phases."""

    def __init__(self, reading_delay_range: tuple[float, float] = (3.0, 8.0)):
        self._reading_delay_range = reading_delay_range

    async def execute_all(self, page: Page, nav_config: NavigationConfig) -> None:
        for phase in nav_config.phases:
            await self.execute_phase(page, phase)

    async def execute_phase(self, page: Page, phase: NavigationPhase) -> None:
        logger.info(f"Executing navigation phase: {phase.phase} ({phase.action})")

        if phase.action == "click":
            await self._do_click(page, phase.target)
        elif phase.action == "press":
            await self._do_press(page, phase.key)
        elif phase.action == "wait":
            await self._do_wait(phase.duration_ms)
        elif phase.action == "sequence":
            for step in phase.steps:
                sub_phase = NavigationPhase.from_dict(step)
                await self.execute_phase(page, sub_phase)
        elif phase.action == "repeat":
            # Repeat steps until no matching element is found
            max_iterations = 20
            for _ in range(max_iterations):
                try:
                    for step in phase.steps:
                        sub_phase = NavigationPhase.from_dict(step)
                        await self.execute_phase(page, sub_phase)
                except Exception:
                    break

    async def _do_click(self, page: Page, target: str) -> None:
        await self._inject_reading_delay()
        locator = page.locator(target).first
        try:
            await locator.wait_for(state="visible", timeout=10000)
            await locator.click()
        except Exception as e:
            logger.warning(f"Click target not found: {target} ({e})")
            raise

    async def _do_press(self, page: Page, key: str) -> None:
        await self._inject_reading_delay()
        await page.keyboard.press(key)

    async def _do_wait(self, duration_ms: int) -> None:
        await asyncio.sleep(duration_ms / 1000.0)

    async def _inject_reading_delay(self) -> None:
        lo, hi = self._reading_delay_range
        if hi > 0:
            delay = random.uniform(lo, hi)
            await asyncio.sleep(delay)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_navigator.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/navigation/navigator.py tests/test_navigator.py
git commit -m "feat: add instruction navigator for phase-based task navigation"
```

---

### Task 11: Stuck Detector

**Files:**
- Create: `src/experiment_bot/navigation/stuck.py`
- Create: `tests/test_stuck.py`

**Step 1: Write failing tests**

```python
# tests/test_stuck.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.navigation.stuck import StuckDetector


@pytest.mark.asyncio
async def test_stuck_detector_fires_after_timeout():
    """Detector calls the fallback after the timeout elapses."""
    fallback_called = asyncio.Event()
    guidance = {"action": "press", "key": "space"}

    async def mock_fallback(page, screenshot):
        fallback_called.set()
        return guidance

    detector = StuckDetector(timeout_seconds=0.1, fallback_fn=mock_fallback)
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_png")

    task = asyncio.create_task(detector.watch(mock_page))

    # Don't call heartbeat — should trigger after 0.1s
    await asyncio.sleep(0.3)
    detector.stop()
    await task

    assert fallback_called.is_set()


@pytest.mark.asyncio
async def test_stuck_detector_reset_on_heartbeat():
    """Heartbeat resets the timer, preventing fallback."""
    fallback_called = False

    async def mock_fallback(page, screenshot):
        nonlocal fallback_called
        fallback_called = True
        return {}

    detector = StuckDetector(timeout_seconds=0.2, fallback_fn=mock_fallback)
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_png")

    task = asyncio.create_task(detector.watch(mock_page))

    # Send heartbeats faster than timeout
    for _ in range(5):
        detector.heartbeat()
        await asyncio.sleep(0.05)

    detector.stop()
    await task
    assert not fallback_called
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_stuck.py -v
```

Expected: FAIL

**Step 3: Implement stuck detector**

```python
# src/experiment_bot/navigation/stuck.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class StuckDetector:
    """Monitors for inactivity and triggers a fallback when stuck."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        fallback_fn: Callable[[Page, bytes], Awaitable[dict[str, Any]]] | None = None,
    ):
        self._timeout = timeout_seconds
        self._fallback_fn = fallback_fn
        self._last_heartbeat: float = 0.0
        self._running = False
        self._event = asyncio.Event()

    def heartbeat(self) -> None:
        """Call this whenever a stimulus is successfully detected."""
        self._event.set()

    def stop(self) -> None:
        self._running = False
        self._event.set()  # Unblock the wait

    async def watch(self, page: Page) -> dict[str, Any] | None:
        """Watch for stuck state. Returns fallback guidance if triggered, else None."""
        self._running = True
        while self._running:
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=self._timeout)
            except asyncio.TimeoutError:
                if not self._running:
                    return None
                logger.warning(f"Stuck detected (no heartbeat for {self._timeout}s)")
                if self._fallback_fn:
                    try:
                        screenshot = await page.screenshot(type="png")
                        guidance = await self._fallback_fn(page, screenshot)
                        logger.info(f"Fallback guidance: {guidance}")
                        return guidance
                    except Exception as e:
                        logger.error(f"Fallback failed: {e}")
                return None
        return None
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_stuck.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/navigation/stuck.py tests/test_stuck.py
git commit -m "feat: add stuck detector with fallback support"
```

---

### Task 12: Stimulus Lookup Table

**Files:**
- Create: `src/experiment_bot/core/stimulus.py`
- Create: `tests/test_stimulus.py`

**Step 1: Write failing tests**

```python
# tests/test_stimulus.py
import pytest
from unittest.mock import AsyncMock

from experiment_bot.core.stimulus import StimulusLookup, StimulusMatch
from experiment_bot.core.config import (
    TaskConfig,
    StimulusConfig,
    DetectionConfig,
    ResponseConfig,
)


def _make_config_with_stimuli(stimuli: list[StimulusConfig]) -> TaskConfig:
    return TaskConfig.from_dict({
        "task": {"name": "T", "platform": "test", "constructs": [], "reference_literature": []},
        "stimuli": [s.to_dict() for s in stimuli],
        "response_distributions": {},
        "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
        "navigation": {"phases": []},
        "task_specific": {},
    })


@pytest.mark.asyncio
async def test_identify_matching_stimulus():
    stim = StimulusConfig(
        id="go_left",
        description="Left arrow",
        detection=DetectionConfig(method="dom_query", selector=".arrow-left"),
        response=ResponseConfig(key="z", condition="go"),
    )
    config = _make_config_with_stimuli([stim])
    lookup = StimulusLookup(config)

    mock_page = AsyncMock()
    # query_selector returns a truthy mock for the matching selector
    mock_page.query_selector = AsyncMock(return_value=AsyncMock())

    match = await lookup.identify(mock_page)
    assert match is not None
    assert match.stimulus_id == "go_left"
    assert match.response_key == "z"
    assert match.condition == "go"


@pytest.mark.asyncio
async def test_identify_no_match():
    stim = StimulusConfig(
        id="go_left",
        description="Left arrow",
        detection=DetectionConfig(method="dom_query", selector=".arrow-left"),
        response=ResponseConfig(key="z", condition="go"),
    )
    config = _make_config_with_stimuli([stim])
    lookup = StimulusLookup(config)

    mock_page = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    match = await lookup.identify(mock_page)
    assert match is None


@pytest.mark.asyncio
async def test_identify_js_eval_method():
    stim = StimulusConfig(
        id="canvas_stim",
        description="Canvas stimulus",
        detection=DetectionConfig(method="js_eval", selector="window.currentStimulus === 'left'"),
        response=ResponseConfig(key="b", condition="go"),
    )
    config = _make_config_with_stimuli([stim])
    lookup = StimulusLookup(config)

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=True)

    match = await lookup.identify(mock_page)
    assert match is not None
    assert match.stimulus_id == "canvas_stim"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_stimulus.py -v
```

Expected: FAIL

**Step 3: Implement stimulus lookup**

```python
# src/experiment_bot/core/stimulus.py
from __future__ import annotations

import logging
from dataclasses import dataclass

from playwright.async_api import Page

from experiment_bot.core.config import TaskConfig, StimulusConfig

logger = logging.getLogger(__name__)


@dataclass
class StimulusMatch:
    stimulus_id: str
    response_key: str | None
    condition: str


@dataclass
class _StimulusRule:
    id: str
    method: str
    selector: str
    alt_method: str
    pattern: str
    response_key: str | None
    condition: str


class StimulusLookup:
    """Pre-compiled stimulus detection rules for fast DOM lookups."""

    def __init__(self, config: TaskConfig):
        self._rules: list[_StimulusRule] = []
        for stim in config.stimuli:
            self._rules.append(_StimulusRule(
                id=stim.id,
                method=stim.detection.method,
                selector=stim.detection.selector,
                alt_method=stim.detection.alt_method,
                pattern=stim.detection.pattern,
                response_key=stim.response.key,
                condition=stim.response.condition,
            ))

    async def identify(self, page: Page) -> StimulusMatch | None:
        """Fast stimulus identification. Returns first match or None."""
        for rule in self._rules:
            matched = await self._check_rule(page, rule)
            if matched:
                return StimulusMatch(
                    stimulus_id=rule.id,
                    response_key=rule.response_key,
                    condition=rule.condition,
                )
        return None

    async def _check_rule(self, page: Page, rule: _StimulusRule) -> bool:
        try:
            if rule.method == "dom_query":
                element = await page.query_selector(rule.selector)
                return element is not None
            elif rule.method == "js_eval":
                result = await page.evaluate(rule.selector)
                return bool(result)
            elif rule.method == "text_content":
                element = await page.query_selector(rule.selector)
                if element:
                    text = await element.text_content()
                    return rule.pattern in (text or "")
                return False
            elif rule.method == "canvas_state":
                result = await page.evaluate(rule.selector)
                return bool(result)
        except Exception as e:
            logger.debug(f"Rule check failed for {rule.id}: {e}")
        return False
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_stimulus.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/stimulus.py tests/test_stimulus.py
git commit -m "feat: add stimulus lookup table for fast DOM-based detection"
```

---

### Task 13: Output Writer

**Files:**
- Create: `src/experiment_bot/output/writer.py`
- Create: `tests/test_writer.py`

**Step 1: Write failing tests**

```python
# tests/test_writer.py
import json
import pytest
from pathlib import Path

from experiment_bot.output.writer import OutputWriter
from experiment_bot.core.config import TaskConfig


SAMPLE_CONFIG_DICT = {
    "task": {"name": "Test", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [],
    "response_distributions": {},
    "performance": {"go_accuracy": 0.9, "stop_accuracy": 0.5, "omission_rate": 0.01, "practice_accuracy": 0.8},
    "navigation": {"phases": []},
    "task_specific": {},
}


def test_writer_creates_output_dir(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("expfactory", "stop_signal_rdoc", config)

    assert run_dir.exists()
    assert (run_dir / "config.json").exists()


def test_writer_logs_trial(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    run_dir = writer.create_run("expfactory", "test_task", config)

    trial = {"trial": 1, "stimulus_id": "go_left", "sampled_rt_ms": 450}
    writer.log_trial(trial)
    writer.finalize()

    log_path = run_dir / "bot_log.json"
    assert log_path.exists()
    data = json.loads(log_path.read_text())
    assert len(data) == 1
    assert data[0]["trial"] == 1
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_writer.py -v
```

Expected: FAIL

**Step 3: Implement writer**

```python
# src/experiment_bot/output/writer.py
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "output"


class OutputWriter:
    """Writes run output to structured directories."""

    def __init__(self, base_dir: Path = DEFAULT_OUTPUT_DIR):
        self._base_dir = base_dir
        self._run_dir: Path | None = None
        self._trials: list[dict] = []

    def create_run(self, platform: str, task_name: str, config: TaskConfig) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._run_dir = self._base_dir / platform / task_name / timestamp
        self._run_dir.mkdir(parents=True, exist_ok=True)
        (self._run_dir / "screenshots").mkdir(exist_ok=True)

        # Save config
        config_path = self._run_dir / "config.json"
        config_path.write_text(json.dumps(config.to_dict(), indent=2))

        self._trials = []
        logger.info(f"Output directory: {self._run_dir}")
        return self._run_dir

    def log_trial(self, trial_data: dict) -> None:
        self._trials.append(trial_data)

    def save_task_data(self, data: str, filename: str = "task_data.csv") -> None:
        if self._run_dir:
            (self._run_dir / filename).write_text(data)

    def save_screenshot(self, data: bytes, name: str) -> None:
        if self._run_dir:
            (self._run_dir / "screenshots" / name).write_bytes(data)

    def save_metadata(self, metadata: dict) -> None:
        if self._run_dir:
            (self._run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))

    def finalize(self) -> None:
        if self._run_dir:
            log_path = self._run_dir / "bot_log.json"
            log_path.write_text(json.dumps(self._trials, indent=2))
            logger.info(f"Saved {len(self._trials)} trial logs to {log_path}")

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_writer.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/output/writer.py tests/test_writer.py
git commit -m "feat: add output writer for structured run data"
```

---

### Task 14: Task Executor

**Files:**
- Create: `src/experiment_bot/core/executor.py`
- Create: `tests/test_executor.py`

This is the most complex module — it orchestrates the full task run.

**Step 1: Write failing tests**

```python
# tests/test_executor.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.core.config import TaskConfig
from experiment_bot.core.stimulus import StimulusMatch


SAMPLE_CONFIG = {
    "task": {"name": "Stop Signal", "platform": "expfactory", "constructs": [], "reference_literature": []},
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        },
        {
            "id": "stop_trial",
            "description": "Stop signal",
            "detection": {"method": "dom_query", "selector": ".stop-signal"},
            "response": {"key": None, "condition": "stop"},
        },
    ],
    "response_distributions": {
        "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
    },
    "performance": {"go_accuracy": 0.95, "stop_accuracy": 0.50, "omission_rate": 0.02, "practice_accuracy": 0.85},
    "navigation": {"phases": []},
    "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
}


def test_executor_init():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory")
    assert executor._config.task.name == "Stop Signal"


def test_should_respond_correctly_on_go():
    """On go trials with high accuracy, bot should usually respond correctly."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    # With 95% accuracy, vast majority should respond
    correct_count = sum(1 for _ in range(100) if executor._should_respond_correctly("go"))
    assert 85 < correct_count < 100


def test_should_omit_rarely():
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    omit_count = sum(1 for _ in range(1000) if executor._should_omit())
    # 2% omission rate = ~20 out of 1000
    assert 5 < omit_count < 50
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_executor.py -v
```

Expected: FAIL

**Step 3: Implement executor**

```python
# src/experiment_bot/core/executor.py
from __future__ import annotations

import asyncio
import logging
import random
import time

import numpy as np
from playwright.async_api import Page, Browser, async_playwright

from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.distributions import ResponseSampler
from experiment_bot.core.stimulus import StimulusLookup, StimulusMatch
from experiment_bot.navigation.navigator import InstructionNavigator
from experiment_bot.navigation.stuck import StuckDetector
from experiment_bot.output.writer import OutputWriter
from experiment_bot.platforms.base import Platform

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Drives Playwright through a cognitive task using a pre-generated TaskConfig."""

    def __init__(
        self,
        config: TaskConfig,
        platform_name: str,
        seed: int | None = None,
        headless: bool = False,
    ):
        self._config = config
        self._platform_name = platform_name
        self._headless = headless
        self._rng = np.random.default_rng(seed)
        self._py_rng = random.Random(seed)

        self._lookup = StimulusLookup(config)
        self._sampler = ResponseSampler(config.response_distributions, seed=seed)
        self._navigator = InstructionNavigator()
        self._writer = OutputWriter()
        self._trial_count = 0

    def _should_respond_correctly(self, condition: str) -> bool:
        """Decide whether to give the correct response based on accuracy targets."""
        if condition == "stop":
            return self._py_rng.random() < self._config.performance.stop_accuracy
        return self._py_rng.random() < self._config.performance.go_accuracy

    def _should_omit(self) -> bool:
        return self._py_rng.random() < self._config.performance.omission_rate

    async def run(self, task_url: str, platform: Platform) -> None:
        """Execute the full task."""
        task_name = self._config.task.name.replace(" ", "_").lower()
        run_dir = self._writer.create_run(self._platform_name, task_name, self._config)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            try:
                logger.info(f"Navigating to {task_url}")
                await page.goto(task_url, wait_until="networkidle")

                # Phase 1: Navigate instructions
                logger.info("Navigating instructions...")
                await self._navigator.execute_all(page, self._config.navigation)

                # Phase 2: Trial loop
                logger.info("Entering trial loop...")
                await self._trial_loop(page, platform)

                # Phase 3: Wait for completion and data
                logger.info("Waiting for task completion...")
                await self._wait_for_completion(page, platform)

            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                screenshot = await page.screenshot(type="png")
                self._writer.save_screenshot(screenshot, "error.png")
                raise
            finally:
                self._writer.save_metadata({
                    "platform": self._platform_name,
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                })
                self._writer.finalize()
                await browser.close()

    async def _trial_loop(self, page: Page, platform: Platform) -> None:
        """Main trial loop: detect stimulus, sample RT, respond."""
        stuck_detector = StuckDetector(timeout_seconds=10.0)
        max_no_stimulus_polls = 500  # Safety limit

        consecutive_misses = 0
        while True:
            # Check if task is complete
            phase = await platform.detect_task_phase(page)
            if phase == TaskPhase.COMPLETE:
                logger.info("Task complete detected")
                break

            if phase in (TaskPhase.FEEDBACK, TaskPhase.ATTENTION_CHECK):
                await self._handle_feedback(page)
                consecutive_misses = 0
                continue

            if phase == TaskPhase.INSTRUCTIONS:
                # Sometimes instructions appear between blocks
                await self._navigator.execute_all(page, self._config.navigation)
                consecutive_misses = 0
                continue

            # Try to detect stimulus
            match = await self._lookup.identify(page)
            if match is None:
                consecutive_misses += 1
                if consecutive_misses > max_no_stimulus_polls:
                    logger.warning("Too many consecutive misses, stopping trial loop")
                    break
                await asyncio.sleep(0.02)  # 20ms poll interval
                continue

            consecutive_misses = 0
            stuck_detector.heartbeat()
            self._trial_count += 1

            await self._execute_trial(page, match)

    async def _execute_trial(self, page: Page, match: StimulusMatch) -> None:
        """Execute a single trial: decide response, wait RT, press key."""
        trial_start = time.monotonic()

        # Determine condition for RT sampling
        condition = match.condition
        is_practice = False  # TODO: track practice vs test phase

        if self._should_omit():
            # Omission: don't respond at all
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": None,
                "sampled_rt_ms": None,
                "actual_rt_ms": None,
                "omission": True,
            })
            # Wait for trial to advance (timeout)
            await asyncio.sleep(2.0)
            return

        if condition == "stop":
            # For stop trials: should we successfully inhibit?
            if self._should_respond_correctly("stop"):
                # Successful stop — don't respond
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": "stop_success",
                    "response_key": None,
                    "sampled_rt_ms": None,
                    "actual_rt_ms": None,
                    "omission": False,
                })
                await asyncio.sleep(2.0)
                return
            else:
                # Failed stop — respond (use stop_failure distribution if available)
                rt_condition = "stop_failure" if "stop_failure" in self._sampler._samplers else "go_correct"
        else:
            rt_condition = "go_correct" if self._should_respond_correctly("go") else "go_error"

        # Sample RT
        try:
            rt_ms = self._sampler.sample_rt(rt_condition)
        except KeyError:
            rt_ms = self._sampler.sample_rt(list(self._sampler._samplers.keys())[0])

        # Wait the sampled RT
        await asyncio.sleep(rt_ms / 1000.0)
        actual_rt = (time.monotonic() - trial_start) * 1000

        # Press the response key
        if match.response_key:
            await page.keyboard.press(match.response_key)

        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": match.response_key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
        })

    async def _handle_feedback(self, page: Page) -> None:
        """Handle inter-block feedback and attention checks."""
        logger.info("Handling feedback/attention screen")
        await asyncio.sleep(2.0)  # Read feedback

        # Try common advance methods
        for selector in ["button", "#jspsych-instructions-next", ".jspsych-btn"]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible():
                    await btn.click()
                    return
            except Exception:
                continue

        # Try pressing Enter or Space
        await page.keyboard.press("Enter")

    async def _wait_for_completion(self, page: Page, platform: Platform) -> None:
        """Wait for the task to fully complete and data to be available."""
        # For ExpFactory: wait ~30 seconds for data download
        if self._platform_name == "expfactory":
            logger.info("Waiting 35 seconds for ExpFactory data download...")
            await asyncio.sleep(35)
        else:
            await asyncio.sleep(5)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_executor.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "feat: add TaskExecutor with trial loop, race model, and RT sampling"
```

---

### Task 15: CLI Entry Point

**Files:**
- Create: `src/experiment_bot/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests**

```python
# tests/test_cli.py
from click.testing import CliRunner
from experiment_bot.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "experiment-bot" in result.output.lower() or "usage" in result.output.lower()


def test_expfactory_help():
    runner = CliRunner()
    result = runner.invoke(main, ["expfactory", "--help"])
    assert result.exit_code == 0
    assert "--task" in result.output


def test_psytoolkit_help():
    runner = CliRunner()
    result = runner.invoke(main, ["psytoolkit", "--help"])
    assert result.exit_code == 0
    assert "--task" in result.output


def test_missing_task_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["expfactory"])
    assert result.exit_code != 0  # Should fail without --task
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL

**Step 3: Implement CLI**

```python
# src/experiment_bot/cli.py
from __future__ import annotations

import asyncio
import logging
import os

import click

from experiment_bot.core.analyzer import Analyzer
from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.executor import TaskExecutor
from experiment_bot.platforms.expfactory import ExpFactoryPlatform
from experiment_bot.platforms.psytoolkit import PsyToolkitPlatform


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_task(
    platform_name: str,
    task_id: str,
    headless: bool,
    regenerate: bool,
    rt_mean: float | None,
    accuracy: float | None,
) -> None:
    from anthropic import AsyncAnthropic

    # Select platform
    if platform_name == "expfactory":
        platform = ExpFactoryPlatform()
    else:
        platform = PsyToolkitPlatform()

    # Check cache
    cache = ConfigCache()
    config = None if regenerate else cache.load(platform_name, task_id)

    if config is None:
        # Download source and analyze
        click.echo(f"Downloading source code for {platform_name}/{task_id}...")
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = await platform.download_source(task_id, Path(tmpdir))

        click.echo("Analyzing task with Claude Opus 4.6...")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise click.ClickException("ANTHROPIC_API_KEY environment variable not set")

        client = AsyncAnthropic(api_key=api_key)
        analyzer = Analyzer(client=client)
        config = await analyzer.analyze(bundle)

        # Apply overrides
        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

        # Cache
        cache.save(platform_name, task_id, config)
        click.echo(f"Config generated and cached.")
    else:
        click.echo(f"Using cached config for {platform_name}/{task_id}")
        # Apply overrides to cached config too
        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

    # Run
    task_url = await platform.get_task_url(task_id)
    click.echo(f"Running task at {task_url}")
    executor = TaskExecutor(config, platform_name=platform_name, headless=headless)
    await executor.run(task_url, platform)
    click.echo("Done!")


@click.group()
def main():
    """experiment-bot: Execute human-like behavior on cognitive tasks."""
    pass


@main.command()
@click.option("--task", required=True, help="Task ID (e.g., 9 for stop signal)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--regenerate-config", is_flag=True, default=False, help="Force regenerate config via API")
@click.option("--rt-mean", type=float, default=None, help="Override mean RT (mu) in ms")
@click.option("--accuracy", type=float, default=None, help="Override go accuracy (0-1)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def expfactory(task: str, headless: bool, regenerate_config: bool, rt_mean: float | None, accuracy: float | None, verbose: bool):
    """Run a task from the Experiment Factory platform."""
    _setup_logging(verbose)
    asyncio.run(_run_task("expfactory", task, headless, regenerate_config, rt_mean, accuracy))


@main.command()
@click.option("--task", required=True, help="Task ID (e.g., stopsignal)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--regenerate-config", is_flag=True, default=False, help="Force regenerate config via API")
@click.option("--rt-mean", type=float, default=None, help="Override mean RT (mu) in ms")
@click.option("--accuracy", type=float, default=None, help="Override go accuracy (0-1)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def psytoolkit(task: str, headless: bool, regenerate_config: bool, rt_mean: float | None, accuracy: float | None, verbose: bool):
    """Run a task from the PsyToolkit platform."""
    _setup_logging(verbose)
    asyncio.run(_run_task("psytoolkit", task, headless, regenerate_config, rt_mean, accuracy))
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/cli.py tests/test_cli.py
git commit -m "feat: add Click CLI with expfactory and psytoolkit subcommands"
```

---

### Task 16: Integration Test — Dry Run

**Files:**
- Create: `tests/test_integration.py`

This test verifies the full pipeline works end-to-end using mocked API responses.

**Step 1: Write the integration test**

```python
# tests/test_integration.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.cache import ConfigCache
from experiment_bot.core.executor import TaskExecutor


FULL_CONFIG = {
    "task": {
        "name": "Stop Signal Task",
        "platform": "expfactory",
        "constructs": ["inhibitory_control"],
        "reference_literature": ["Logan 1994"],
    },
    "stimuli": [
        {
            "id": "go_left",
            "description": "Left arrow go trial",
            "detection": {"method": "dom_query", "selector": ".arrow-left"},
            "response": {"key": "z", "condition": "go"},
        },
        {
            "id": "go_right",
            "description": "Right arrow go trial",
            "detection": {"method": "dom_query", "selector": ".arrow-right"},
            "response": {"key": "/", "condition": "go"},
        },
        {
            "id": "stop_trial",
            "description": "Stop signal trial",
            "detection": {"method": "dom_query", "selector": ".stop-signal"},
            "response": {"key": None, "condition": "stop"},
        },
    ],
    "response_distributions": {
        "go_correct": {"distribution": "ex_gaussian", "params": {"mu": 450, "sigma": 60, "tau": 80}},
        "go_error": {"distribution": "ex_gaussian", "params": {"mu": 380, "sigma": 70, "tau": 100}},
        "stop_failure": {"distribution": "ex_gaussian", "params": {"mu": 400, "sigma": 50, "tau": 60}},
    },
    "performance": {
        "go_accuracy": 0.95,
        "stop_accuracy": 0.50,
        "omission_rate": 0.02,
        "practice_accuracy": 0.85,
    },
    "navigation": {"phases": []},
    "task_specific": {"model": "independent_race", "ssrt_target_ms": 250},
}


def test_full_config_parses():
    config = TaskConfig.from_dict(FULL_CONFIG)
    assert config.task.name == "Stop Signal Task"
    assert len(config.stimuli) == 3


def test_config_cache_round_trip(tmp_path):
    config = TaskConfig.from_dict(FULL_CONFIG)
    cache = ConfigCache(cache_dir=tmp_path)
    cache.save("expfactory", "9", config)
    loaded = cache.load("expfactory", "9")
    assert loaded.task.name == "Stop Signal Task"
    assert len(loaded.stimuli) == 3
    assert loaded.response_distributions["go_correct"].params["mu"] == 450


def test_executor_constructs_from_config():
    config = TaskConfig.from_dict(FULL_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    # Verify the lookup has all stimulus rules
    assert len(executor._lookup._rules) == 3
    # Verify sampler has all distributions
    assert "go_correct" in executor._sampler._samplers
    assert "stop_failure" in executor._sampler._samplers
```

**Step 2: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for full config pipeline"
```

---

### Task 17: End-to-End Smoke Test (Live)

This is the final validation. No code to write — just run the bot against each of the four tasks.

**Step 1: Set up environment**

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

**Step 2: Run ExpFactory stop signal**

```bash
uv run experiment-bot expfactory --task 9 -v
```

Watch the browser. Verify:
- Config is generated and cached
- Bot navigates instructions
- Bot responds to go trials with realistic RTs
- Bot withholds on some stop trials
- Data is saved to `output/expfactory/`

**Step 3: Run ExpFactory cued task switching**

```bash
uv run experiment-bot expfactory --task 2 -v
```

**Step 4: Run PsyToolkit stop signal**

```bash
uv run experiment-bot psytoolkit --task stopsignal -v
```

**Step 5: Run PsyToolkit cued task switching**

```bash
uv run experiment-bot psytoolkit --task taskswitching_cued -v
```

**Step 6: Review output**

Check `output/` directory structure. Verify `config.json`, `bot_log.json`, and `run_metadata.json` are populated for each run.

**Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjustments from live smoke testing"
```

---

## Task Dependency Graph

```
Task 1 (scaffolding)
  └─▶ Task 2 (data models)
        ├─▶ Task 3 (distributions)
        ├─▶ Task 4 (platform base)
        │     ├─▶ Task 5 (expfactory adapter)
        │     └─▶ Task 6 (psytoolkit adapter)
        ├─▶ Task 7 (prompts/schema)
        │     └─▶ Task 8 (analyzer)
        │           └─▶ Task 9 (cache)
        ├─▶ Task 10 (navigator)
        │     └─▶ Task 11 (stuck detector)
        ├─▶ Task 12 (stimulus lookup)
        └─▶ Task 13 (output writer)
              └─▶ Task 14 (executor) [depends on 3, 10, 11, 12, 13]
                    └─▶ Task 15 (CLI) [depends on 5, 6, 8, 9, 14]
                          └─▶ Task 16 (integration test)
                                └─▶ Task 17 (live smoke test)
```

Tasks 3, 4, 7, 10, 12, 13 can be parallelized after Task 2.
Tasks 5 and 6 can be parallelized after Task 4.

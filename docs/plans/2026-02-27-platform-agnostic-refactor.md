# Platform-Agnostic Experiment Bot Refactor

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the experiment bot from a platform-coupled system (hardcoded for ExpFactory and PsyToolkit) into a domain-general bot that takes any experiment URL and lets Claude infer everything needed to complete the task.

**Architecture:** Replace the `Platform` adapter layer and platform-specific subcommands with a single URL-based entry point. A generic HTTP scraper fetches page source and linked resources from any URL. Claude's analysis prompt is rewritten to be platform-blind — it reads raw HTML/JS source and infers stimulus detection, phase detection, navigation, data capture, and response timing. The executor becomes a pure config interpreter with zero platform-conditional code. The cache is re-keyed by URL hash instead of platform+task_id.

**Tech Stack:** Python 3.12, Playwright (async), Anthropic Claude API, Click CLI, numpy, httpx

---

## Inventory of Platform-Specific Code to Remove

Before starting, this is the full audit of what must change:

| File | Platform-specific code | Action |
|------|----------------------|--------|
| `cli.py` | `expfactory` and `psytoolkit` subcommands | Replace with single `run` command |
| `platforms/base.py` | `Platform` ABC, `detect_task_phase_from_config` | Move detection to `core/`, delete ABC |
| `platforms/expfactory.py` | Entire file — URL patterns, DOM heuristics, resource fetching | Delete |
| `platforms/psytoolkit.py` | Entire file — ZIP download, JS global detection | Delete |
| `platforms/registry.py` | Platform name to class mapping | Delete |
| `prompts/system.md` | jsPsych/PsyToolkit specific guidance throughout | Rewrite entirely |
| `prompts/schema.json` | `platform` enum `["expfactory", "psytoolkit"]`; no `data_capture` | Remove enum, add sections |
| `core/config.py` | `SourceBundle.platform`, `TaskMetadata.platform` | Make URL-based |
| `core/analyzer.py` | `_build_user_message` sends platform/task_id | Send URL + hints |
| `core/cache.py` | Keyed by `platform/task_id` | Key by URL hash |
| `core/executor.py:29` | `platform_name` constructor param | Remove |
| `core/executor.py:68-109` | `_resolve_key_mapping_legacy` — expfactory group-index logic | Delete |
| `core/executor.py:220` | `platform.detect_task_phase(page)` — Platform dependency | Use config-driven detection |
| `core/executor.py:533-536` | `#jspsych-attention-check-rdoc-stimulus` hardcoded selector | Move to config |
| `core/executor.py:592` | `get_data_capture(self._platform_name)` | Use config-driven capture |
| `core/executor.py:597` | `"tsv" if platform == "psytoolkit" else "csv"` | Read format from config |
| `output/data_capture.py` | `PsyToolkitDataCapture`, `ExpFactoryDataCapture`, registry | Replace with generic |
| `output/writer.py` | Uses `platform_name` in directory path | Use task name or URL slug |
| `scripts/launch.sh` | Hardcoded platform:task registry | Accept URL |
| `scripts/check_data.py` | `STOP_SIGNAL_NAMES`, `TASK_SWITCHING_NAMES`, column schemas | Generalize |

---

## Task 1: Config Schema — Add DataCaptureConfig and AttentionCheckConfig

Foundation task: extend the config schema so Claude can specify data capture and attention check strategies declaratively, removing the need for platform-specific code.

**Files:**
- Modify: `src/experiment_bot/core/config.py`
- Modify: `src/experiment_bot/prompts/schema.json`
- Test: `tests/test_config.py`

**Step 1: Write failing test for DataCaptureConfig**

```python
# In tests/test_config.py — add this test
def test_data_capture_config_from_dict():
    d = {
        "method": "js_expression",
        "expression": "jsPsych.data.get().csv()",
        "format": "csv",
    }
    from experiment_bot.core.config import DataCaptureConfig
    cfg = DataCaptureConfig.from_dict(d)
    assert cfg.method == "js_expression"
    assert cfg.expression == "jsPsych.data.get().csv()"
    assert cfg.format == "csv"


def test_data_capture_config_button_click():
    d = {
        "method": "button_click",
        "button_selector": "input[value='show data']",
        "result_selector": "#showdata",
        "format": "tsv",
    }
    from experiment_bot.core.config import DataCaptureConfig
    cfg = DataCaptureConfig.from_dict(d)
    assert cfg.method == "button_click"
    assert cfg.button_selector == "input[value='show data']"


def test_data_capture_config_defaults():
    from experiment_bot.core.config import DataCaptureConfig
    cfg = DataCaptureConfig()
    assert cfg.method == ""
    assert cfg.format == "csv"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_data_capture_config_from_dict -v`
Expected: FAIL with `ImportError: cannot import name 'DataCaptureConfig'`

**Step 3: Implement DataCaptureConfig**

Add to `src/experiment_bot/core/config.py` before `RuntimeConfig`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_data_capture_config_from_dict tests/test_config.py::test_data_capture_config_button_click tests/test_config.py::test_data_capture_config_defaults -v`
Expected: PASS

**Step 5: Write failing test for AttentionCheckConfig**

```python
def test_attention_check_config_from_dict():
    d = {
        "detection_selector": "#jspsych-attention-check-rdoc-stimulus",
        "text_selector": ".jspsych-display-element",
    }
    from experiment_bot.core.config import AttentionCheckConfig
    cfg = AttentionCheckConfig.from_dict(d)
    assert cfg.detection_selector == "#jspsych-attention-check-rdoc-stimulus"
    assert cfg.text_selector == ".jspsych-display-element"
```

**Step 6: Implement AttentionCheckConfig**

Add to `src/experiment_bot/core/config.py`:

```python
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
```

**Step 7: Add both to RuntimeConfig**

Update `RuntimeConfig` to include `data_capture` and `attention_check` fields:

```python
@dataclass
class RuntimeConfig:
    phase_detection: PhaseDetectionConfig = field(default_factory=PhaseDetectionConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    advance_behavior: AdvanceBehaviorConfig = field(default_factory=AdvanceBehaviorConfig)
    paradigm: ParadigmConfig = field(default_factory=ParadigmConfig)
    data_capture: DataCaptureConfig = field(default_factory=DataCaptureConfig)
    attention_check: AttentionCheckConfig = field(default_factory=AttentionCheckConfig)

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeConfig:
        return cls(
            phase_detection=PhaseDetectionConfig.from_dict(d.get("phase_detection", {})),
            timing=TimingConfig.from_dict(d.get("timing", {})),
            advance_behavior=AdvanceBehaviorConfig.from_dict(d.get("advance_behavior", {})),
            paradigm=ParadigmConfig.from_dict(d.get("paradigm", {})),
            data_capture=DataCaptureConfig.from_dict(d.get("data_capture", {})),
            attention_check=AttentionCheckConfig.from_dict(d.get("attention_check", {})),
        )

    def to_dict(self) -> dict:
        return {
            "phase_detection": self.phase_detection.to_dict(),
            "timing": self.timing.to_dict(),
            "advance_behavior": self.advance_behavior.to_dict(),
            "paradigm": self.paradigm.to_dict(),
            "data_capture": self.data_capture.to_dict(),
            "attention_check": self.attention_check.to_dict(),
        }
```

**Step 8: Write failing test for RuntimeConfig with new fields**

```python
def test_runtime_config_with_data_capture():
    d = {
        "data_capture": {
            "method": "js_expression",
            "expression": "jsPsych.data.get().csv()",
            "format": "csv",
        },
        "attention_check": {
            "detection_selector": "#attention-check",
        },
    }
    from experiment_bot.core.config import RuntimeConfig
    cfg = RuntimeConfig.from_dict(d)
    assert cfg.data_capture.method == "js_expression"
    assert cfg.attention_check.detection_selector == "#attention-check"
```

**Step 9: Run all config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

**Step 10: Make SourceBundle URL-based**

Update `SourceBundle`:

```python
@dataclass
class SourceBundle:
    url: str                          # The experiment URL
    source_files: dict[str, str]      # filename -> content
    description_text: str             # Human-readable description or page HTML
    metadata: dict = field(default_factory=dict)
    hint: str = ""                    # User-provided hint about the task
```

Note: `platform` and `task_id` fields are removed. The URL is the identifier.

**Step 11: Make TaskMetadata platform-optional**

```python
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
```

**Step 12: Update schema.json**

Remove the `enum` constraint from `platform`:
```json
"platform": {"type": "string", "description": "Detected platform (e.g., jsPsych, PsyToolkit, lab.js, Gorilla, etc.) or empty if unknown"}
```

Remove `"platform"` from `required` in the `task` object.

Add `data_capture` and `attention_check` to the `runtime` properties in schema.json.

**Step 13: Run full test suite**

Run: `uv run pytest -v`
Expected: Some existing tests may need `platform` parameter updates. Fix any that fail by making platform optional in test fixtures.

**Step 14: Commit**

```bash
git add src/experiment_bot/core/config.py src/experiment_bot/prompts/schema.json tests/test_config.py
git commit -m "feat: add DataCaptureConfig, AttentionCheckConfig; make platform optional"
```

---

## Task 2: Generic Source Scraper

Replace the platform-specific `download_source()` methods with a single generic HTTP scraper that works for any experiment URL.

**Files:**
- Create: `src/experiment_bot/core/scraper.py`
- Test: `tests/test_scraper.py`

**Step 1: Write failing test for generic scraper**

```python
# tests/test_scraper.py
import pytest
from unittest.mock import AsyncMock, patch

from experiment_bot.core.scraper import scrape_experiment_source
from experiment_bot.core.config import SourceBundle


@pytest.mark.asyncio
async def test_scrape_basic_html():
    """Scraper should fetch URL HTML and return a SourceBundle."""
    html = '<html><body><script src="/js/experiment.js"></script></body></html>'

    mock_response = AsyncMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None

    mock_js_response = AsyncMock()
    mock_js_response.text = "var x = 1;"
    mock_js_response.status_code = 200
    mock_js_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[mock_response, mock_js_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("experiment_bot.core.scraper.httpx.AsyncClient", return_value=mock_client):
        bundle = await scrape_experiment_source(
            url="https://example.com/experiment/",
            hint="A stop signal task",
        )

    assert isinstance(bundle, SourceBundle)
    assert bundle.url == "https://example.com/experiment/"
    assert bundle.hint == "A stop signal task"
    assert "experiment.js" in bundle.source_files
    assert bundle.description_text == html
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scraper.py::test_scrape_basic_html -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'experiment_bot.core.scraper'`

**Step 3: Implement the generic scraper**

Create `src/experiment_bot/core/scraper.py`:

```python
from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from experiment_bot.core.config import SourceBundle

logger = logging.getLogger(__name__)


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


def _parse_resource_tags(html: str) -> tuple[list[str], list[str]]:
    """Parse HTML and return (script_srcs, stylesheet_hrefs)."""
    parser = _ResourceTagParser()
    parser.feed(html)
    return parser.scripts, parser.styles


async def scrape_experiment_source(
    url: str,
    hint: str = "",
    extra_urls: list[str] | None = None,
) -> SourceBundle:
    """Fetch experiment page HTML and linked resources from any URL.

    Args:
        url: The experiment page URL.
        hint: Optional user-provided hint about the task (e.g., "stop signal task").
        extra_urls: Optional additional resource URLs to fetch.

    Returns:
        SourceBundle with all fetched source files.
    """
    source_files: dict[str, str] = {}

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Fetch the main page
        resp = await client.get(url)
        resp.raise_for_status()
        page_html = resp.text

        # Parse and fetch linked resources
        scripts, styles = _parse_resource_tags(page_html)
        for path in scripts + styles:
            resource_url = urljoin(url, path)
            try:
                r = await client.get(resource_url)
                if r.status_code == 200:
                    filename = path.split("/")[-1].split("?")[0]
                    source_files[filename] = r.text
            except Exception as e:
                logger.debug(f"Failed to fetch resource {resource_url}: {e}")

        # Fetch any extra URLs
        for extra_url in extra_urls or []:
            try:
                r = await client.get(extra_url)
                if r.status_code == 200:
                    filename = extra_url.split("/")[-1].split("?")[0]
                    source_files[filename] = r.text
            except Exception as e:
                logger.debug(f"Failed to fetch extra URL {extra_url}: {e}")

    return SourceBundle(
        url=url,
        source_files=source_files,
        description_text=page_html,
        hint=hint,
        metadata={"fetched_resources": len(source_files)},
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: PASS

**Step 5: Write test for relative URL resolution**

```python
@pytest.mark.asyncio
async def test_scrape_resolves_relative_urls():
    """Scraper should resolve relative URLs against the base URL."""
    from urllib.parse import urljoin
    assert urljoin("https://example.com/exp/", "js/experiment.js") == "https://example.com/exp/js/experiment.js"
    assert urljoin("https://example.com/exp/", "../css/style.css") == "https://example.com/css/style.css"
```

**Step 6: Run test**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/experiment_bot/core/scraper.py tests/test_scraper.py
git commit -m "feat: add generic HTTP scraper for any experiment URL"
```

---

## Task 3: Platform-Agnostic System Prompt

Rewrite the Claude analysis prompt to be completely platform-blind. This is the most critical task — the prompt quality determines whether the bot works on arbitrary experiments.

**Files:**
- Modify: `src/experiment_bot/prompts/system.md`
- Modify: `src/experiment_bot/core/analyzer.py`

**Step 1: Rewrite system.md**

Replace the entire contents of `src/experiment_bot/prompts/system.md` with:

```markdown
You are a cognitive psychology expert and web developer analyzing the source code of a web-based behavioral experiment.

## Your Task

Given the HTML/JavaScript source code of a cognitive experiment, produce a JSON configuration that enables an automated bot to complete the task with human-like behavior. You must infer everything from the source code — the experiment could be built with any framework (jsPsych, PsyToolkit, lab.js, Gorilla, custom HTML, etc.).

## What You Must Determine

1. **Task identification**: What cognitive task is this? What constructs does it measure? Cite relevant published literature (authors and year).

2. **Stimulus-response mappings**: For each possible stimulus, determine:
   - How to detect it (JavaScript expression or CSS selector)
   - What the correct keyboard response is (key name or null to withhold)
   - A unique condition label for the stimulus

   Detection methods:
   - `dom_query`: CSS selector — truthy if element exists (e.g., `img[src*='circle']`)
   - `js_eval`: JavaScript expression — truthy if returns a truthy value
   - `text_content`: CSS selector + pattern — truthy if element text contains pattern
   - `canvas_state`: JavaScript expression for canvas-based tasks — same as js_eval

   **IMPORTANT**: Identify ALL possible stimulus types. Missing a stimulus type will cause the bot to freeze. Order stimulus rules so that inhibition/stop signals are detected BEFORE go stimuli when both may be simultaneously present.

3. **Response time distributions**: Based on published literature for this task type, provide ex-Gaussian distribution parameters (mu, sigma, tau in milliseconds) for each response condition. These should reflect typical healthy adult performance.

   RT distribution naming conventions (the executor uses these names to select distributions):
   - **Simple and stop signal tasks**: Use `go_correct`, `go_error`, and `stop_failure` as distribution keys
   - **Task switching paradigms**: Use `task_repeat_cue_repeat`, `task_repeat_cue_switch`, `task_switch`, and `first_trial` as distribution keys. Name stimulus conditions as `{task_type}_{stimulus}` (e.g., `parity_even`, `color_left`) — the executor extracts the task type from the condition prefix and compares with the previous trial to select the correct distribution
   - **Other paradigms**: Choose descriptive distribution key names that match the condition labels

   Literature-grounded ranges:
   - Typical healthy adult go RTs: mu=400-500ms, sigma=50-80ms, tau=60-100ms
   - Stop signal: SSRT ~200-280ms (Verbruggen & Logan, 2009)
   - Task switching: switch cost ~50-150ms added to mu (Monsell, 2003)

4. **Performance targets**: Accuracy (0-1), stop accuracy if applicable, omission rate, and practice accuracy.

5. **Navigation flow**: How does a participant get from the initial page to the first trial? List every click, keypress, and wait needed. Include CSS selectors for buttons and the exact keys to press. Common patterns:
   - Button clicks (fullscreen, next, start)
   - Keypresses (Space, Enter, specific letters)
   - Waits (for loading, animations)
   - Pre-keypress JavaScript (some frameworks require calling a function before keypresses are registered)

6. **Phase detection**: JavaScript expressions the bot evaluates each poll cycle to determine the current experiment phase. Provide JS expressions for: `complete`, `loading`, `instructions`, `attention_check`, `feedback`, `practice`, `test`. Each expression should be a self-contained JS snippet that returns true/false. Examine the source code for:
   - Completion indicators: specific DOM elements, JS globals, page text
   - Loading/start screens: start buttons, loading spinners
   - Instruction pages: next buttons, instruction containers
   - Between-block feedback: "You have completed X blocks" text, feedback elements

   **CRITICAL**: Check completion BEFORE other phases to avoid false positives (e.g., "completed 1 of 3 blocks" contains "completed" but is not task completion).

7. **Timing configuration**: Analyze the source code to determine:
   - `response_window_js`: If stimulus detection can fire BEFORE the experiment's RT timer starts (e.g., during a fixation or cue phase), provide a JS expression that returns true only when the response window is actually open. This prevents impossibly fast recorded RTs. Examine the source for keyboard listener activation timing.
   - `cue_selector_js`: For task-switching paradigms, a JS expression that returns the current cue text (used for cue-switch tracking)
   - `completion_wait_ms`: How long the experiment takes to save/upload data after the last trial
   - `max_no_stimulus_polls`: How many empty poll cycles before giving up (canvas-based tasks may need more: ~2000)

8. **Advance behavior**: How to advance past instruction/feedback screens that appear between blocks:
   - `advance_keys`: Keys to press (typically Space or Enter)
   - `pre_keypress_js`: JavaScript to call before keypresses (some frameworks require this)
   - `exit_pager_key`: Key to exit multi-page instruction viewers
   - `feedback_selectors`: CSS selectors for "Continue" or "Next" buttons

9. **Data capture**: How to extract the experiment's recorded data after completion:
   - `method`: One of `"js_expression"`, `"button_click"`, or `""` (if no data capture possible)
   - For `js_expression`: provide a JS `expression` that returns the data as a string
   - For `button_click`: provide `button_selector` (CSS selector for "show data" button) and `result_selector` (CSS selector for the element containing the data)
   - `format`: `"csv"`, `"tsv"`, or `"json"`

10. **Attention checks**: If the experiment has attention checks:
    - `detection_selector`: CSS/JS selector that detects when an attention check is displayed
    - `text_selector`: CSS selector to read the attention check prompt text (the bot parses "Press the X key" patterns)

11. **Task-specific parameters**: Include a `key_map` in `task_specific` — a flat dictionary mapping each stimulus condition to its correct keyboard key. Also include `trial_timing.max_response_time_ms` if the experiment enforces a response deadline.

## Response Format

Return ONLY valid JSON conforming to the provided schema. No markdown, no explanation, just the JSON object.

## Analysis Strategy

1. Read the HTML to identify the experiment framework and entry point
2. Trace the JavaScript to find trial definition, stimulus rendering, and response handling
3. Identify keyboard event listeners to determine valid response keys
4. Map the experiment's internal state variables to observable DOM/JS state
5. Determine the navigation sequence from page load to first trial
6. Find completion/data-saving logic to set up phase detection and data capture
```

**Step 2: Update analyzer to use URL-based SourceBundle**

Modify `_build_user_message` in `src/experiment_bot/core/analyzer.py`:

```python
def _build_user_message(self, bundle: SourceBundle) -> str:
    parts = [
        f"## Experiment URL: {bundle.url}",
    ]
    if bundle.hint:
        parts.append(f"## User Hint: {bundle.hint}")
    parts.append("")
    parts.append("## Page HTML")
    parts.append(bundle.description_text[:5000])
    parts.append("")

    for filename, content in bundle.source_files.items():
        parts.append(f"## File: {filename}")
        parts.append(content[:30000])
        parts.append("")

    parts.append("## Required Output Schema")
    parts.append(json.dumps(self._schema, indent=2))
    return "\n".join(parts)
```

**Step 3: Update schema.json fully**

Add `data_capture` and `attention_check` to the `runtime.properties` section. Remove the `platform` enum. Make `platform` not required in `task`. These changes were specified in Task 1 step 12 — finalize them here.

**Step 4: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS (tests that reference `bundle.platform` or `bundle.task_id` will need updating)

**Step 5: Update any tests that construct SourceBundle with old fields**

Search for `SourceBundle(platform=` in tests and update to use `url=` instead. Search for tests that check `bundle.platform` and update.

**Step 6: Commit**

```bash
git add src/experiment_bot/prompts/system.md src/experiment_bot/core/analyzer.py src/experiment_bot/prompts/schema.json
git commit -m "feat: rewrite analysis prompt and schema for platform-agnostic operation"
```

---

## Task 4: Config-Driven Phase Detection — Remove Platform Layer

Replace the `Platform` ABC and platform-specific `detect_task_phase` with a single config-driven function. The executor calls this directly instead of going through a platform adapter.

**Files:**
- Create: `src/experiment_bot/core/phase_detection.py`
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_phase_detection.py`
- Delete (later): `src/experiment_bot/platforms/`

**Step 1: Write failing test for standalone phase detection**

```python
# tests/test_phase_detection.py
import pytest
from unittest.mock import AsyncMock

from experiment_bot.core.phase_detection import detect_phase
from experiment_bot.core.config import PhaseDetectionConfig, TaskPhase


@pytest.mark.asyncio
async def test_detect_phase_complete():
    page = AsyncMock()
    # Simulate: complete expression returns True
    page.evaluate_handle = AsyncMock()

    config = PhaseDetectionConfig(
        complete="document.querySelector('#done') !== null",
        test="true",
    )
    # We need to mock page.evaluate to return True for the complete check
    async def mock_evaluate(js):
        if "complete" in str(config.complete) and config.complete in js:
            return True
        return False
    page.evaluate = AsyncMock(side_effect=mock_evaluate)

    result = await detect_phase(page, config)
    assert result == TaskPhase.COMPLETE


@pytest.mark.asyncio
async def test_detect_phase_fallback_to_test():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)

    config = PhaseDetectionConfig(
        complete="false",
        test="true",
    )
    result = await detect_phase(page, config)
    assert result == TaskPhase.TEST


@pytest.mark.asyncio
async def test_detect_phase_no_config():
    page = AsyncMock()
    config = PhaseDetectionConfig()  # All defaults — test="true"
    result = await detect_phase(page, config)
    assert result == TaskPhase.TEST
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase_detection.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement standalone phase detection**

Create `src/experiment_bot/core/phase_detection.py`:

```python
from __future__ import annotations

import logging

from playwright.async_api import Page

from experiment_bot.core.config import PhaseDetectionConfig, TaskPhase

logger = logging.getLogger(__name__)


async def detect_phase(page: Page, config: PhaseDetectionConfig) -> TaskPhase:
    """Config-driven phase detection. Returns TaskPhase.TEST as default fallback."""
    for phase_name, js_expr in [
        ("complete", config.complete),
        ("loading", config.loading),
        ("instructions", config.instructions),
        ("attention_check", config.attention_check),
        ("feedback", config.feedback),
        ("practice", config.practice),
    ]:
        if js_expr:
            try:
                result = await page.evaluate(
                    f"(() => {{ try {{ return {js_expr}; }} catch(e) {{ return false; }} }})()"
                )
                if result:
                    return TaskPhase(phase_name)
            except Exception:
                # Context destroyed (page navigated away) typically means complete
                return TaskPhase.COMPLETE

    if config.test:
        return TaskPhase.TEST
    return TaskPhase.TEST
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase_detection.py -v`
Expected: PASS

**Step 5: Update executor to use config-driven detection**

In `src/experiment_bot/core/executor.py`:

1. Remove `from experiment_bot.platforms.base import Platform` import
2. Add `from experiment_bot.core.phase_detection import detect_phase`
3. Change `run()` signature: remove `platform: Platform` parameter
4. Replace `await platform.detect_task_phase(page)` with `await detect_phase(page, self._config.runtime.phase_detection)`
5. Remove `platform` argument from `_wait_for_completion` and `_trial_loop`

The `_trial_loop` phase detection line changes from:
```python
phase = await platform.detect_task_phase(page)
```
to:
```python
phase = await detect_phase(page, self._config.runtime.phase_detection)
```

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: Some executor tests may fail due to signature change. Fix them.

**Step 7: Commit**

```bash
git add src/experiment_bot/core/phase_detection.py src/experiment_bot/core/executor.py tests/test_phase_detection.py
git commit -m "feat: config-driven phase detection, remove Platform dependency from executor"
```

---

## Task 5: Config-Driven Data Capture

Replace the platform-specific `PsyToolkitDataCapture` and `ExpFactoryDataCapture` with a single config-driven data capture module.

**Files:**
- Modify: `src/experiment_bot/output/data_capture.py`
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_data_capture.py`

**Step 1: Write failing test for config-driven capture**

```python
# In tests/test_data_capture.py — add or replace tests
import pytest
from unittest.mock import AsyncMock

from experiment_bot.output.data_capture import ConfigDrivenCapture
from experiment_bot.core.config import DataCaptureConfig


@pytest.mark.asyncio
async def test_js_expression_capture():
    config = DataCaptureConfig(
        method="js_expression",
        expression="jsPsych.data.get().csv()",
        format="csv",
    )
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="col1,col2\n1,2\n3,4")

    capturer = ConfigDrivenCapture(config)
    data = await capturer.capture(page)
    assert data == "col1,col2\n1,2\n3,4"


@pytest.mark.asyncio
async def test_button_click_capture():
    config = DataCaptureConfig(
        method="button_click",
        button_selector="input[value='show data']",
        result_selector="#showdata",
        format="tsv",
        wait_ms=500,
    )
    page = AsyncMock()
    button = AsyncMock()
    page.query_selector = AsyncMock(return_value=button)
    page.wait_for_timeout = AsyncMock()
    page.eval_on_selector = AsyncMock(return_value="<table><tr><td>a</td><td>b</td></tr></table>")

    capturer = ConfigDrivenCapture(config)
    data = await capturer.capture(page)
    assert data is not None
    assert "a\tb" in data


@pytest.mark.asyncio
async def test_no_capture_method():
    config = DataCaptureConfig()  # method=""
    capturer = ConfigDrivenCapture(config)
    data = await capturer.capture(AsyncMock())
    assert data is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_capture.py::test_js_expression_capture -v`
Expected: FAIL with `ImportError: cannot import name 'ConfigDrivenCapture'`

**Step 3: Implement ConfigDrivenCapture**

Rewrite `src/experiment_bot/output/data_capture.py`:

```python
from __future__ import annotations

import logging
from html.parser import HTMLParser

from playwright.async_api import Page

from experiment_bot.core.config import DataCaptureConfig

logger = logging.getLogger(__name__)


class _TableParser(HTMLParser):
    """Extract rows from an HTML table as lists of cell text."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag == "td" and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._current_cell is not None and self._current_row is not None:
            self._current_row.append("".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self._rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    @property
    def rows(self) -> list[list[str]]:
        return self._rows


def parse_html_table(html: str) -> str:
    """Convert an HTML table to a TSV string."""
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return ""
    return "\n".join("\t".join(row) for row in parser.rows)


class ConfigDrivenCapture:
    """Captures experiment data using the strategy specified in DataCaptureConfig."""

    def __init__(self, config: DataCaptureConfig):
        self._config = config

    async def capture(self, page: Page) -> str | None:
        if not self._config.method:
            return None

        try:
            if self._config.method == "js_expression":
                return await self._capture_js_expression(page)
            elif self._config.method == "button_click":
                return await self._capture_button_click(page)
            else:
                logger.warning(f"Unknown capture method: {self._config.method}")
                return None
        except Exception:
            logger.warning("Data capture failed", exc_info=True)
            return None

    async def _capture_js_expression(self, page: Page) -> str | None:
        expr = self._config.expression
        result = await page.evaluate(
            f"(() => {{ try {{ return {expr}; }} catch(e) {{ return null; }} }})()"
        )
        return result if isinstance(result, str) else None

    async def _capture_button_click(self, page: Page) -> str | None:
        button = await page.query_selector(self._config.button_selector)
        if not button:
            logger.warning(f"Data button not found: {self._config.button_selector}")
            return None

        await button.click()
        await page.wait_for_timeout(self._config.wait_ms)

        html = await page.eval_on_selector(
            self._config.result_selector, "el => el.innerHTML"
        )
        return parse_html_table(html)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_data_capture.py -v`
Expected: PASS

**Step 5: Update executor to use ConfigDrivenCapture**

In `executor.py`, change `_wait_for_completion`:

```python
async def _wait_for_completion(self, page: Page) -> None:
    """Wait for task completion and capture experiment data."""
    await asyncio.sleep(2.0)

    from experiment_bot.output.data_capture import ConfigDrivenCapture
    capturer = ConfigDrivenCapture(self._config.runtime.data_capture)
    data = await capturer.capture(page)
    if data:
        ext = self._config.runtime.data_capture.format or "csv"
        self._writer.save_task_data(data, f"experiment_data.{ext}")
        logger.info("Experiment data saved")
    else:
        wait_s = self._config.runtime.timing.completion_wait_ms / 1000.0
        logger.info(f"No data captured, waiting {wait_s:.1f}s for platform data save")
        await asyncio.sleep(wait_s)
```

Remove the `get_data_capture` import and the `platform_name` reference.

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/experiment_bot/output/data_capture.py src/experiment_bot/core/executor.py tests/test_data_capture.py
git commit -m "feat: config-driven data capture, remove platform-specific capture classes"
```

---

## Task 6: Generalize Executor — Remove All Platform References

Remove `platform_name`, legacy key mapping, hardcoded attention check selectors, and platform-specific file extensions from the executor.

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Modify: `src/experiment_bot/output/writer.py`
- Test: `tests/test_executor.py`

**Step 1: Remove platform_name from TaskExecutor constructor**

Change:
```python
def __init__(self, config: TaskConfig, platform_name: str, seed=None, headless=False):
```
to:
```python
def __init__(self, config: TaskConfig, seed=None, headless=False):
```

Remove `self._platform_name = platform_name` and all references to `self._platform_name`.

**Step 2: Remove `_resolve_key_mapping_legacy` entirely**

Delete the `_resolve_key_mapping_legacy` method (old lines 68-109). In `_resolve_key_mapping`, change the fallback from calling legacy resolution to returning an empty dict:

```python
@staticmethod
def _resolve_key_mapping(config: TaskConfig) -> dict[str, str]:
    ts = config.task_specific
    if "key_map" in ts:
        return dict(ts["key_map"])
    return {}
```

**Step 3: Use config-driven attention check selectors**

Replace the hardcoded `_handle_attention_check`:

```python
async def _handle_attention_check(self, page: Page) -> None:
    import re
    await asyncio.sleep(1.5)
    ac = self._config.runtime.attention_check
    try:
        # Use config selectors, fall back to generic body text
        selector_js = ac.text_selector or "body"
        text = await page.evaluate(
            f"(() => {{ var el = document.querySelector('{selector_js}'); return el ? el.textContent : ''; }})()"
        )
        key = self._parse_attention_check_key(text)
        if key:
            logger.info(f"Attention check: pressing '{key}'")
            await page.keyboard.press(key)
        else:
            logger.warning(f"Could not parse attention check text: {text[:100]}")
            await page.keyboard.press("Enter")
    except Exception as e:
        logger.warning(f"Attention check handling failed: {e}")
        await page.keyboard.press("Enter")
```

**Step 4: Update `run()` signature — remove Platform parameter**

Change:
```python
async def run(self, task_url: str, platform: Platform) -> None:
```
to:
```python
async def run(self, task_url: str) -> None:
```

Remove `platform` from `_trial_loop` and `_wait_for_completion` calls.

**Step 5: Update OutputWriter to not use platform_name in directory path**

In `output/writer.py`, change the `create_run` signature to accept just `task_name`:

```python
def create_run(self, task_name: str, config: TaskConfig) -> Path:
```

The output directory becomes `output/<task_name>/<timestamp>/` instead of `output/<platform>/<task_name>/<timestamp>/`.

**Step 6: Update all existing tests**

Search for `platform_name=` and `platform=` in test files and update. Run the full suite.

**Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS after fixing test fixtures

**Step 8: Commit**

```bash
git add src/experiment_bot/core/executor.py src/experiment_bot/output/writer.py tests/
git commit -m "refactor: remove platform_name, legacy key mapping, hardcoded selectors from executor"
```

---

## Task 7: URL-Based CLI and Cache

Replace the platform subcommands with a single `run` command. Change the cache key from `platform/task_id` to URL hash.

**Files:**
- Modify: `src/experiment_bot/cli.py`
- Modify: `src/experiment_bot/core/cache.py`
- Test: `tests/test_cli.py`, `tests/test_cache.py`

**Step 1: Write failing test for URL-based cache**

```python
# In tests/test_cache.py — add test
import hashlib

def test_cache_url_key():
    from experiment_bot.core.cache import ConfigCache
    cache = ConfigCache()
    url = "https://example.com/experiment/"
    expected_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = cache._config_path(url)
    assert expected_hash in str(path)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache.py::test_cache_url_key -v`
Expected: FAIL — `_config_path` still takes `platform, task_id`

**Step 3: Update cache to URL-based**

Rewrite `src/experiment_bot/core/cache.py`:

```python
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from experiment_bot.core.config import TaskConfig

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "cache"


class ConfigCache:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self._cache_dir = cache_dir

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _config_path(self, url: str, label: str = "") -> Path:
        key = label if label else self._url_hash(url)
        return self._cache_dir / key / "config.json"

    def load(self, url: str, label: str = "") -> TaskConfig | None:
        path = self._config_path(url, label)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TaskConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load cached config: {e}")
            return None

    def save(self, url: str, config: TaskConfig, label: str = "") -> None:
        path = self._config_path(url, label)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config.to_dict(), indent=2))
```

**Step 4: Run cache tests**

Run: `uv run pytest tests/test_cache.py -v`
Expected: PASS (after updating any tests that use old `platform/task_id` API)

**Step 5: Rewrite CLI**

Replace `src/experiment_bot/cli.py` entirely with a single `run` command:

```python
from __future__ import annotations

import asyncio
import logging
import os

import click


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def _run_task(
    url: str,
    hint: str,
    label: str,
    headless: bool,
    regenerate: bool,
    rt_mean: float | None,
    accuracy: float | None,
) -> None:
    from anthropic import AsyncAnthropic

    from experiment_bot.core.analyzer import Analyzer
    from experiment_bot.core.cache import ConfigCache
    from experiment_bot.core.executor import TaskExecutor
    from experiment_bot.core.scraper import scrape_experiment_source

    cache = ConfigCache()
    config = None if regenerate else cache.load(url, label)

    if config is None:
        click.echo(f"Scraping source from {url}...")
        bundle = await scrape_experiment_source(url=url, hint=hint)

        click.echo("Analyzing task with Claude...")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise click.ClickException("ANTHROPIC_API_KEY environment variable not set")

        client = AsyncAnthropic(api_key=api_key)
        analyzer = Analyzer(client=client)
        config = await analyzer.analyze(bundle)

        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

        cache.save(url, config, label)
        click.echo("Config generated and cached.")
    else:
        click.echo(f"Using cached config.")
        if rt_mean is not None:
            for dist in config.response_distributions.values():
                dist.params["mu"] = rt_mean
        if accuracy is not None:
            config.performance.go_accuracy = accuracy

    import numpy as np
    from experiment_bot.core.distributions import jitter_distributions
    config = jitter_distributions(config, np.random.default_rng())
    click.echo("Applied between-subject parameter jitter")

    click.echo(f"Running task at {url}")
    executor = TaskExecutor(config, headless=headless)
    await executor.run(url)
    click.echo("Done!")


@click.command()
@click.argument("url")
@click.option("--hint", default="", help="Hint about the task (e.g., 'stop signal task')")
@click.option("--label", default="", help="Cache label (default: URL hash)")
@click.option("--headless", is_flag=True, default=False, help="Run browser in headless mode")
@click.option("--regenerate-config", is_flag=True, default=False, help="Force regenerate config")
@click.option("--rt-mean", type=float, default=None, help="Override mean RT (mu) in ms")
@click.option("--accuracy", type=float, default=None, help="Override go accuracy (0-1)")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def main(url: str, hint: str, label: str, headless: bool, regenerate_config: bool, rt_mean: float | None, accuracy: float | None, verbose: bool):
    """experiment-bot: Execute human-like behavior on web-based cognitive tasks.

    URL is the experiment page to complete.
    """
    _setup_logging(verbose)
    asyncio.run(_run_task(url, hint, label, headless, regenerate_config, rt_mean, accuracy))
```

Note: `main` changes from a `@click.group()` to a `@click.command()`. The URL is a positional argument.

**Step 6: Update CLI tests**

Update `tests/test_cli.py` to test the new single-command interface.

**Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS

**Step 8: Commit**

```bash
git add src/experiment_bot/cli.py src/experiment_bot/core/cache.py tests/test_cli.py tests/test_cache.py
git commit -m "feat: URL-based CLI and cache, single run command replaces platform subcommands"
```

---

## Task 8: Delete Platform Layer

Remove the entire `platforms/` directory and its remaining references.

**Files:**
- Delete: `src/experiment_bot/platforms/base.py`
- Delete: `src/experiment_bot/platforms/expfactory.py`
- Delete: `src/experiment_bot/platforms/psytoolkit.py`
- Delete: `src/experiment_bot/platforms/registry.py`
- Delete: `src/experiment_bot/platforms/__init__.py`
- Delete: `tests/test_platforms_base.py`
- Delete: `tests/test_expfactory.py`
- Delete: `tests/test_psytoolkit.py`
- Modify: any remaining imports

**Step 1: Search for remaining platform imports**

```bash
grep -r "from experiment_bot.platforms" src/ tests/
grep -r "import experiment_bot.platforms" src/ tests/
grep -r "platform_name" src/ tests/
```

Fix any remaining references.

**Step 2: Delete the platforms directory**

```bash
rm -rf src/experiment_bot/platforms/
rm -f tests/test_platforms_base.py tests/test_expfactory.py tests/test_psytoolkit.py
```

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS with no import errors

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: delete platform layer — all behavior is now config-driven"
```

---

## Task 9: Update Scripts

Make `launch.sh` and `check_data.py` work with the new URL-based CLI.

**Files:**
- Modify: `scripts/launch.sh`
- Modify: `scripts/check_data.py`

**Step 1: Update launch.sh**

Replace the hardcoded platform:task registry with a URL-based approach:

```bash
# New usage:
# ./scripts/launch.sh --url "https://deploy.expfactory.org/preview/9/" --count 3 --headless
# ./scripts/launch.sh --url "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html" --count 5
```

Accept `--url` and `--hint` instead of `--platform` and `--task`. The launch command becomes:
```bash
uv run experiment-bot "$URL" --hint "$HINT" $HEADLESS_FLAG
```

**Step 2: Generalize check_data.py**

Remove the hardcoded `STOP_SIGNAL_NAMES` and `TASK_SWITCHING_NAMES` sets. Instead:
- Walk `output/` for any task directories
- Attempt to load `config.json` from each session to determine task type from `task.constructs` or `task.name`
- Use the config's `data_capture.format` field to determine file extension
- Fall back to auto-detecting CSV vs TSV

**Step 3: Test the scripts**

Manually verify with existing output data. Since these are standalone scripts, unit testing is less critical than end-to-end verification.

**Step 4: Commit**

```bash
git add scripts/launch.sh scripts/check_data.py
git commit -m "refactor: update scripts for URL-based CLI interface"
```

---

## Task 10: Update and Add Tests

Ensure comprehensive test coverage for the new generic architecture.

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `tests/test_executor.py`
- Modify: `tests/test_navigator.py`
- Modify: `tests/test_stuck.py`
- Create: `tests/test_integration_generic.py`

**Step 1: Write integration test for full generic pipeline**

```python
# tests/test_integration_generic.py
import pytest
from experiment_bot.core.config import (
    TaskConfig, TaskMetadata, StimulusConfig, DetectionConfig,
    ResponseConfig, DistributionConfig, PerformanceConfig,
    NavigationConfig, RuntimeConfig, PhaseDetectionConfig,
    TimingConfig, DataCaptureConfig, AttentionCheckConfig,
)


def test_generic_config_round_trip():
    """A config with no platform field round-trips through JSON."""
    config = TaskConfig(
        task=TaskMetadata(name="Test Task", constructs=["inhibition"], reference_literature=["Test 2024"]),
        stimuli=[
            StimulusConfig(
                id="go",
                description="Go stimulus",
                detection=DetectionConfig(method="js_eval", selector="window.stimulus === 'go'"),
                response=ResponseConfig(key="f", condition="go"),
            )
        ],
        response_distributions={"go_correct": DistributionConfig("ex_gaussian", {"mu": 450, "sigma": 60, "tau": 80})},
        performance=PerformanceConfig(go_accuracy=0.95, stop_accuracy=0.0, omission_rate=0.02, practice_accuracy=0.9),
        navigation=NavigationConfig(phases=[]),
        runtime=RuntimeConfig(
            phase_detection=PhaseDetectionConfig(complete="document.querySelector('#done') !== null"),
            data_capture=DataCaptureConfig(method="js_expression", expression="getData()", format="csv"),
            attention_check=AttentionCheckConfig(text_selector="#attention-text"),
        ),
    )
    d = config.to_dict()
    restored = TaskConfig.from_dict(d)
    assert restored.task.name == "Test Task"
    assert restored.task.platform == ""
    assert restored.runtime.data_capture.method == "js_expression"
    assert restored.runtime.attention_check.text_selector == "#attention-text"
```

**Step 2: Fix any remaining broken tests**

Run: `uv run pytest -v`
Fix any failures by removing references to deleted platform code.

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: update test suite for platform-agnostic architecture"
```

---

## Task 11: Clean Up Cache and Documentation

Remove stale cached configs (they reference the old platform-based schema) and update the README.

**Files:**
- Delete: `cache/expfactory/` and `cache/psytoolkit/` directories
- Modify: `README.md` (if it exists)

**Step 1: Remove stale cache files**

```bash
rm -rf cache/expfactory cache/psytoolkit
```

New caches will be generated on first run with the updated schema.

**Step 2: Update README usage examples**

Old:
```bash
experiment-bot expfactory --task 9
experiment-bot psytoolkit --task stopsignal
```

New:
```bash
experiment-bot "https://deploy.expfactory.org/preview/9/"
experiment-bot "https://www.psytoolkit.org/experiment-library/experiment_stopsignal.html" --hint "stop signal task"
experiment-bot "https://example.com/my-experiment/" --label my_experiment --headless
```

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove stale platform-based cache, update docs for URL-based interface"
```

---

## Summary: New Pipeline

```
experiment-bot <URL> [--hint "..."] [--label "..."] [--headless]
    |
    v
  Cache check (by URL hash or --label)
    |
    +-- HIT: load TaskConfig from cache/<hash>/config.json
    |
    +-- MISS:
        +-- scraper.py: HTTP GET URL -> HTML + linked JS/CSS
        +-- analyzer.py: Claude Opus -> TaskConfig JSON (platform-agnostic prompt)
        +-- cache.save()
    |
    v
  jitter_distributions() -- per-session variability
    |
    v
  TaskExecutor.run(URL)
    +-- Launch Playwright -> navigate to URL
    +-- InstructionNavigator -> config.navigation.phases
    +-- Trial loop:
    |   +-- detect_phase() -- config.runtime.phase_detection JS expressions
    |   +-- StimulusLookup.identify() -- config.stimuli detection rules
    |   +-- ResponseSampler -- config.response_distributions
    |   +-- page.keyboard.press()
    +-- ConfigDrivenCapture -- config.runtime.data_capture
    +-- OutputWriter -> output/<task_name>/<timestamp>/
```

**Key invariant preserved:** Zero Claude API calls during trial execution. All inference happens once at analysis time and is cached.

**What the user provides:** A URL. Optionally a hint and a cache label.

**What Claude infers:** Task type, stimuli, responses, navigation, phase detection, timing, data capture — everything.

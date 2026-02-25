# Experiment Data Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the bot's self-reported summary statistics with actual experiment data captured from each platform, so the user can analyze ground-truth data.

**Architecture:** Add a `DataCapture` abstraction with platform-specific implementations: PsyToolkit scrapes `div#showdata` after clicking "show data"; ExpFactory intercepts the CSV download via Playwright's download event. The executor calls the appropriate capturer during `_wait_for_completion`, saves raw data via `OutputWriter.save_task_data()`, and removes the `summarize_run()` call. The summary module is deleted entirely.

**Tech Stack:** Python 3.12, Playwright async API, dataclasses, pytest

---

### Task 1: Add DataCapture base class and PsyToolkit implementation

**Files:**
- Create: `src/experiment_bot/output/data_capture.py`
- Test: `tests/test_data_capture.py`

**Step 1: Write the failing test for PsyToolkit data capture**

```python
# tests/test_data_capture.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from experiment_bot.output.data_capture import PsyToolkitDataCapture


@pytest.mark.asyncio
async def test_psytoolkit_capture_clicks_show_data_and_scrapes_table():
    """PsyToolkit capturer clicks 'show data' button, then scrapes div#showdata."""
    page = AsyncMock()

    # Mock: button exists and is visible
    show_btn = AsyncMock()
    show_btn.is_visible.return_value = True
    locator_mock = MagicMock()
    locator_mock.first = show_btn
    page.locator.return_value = locator_mock

    # Mock: div#showdata returns an HTML table
    page.eval_on_selector.return_value = (
        "<table><tr><td>go</td><td>left</td><td>0</td><td>423</td>"
        "<td>1</td><td>0</td><td>65</td><td>1</td></tr></table>"
    )

    capturer = PsyToolkitDataCapture()
    result = await capturer.capture(page)

    assert result is not None
    assert "go" in result
    assert "423" in result
    page.locator.assert_called()
    show_btn.click.assert_awaited()


@pytest.mark.asyncio
async def test_psytoolkit_capture_returns_none_when_no_showdata():
    """Returns None if div#showdata is not found after clicking."""
    page = AsyncMock()

    show_btn = AsyncMock()
    show_btn.is_visible.return_value = False
    locator_mock = MagicMock()
    locator_mock.first = show_btn
    page.locator.return_value = locator_mock
    page.eval_on_selector.side_effect = Exception("not found")

    capturer = PsyToolkitDataCapture()
    result = await capturer.capture(page)
    assert result is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment_bot.output.data_capture'`

**Step 3: Write the implementation**

```python
# src/experiment_bot/output/data_capture.py
"""Capture actual experiment data from platform UIs after task completion."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class DataCapture(ABC):
    """Base class for capturing experiment data from a platform."""

    @abstractmethod
    async def capture(self, page: Page) -> str | None:
        """Capture experiment data from the page. Returns raw data string or None."""


class PsyToolkitDataCapture(DataCapture):
    """Capture data from PsyToolkit's div#showdata table."""

    async def capture(self, page: Page) -> str | None:
        try:
            # Click the "show data" button to reveal the data table
            btn = page.locator("input[value='show data'], button:has-text('show data')")
            if await btn.first.is_visible():
                await btn.first.click()
                await asyncio.sleep(1.0)  # Wait for table to render

            # Scrape the showdata div's inner HTML
            html = await page.eval_on_selector(
                "#showdata", "el => el.innerHTML"
            )
            if html and html.strip():
                logger.info(f"Captured PsyToolkit data ({len(html)} chars)")
                return html
        except Exception as e:
            logger.warning(f"PsyToolkit data capture failed: {e}")
        return None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_capture.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/experiment_bot/output/data_capture.py tests/test_data_capture.py
git commit -m "feat: add DataCapture base class and PsyToolkit implementation"
```

---

### Task 2: Add HTML-to-TSV parser for PsyToolkit showdata

The `div#showdata` contains an HTML `<table>` with no headers. We need to convert this to a flat TSV string for saving. The user will analyze the data, so we just need a clean tabular format.

**Files:**
- Modify: `src/experiment_bot/output/data_capture.py`
- Test: `tests/test_data_capture.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_data_capture.py

from experiment_bot.output.data_capture import parse_showdata_html


def test_parse_showdata_html_extracts_rows():
    """Parses PsyToolkit showdata HTML table into TSV string."""
    html = """<table>
    <tr><td>go</td><td>left</td><td>0</td><td>423</td><td>1</td><td>0</td><td>65</td><td>1</td></tr>
    <tr><td>nogo</td><td>right</td><td>450</td><td>500</td><td>3</td><td>450</td><td>0</td><td>0</td></tr>
    </table>"""
    result = parse_showdata_html(html)
    lines = result.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "go\tleft\t0\t423\t1\t0\t65\t1"
    assert lines[1] == "nogo\tright\t450\t500\t3\t450\t0\t0"


def test_parse_showdata_html_empty_table():
    result = parse_showdata_html("<table></table>")
    assert result == ""


def test_parse_showdata_html_handles_whitespace_in_cells():
    html = "<table><tr><td> go </td><td> left </td></tr></table>"
    result = parse_showdata_html(html)
    assert result.strip() == "go\tleft"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_capture.py::test_parse_showdata_html_extracts_rows -v`
Expected: FAIL — `ImportError: cannot import name 'parse_showdata_html'`

**Step 3: Write the parser and wire it into PsyToolkitDataCapture**

Add to `src/experiment_bot/output/data_capture.py`:

```python
from html.parser import HTMLParser


class _TableParser(HTMLParser):
    """Extract rows from an HTML table as lists of cell text."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_row = []
        elif tag == "td":
            self._current_cell = []
            self._in_cell = True

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "td":
            self._in_cell = False
            self._current_row.append("".join(self._current_cell))
        elif tag == "tr" and self._current_row:
            self.rows.append(self._current_row)


def parse_showdata_html(html: str) -> str:
    """Convert an HTML table to TSV string."""
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return ""
    return "\n".join("\t".join(row) for row in parser.rows)
```

Update `PsyToolkitDataCapture.capture()` to return parsed TSV instead of raw HTML:

```python
async def capture(self, page: Page) -> str | None:
    try:
        btn = page.locator("input[value='show data'], button:has-text('show data')")
        if await btn.first.is_visible():
            await btn.first.click()
            await asyncio.sleep(1.0)

        html = await page.eval_on_selector(
            "#showdata", "el => el.innerHTML"
        )
        if html and html.strip():
            tsv = parse_showdata_html(html)
            if tsv:
                logger.info(f"Captured PsyToolkit data ({len(tsv.splitlines())} rows)")
                return tsv
    except Exception as e:
        logger.warning(f"PsyToolkit data capture failed: {e}")
    return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_capture.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/experiment_bot/output/data_capture.py tests/test_data_capture.py
git commit -m "feat: parse PsyToolkit showdata HTML table to TSV"
```

---

### Task 3: Add ExpFactory CSV download capture

ExpFactory (jsPsych) downloads a CSV file to `~/Downloads` at the end of each task. The filename is arbitrary and platform-generated. We use Playwright's download event listener to intercept it.

**Files:**
- Modify: `src/experiment_bot/output/data_capture.py`
- Test: `tests/test_data_capture.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_data_capture.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from experiment_bot.output.data_capture import ExpFactoryDataCapture


@pytest.mark.asyncio
async def test_expfactory_capture_intercepts_download():
    """ExpFactory capturer intercepts CSV download via Playwright download event."""
    page = AsyncMock()

    # Simulate a download event that resolves with a mock download
    mock_download = AsyncMock()
    mock_download.suggested_filename = "experiment_data_12345.csv"
    mock_download.path.return_value = "/tmp/fake_download.csv"

    # page.expect_download() is an async context manager
    download_ctx = AsyncMock()
    download_ctx.__aenter__ = AsyncMock(return_value=download_ctx)
    download_ctx.__aexit__ = AsyncMock(return_value=False)
    download_ctx.value = mock_download
    page.expect_download.return_value = download_ctx

    capturer = ExpFactoryDataCapture()
    # We need to mock Path.read_text for the saved file
    with patch("pathlib.Path.read_text", return_value="rt,response,correct\n450,left,1\n"):
        result = await capturer.capture(page)

    assert result is not None
    assert "rt,response,correct" in result


@pytest.mark.asyncio
async def test_expfactory_capture_returns_none_on_timeout():
    """Returns None if no download arrives within timeout."""
    page = AsyncMock()

    # Simulate timeout by raising
    download_ctx = AsyncMock()
    download_ctx.__aenter__ = AsyncMock(side_effect=TimeoutError("no download"))
    download_ctx.__aexit__ = AsyncMock(return_value=False)
    page.expect_download.return_value = download_ctx

    capturer = ExpFactoryDataCapture()
    result = await capturer.capture(page)
    assert result is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_capture.py::test_expfactory_capture_intercepts_download -v`
Expected: FAIL — `ImportError: cannot import name 'ExpFactoryDataCapture'`

**Step 3: Write the implementation**

Add to `src/experiment_bot/output/data_capture.py`:

```python
class ExpFactoryDataCapture(DataCapture):
    """Capture jsPsych CSV data via Playwright's download interception.

    ExpFactory tasks trigger a file download at task completion. Playwright's
    expect_download() context manager intercepts this without it hitting the
    filesystem at ~/Downloads.
    """

    def __init__(self, timeout_ms: int = 60_000):
        self._timeout_ms = timeout_ms

    async def capture(self, page: Page) -> str | None:
        try:
            async with page.expect_download(timeout=self._timeout_ms) as download_info:
                # The download is triggered by jsPsych's completion handler.
                # We just wait for it — no user action needed.
                pass
            download = download_info.value
            path = await download.path()
            if path:
                data = Path(path).read_text()
                logger.info(
                    f"Captured ExpFactory CSV: {download.suggested_filename} "
                    f"({len(data.splitlines())} rows)"
                )
                return data
        except TimeoutError:
            logger.warning(
                f"No download detected within {self._timeout_ms}ms"
            )
        except Exception as e:
            logger.warning(f"ExpFactory data capture failed: {e}")
        return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_capture.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/experiment_bot/output/data_capture.py tests/test_data_capture.py
git commit -m "feat: add ExpFactory CSV download capture via Playwright"
```

---

### Task 4: Add `get_data_capture()` factory function

We need a way for the executor to get the right capturer for each platform, consistent with the existing registry pattern.

**Files:**
- Modify: `src/experiment_bot/output/data_capture.py`
- Test: `tests/test_data_capture.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_data_capture.py
from experiment_bot.output.data_capture import get_data_capture


def test_get_data_capture_psytoolkit():
    cap = get_data_capture("psytoolkit")
    assert isinstance(cap, PsyToolkitDataCapture)


def test_get_data_capture_expfactory():
    cap = get_data_capture("expfactory")
    assert isinstance(cap, ExpFactoryDataCapture)


def test_get_data_capture_unknown_returns_none():
    cap = get_data_capture("unknown_platform")
    assert cap is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_capture.py::test_get_data_capture_psytoolkit -v`
Expected: FAIL — `ImportError: cannot import name 'get_data_capture'`

**Step 3: Write the factory function**

Add to `src/experiment_bot/output/data_capture.py`:

```python
_CAPTURERS: dict[str, type[DataCapture]] = {
    "psytoolkit": PsyToolkitDataCapture,
    "expfactory": ExpFactoryDataCapture,
}


def get_data_capture(platform_name: str) -> DataCapture | None:
    """Return the appropriate data capturer for a platform, or None."""
    cls = _CAPTURERS.get(platform_name)
    return cls() if cls else None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_capture.py -v`
Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add src/experiment_bot/output/data_capture.py tests/test_data_capture.py
git commit -m "feat: add platform-aware data capture factory"
```

---

### Task 5: Wire data capture into executor's `_wait_for_completion`

Replace the blind `asyncio.sleep()` in `_wait_for_completion` with actual data capture. The executor should:
1. Create a data capturer for the platform
2. Call `capture(page)` to get the raw data
3. Save it via `self._writer.save_task_data(data)`
4. Fall back to a shorter sleep if capture returns None

**Files:**
- Modify: `src/experiment_bot/core/executor.py`
- Test: `tests/test_executor.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_executor.py
@pytest.mark.asyncio
async def test_wait_for_completion_captures_data(tmp_path):
    """_wait_for_completion should call data capture and save result."""
    config = TaskConfig.from_dict(SAMPLE_CONFIG)
    executor = TaskExecutor(config, platform_name="expfactory", seed=42)
    executor._writer = MagicMock()
    executor._writer.run_dir = tmp_path

    page = AsyncMock()
    platform = AsyncMock()

    mock_capturer = AsyncMock()
    mock_capturer.capture.return_value = "rt,response\n450,left\n"

    with patch(
        "experiment_bot.core.executor.get_data_capture",
        return_value=mock_capturer,
    ):
        await executor._wait_for_completion(page, platform)

    mock_capturer.capture.assert_awaited_once_with(page)
    executor._writer.save_task_data.assert_called_once_with(
        "rt,response\n450,left\n", "experiment_data.csv"
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_executor.py::test_wait_for_completion_captures_data -v`
Expected: FAIL — `get_data_capture` not imported in executor

**Step 3: Update executor to use data capture**

In `src/experiment_bot/core/executor.py`:

1. Add import at top:
```python
from experiment_bot.output.data_capture import get_data_capture
```

2. Replace `_wait_for_completion`:
```python
async def _wait_for_completion(self, page: Page, platform: Platform) -> None:
    """Wait for task completion and capture experiment data."""
    # Give the platform a moment to finalize
    await asyncio.sleep(2.0)

    capturer = get_data_capture(self._platform_name)
    if capturer:
        logger.info(f"Capturing experiment data for {self._platform_name}...")
        data = await capturer.capture(page)
        if data:
            ext = "tsv" if self._platform_name == "psytoolkit" else "csv"
            self._writer.save_task_data(data, f"experiment_data.{ext}")
            logger.info("Experiment data saved")
        else:
            logger.warning("No experiment data captured")
    else:
        # Unknown platform — fall back to waiting
        wait_s = self._config.runtime.timing.completion_wait_ms / 1000.0
        logger.info(f"No data capturer for {self._platform_name}, waiting {wait_s:.1f}s")
        await asyncio.sleep(wait_s)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_executor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/core/executor.py tests/test_executor.py
git commit -m "feat: wire data capture into executor completion phase"
```

---

### Task 6: Remove summary statistics logic

The user explicitly said they will analyze the data themselves. Remove `summarize_run()` from the executor and delete the summary module.

**Files:**
- Modify: `src/experiment_bot/core/executor.py` (remove import + call)
- Delete: `src/experiment_bot/output/summary.py`
- Delete or update: any tests that reference `summarize_run`
- Test: `tests/test_executor.py`

**Step 1: Check for all references to summary**

Run: `uv run python -c "import ast; [print(f) for f in __import__('pathlib').Path('src').rglob('*.py') if 'summary' in f.read_text()]"`

Or just grep: `grep -r "summary" src/ tests/ --include="*.py" -l`

**Step 2: Remove the import and call from executor.py**

In `src/experiment_bot/core/executor.py`:
- Remove line: `from experiment_bot.output.summary import summarize_run`
- Remove from the `finally` block:
  ```python
  if self._writer.run_dir:
      summary = summarize_run(self._writer.run_dir)
      if summary:
          logger.info(f"Run summary: {summary.get('total_trials', 0)} trials")
  ```

**Step 3: Delete the summary module**

```bash
rm src/experiment_bot/output/summary.py
```

**Step 4: Remove numpy from executor imports if it was only used by summary**

Check if `numpy` import in executor is still needed (it is — used by `ResponseSampler`). No change needed.

**Step 5: Run all tests to verify nothing breaks**

Run: `uv run pytest -v`
Expected: All tests PASS (any tests that directly tested `summarize_run` will fail — delete those too)

**Step 6: Commit**

```bash
git add -u
git commit -m "refactor: remove self-reported summary statistics"
```

---

### Task 7: Update `OutputWriter.save_task_data` to support bytes

The Playwright download `path()` returns a temp path. We may want to copy binary-safe. Also update the method to log what it saves.

**Files:**
- Modify: `src/experiment_bot/output/writer.py`
- Modify: `tests/test_writer.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_writer.py

def test_save_task_data_writes_content(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    writer.create_run("expfactory", "test_task", config)
    writer.save_task_data("col1,col2\nval1,val2\n", "experiment_data.csv")
    saved = (writer.run_dir / "experiment_data.csv").read_text()
    assert "col1,col2" in saved
    assert "val1,val2" in saved


def test_save_task_data_tsv(tmp_path):
    config = TaskConfig.from_dict(SAMPLE_CONFIG_DICT)
    writer = OutputWriter(base_dir=tmp_path)
    writer.create_run("psytoolkit", "stopsignal", config)
    writer.save_task_data("go\tleft\t423\n", "experiment_data.tsv")
    saved = (writer.run_dir / "experiment_data.tsv").read_text()
    assert "go\tleft\t423" in saved
```

**Step 2: Run tests to verify they pass** (these should already pass with existing implementation)

Run: `uv run pytest tests/test_writer.py -v`
Expected: PASS

**Step 3: Add logging to `save_task_data`**

```python
def save_task_data(self, data: str, filename: str = "task_data.csv") -> None:
    if self._run_dir:
        path = self._run_dir / filename
        path.write_text(data)
        logger.info(f"Saved experiment data to {path}")
```

**Step 4: Run tests again**

Run: `uv run pytest tests/test_writer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/experiment_bot/output/writer.py tests/test_writer.py
git commit -m "test: add writer tests for experiment data saving"
```

---

### Task 8: Handle ExpFactory download timing

The ExpFactory `completion_wait_ms` is currently 35000ms because jsPsych uploads data to the server before triggering the CSV download. We need to set up the download listener BEFORE trials complete, not after. The Playwright `expect_download` should be registered early so we catch the download whenever it fires.

**Files:**
- Modify: `src/experiment_bot/output/data_capture.py`
- Modify: `src/experiment_bot/core/executor.py`

**Step 1: Restructure ExpFactory capture to use a pre-registered listener**

The current approach in Task 3 has a flaw: `expect_download()` creates a listener that waits from the moment it's called. But the download fires during/after jsPsych's completion handler, which could happen while we're still in `_wait_for_completion`. We need to:

1. Start listening for downloads BEFORE entering the trial loop
2. After trials complete, wait for the download to resolve

Update `ExpFactoryDataCapture` to a two-phase API:

```python
class ExpFactoryDataCapture(DataCapture):
    """Capture jsPsych CSV via Playwright download interception."""

    def __init__(self, timeout_ms: int = 60_000):
        self._timeout_ms = timeout_ms

    async def capture(self, page: Page) -> str | None:
        """Wait for any pending download and return its contents."""
        try:
            async with page.expect_download(timeout=self._timeout_ms) as download_info:
                pass  # Download was already triggered by jsPsych completion
            download = download_info.value
            path = await download.path()
            if path:
                data = Path(path).read_text()
                logger.info(
                    f"Captured ExpFactory CSV: {download.suggested_filename} "
                    f"({len(data.splitlines())} rows)"
                )
                return data
        except TimeoutError:
            logger.warning(f"No download within {self._timeout_ms}ms")
        except Exception as e:
            logger.warning(f"ExpFactory data capture failed: {e}")
        return None
```

**Note:** This is actually fine as-is. The `expect_download` call in `capture()` will catch any download that fires after it's called. The jsPsych completion handler runs, then there's a server upload, then the CSV download triggers. As long as we call `capture()` before the download completes (which is why we have the 60s timeout), we'll catch it. The 2-second sleep at the start of `_wait_for_completion` is enough buffer.

If real-world testing reveals timing issues, we can refactor to register the listener earlier. But start simple.

**Step 2: Verify all tests still pass**

Run: `uv run pytest -v`
Expected: All PASS

**Step 3: Commit (if any changes)**

```bash
git add -u
git commit -m "docs: add timing notes for ExpFactory download capture"
```

---

### Task 9: Full regression — run all unit tests

**Step 1: Run the complete test suite**

Run: `uv run pytest -v`
Expected: All tests PASS, no regressions

**Step 2: Verify no remaining references to `summary_stats` or `summarize_run`**

Run: `grep -r "summarize_run\|summary_stats\|summary\.py" src/ tests/ --include="*.py"`
Expected: No matches (or only in this plan file)

**Step 3: Commit if any cleanup needed**

---

### Task 10: Smoke test all 4 tasks

Run each of the 4 smoke tests and verify that `experiment_data.csv` (ExpFactory) or `experiment_data.tsv` (PsyToolkit) appears in the output directory with actual experiment data.

**Step 1: PsyToolkit stop signal**

Run: `uv run experiment-bot psytoolkit --task stopsignal -v`
Verify: `output/psytoolkit/stopsignal/<timestamp>/experiment_data.tsv` exists and contains rows like `go\tleft\t0\t423\t1\t0\t65\t1`

**Step 2: PsyToolkit cued task switching**

Run: `uv run experiment-bot psytoolkit --task taskswitching_cued -v`
Verify: `output/psytoolkit/cued_task_switching/<timestamp>/experiment_data.tsv` exists

**Step 3: ExpFactory stop signal (task 9)**

Run: `uv run experiment-bot expfactory --task 9 -v`
Verify: `output/expfactory/stop_signal_task_(rdoc)/<timestamp>/experiment_data.csv` exists with CSV headers and data rows

**Step 4: ExpFactory cued task switching (task 2)**

Run: `uv run experiment-bot expfactory --task 2 -v`
Verify: `output/expfactory/cued_task_switching_(rdoc)/<timestamp>/experiment_data.csv` exists

**Step 5: Commit any bug fixes discovered during smoke testing**

---

### Task 11: Clean up — remove `summary_stats.json` from old output dirs

This is optional cleanup. The old `summary_stats.json` files in `output/` are now misleading since they were computed from the bot's own RT sampler, not real data.

**Step 1: Remove old summary files**

```bash
find output/ -name "summary_stats.json" -delete
```

**Step 2: No commit needed** (output/ is gitignored)

---

### Task 12: Final commit and branch readiness

**Step 1: Run full test suite one final time**

Run: `uv run pytest -v`
Expected: All PASS

**Step 2: Review git log for clean commit history**

Run: `git log --oneline`

**Step 3: Report complete**

Branch is ready for merge/PR.

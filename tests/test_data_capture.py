from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.output.data_capture import (
    DataCapture,
    ExpFactoryDataCapture,
    PsyToolkitDataCapture,
    get_data_capture,
    parse_showdata_html,
)


# ---------------------------------------------------------------------------
# Task 1 — PsyToolkitDataCapture
# ---------------------------------------------------------------------------


async def test_psytoolkit_capture_success():
    """Button visible, clicks it, scrapes table, returns TSV."""
    page = AsyncMock()

    # Simulate the button being found and clicked
    button = AsyncMock()
    page.query_selector.return_value = button

    # After clicking, eval_on_selector returns a simple HTML table
    page.eval_on_selector.return_value = (
        "<table>"
        "<tr><td>go</td><td>left</td><td>423</td></tr>"
        "<tr><td>stop</td><td>right</td><td>0</td></tr>"
        "</table>"
    )

    cap = PsyToolkitDataCapture()
    result = await cap.capture(page)

    # Should have queried for the button
    page.query_selector.assert_called_once_with(
        "input[value='show data'], button:has-text('show data')"
    )
    button.click.assert_awaited_once()

    # Result should be TSV (parsed from HTML)
    assert result is not None
    lines = result.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "go\tleft\t423"
    assert lines[1] == "stop\tright\t0"


async def test_psytoolkit_capture_no_button():
    """Button not visible -> returns None."""
    page = AsyncMock()
    page.query_selector.return_value = None

    cap = PsyToolkitDataCapture()
    result = await cap.capture(page)

    assert result is None


async def test_psytoolkit_capture_no_showdata_div():
    """Button exists but div#showdata not found -> returns None."""
    page = AsyncMock()
    button = AsyncMock()
    page.query_selector.return_value = button
    page.eval_on_selector.side_effect = Exception("Element not found")

    cap = PsyToolkitDataCapture()
    result = await cap.capture(page)

    assert result is None


# ---------------------------------------------------------------------------
# Task 2 — parse_showdata_html
# ---------------------------------------------------------------------------


def test_parse_showdata_html_extracts_rows():
    """2-row table -> 2-line TSV."""
    html = (
        "<table>"
        "<tr><td>go</td><td>left</td><td>0</td><td>423</td><td>1</td><td>0</td><td>65</td><td>1</td></tr>"
        "<tr><td>stop</td><td>right</td><td>1</td><td>0</td><td>0</td><td>1</td><td>76</td><td>0</td></tr>"
        "</table>"
    )
    result = parse_showdata_html(html)
    lines = result.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "go\tleft\t0\t423\t1\t0\t65\t1"
    assert lines[1] == "stop\tright\t1\t0\t0\t1\t76\t0"


def test_parse_showdata_html_empty_table():
    """Empty table -> empty string."""
    html = "<table></table>"
    result = parse_showdata_html(html)
    assert result == ""


def test_parse_showdata_html_handles_whitespace_in_cells():
    """Whitespace in cells is stripped."""
    html = (
        "<table>"
        "<tr><td>  go  </td><td> left </td><td>\t423\n</td></tr>"
        "</table>"
    )
    result = parse_showdata_html(html)
    assert result.strip() == "go\tleft\t423"


# ---------------------------------------------------------------------------
# Task 3 — ExpFactoryDataCapture
# ---------------------------------------------------------------------------


async def test_expfactory_capture_intercepts_download(tmp_path: Path):
    """Mock download event, verify CSV content returned."""
    csv_content = "trial,rt,correct\n1,450,1\n2,523,0\n"

    # Write a temp CSV file to simulate the download
    csv_file = tmp_path / "data.csv"
    csv_file.write_text(csv_content)

    page = AsyncMock()

    # Build the async context manager that expect_download returns.
    # Playwright's expect_download() is a sync method returning an async CM,
    # so we use MagicMock for the method itself (not AsyncMock).
    download = AsyncMock()
    download.path.return_value = csv_file

    download_info = AsyncMock()
    download_info.value = download

    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=download_info)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    page.expect_download = MagicMock(return_value=ctx_manager)

    cap = ExpFactoryDataCapture()
    result = await cap.capture(page)

    assert result == csv_content


async def test_expfactory_capture_returns_none_on_timeout():
    """TimeoutError -> returns None."""
    page = AsyncMock()

    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(
        side_effect=TimeoutError("Download timed out")
    )
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    page.expect_download = MagicMock(return_value=ctx_manager)

    cap = ExpFactoryDataCapture()
    result = await cap.capture(page)

    assert result is None


async def test_expfactory_capture_returns_none_on_other_error():
    """Other exceptions -> returns None."""
    page = AsyncMock()

    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(side_effect=RuntimeError("Unexpected"))
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    page.expect_download = MagicMock(return_value=ctx_manager)

    cap = ExpFactoryDataCapture()
    result = await cap.capture(page)

    assert result is None


# ---------------------------------------------------------------------------
# Task 3 — get_data_capture factory
# ---------------------------------------------------------------------------


def test_get_data_capture_psytoolkit():
    cap = get_data_capture("psytoolkit")
    assert isinstance(cap, PsyToolkitDataCapture)


def test_get_data_capture_expfactory():
    cap = get_data_capture("expfactory")
    assert isinstance(cap, ExpFactoryDataCapture)


def test_get_data_capture_unknown():
    cap = get_data_capture("unknown_platform")
    assert cap is None

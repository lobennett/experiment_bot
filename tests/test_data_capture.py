from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from experiment_bot.output.data_capture import (
    ConfigDrivenCapture,
    DataCapture,
    ExpFactoryDataCapture,
    PsyToolkitDataCapture,
    get_data_capture,
    parse_showdata_html,
)
from experiment_bot.core.config import DataCaptureConfig


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


async def test_expfactory_capture_extracts_jspsych_data():
    """jsPsych.data.get().csv() returns CSV string."""
    csv_content = "trial,rt,correct\n1,450,1\n2,523,0\n"
    page = AsyncMock()
    page.evaluate.return_value = csv_content

    cap = ExpFactoryDataCapture()
    result = await cap.capture(page)

    assert result == csv_content
    page.evaluate.assert_awaited_once()


async def test_expfactory_capture_returns_none_when_no_jspsych():
    """Returns None if jsPsych data store is not available."""
    page = AsyncMock()
    page.evaluate.return_value = None

    cap = ExpFactoryDataCapture()
    result = await cap.capture(page)

    assert result is None


async def test_expfactory_capture_returns_none_on_error():
    """Other exceptions -> returns None."""
    page = AsyncMock()
    page.evaluate.side_effect = RuntimeError("Unexpected")

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


# ---------------------------------------------------------------------------
# ConfigDrivenCapture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_driven_js_expression_capture():
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
async def test_config_driven_button_click_capture():
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
async def test_config_driven_no_capture_method():
    config = DataCaptureConfig()  # method=""
    capturer = ConfigDrivenCapture(config)
    data = await capturer.capture(AsyncMock())
    assert data is None

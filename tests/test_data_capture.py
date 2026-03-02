from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from experiment_bot.output.data_capture import (
    ConfigDrivenCapture,
    parse_showdata_html,
)
from experiment_bot.core.config import DataCaptureConfig


# ---------------------------------------------------------------------------
# parse_showdata_html
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

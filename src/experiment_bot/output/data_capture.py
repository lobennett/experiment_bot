from __future__ import annotations

import abc
import logging
from html.parser import HTMLParser

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class DataCapture(abc.ABC):
    """Captures raw experiment data from a completed task page."""

    @abc.abstractmethod
    async def capture(self, page: Page) -> str | None:
        """Return captured data as a string, or None on failure."""


# ---------------------------------------------------------------------------
# HTML table parser (Task 2)
# ---------------------------------------------------------------------------


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
            if self._current_row:  # skip empty rows
                self._rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    @property
    def rows(self) -> list[list[str]]:
        return self._rows


def parse_showdata_html(html: str) -> str:
    """Convert an HTML table to a TSV string (tab-separated, one row per line)."""
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return ""
    return "\n".join("\t".join(row) for row in parser.rows)


# ---------------------------------------------------------------------------
# PsyToolkit (Tasks 1 + 2)
# ---------------------------------------------------------------------------


class PsyToolkitDataCapture(DataCapture):
    """Click 'show data', scrape the rendered table, return as TSV."""

    async def capture(self, page: Page) -> str | None:
        try:
            button = await page.query_selector(
                "input[value='show data'], button:has-text('show data')"
            )
            if button is None:
                logger.warning("PsyToolkit 'show data' button not found")
                return None

            await button.click()
            await page.wait_for_timeout(1000)

            html: str = await page.eval_on_selector(
                "#showdata", "el => el.innerHTML"
            )
            return parse_showdata_html(html)
        except Exception:
            logger.warning("PsyToolkit data capture failed", exc_info=True)
            return None


# ---------------------------------------------------------------------------
# ExpFactory (Task 3)
# ---------------------------------------------------------------------------


class ExpFactoryDataCapture(DataCapture):
    """Extract jsPsych trial data directly from the in-memory data store.

    jsPsych keeps all trial data in ``jsPsych.data``.  After the experiment
    completes we call ``jsPsych.data.get().csv()`` to retrieve the CSV string.
    This is more reliable than intercepting the file download because the
    download event fires during trial-loop completion (before our capture call).
    """

    async def capture(self, page: Page) -> str | None:
        try:
            csv_data: str | None = await page.evaluate(
                """() => {
                    try {
                        if (typeof jsPsych !== 'undefined' && jsPsych.data) {
                            return jsPsych.data.get().csv();
                        }
                    } catch(e) {}
                    return null;
                }"""
            )
            if csv_data:
                logger.info(
                    "Captured ExpFactory CSV (%d rows)",
                    csv_data.count("\n"),
                )
                return csv_data
            logger.warning("jsPsych data store not available or empty")
            return None
        except Exception:
            logger.warning("ExpFactory data capture failed", exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_CAPTURERS: dict[str, type[DataCapture]] = {
    "psytoolkit": PsyToolkitDataCapture,
    "expfactory": ExpFactoryDataCapture,
}


def get_data_capture(platform_name: str) -> DataCapture | None:
    """Return a DataCapture instance for the given platform, or None."""
    cls = _CAPTURERS.get(platform_name)
    return cls() if cls else None

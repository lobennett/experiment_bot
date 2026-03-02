from __future__ import annotations

import logging
from html.parser import HTMLParser

from playwright.async_api import Page

from experiment_bot.core.config import DataCaptureConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML table parser
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
# Config-driven capture
# ---------------------------------------------------------------------------


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
        return parse_showdata_html(html)

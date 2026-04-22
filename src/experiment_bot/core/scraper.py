from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from experiment_bot.core.config import SourceBundle

logger = logging.getLogger(__name__)


_MIN_INLINE_SCRIPT_BYTES = 50  # ignore trivial one-liners


class _ResourceTagParser(HTMLParser):
    """Extract script src, link href, and inline script content from HTML."""

    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.inline_scripts: list[str] = []
        self._in_inline_script: bool = False
        self._inline_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_dict = dict(attrs)
        if tag == "script":
            if attr_dict.get("src"):
                self.scripts.append(attr_dict["src"])
            else:
                # Inline script — start buffering content
                self._in_inline_script = True
                self._inline_buf = []
        if tag == "link" and attr_dict.get("rel") == "stylesheet" and attr_dict.get("href"):
            self.styles.append(attr_dict["href"])

    def handle_endtag(self, tag: str):
        if tag == "script" and self._in_inline_script:
            content = "".join(self._inline_buf).strip()
            if len(content) >= _MIN_INLINE_SCRIPT_BYTES:
                self.inline_scripts.append(content)
            self._in_inline_script = False
            self._inline_buf = []

    def handle_data(self, data: str):
        if self._in_inline_script:
            self._inline_buf.append(data)


def _parse_resource_tags(html: str) -> tuple[list[str], list[str], list[str]]:
    """Parse HTML and return (script_srcs, stylesheet_hrefs, inline_script_contents)."""
    parser = _ResourceTagParser()
    parser.feed(html)
    return parser.scripts, parser.styles, parser.inline_scripts


async def scrape_experiment_source(
    url: str,
    hint: str = "",
    extra_urls: list[str] | None = None,
) -> SourceBundle:
    """Fetch experiment page HTML and linked resources from any URL.

    Args:
        url: The experiment page URL.
        hint: Optional user-provided hint about the task type.
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

        # Parse and fetch linked resources; collect inline scripts
        scripts, styles, inline_scripts = _parse_resource_tags(page_html)
        for path in scripts + styles:
            resource_url = urljoin(url, path)
            try:
                r = await client.get(resource_url)
                if r.status_code == 200:
                    filename = path.split("/")[-1].split("?")[0]
                    source_files[filename] = r.text
            except httpx.HTTPError as e:
                logger.debug(f"Failed to fetch resource {resource_url}: {e}")

        # Store inline scripts as virtual files so Claude can read page-level JS
        for idx, content in enumerate(inline_scripts):
            key = f"inline_script_{idx + 1}.js" if len(inline_scripts) > 1 else "inline_script.js"
            source_files[key] = content

        # Fetch any extra URLs
        for extra_url in extra_urls or []:
            try:
                r = await client.get(extra_url)
                if r.status_code == 200:
                    filename = extra_url.split("/")[-1].split("?")[0]
                    source_files[filename] = r.text
            except httpx.HTTPError as e:
                logger.debug(f"Failed to fetch extra URL {extra_url}: {e}")

    return SourceBundle(
        url=url,
        source_files=source_files,
        description_text=page_html,
        hint=hint,
        metadata={"fetched_resources": len(source_files)},
    )

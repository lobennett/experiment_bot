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

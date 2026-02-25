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
                task_name = parts[-2] if len(parts) >= 2 else task_id
                break

        return SourceBundle(
            platform="expfactory",
            task_id=task_id,
            source_files=source_files,
            description_text=html,
            metadata={"url": url, "task_name": task_name},
        )

    async def detect_task_phase(self, page: Page, runtime_config=None) -> TaskPhase:
        try:
            if runtime_config and runtime_config.phase_detection.complete:
                result = await self.detect_task_phase_from_config(
                    page, runtime_config.phase_detection
                )
                if result:
                    return result
            return await self._detect_task_phase_inner(page)
        except Exception:
            # Page navigation (e.g., ExpFactory data download) destroys context
            return TaskPhase.COMPLETE

    async def _detect_task_phase_inner(self, page: Page) -> TaskPhase:
        completion_el = await page.query_selector("#completion_msg")
        if completion_el and await completion_el.is_visible():
            return TaskPhase.COMPLETE

        fullscreen_btn = await page.query_selector("button#jspsych-fullscreen-btn")
        if fullscreen_btn:
            return TaskPhase.LOADING

        next_btn = await page.query_selector("button#jspsych-instructions-next")
        if next_btn:
            return TaskPhase.INSTRUCTIONS

        attention_el = await page.query_selector("#jspsych-attention-check-rdoc-stimulus")
        if attention_el:
            return TaskPhase.ATTENTION_CHECK

        phase_text = await page.evaluate("""
            () => {
                const el = document.querySelector('.jspsych-display-element');
                return el ? el.textContent : '';
            }
        """)

        lower_text = phase_text.lower()

        # Check for between-block screens BEFORE completion keywords.
        # Between-block feedback often says "You have completed 1 out of 3 blocks"
        # which contains "completed" and would falsely trigger completion.
        if "block" in lower_text or "feedback" in lower_text:
            return TaskPhase.FEEDBACK
        if "practice" in lower_text:
            return TaskPhase.PRACTICE
        if "attention" in lower_text:
            return TaskPhase.ATTENTION_CHECK

        # Completion text — only reached if no block/feedback/practice/attention indicators
        if any(w in lower_text for w in (
            "finished", "complete", "done", "thank you", "the end",
            "experiment over", "data has been saved",
        )):
            return TaskPhase.COMPLETE

        return TaskPhase.TEST

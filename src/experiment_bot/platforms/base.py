from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Page

from experiment_bot.core.config import SourceBundle, TaskPhase


class Platform(ABC):
    @abstractmethod
    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        """Download task source code and description text."""

    @abstractmethod
    async def get_task_url(self, task_id: str) -> str:
        """Return the URL to launch the task in a browser."""

    @abstractmethod
    async def detect_task_phase(self, page: Page) -> TaskPhase:
        """Detect the current task phase from the page DOM."""

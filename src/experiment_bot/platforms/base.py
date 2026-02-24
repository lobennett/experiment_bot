from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import Page

from experiment_bot.core.config import SourceBundle, TaskPhase, PhaseDetectionConfig


class Platform(ABC):
    @abstractmethod
    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        """Download task source code and description text."""

    @abstractmethod
    async def get_task_url(self, task_id: str) -> str:
        """Return the URL to launch the task in a browser."""

    @abstractmethod
    async def detect_task_phase(self, page: Page, runtime_config=None) -> TaskPhase:
        """Detect the current task phase from the page DOM."""

    @staticmethod
    async def detect_task_phase_from_config(
        page: Page, phase_config: PhaseDetectionConfig
    ) -> TaskPhase | None:
        """Evaluate config-driven phase detection. Returns None if no config expressions set."""
        if not phase_config.complete and not phase_config.loading:
            return None  # No config — let subclass handle it

        for phase_name, js_expr in [
            ("complete", phase_config.complete),
            ("loading", phase_config.loading),
            ("instructions", phase_config.instructions),
            ("attention_check", phase_config.attention_check),
            ("feedback", phase_config.feedback),
            ("practice", phase_config.practice),
        ]:
            if js_expr:
                try:
                    result = await page.evaluate(
                        f"(() => {{ try {{ return {js_expr}; }} catch(e) {{ return false; }} }})()"
                    )
                    if result:
                        return TaskPhase(phase_name)
                except Exception:
                    continue

        if phase_config.test:
            return TaskPhase.TEST
        return None

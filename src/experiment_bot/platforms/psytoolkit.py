from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import httpx
from playwright.async_api import Page

from experiment_bot.core.config import SourceBundle, TaskPhase
from experiment_bot.platforms.base import Platform

logger = logging.getLogger(__name__)


class PsyToolkitPlatform(Platform):
    """Adapter for PsyToolkit experiment library tasks."""

    def get_zip_url(self, task_id: str) -> str:
        return f"https://www.psytoolkit.org/doc_exp/{task_id}.zip"

    def get_library_url(self, task_id: str) -> str:
        return f"https://www.psytoolkit.org/experiment-library/{task_id}.html"

    def get_demo_url(self, task_id: str) -> str:
        return f"https://www.psytoolkit.org/experiment-library/experiment_{task_id}.html"

    async def get_task_url(self, task_id: str) -> str:
        return self.get_demo_url(task_id)

    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        source_files: dict[str, str] = {}

        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Try zip download first; fall back to demo page HTML
            try:
                zip_url = self.get_zip_url(task_id)
                resp = await client.get(zip_url)
                resp.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    for name in zf.namelist():
                        if not name.endswith("/"):
                            try:
                                source_files[name] = zf.read(name).decode(
                                    "utf-8", errors="replace"
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.info(f"Zip download unavailable ({e}), using demo page as source")
                demo_url = self.get_demo_url(task_id)
                resp = await client.get(demo_url)
                resp.raise_for_status()
                source_files[f"experiment_{task_id}.html"] = resp.text

            lib_url = self.get_library_url(task_id)
            resp = await client.get(lib_url)
            resp.raise_for_status()
            description_text = resp.text

        return SourceBundle(
            platform="psytoolkit",
            task_id=task_id,
            source_files=source_files,
            description_text=description_text,
            metadata={"demo_url": self.get_demo_url(task_id)},
        )

    async def detect_task_phase(self, page: Page) -> TaskPhase:
        try:
            phase_info = await page.evaluate(
                """
                () => {
                    // Once PsyToolkit canvas experiment is running, use JS state
                    const canvas = document.querySelector('canvas#exp');
                    const experimentStarted = typeof general_trial_counter !== 'undefined';

                    if (canvas && experimentStarted) {
                        // Check completion
                        if (typeof psy_experiment_done !== 'undefined' && psy_experiment_done) return 'complete';
                        if (typeof current_task !== 'undefined' && current_task === ''
                            && general_trial_counter > 0) return 'complete';
                        return 'test';
                    }

                    // Pre-experiment: check DOM text
                    const body = document.body.textContent || '';
                    if (body.includes('Click to start')) return 'loading';
                    if (body.includes('finished') || body.includes('Finished') || body.includes('Thank you')) return 'complete';
                    return 'test';
                }
            """
            )
            return TaskPhase(phase_info)
        except Exception:
            return TaskPhase.TEST

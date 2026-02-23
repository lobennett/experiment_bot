from __future__ import annotations

import asyncio
import logging
import random
import time

import numpy as np
from playwright.async_api import Page, Browser, async_playwright

from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.distributions import ResponseSampler
from experiment_bot.core.stimulus import StimulusLookup, StimulusMatch
from experiment_bot.navigation.navigator import InstructionNavigator
from experiment_bot.navigation.stuck import StuckDetector
from experiment_bot.output.writer import OutputWriter
from experiment_bot.platforms.base import Platform

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Drives Playwright through a cognitive task using a pre-generated TaskConfig."""

    def __init__(
        self,
        config: TaskConfig,
        platform_name: str,
        seed: int | None = None,
        headless: bool = False,
    ):
        self._config = config
        self._platform_name = platform_name
        self._headless = headless
        self._rng = np.random.default_rng(seed)
        self._py_rng = random.Random(seed)

        self._lookup = StimulusLookup(config)
        self._sampler = ResponseSampler(config.response_distributions, seed=seed)
        self._navigator = InstructionNavigator()
        self._writer = OutputWriter()
        self._trial_count = 0

    def _should_respond_correctly(self, condition: str) -> bool:
        """Decide whether to give the correct response based on accuracy targets."""
        if condition == "stop":
            return self._py_rng.random() < self._config.performance.stop_accuracy
        return self._py_rng.random() < self._config.performance.go_accuracy

    def _should_omit(self) -> bool:
        return self._py_rng.random() < self._config.performance.omission_rate

    async def run(self, task_url: str, platform: Platform) -> None:
        """Execute the full task."""
        task_name = self._config.task.name.replace(" ", "_").lower()
        run_dir = self._writer.create_run(self._platform_name, task_name, self._config)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            try:
                logger.info(f"Navigating to {task_url}")
                await page.goto(task_url, wait_until="networkidle")

                # Phase 1: Navigate instructions
                logger.info("Navigating instructions...")
                await self._navigator.execute_all(page, self._config.navigation)

                # Phase 2: Trial loop
                logger.info("Entering trial loop...")
                await self._trial_loop(page, platform)

                # Phase 3: Wait for completion and data
                logger.info("Waiting for task completion...")
                await self._wait_for_completion(page, platform)

            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                screenshot = await page.screenshot(type="png")
                self._writer.save_screenshot(screenshot, "error.png")
                raise
            finally:
                self._writer.save_metadata({
                    "platform": self._platform_name,
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                })
                self._writer.finalize()
                await browser.close()

    async def _trial_loop(self, page: Page, platform: Platform) -> None:
        """Main trial loop: detect stimulus, sample RT, respond."""
        stuck_detector = StuckDetector(timeout_seconds=10.0)
        max_no_stimulus_polls = 500

        consecutive_misses = 0
        while True:
            phase = await platform.detect_task_phase(page)
            if phase == TaskPhase.COMPLETE:
                logger.info("Task complete detected")
                break

            if phase in (TaskPhase.FEEDBACK, TaskPhase.ATTENTION_CHECK):
                await self._handle_feedback(page)
                consecutive_misses = 0
                continue

            if phase == TaskPhase.INSTRUCTIONS:
                await self._navigator.execute_all(page, self._config.navigation)
                consecutive_misses = 0
                continue

            match = await self._lookup.identify(page)
            if match is None:
                consecutive_misses += 1
                if consecutive_misses > max_no_stimulus_polls:
                    logger.warning("Too many consecutive misses, stopping trial loop")
                    break
                await asyncio.sleep(0.02)
                continue

            consecutive_misses = 0
            stuck_detector.heartbeat()
            self._trial_count += 1

            await self._execute_trial(page, match)

    async def _execute_trial(self, page: Page, match: StimulusMatch) -> None:
        """Execute a single trial: decide response, wait RT, press key."""
        trial_start = time.monotonic()
        condition = match.condition

        if self._should_omit():
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": None,
                "sampled_rt_ms": None,
                "actual_rt_ms": None,
                "omission": True,
            })
            await asyncio.sleep(2.0)
            return

        if condition == "stop":
            if self._should_respond_correctly("stop"):
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": "stop_success",
                    "response_key": None,
                    "sampled_rt_ms": None,
                    "actual_rt_ms": None,
                    "omission": False,
                })
                await asyncio.sleep(2.0)
                return
            else:
                rt_condition = "stop_failure" if "stop_failure" in self._sampler._samplers else "go_correct"
        else:
            rt_condition = "go_correct" if self._should_respond_correctly("go") else "go_error"

        try:
            rt_ms = self._sampler.sample_rt(rt_condition)
        except KeyError:
            rt_ms = self._sampler.sample_rt(list(self._sampler._samplers.keys())[0])

        await asyncio.sleep(rt_ms / 1000.0)
        actual_rt = (time.monotonic() - trial_start) * 1000

        if match.response_key:
            await page.keyboard.press(match.response_key)

        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": match.response_key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
        })

    async def _handle_feedback(self, page: Page) -> None:
        """Handle inter-block feedback and attention checks."""
        logger.info("Handling feedback/attention screen")
        await asyncio.sleep(2.0)

        for selector in ["button", "#jspsych-instructions-next", ".jspsych-btn"]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible():
                    await btn.click()
                    return
            except Exception:
                continue

        await page.keyboard.press("Enter")

    async def _wait_for_completion(self, page: Page, platform: Platform) -> None:
        """Wait for the task to fully complete and data to be available."""
        if self._platform_name == "expfactory":
            logger.info("Waiting 35 seconds for ExpFactory data download...")
            await asyncio.sleep(35)
        else:
            await asyncio.sleep(5)

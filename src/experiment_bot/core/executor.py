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
from experiment_bot.output.summary import summarize_run
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

        # Resolve dynamic key mappings from task_specific
        self._key_map = self._resolve_key_mapping(config)

    @staticmethod
    def _resolve_key_mapping(config: TaskConfig) -> dict[str, str]:
        """Resolve dynamic keys from task_specific config."""
        key_map: dict[str, str] = {}
        ts = config.task_specific
        group = ts.get("default_group_index", 0)

        # Stop signal format: task_specific.key_mapping
        if "key_mapping" in ts:
            km = ts["key_mapping"]
            group = km.get("default_group_index", group)
            if group <= 4:
                mapping = km.get("group_0_to_4", {})
            else:
                mapping = km.get("group_5_to_14", {})
            for shape, key in mapping.items():
                key_map[f"go_{shape}"] = key

        # Task switching format: task_specific.group_index_mappings
        if "group_index_mappings" in ts:
            gim = ts["group_index_mappings"]
            if group <= 4:
                mapping = gim.get("0_to_4", {})
            elif group <= 9:
                mapping = gim.get("5_to_9", {})
            else:
                mapping = gim.get("10_to_14", {})
            # Map condition names to keys
            if "even" in mapping:
                key_map["parity_even"] = mapping["even"]
            if "odd" in mapping:
                key_map["parity_odd"] = mapping["odd"]
            if "higher" in mapping:
                key_map["magnitude_high"] = mapping["higher"]
            if "lower" in mapping:
                key_map["magnitude_low"] = mapping["lower"]

        return key_map

    def _resolve_response_key(self, match: StimulusMatch) -> str | None:
        """Resolve the actual key to press for a stimulus match."""
        if match.response_key and match.response_key not in ("dynamic_mapping", "dynamic"):
            return match.response_key
        # Look up from dynamic key map
        return self._key_map.get(match.condition)

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
                if self._writer.run_dir:
                    summary = summarize_run(self._writer.run_dir)
                    if summary:
                        logger.info(f"Run summary: {summary.get('total_trials', 0)} trials")
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

            if phase == TaskPhase.ATTENTION_CHECK:
                await self._handle_attention_check(page)
                consecutive_misses = 0
                continue

            if phase == TaskPhase.FEEDBACK:
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

            # Skip non-trial stimuli
            if match.condition == "no_response":
                await asyncio.sleep(0.05)
                continue

            # Handle navigation stimuli (press Enter on feedback screens)
            if match.condition == "navigation":
                key = match.response_key or "Enter"
                logger.info(f"Navigation stimulus detected, pressing {key}")
                await asyncio.sleep(1.0)
                await page.keyboard.press(key)
                continue

            # Handle attention checks
            if match.condition in ("attention_check", "attention_check_response"):
                logger.info("Attention check detected")
                await self._handle_attention_check(page)
                continue

            self._trial_count += 1
            await self._execute_trial(page, match)

    def _get_stop_signal_selector(self) -> str | None:
        """Get the stop signal detection selector from config stimuli."""
        for stim in self._config.stimuli:
            if stim.response.condition == "stop":
                return stim.detection.selector
        return None

    async def _check_stop_signal(self, page: Page, selector: str) -> bool:
        """Check if the stop signal element is currently present."""
        try:
            result = await page.evaluate(selector)
            return bool(result)
        except Exception:
            return False

    async def _execute_trial(self, page: Page, match: StimulusMatch) -> None:
        """Execute a single trial with independent race model for stop signals."""
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

        # For go trials: sample RT, but poll for stop signal during the wait
        rt_condition = "go_correct" if self._should_respond_correctly("go") else "go_error"
        rt_ms = self._sampler.sample_rt_with_fallback(rt_condition)

        stop_selector = self._get_stop_signal_selector()
        stop_detected = False

        if stop_selector:
            # Independent race model: poll for stop signal during RT wait
            poll_interval = 0.02  # 20ms
            elapsed = 0.0
            while elapsed < rt_ms / 1000.0:
                if await self._check_stop_signal(page, stop_selector):
                    stop_detected = True
                    break
                await asyncio.sleep(poll_interval)
                elapsed = (time.monotonic() - trial_start)
        else:
            await asyncio.sleep(rt_ms / 1000.0)

        if stop_detected:
            # Independent race model: compare remaining go time vs SSRT
            # SSD ≈ time from trial start to stop signal appearance
            ssd_s = time.monotonic() - trial_start
            remaining_go_s = (rt_ms / 1000.0) - ssd_s
            ssrt_s = self._config.task_specific.get(
                "stop_signal_parameters", {}
            ).get("target_SSRT_ms", 250) / 1000.0

            if remaining_go_s > ssrt_s:
                # Go process hasn't finished; stop process wins → inhibit
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": "stop_success",
                    "response_key": None,
                    "sampled_rt_ms": round(rt_ms, 1),
                    "actual_rt_ms": None,
                    "omission": False,
                })
                await asyncio.sleep(1.5)  # Wait for trial to advance
                return
            else:
                # Go process finishes before stop can catch up → failed stop
                # Wait the remaining go RT then respond
                if remaining_go_s > 0:
                    await asyncio.sleep(remaining_go_s)
                actual_rt = (time.monotonic() - trial_start) * 1000
                resolved_key = self._resolve_response_key(match)
                if resolved_key:
                    await page.keyboard.press(resolved_key)
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": "stop_failure",
                    "response_key": resolved_key,
                    "sampled_rt_ms": round(rt_ms, 1),
                    "actual_rt_ms": round(actual_rt, 1),
                    "omission": False,
                })
                return

        # No stop signal — normal go trial response
        if not stop_detected and not stop_selector:
            actual_rt = (time.monotonic() - trial_start) * 1000
        else:
            # Wait remaining RT time if we were polling
            remaining = (rt_ms / 1000.0) - (time.monotonic() - trial_start)
            if remaining > 0:
                await asyncio.sleep(remaining)
            actual_rt = (time.monotonic() - trial_start) * 1000

        resolved_key = self._resolve_response_key(match)
        if resolved_key:
            await page.keyboard.press(resolved_key)

        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": resolved_key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
        })

    _ORDINAL_MAP = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
        "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
        "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
        "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
        "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25, "twenty-sixth": 26,
        "last": 26,
    }

    async def _handle_attention_check(self, page: Page) -> None:
        """Handle attention check by reading the prompt and pressing the requested key."""
        import re
        await asyncio.sleep(1.5)
        try:
            text = await page.evaluate("""
                () => {
                    const el = document.querySelector('#jspsych-attention-check-rdoc-stimulus') ||
                               document.querySelector('.jspsych-display-element');
                    return el ? el.textContent : '';
                }
            """)
            key = self._parse_attention_check_key(text)
            if key:
                logger.info(f"Attention check: pressing '{key}'")
                await page.keyboard.press(key)
            else:
                logger.warning(f"Could not parse attention check text: {text[:100]}")
                await page.keyboard.press("Enter")
        except Exception as e:
            logger.warning(f"Attention check handling failed: {e}")
            await page.keyboard.press("Enter")

    def _parse_attention_check_key(self, text: str) -> str | None:
        """Parse attention check text to determine which key to press."""
        import re
        # "Press the X key"
        m = re.search(r'[Pp]ress the (\w) key', text)
        if m:
            return m.group(1).lower()

        # "Press the key for the Nth letter of the English alphabet"
        m = re.search(r'[Pp]ress the key for the (\w+(?:-\w+)?)\s+letter', text)
        if m:
            ordinal = m.group(1).lower()
            n = self._ORDINAL_MAP.get(ordinal)
            if n and 1 <= n <= 26:
                return chr(ord('a') + n - 1)

        return None

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

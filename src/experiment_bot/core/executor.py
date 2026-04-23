from __future__ import annotations

import asyncio
import logging
import random
import time

import numpy as np
from playwright.async_api import Page, async_playwright

from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.distributions import ResponseSampler
from experiment_bot.core.stimulus import StimulusLookup, StimulusMatch
from experiment_bot.navigation.navigator import InstructionNavigator
from experiment_bot.navigation.stuck import StuckDetector
from experiment_bot.output.writer import OutputWriter
from experiment_bot.core.phase_detection import detect_phase
from experiment_bot.output.data_capture import ConfigDrivenCapture

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Drives Playwright through a cognitive task using a pre-generated TaskConfig."""

    def __init__(
        self,
        config: TaskConfig,
        seed: int | None = None,
        headless: bool = False,
    ):
        self._config = config
        self._headless = headless
        self._rng = np.random.default_rng(seed)
        self._py_rng = random.Random(seed)

        self._lookup = StimulusLookup(config)
        self._sampler = ResponseSampler(
            config.response_distributions,
            temporal_effects=config.temporal_effects,
            floor_ms=config.runtime.timing.rt_floor_ms,
            seed=seed,
        )
        self._navigator = InstructionNavigator()
        self._writer = OutputWriter()
        self._trial_count = 0
        self._prev_trial_error = False
        self._prev_interrupt_detected: bool = False
        self._response_window_confirmed: bool = False  # Set by trial loop to skip redundant check
        self._seen_response_keys: set[str] = set()  # Track dynamically resolved keys

        # Resolve static key mappings from task_specific
        self._key_map = self._resolve_key_mapping(config)
        # Cache interrupt JS — config is immutable so this never changes
        self._interrupt_js = self._build_interrupt_check_js()
        # Cache condition names — config is immutable, no need to recompute per trial
        self._navigation_condition_name: str = (
            config.runtime.navigation_stimulus_condition or "navigation"
        )
        self._attention_check_conditions: set[str] = set(
            config.runtime.attention_check.stimulus_conditions
        ) or {"attention_check", "attention_check_response"}

    @staticmethod
    def _resolve_key_mapping(config: TaskConfig) -> dict[str, str]:
        """Resolve key mappings from config.task_specific.key_map."""
        ts = config.task_specific
        if "key_map" in ts:
            return dict(ts["key_map"])
        return {}

    # Sentinel values returned by response_key_js that indicate "withhold / no response".
    # Case-insensitive comparison is used — see _is_withhold_sentinel().
    # Permissive expansion: no Playwright key names match any of these strings, so
    # false-positives are impossible while false-negatives cause a crash.
    _WITHHOLD_SENTINELS: frozenset[str] = frozenset({
        "", "none", "null",
        "withhold", "no_response", "noresponse",
        "no_key", "nokey", "suppress", "skip", "pass",
    })

    @staticmethod
    def _is_withhold_sentinel(value: object) -> bool:
        """Return True if *value* represents a withhold / no-key-press instruction.

        Handles None, empty string, and the case-insensitive strings "none" and
        "null" that Claude's JS expressions legitimately return when a trial
        requires response suppression (e.g. stop-signal withhold trials).
        """
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        return value.strip().lower() in TaskExecutor._WITHHOLD_SENTINELS

    async def _resolve_response_key(self, match: StimulusMatch, page: Page | None = None) -> str | None:
        """Resolve the actual key to press for a stimulus match.

        Resolution order:
        1. Static key from stimulus config
        2. Per-stimulus response_key_js (evaluated on page)
        3. Global task_specific.response_key_js (evaluated on page)
        4. Static key_map fallback

        Returns None when no key is found OR when the resolved value is a
        withhold sentinel ("", None, "none", "null" — case-insensitive).
        Callers must treat None as "do not press any key".
        """
        # Static key from config
        if match.response_key and match.response_key not in ("dynamic_mapping", "dynamic"):
            self._seen_response_keys.add(match.response_key)
            return match.response_key

        # Per-stimulus response_key_js
        if page:
            stim_cfg = next((s for s in self._config.stimuli if s.id == match.stimulus_id), None)
            if stim_cfg and stim_cfg.response.response_key_js:
                try:
                    key = await page.evaluate(stim_cfg.response.response_key_js)
                    if self._is_withhold_sentinel(key):
                        return None
                    key = str(key)
                    self._seen_response_keys.add(key)
                    return key
                except Exception as e:
                    # Page context may be torn down by navigation
                    logger.warning(f"response_key_js failed for {match.stimulus_id}: {e}")

            # Global response_key_js from task_specific
            global_js = self._config.task_specific.get("response_key_js", "")
            if global_js:
                try:
                    key = await page.evaluate(global_js)
                    if self._is_withhold_sentinel(key):
                        return None
                    key = str(key)
                    self._seen_response_keys.add(key)
                    return key
                except Exception as e:
                    # Page context may be torn down by navigation
                    logger.warning(f"task_specific.response_key_js failed: {e}")

        # Static key_map fallback (skip "dynamic" sentinel values and withhold sentinels)
        mapped = self._key_map.get(match.condition)
        if mapped and mapped not in ("dynamic_mapping", "dynamic"):
            if self._is_withhold_sentinel(mapped):
                return None
            self._seen_response_keys.add(mapped)
            return mapped

        return None

    def _is_trial_stimulus(self, match: StimulusMatch) -> bool:
        """Whether a stimulus represents a trial requiring RT-distributed response.

        Derived from config: a condition is trial-level if it maps to an RT distribution.
        """
        dists = self._config.response_distributions
        condition = match.condition
        # Direct match or correct/error variant exists
        if condition in dists or f"{condition}_correct" in dists or f"{condition}_error" in dists:
            return True
        # Has distributions and stimulus has a response key → likely a trial
        return bool(dists) and match.response_key is not None

    def _should_respond_correctly(self, condition: str) -> bool:
        """Decide whether to give the correct response based on accuracy targets."""
        return self._py_rng.random() < self._config.performance.get_accuracy(condition)

    def _should_omit(self, condition: str = "") -> bool:
        return self._py_rng.random() < self._config.performance.get_omission_rate(condition)

    def _pick_wrong_key(self, correct_key: str) -> str:
        """Return a random incorrect key from known response keys."""
        # Use static key_map when all values are real keys; exclude sentinel values
        static_keys = {
            v for v in self._key_map.values()
            if v not in ("dynamic", "dynamic_mapping")
            and not self._is_withhold_sentinel(v)
        }
        all_keys = list(static_keys or self._seen_response_keys)
        wrong_keys = [k for k in all_keys if k != correct_key and not self._is_withhold_sentinel(k)]
        if not wrong_keys:
            return correct_key  # Only one real key available; can't press wrong one
        return self._py_rng.choice(wrong_keys)

    def _resolve_rt_distribution_key(self, condition: str, is_correct: bool) -> str:
        """Determine which RT distribution to sample from.

        Resolution order:
        1. {condition}_correct / {condition}_error variants
        2. Direct condition name match
        3. Fallback to first available distribution
        """
        dists = self._config.response_distributions

        # Try condition-specific correct/error variants
        if not is_correct:
            error_key = f"{condition}_error"
            if error_key in dists:
                return error_key
        else:
            correct_key = f"{condition}_correct"
            if correct_key in dists:
                return correct_key

        # Direct match: condition name is itself a distribution key
        if condition in dists:
            return condition

        # Fallback to first available distribution
        if dists:
            return next(iter(dists))
        return condition

    async def run(self, task_url: str) -> None:
        """Execute the full task."""
        task_name = self._config.task.name.replace(" ", "_").lower()
        run_dir = self._writer.create_run(task_name, self._config)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport=self._config.runtime.timing.viewport,
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
                await self._trial_loop(page)

                # Phase 3: Wait for completion and data
                logger.info("Waiting for task completion...")
                await self._wait_for_completion(page)

            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                screenshot = await page.screenshot(type="png")
                self._writer.save_screenshot(screenshot, "error.png")
                raise
            finally:
                self._writer.save_metadata({
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                })
                self._writer.finalize()
                await browser.close()

    async def _trial_loop(self, page: Page) -> None:
        """Main trial loop: detect stimulus, sample RT, respond."""
        timing = self._config.runtime.timing
        stuck_detector = StuckDetector(timeout_seconds=timing.stuck_timeout_s)
        max_no_stimulus_polls = timing.max_no_stimulus_polls

        consecutive_misses = 0
        while True:
            phase = await detect_phase(page, self._config.runtime.phase_detection)
            if phase == TaskPhase.COMPLETE:
                logger.info("Task complete detected")
                break

            if phase == TaskPhase.ATTENTION_CHECK:
                await self._handle_attention_check(page)
                consecutive_misses = 0
                continue

            if phase in (TaskPhase.FEEDBACK, TaskPhase.INSTRUCTIONS):
                probe = await self._lookup.identify(page)
                if probe is None or not self._is_trial_stimulus(probe):
                    if phase == TaskPhase.FEEDBACK:
                        await self._handle_feedback(page)
                    else:
                        await self._navigator.execute_all(page, self._config.navigation)
                    consecutive_misses = 0
                    continue
                logger.debug("Trial stimulus %s overrides %s phase", probe.stimulus_id, phase.value)

            # Gate stimulus detection on response window — prevents detecting
            # stale JS globals during fixation, cue display, or feedback phases.
            # When the window stays closed too long, fall through to advance
            # behavior so between-block instruction screens still get dismissed.
            self._response_window_confirmed = False
            if timing.response_window_js:
                try:
                    ready = await page.evaluate(timing.response_window_js)
                    if not ready:
                        consecutive_misses += 1
                        ab = self._config.runtime.advance_behavior
                        if consecutive_misses % ab.advance_interval_polls == 0 and consecutive_misses < max_no_stimulus_polls:
                            logger.info(f"Response window closed for {consecutive_misses} polls, pressing advance keys")
                            if ab.pre_keypress_js:
                                try:
                                    await page.evaluate(ab.pre_keypress_js)
                                except Exception:
                                    # Page context may be torn down by navigation
                                    pass
                            for key in ab.advance_keys:
                                await page.keyboard.press(key)
                        if consecutive_misses > max_no_stimulus_polls:
                            logger.warning("Response window closed too long, stopping trial loop")
                            break
                        await asyncio.sleep(timing.poll_interval_ms / 1000.0)
                        continue
                    self._response_window_confirmed = True
                    consecutive_misses = 0
                except Exception:
                    # Page context may be torn down by navigation
                    pass

            if phase in (TaskPhase.FEEDBACK, TaskPhase.INSTRUCTIONS):
                match = probe
            else:
                match = await self._lookup.identify(page)
            if match is None:
                consecutive_misses += 1
                if consecutive_misses > max_no_stimulus_polls:
                    logger.warning("Too many consecutive misses, stopping trial loop")
                    break
                # Try pressing advance keys periodically to advance between-block screens
                ab = self._config.runtime.advance_behavior
                if consecutive_misses % ab.advance_interval_polls == 0 and consecutive_misses < max_no_stimulus_polls:
                    logger.info(f"No stimulus for {consecutive_misses} polls, pressing advance keys")
                    if ab.pre_keypress_js:
                        try:
                            await page.evaluate(ab.pre_keypress_js)
                        except Exception:
                            # Page context may be torn down by navigation
                            pass
                    for key in ab.advance_keys:
                        await page.keyboard.press(key)
                    # Also try exit pager key at double the interval
                    if ab.exit_pager_key and consecutive_misses % (ab.advance_interval_polls * 2) == 0:
                        await asyncio.sleep(0.5)
                        if ab.pre_keypress_js:
                            try:
                                await page.evaluate(ab.pre_keypress_js)
                            except Exception:
                                # Page context may be torn down by navigation
                                pass
                        await page.keyboard.press(ab.exit_pager_key)
                if consecutive_misses == 1:
                    logger.debug("No stimulus match on poll")
                await asyncio.sleep(timing.poll_interval_ms / 1000.0)
                continue

            # Skip non-trial stimuli (fixation, ITI) without resetting miss counter.
            # Resetting here would prevent advance behavior from triggering when
            # the executor is stuck detecting fixation on an instruction screen.
            # Navigation and attention-check stimuli are NOT skipped here — they
            # always need handling regardless of whether they look like trial stimuli.
            is_special = (
                match.condition == self._navigation_condition_name
                or match.condition in self._attention_check_conditions
            )
            if not is_special and not self._is_trial_stimulus(match) and match.response_key is None:
                await asyncio.sleep(0.05)
                continue

            consecutive_misses = 0
            stuck_detector.heartbeat()

            # Handle navigation stimuli (press Enter on feedback screens).
            # The condition label is read from config so the executor is not coupled
            # to the literal string "navigation".  When the config omits the field
            # (empty string), we fall back to "navigation" for backward compatibility.
            if match.condition == self._navigation_condition_name:
                key = match.response_key or "Enter"
                logger.info(f"Navigation stimulus detected, pressing {key}")
                await asyncio.sleep(
                    self._config.runtime.timing.navigation_delay_ms / 1000.0
                )
                await page.keyboard.press(key)
                continue

            # Handle attention checks.
            # The set of condition labels is read from config so the executor is not
            # coupled to the legacy literals "attention_check" /
            # "attention_check_response".
            if match.condition in self._attention_check_conditions:
                logger.info("Attention check detected")
                await self._handle_attention_check(page)
                continue

            self._trial_count += 1

            # Read trial context (e.g. cue text)
            cue = None
            if timing.trial_context_js:
                try:
                    raw_cue = await page.evaluate(timing.trial_context_js)
                    if raw_cue:  # Ignore empty strings from non-stimulus phases
                        cue = raw_cue
                except Exception:
                    # Page context may be torn down by navigation
                    pass

            logger.info(f"Trial {self._trial_count}: {match.stimulus_id} ({match.condition}) cue={cue!r}")
            await self._execute_trial(page, match, cue=cue)

            # After responding, wait for the response window to close (next trial's
            # fixation) to avoid re-detecting the same stimulus and pressing into
            # the wrong trial.
            if timing.response_window_js:
                await self._wait_for_trial_end(
                    page,
                    timing.response_window_js,
                    timeout_s=timing.trial_end_timeout_s,
                )

    async def _wait_for_trial_end(
        self, page: Page, response_window_js: str, timeout_s: float = 5.0
    ) -> None:
        """Wait for the response window to close, indicating the current trial ended."""
        poll_s = self._config.runtime.timing.poll_interval_ms / 1000.0
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                ready = await page.evaluate(response_window_js)
                if not ready:
                    return
            except Exception:
                # Page context may be torn down by navigation — treat as trial ended
                return
            await asyncio.sleep(poll_s)

    def _build_interrupt_check_js(self) -> str | None:
        """Build a JS expression that detects any interrupt stimulus.

        Combines all interrupt-condition stimuli into a single JS expression,
        handling both dom_query (CSS selectors) and js_eval methods.
        """
        stop_cond = self._config.runtime.trial_interrupt.detection_condition
        checks = []
        for stim in self._config.stimuli:
            if stim.response.condition == stop_cond:
                if stim.detection.method == "dom_query":
                    sel = stim.detection.selector.replace("'", "\\'")
                    checks.append(f"document.querySelector('{sel}') !== null")
                else:  # js_eval, canvas_state
                    checks.append(f"!!({stim.detection.selector})")
        if not checks:
            return None
        return " || ".join(checks)

    async def _check_interrupt(self, page: Page, js_expr: str) -> bool:
        """Check if an interrupt stimulus is currently present on page."""
        try:
            result = await page.evaluate(js_expr)
            return bool(result)
        except Exception:
            # Page context may be torn down by navigation — treat as no interrupt
            return False

    async def _wait_for_response_window(self, page: Page, js_expr: str) -> None:
        """Poll until the platform's response window is open.

        Some experiments display a cue or fixation before the response window
        opens. This method synchronizes the bot's timing to the actual window.
        """
        poll_s = self._config.runtime.timing.poll_interval_ms / 1000.0
        timeout = 5.0  # Max wait to avoid hanging
        start = time.monotonic()
        while (time.monotonic() - start) < timeout:
            try:
                ready = await page.evaluate(js_expr)
                if ready:
                    return
            except Exception:
                # Page context may be torn down by navigation — stop polling
                pass
            await asyncio.sleep(poll_s)
        logger.warning("Response window poll timed out after 5s, proceeding anyway")

    async def _execute_trial(self, page: Page, match: StimulusMatch, cue: str | None = None) -> None:
        """Execute a single trial with probabilistic interrupt handling.

        For tasks with a trial interrupt (e.g. stop signal), polls for the
        interrupt stimulus during the RT wait. If detected, uses configured
        accuracy to decide inhibition success/failure probabilistically,
        producing race-model-valid behavior.
        """
        trial_start = time.monotonic()
        condition = match.condition

        if self._should_omit(condition):
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": None,
                "sampled_rt_ms": None,
                "actual_rt_ms": None,
                "omission": True,
            })
            self._prev_trial_error = True
            self._prev_interrupt_detected = False
            await asyncio.sleep(self._config.runtime.timing.omission_wait_ms / 1000.0)
            return

        # Synchronize with platform's response window when the trial loop hasn't
        # already confirmed it (e.g., PsyToolkit where the gate isn't in the loop)
        timing = self._config.runtime.timing
        if timing.response_window_js and not self._response_window_confirmed:
            await self._wait_for_response_window(page, timing.response_window_js)
        trial_start = time.monotonic()

        # Sample go RT — track whether this is an intentional error trial
        is_correct = self._should_respond_correctly(condition)
        rt_condition = self._resolve_rt_distribution_key(condition, is_correct)
        is_error = not is_correct
        te = self._config.temporal_effects
        skip_cond_rep = self._prev_interrupt_detected and te.post_interrupt_slowing.enabled
        rt_ms = self._sampler.sample_rt_with_fallback(rt_condition, skip_condition_repetition=skip_cond_rep)

        # Sequential slowing effects (mutually exclusive — most specific wins)
        if self._prev_interrupt_detected and te.post_interrupt_slowing.enabled:
            rt_ms += self._rng.uniform(
                te.post_interrupt_slowing.slowing_ms_min,
                te.post_interrupt_slowing.slowing_ms_max,
            )
        elif self._prev_trial_error and te.post_error_slowing.enabled:
            rt_ms += self._rng.uniform(
                te.post_error_slowing.slowing_ms_min,
                te.post_error_slowing.slowing_ms_max,
            )

        # Cap RT at the task's max response window (prevents late keypresses)
        max_response_ms = self._config.task_specific.get(
            "trial_timing", {}
        ).get("max_response_time_ms") or 0
        if max_response_ms > 0:
            rt_ms = min(rt_ms, max_response_ms * self._config.runtime.timing.rt_cap_fraction)

        interrupt_detected = False

        if self._interrupt_js:
            # Poll for interrupt stimulus during RT wait
            poll_interval = self._config.runtime.timing.poll_interval_ms / 1000.0
            while (time.monotonic() - trial_start) < rt_ms / 1000.0:
                if await self._check_interrupt(page, self._interrupt_js):
                    interrupt_detected = True
                    break
                await asyncio.sleep(poll_interval)
        else:
            await asyncio.sleep(rt_ms / 1000.0)

        interrupt_cfg = self._config.runtime.trial_interrupt
        if interrupt_detected:
            # Decide inhibition outcome probabilistically based on configured accuracy
            if self._should_respond_correctly(interrupt_cfg.detection_condition):
                # Successful inhibition — withhold response
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": f"{interrupt_cfg.detection_condition}_withheld",
                    "response_key": None,
                    "sampled_rt_ms": round(rt_ms, 1),
                    "actual_rt_ms": None,
                    "omission": False,
                })
                self._prev_trial_error = False
                self._prev_interrupt_detected = True
                await asyncio.sleep(interrupt_cfg.inhibit_wait_ms / 1000.0)
                return
            else:
                # Failed inhibition — sample from failure RT distribution
                # (faster than go RTs, satisfying independent race model)
                sf_rt_ms = self._sampler.sample_rt_with_fallback(interrupt_cfg.failure_rt_key)
                if max_response_ms > 0:
                    sf_rt_ms = min(sf_rt_ms, max_response_ms * interrupt_cfg.failure_rt_cap_fraction)

                # Wait until failure RT has elapsed from trial start
                elapsed_s = time.monotonic() - trial_start
                remaining_s = (sf_rt_ms / 1000.0) - elapsed_s
                if remaining_s > 0:
                    await asyncio.sleep(remaining_s)

                actual_rt = (time.monotonic() - trial_start) * 1000
                resolved_key = await self._resolve_response_key(match, page)
                if resolved_key:
                    await page.keyboard.press(resolved_key)
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": f"{interrupt_cfg.detection_condition}_responded",
                    "response_key": resolved_key,
                    "sampled_rt_ms": round(sf_rt_ms, 1),
                    "actual_rt_ms": round(actual_rt, 1),
                    "omission": False,
                })
                self._prev_trial_error = True
                self._prev_interrupt_detected = True
                return

        # No interrupt — normal trial response
        if not self._interrupt_js:
            actual_rt = (time.monotonic() - trial_start) * 1000
        else:
            # Wait remaining RT time if we were polling
            remaining = (rt_ms / 1000.0) - (time.monotonic() - trial_start)
            if remaining > 0:
                await asyncio.sleep(remaining)
            actual_rt = (time.monotonic() - trial_start) * 1000

        resolved_key = await self._resolve_response_key(match, page)

        # A None resolved_key here means the config's response_key_js returned a
        # withhold sentinel ("", "none", "null").  This is a config-authored
        # withhold instruction — not a random omission.  Log it distinctly and
        # skip the keyboard press.
        if resolved_key is None:
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": None,
                "sampled_rt_ms": round(rt_ms, 1),
                "actual_rt_ms": None,
                "omission": False,
                "withheld": True,
                "rt_distribution": rt_condition,
                "cue": cue,
            })
            self._prev_trial_error = False
            self._prev_interrupt_detected = False
            return

        if is_error:
            resolved_key = self._pick_wrong_key(resolved_key)
        await page.keyboard.press(resolved_key)

        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": resolved_key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
            "intended_error": is_error,
            "rt_distribution": rt_condition,
            "cue": cue,
        })
        self._prev_trial_error = is_error
        self._prev_interrupt_detected = False

    async def _handle_attention_check(self, page: Page) -> None:
        """Handle attention check using config-driven response logic.

        Claude must provide response_js in the attention_check config —
        the executor has no built-in knowledge of attention check formats.
        """
        await asyncio.sleep(
            self._config.runtime.timing.attention_check_delay_ms / 1000.0
        )
        ac = self._config.runtime.attention_check
        try:
            if ac.response_js:
                key = await page.evaluate(ac.response_js)
                if key:
                    logger.info(f"Attention check: pressing '{key}'")
                    await page.keyboard.press(str(key))
                    return
            logger.warning("No response_js configured for attention check, pressing Enter")
            await page.keyboard.press("Enter")
        except Exception as e:
            # Page context may be torn down by navigation — fall back to Enter
            logger.warning(f"Attention check handling failed: {e}")
            await page.keyboard.press("Enter")

    async def _handle_feedback(self, page: Page) -> None:
        """Handle inter-block feedback screens."""
        logger.info("Handling feedback screen")
        ab = self._config.runtime.advance_behavior
        await asyncio.sleep(self._config.runtime.timing.feedback_delay_ms / 1000.0)

        for selector in ab.feedback_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible():
                    await btn.click()
                    return
            except Exception:
                # Button may not exist on this feedback screen — try next selector
                continue

        for key in ab.feedback_fallback_keys:
            await page.keyboard.press(key)
            await asyncio.sleep(0.5)

    async def _wait_for_completion(self, page: Page) -> None:
        """Wait for task completion and capture experiment data."""
        await asyncio.sleep(
            self._config.runtime.timing.completion_settle_ms / 1000.0
        )

        capturer = ConfigDrivenCapture(self._config.runtime.data_capture)
        data = await capturer.capture(page)
        if data:
            ext = self._config.runtime.data_capture.format or "csv"
            self._writer.save_task_data(data, f"experiment_data.{ext}")
            logger.info("Experiment data saved")
        else:
            wait_s = self._config.runtime.timing.completion_wait_ms / 1000.0
            logger.info(f"No data captured, waiting {wait_s:.1f}s for platform data save")
            await asyncio.sleep(wait_s)

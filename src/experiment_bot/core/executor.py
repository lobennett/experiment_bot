from __future__ import annotations

import logging
import random

import numpy as np
from playwright.async_api import Page, async_playwright

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.distributions import ResponseSampler
from experiment_bot.drivers.diagnostic import DiagnosticDriver
from experiment_bot.drivers.registry import identify_driver
from experiment_bot.output.writer import OutputWriter

logger = logging.getLogger(__name__)


def _taskcard_to_config(tc):
    """Project a TaskCard into a TaskConfig the executor knows how to drive.

    Reads: tc.task, tc.stimuli, tc.navigation, tc.runtime, tc.task_specific,
    tc.performance. Behavioral fields are projected from ParameterValue.value.
    """
    from experiment_bot.core.config import (
        TaskConfig,
        DistributionConfig,
        TemporalEffectsConfig,
        BetweenSubjectJitterConfig,
    )
    cfg = TaskConfig(
        task=tc.task,
        stimuli=tc.stimuli,
        response_distributions={
            k: DistributionConfig(distribution="ex_gaussian", params=v.value)
            for k, v in tc.response_distributions.items()
        },
        performance=tc.performance,
        navigation=tc.navigation,
        task_specific=tc.task_specific,
        runtime=tc.runtime,
    )
    te_dict = {k: v.value for k, v in tc.temporal_effects.items()}
    cfg.temporal_effects = TemporalEffectsConfig.from_dict(te_dict)
    bsj = tc.between_subject_jitter
    if isinstance(bsj, dict):
        bsj_value = bsj.get("value", {})
    else:
        # already a BetweenSubjectJitterConfig
        cfg.between_subject_jitter = bsj
        return cfg
    cfg.between_subject_jitter = BetweenSubjectJitterConfig.from_dict(bsj_value)
    return cfg


class TaskExecutor:
    """Drives Playwright through a cognitive task using a pre-generated TaskConfig."""

    def __init__(
        self,
        config,  # TaskCard or TaskConfig
        seed: int | None = None,
        headless: bool = False,
        session_params: dict | None = None,
    ):
        """SP10 slim executor: holds sampler + writer + history. All
        platform-touching concerns live in the driver (constructed by
        identify_driver at session start)."""
        from experiment_bot.taskcard.types import TaskCard
        if isinstance(config, TaskCard):
            self._taskcard = config
            config = _taskcard_to_config(config)
        else:
            self._taskcard = None
        self._config = config
        self._headless = headless
        # Persisted to run_metadata.json so a session is exactly
        # reproducible (same seed + same TaskCard hash = same output).
        self._session_seed = seed
        self._session_params = session_params or {}
        self._rng = np.random.default_rng(seed)
        self._py_rng = random.Random(seed)

        self._sampler = ResponseSampler(
            config.response_distributions,
            temporal_effects=config.temporal_effects,
            floor_ms=config.runtime.timing.rt_floor_ms,
            seed=seed,
            paradigm_classes=getattr(config.task, "paradigm_classes", None) or [],
        )
        self._writer = OutputWriter()
        self._trial_count = 0
        # Rolling window of recent error flags for the effect library's
        # post-event-slowing handler. Unchanged from SP6.
        from collections import deque
        self._recent_errors: deque[bool] = deque(maxlen=8)

    async def run(self, task_url: str) -> None:
        """Execute the full task via the SP10 driver architecture."""
        task_name = self._config.task.name.replace(" ", "_").lower()
        run_dir = self._writer.create_run(task_name, self._config)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport=self._config.runtime.timing.viewport,
            )
            page = await context.new_page()
            session_status = "ok"
            diagnostic_path = None
            try:
                logger.info("Navigating to %s", task_url)
                await page.goto(task_url, wait_until="networkidle")
                driver = await identify_driver(page)
                if isinstance(driver, DiagnosticDriver):
                    driver._report_dir = run_dir
                try:
                    await self._run_session(page, driver)
                finally:
                    try:
                        await driver.teardown(page)
                    except Exception as e:
                        logger.warning("driver.teardown raised: %s", e)
            except Exception as e:
                from experiment_bot.drivers.base import DriverError
                if isinstance(e, DriverError) and e.kind.startswith("diagnostic_"):
                    session_status = "diagnostic_mode"
                    diagnostic_path = e.context.get("report_path")
                    logger.warning("Session aborted in diagnostic mode: %s", e.kind)
                else:
                    session_status = "error"
                    logger.error("Task execution failed: %s", e)
                    try:
                        screenshot = await page.screenshot(type="png")
                        self._writer.save_screenshot(screenshot, "error.png")
                    except Exception:
                        pass
                    raise
            finally:
                metadata = {
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                    "session_seed": self._session_seed,
                    "session_params": self._session_params,
                    "status": session_status,
                }
                if diagnostic_path is not None:
                    metadata["diagnostic_report_path"] = diagnostic_path
                if self._taskcard is not None:
                    pb = getattr(self._taskcard, "produced_by", None)
                    metadata["taskcard_sha256"] = (
                        getattr(pb, "taskcard_sha256", "") if pb else ""
                    )
                self._writer.save_metadata(metadata)
                self._writer.finalize()
                await browser.close()

    async def _run_session(self, page, driver) -> None:
        """SP10 driver-based trial loop."""
        from experiment_bot.drivers.base import TrialLoopState
        logger.info("Driver %s.setup() begin", driver.__class__.__name__)
        await driver.setup(page)
        logger.info("Driver setup complete; entering trial loop")
        history: list[dict] = []
        iter_count = 0
        last_log_iter = 0
        nav_streak = 0
        while True:
            iter_count += 1
            state = await driver.loop_state(page)
            if iter_count == 1 or iter_count - last_log_iter >= 25:
                logger.info(
                    "Trial loop iter=%d state=%s trial_count=%d nav_streak=%d",
                    iter_count, state.name, self._trial_count, nav_streak,
                )
                last_log_iter = iter_count
            if state == TrialLoopState.COMPLETE:
                logger.info("Loop COMPLETE at iter=%d trial_count=%d", iter_count, self._trial_count)
                break
            if state == TrialLoopState.NEEDS_NAVIGATION:
                outcome = await driver.navigate(page)
                nav_streak += 1
                if nav_streak <= 5 or nav_streak % 25 == 0:
                    logger.info(
                        "Navigate iter=%d streak=%d action=%s type=%s",
                        iter_count, nav_streak, outcome.action,
                        outcome.details.get("type_name") if outcome.details else None,
                    )
                if nav_streak > 200:
                    logger.error(
                        "navigation streak exceeded 200; aborting to avoid infinite loop"
                    )
                    raise RuntimeError(
                        f"navigation streak={nav_streak} without progress to READY_FOR_TRIAL"
                    )
                self._writer.log_trial({
                    "type": "navigation",
                    "action": outcome.action,
                    "details": dict(outcome.details),
                })
                continue
            # READY_FOR_TRIAL — reset the streak counter
            nav_streak = 0
            ctx = await driver.get_trial_context(page)
            rt = self._sampler.sample_rt_with_fallback(ctx.condition)
            # post_event_slowing isn't applied by the sampler (it depends
            # on the bot's intended_correct flag from the previous trial,
            # which the sampler doesn't see). Apply it here.
            prev_error = bool(self._recent_errors[0]) if self._recent_errors else False
            rt = self._sampler.apply_post_event_slowing(rt, ctx.condition, prev_error)
            intended_correct = self._py_rng.random() < self._config.performance.get_accuracy(ctx.condition)
            # Stop-trial handling: when the driver detects a stop trial,
            # the bot withholds with the TaskCard's stop-accuracy
            # probability (e.g. 0.5 = 50% successful inhibition, matching
            # SSD-adapted human performance). Withhold means response=None.
            is_stop_trial = bool((ctx.metadata or {}).get("is_stop_trial"))
            if is_stop_trial:
                # accuracy("stop") = probability of successful inhibition
                inhibit_p = self._config.performance.get_accuracy("stop")
                if self._py_rng.random() < inhibit_p:
                    response = None
                else:
                    response = _resolve_response(
                        ctx, intended_correct=True,
                        rng=self._py_rng, taskcard=self._taskcard,
                    )
            else:
                response = _resolve_response(
                    ctx, intended_correct, self._py_rng, self._taskcard,
                )
            result = await driver.deliver_response(page, response, rt)
            self._writer.log_trial({
                "type": "trial",
                "trial_index": self._trial_count,
                "stimulus_id": ctx.stimulus_id,
                "condition": ctx.condition,
                "expected_correct": ctx.expected_correct,
                "allowed_responses": list(ctx.allowed_responses),
                "trial_type_name": (ctx.metadata or {}).get("type_name"),
                "is_stop_trial": is_stop_trial,
                "intended_correct": intended_correct,
                "response_key": response,
                "rt_ms": rt,
                "delivery": {
                    "success": result.success, "method": result.method,
                    "actual_rt_ms": result.actual_rt_ms, "error": result.error,
                },
            })
            history.append({
                "condition": ctx.condition,
                "intended_correct": intended_correct,
                "rt": rt,
            })
            self._recent_errors.appendleft(not intended_correct)
            self._trial_count += 1
            await driver.wait_for_trial_end(page)
        await driver.wait_for_completion(page)
        data = await driver.retrieve_data(page)
        self._writer.save_experiment_data(data)


def _resolve_response(ctx, intended_correct, rng, taskcard):
    """SP10 response-key resolution.

    Priority:
    1. ctx.expected_correct (driver-provided)
    2. legacy taskcard.task_specific.key_map[condition] for migration
    3. random pick from ctx.allowed_responses

    None means withhold (e.g. stop-signal stop trial).
    """
    if ctx.expected_correct is None and not ctx.allowed_responses:
        return None  # withhold
    correct = ctx.expected_correct
    if correct is None and taskcard is not None:
        legacy = (taskcard.task_specific or {}).get("key_map", {}) if hasattr(taskcard, "task_specific") else {}
        cand = legacy.get(ctx.condition)
        if cand and cand not in ("dynamic", "dynamic_mapping"):
            correct = cand
    if correct is None:
        return rng.choice(list(ctx.allowed_responses)) if ctx.allowed_responses else None
    if intended_correct:
        return correct
    wrong = [k for k in ctx.allowed_responses if k != correct]
    return rng.choice(wrong) if wrong else None

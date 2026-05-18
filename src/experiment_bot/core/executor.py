from __future__ import annotations

import logging
import random

import numpy as np

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.distributions import ResponseSampler
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

    async def run(self, task_url):
        pass

    async def _run_session(self, page, driver) -> None:
        """SP10 driver-based trial loop."""
        from experiment_bot.drivers.base import TrialLoopState
        await driver.setup(page)
        history: list[dict] = []
        while True:
            state = await driver.loop_state(page)
            if state == TrialLoopState.COMPLETE:
                break
            if state == TrialLoopState.NEEDS_NAVIGATION:
                outcome = await driver.navigate(page)
                self._writer.log_trial({
                    "type": "navigation",
                    "action": outcome.action,
                    "details": dict(outcome.details),
                })
                continue
            ctx = await driver.get_trial_context(page)
            rt = self._sampler.sample(ctx.condition, history=history)
            intended_correct = self._py_rng.random() < self._config.performance.get_accuracy(ctx.condition)
            response = _resolve_response(ctx, intended_correct, self._py_rng, self._taskcard)
            result = await driver.deliver_response(page, response, rt)
            self._writer.log_trial({
                "type": "trial",
                "trial_index": self._trial_count,
                "stimulus_id": ctx.stimulus_id,
                "condition": ctx.condition,
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

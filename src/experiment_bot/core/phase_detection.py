from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

from experiment_bot.core.config import PhaseDetectionConfig, TaskPhase

logger = logging.getLogger(__name__)

# Sentinel returned (via module-level attribute) to inform the caller that
# COMPLETE was detected via a context-destroyed exception rather than the
# predicate evaluating to true.  The caller (trial loop) uses this to set
# loop_exit_reason = "context_destroyed" instead of "complete".
context_destroyed: bool = False


async def detect_phase(
    page: Page,
    config: PhaseDetectionConfig,
) -> TaskPhase:
    """Config-driven phase detection. Returns TaskPhase.TEST as default fallback.

    On exception during predicate evaluation (typically a Playwright context-
    destroyed error caused by page navigation), the function performs ONE short
    settle (0.25 s) followed by a single re-evaluation before falling back to
    COMPLETE.  This reduces transient false-COMPLETE detections during normal
    inter-trial navigation without slowing the hot normal path at all.

    The module-level ``context_destroyed`` flag is set to True when COMPLETE
    is derived from an exception rather than the predicate returning truthy,
    allowing callers to distinguish the two cases.
    """
    global context_destroyed
    context_destroyed = False

    for phase_name, js_expr in [
        ("complete", config.complete),
        ("loading", config.loading),
        ("instructions", config.instructions),
        ("attention_check", config.attention_check),
        ("feedback", config.feedback),
        ("practice", config.practice),
    ]:
        if js_expr:
            try:
                result = await page.evaluate(
                    f"(() => {{ try {{ return {js_expr}; }} catch(e) {{ return false; }} }})()"
                )
                if result:
                    return TaskPhase(phase_name)
            except Exception:
                # Exception on first eval — could be a transient navigation race.
                # Settle briefly and re-evaluate once before treating as COMPLETE.
                await asyncio.sleep(0.25)
                try:
                    result = await page.evaluate(
                        f"(() => {{ try {{ return {js_expr}; }} catch(e) {{ return false; }} }})()"
                    )
                    if result:
                        # Predicate confirmed true after settle — genuine complete.
                        return TaskPhase(phase_name)
                    # Re-eval returned falsy — the first exception was transient;
                    # don't treat this as COMPLETE; continue checking other phases.
                    continue
                except Exception:
                    # Context still destroyed after settle — page is gone.
                    context_destroyed = True
                    return TaskPhase.COMPLETE

    # No phase predicate matched — default to TEST (the trial loop's
    # "do work" state). `config.test` exists in the schema for symmetry
    # but is not consulted: TEST is always the fall-through.
    return TaskPhase.TEST

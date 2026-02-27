from __future__ import annotations

import logging

from playwright.async_api import Page

from experiment_bot.core.config import PhaseDetectionConfig, TaskPhase

logger = logging.getLogger(__name__)


async def detect_phase(page: Page, config: PhaseDetectionConfig) -> TaskPhase:
    """Config-driven phase detection. Returns TaskPhase.TEST as default fallback."""
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
                # Context destroyed (page navigated away) typically means complete
                return TaskPhase.COMPLETE

    if config.test:
        return TaskPhase.TEST
    return TaskPhase.TEST

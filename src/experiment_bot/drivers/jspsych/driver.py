"""JsPsychDriver: PlatformDriver for jsPsych 7.x experiments.

See vendor/jspsych/7.3.1/ for the version-pinned API anchor files.
The driver hooks pluginAPI.getKeyboardResponse to capture the per-trial
callback, then invokes it directly for response delivery.

Phase 3 of SP10. This file holds setup/can_handle/create only; the
remaining PlatformDriver methods are added in Tasks 13-16.
"""
from __future__ import annotations

import logging
from typing import ClassVar

from playwright.async_api import Page

from experiment_bot.drivers.base import (
    DeliveryResult, ExperimentData, NavigationOutcome,
    TrialContext, TrialLoopState, UnsupportedVersionError,
)

logger = logging.getLogger(__name__)


# JS that installs the response-callback hook. Stored as a module-level
# constant for readability; loaded by setup().
_INSTALL_HOOK_JS = """
(() => {
  if (window.__bot_hook_installed) return { ok: true, already: true };
  window.__bot_hook_installed = true;
  window.__bot_hook = { current: null, history: [] };
  if (!window.jsPsych || !window.jsPsych.pluginAPI) {
    return { ok: false, reason: 'no_pluginAPI' };
  }
  const orig = window.jsPsych.pluginAPI.getKeyboardResponse;
  if (typeof orig !== 'function') {
    return { ok: false, reason: 'no_getKeyboardResponse' };
  }
  // Monkey-patch: store the callback + valid_responses per call. Still
  // delegate to the original so jsPsych's own listener also registers
  // (preserves behavior if a real user happens to press a key).
  window.jsPsych.pluginAPI.getKeyboardResponse = function(params) {
    window.__bot_hook.current = {
      callback_function: params.callback_function,
      valid_responses: params.valid_responses,
      persist: params.persist,
      rt_method: params.rt_method,
      registered_at: performance.now(),
    };
    return orig.call(this, params);
  };
  return { ok: true };
})()
"""


class JsPsychDriver:
    """jsPsych 7.x platform driver."""

    SUPPORTED_VERSIONS: ClassVar[tuple[str, ...]] = ("7.3.1",)

    def __init__(self, version: str):
        self._version = version

    @classmethod
    async def can_handle(cls, page: Page) -> bool:
        """Match any page where window.jsPsych is defined."""
        try:
            return bool(await page.evaluate("typeof window.jsPsych !== 'undefined'"))
        except Exception as e:
            logger.warning("JsPsychDriver.can_handle: page.evaluate raised: %s", e)
            return False

    @classmethod
    async def create(cls, page: Page) -> "JsPsychDriver":
        """Read live version, check against SUPPORTED_VERSIONS, instantiate
        or raise UnsupportedVersionError."""
        version = await page.evaluate(
            "(window.jsPsych && typeof window.jsPsych.version === 'function') "
            "? window.jsPsych.version() : null"
        )
        if version not in cls.SUPPORTED_VERSIONS:
            raise UnsupportedVersionError(
                detected_version=str(version),
                supported_versions=cls.SUPPORTED_VERSIONS,
                missing_anchors=[f"vendor/jspsych/{version}/"],
            )
        return cls(version=version)

    async def setup(self, page: Page) -> None:
        """Install the pluginAPI.getKeyboardResponse hook. Idempotent;
        re-running setup on the same page is a no-op."""
        result = await page.evaluate(_INSTALL_HOOK_JS)
        if isinstance(result, dict) and result.get("ok") is False:
            logger.warning(
                "JsPsychDriver hook install reported: %s", result.get("reason"),
            )

    # Methods below are stubs; Tasks 13-16 implement them.

    async def loop_state(self, page: Page) -> TrialLoopState:
        raise NotImplementedError("Task 14 implements loop_state")

    async def navigate(self, page: Page) -> NavigationOutcome:
        raise NotImplementedError("Task 15 implements navigate")

    async def get_trial_context(self, page: Page) -> TrialContext:
        raise NotImplementedError("Task 14 implements get_trial_context")

    async def deliver_response(
        self, page: Page, response: str | None, rt_ms: float | None,
    ) -> DeliveryResult:
        """Deliver a response via the jsPsych callback hook.

        response=None means withhold (e.g. stop-signal stop trial) — no-op.
        rt_ms is the bot's sampled response time in milliseconds.
        """
        from time import perf_counter
        from experiment_bot.drivers.jspsych.responses import deliver

        if response is None:
            return DeliveryResult(
                success=True,
                delivered_at_ms=0.0,
                actual_rt_ms=rt_ms or 0.0,
                method="withhold_no_op",
            )
        start = perf_counter()
        result = await deliver(page, response, rt_ms or 0.0)
        elapsed_ms = (perf_counter() - start) * 1000
        return DeliveryResult(
            success=bool(result.get("ok")),
            delivered_at_ms=elapsed_ms,
            actual_rt_ms=rt_ms or 0.0,
            method="jspsych_callback_hook",
            error=result.get("reason") if not result.get("ok") else None,
        )

    async def wait_for_trial_end(self, page: Page) -> None:
        raise NotImplementedError("Task 15 implements wait_for_trial_end")

    async def wait_for_completion(self, page: Page) -> None:
        raise NotImplementedError("Task 15 implements wait_for_completion")

    async def retrieve_data(self, page: Page) -> ExperimentData:
        raise NotImplementedError("Task 16 implements retrieve_data")

    async def teardown(self, page: Page) -> None:
        # Defensive: remove the monkey-patch if possible.
        try:
            await page.evaluate(
                "(() => { if (window.__bot_hook_installed) {"
                " try { delete window.__bot_hook_installed; delete window.__bot_hook; } catch(e) {} } })()"
            )
        except Exception as e:
            logger.debug("teardown encountered: %s", e)

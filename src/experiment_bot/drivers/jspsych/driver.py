"""JsPsychDriver: PlatformDriver for jsPsych 7.x experiments.

See vendor/jspsych/7.3.1/ for the version-pinned API anchor files.
The driver hooks pluginAPI.getKeyboardResponse to capture the per-trial
callback, then invokes it directly for response delivery.

Phase 3 of SP10. This file holds setup/can_handle/create only; the
remaining PlatformDriver methods are added in Tasks 13-16.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import ClassVar

from playwright.async_api import Page

from experiment_bot.drivers.base import (
    DeliveryResult, DriverError, ExperimentData, NavigationOutcome,
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
    """jsPsych platform driver. Supports 7.3.1 and 6.0.5.

    The two version eras differ in API surface (e.g. `getCurrentTrial`
    vs `currentTrial`, `getProgress` vs `progress`, `trial.type` as
    class instance vs string), but the hook target —
    `pluginAPI.getKeyboardResponse` — is the same. Driver methods
    detect the live version's API at JS-evaluation time so a single
    driver covers both.
    """

    SUPPORTED_VERSIONS: ClassVar[tuple[str, ...]] = ("7.3.1", "6.0.5")

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
        """Detect the live jsPsych version and instantiate, or raise
        UnsupportedVersionError if unanchored. Detection order:

        1. v7+ exposes `jsPsych.version()` as a callable.
        2. Some versions expose `jsPsych.version` as a string property.
        3. Fall back to scanning <script src> for `jspsych-X.Y.Z/` —
           v6.0.5 (and most pre-v7) embed the version in the bundle
           path because the API itself doesn't expose it.
        """
        version = await page.evaluate(
            """(() => {
                if (!window.jsPsych) return null;
                try {
                  if (typeof window.jsPsych.version === 'function') {
                    return window.jsPsych.version();
                  }
                } catch (e) {}
                if (typeof window.jsPsych.version === 'string') {
                  return window.jsPsych.version;
                }
                // Last-resort: scan script srcs for jspsych-X.Y.Z/
                for (const s of document.scripts) {
                  const src = s.src || '';
                  const m = src.match(/jspsych-(\\d+\\.\\d+\\.\\d+)/);
                  if (m) return m[1];
                }
                return null;
            })()"""
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
        """Read jsPsych state via phases.read_loop_state and map to
        TrialLoopState. Unknown / error states default to
        NEEDS_NAVIGATION (the bot library will poll again)."""
        from experiment_bot.drivers.jspsych.phases import read_loop_state
        info = await read_loop_state(page)
        s = info.get("state")
        if s == "complete":
            return TrialLoopState.COMPLETE
        if s == "ready_for_trial":
            return TrialLoopState.READY_FOR_TRIAL
        return TrialLoopState.NEEDS_NAVIGATION

    async def navigate(self, page: Page) -> NavigationOutcome:
        """Advance jsPsych through the current non-trial phase."""
        from experiment_bot.drivers.jspsych.navigation import navigate_page
        info = await navigate_page(page)
        # Pause so jsPsych can process the click + transition before the
        # next loop_state poll. jsPsych's plugin advance hooks may
        # involve setTimeout or async work; 0.3s gives them room.
        await asyncio.sleep(0.3)
        return NavigationOutcome(
            action=info.get("action", "noop"),
            details={
                "type_name": info.get("type_name"),
                **info.get("details", {}),
            },
        )

    async def get_trial_context(self, page: Page) -> TrialContext:
        """Read the active trial + armed hook state from the page.
        Raises DriverError(kind='no_active_trial') if no active trial."""
        from experiment_bot.drivers.jspsych.phases import read_trial_context
        info = await read_trial_context(page)
        if info is None:
            raise DriverError(
                kind="no_active_trial",
                context={"reason": "no_armed_hook_or_no_current_trial"},
                recoverable=True,
            )
        return TrialContext(
            stimulus_id=info["stimulus_id"],
            condition=info["condition"],
            allowed_responses=tuple(info.get("allowed_responses") or ()),
            expected_correct=info.get("expected_correct"),
            response_window_ms=info.get("response_window_ms"),
            metadata=info.get("metadata", {}),
        )

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
        """Wait until the current trial actually ends.

        For plugins with `response_ends_trial: true` (html-keyboard-
        response default), the captured callback's after_response handler
        ends the trial promptly. For plugins like
        poldracklab-stop-signal where `response_ends_trial: false`, the
        trial keeps running for trial_duration ms after the bot's
        response — and the plugin may re-arm the keyboard listener
        within that window. Without waiting here, the bot's loop polls,
        sees the hook re-armed, fires again — producing multiple
        deliveries for a single platform trial.

        Snapshot the current trial reference (via Date.now()-keyed
        marker injected when the hook fires), then poll
        getCurrentTrial() until it differs or returns null. Falls back
        to a 1.5s timeout so a stuck trial doesn't hang the loop.
        """
        # Mark the trial we just fired for. Use a sentinel attribute on
        # the trial object so we don't depend on object identity across
        # page.evaluate boundaries.
        await page.evaluate("""
        (() => {
          try {
            let t = null;
            if (window.jsPsych) {
              if (typeof window.jsPsych.getCurrentTrial === 'function') {
                t = window.jsPsych.getCurrentTrial();
              } else if (typeof window.jsPsych.currentTrial === 'function') {
                t = window.jsPsych.currentTrial();
              }
            }
            if (t) {
              t.__bot_fired_at = (window.__bot_hook && window.__bot_hook.fire_count) || 0;
              window.__bot_hook.fire_count = (window.__bot_hook.fire_count || 0) + 1;
            }
          } catch(e) {}
        })()
        """)
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            try:
                # Returns true when current trial has no fire marker (= new trial)
                advanced = await page.evaluate("""
                (() => {
                  try {
                    let t = null;
                    if (window.jsPsych) {
                      if (typeof window.jsPsych.getCurrentTrial === 'function') {
                        t = window.jsPsych.getCurrentTrial();
                      } else if (typeof window.jsPsych.currentTrial === 'function') {
                        t = window.jsPsych.currentTrial();
                      }
                    }
                    if (!t) return true;
                    return t.__bot_fired_at == null;
                  } catch(e) { return true; }
                })()
                """)
            except Exception:
                return
            if advanced:
                return
            await asyncio.sleep(0.05)

    async def wait_for_completion(
        self, page: Page,
        timeout_s: float = 60.0,
        poll_interval_s: float = 0.5,
    ) -> None:
        """Poll jsPsych progress percent_complete; return when >= 100
        or when timeout elapses. v7: getProgress(). v6: progress() —
        but the v7 .progress getter throws MigrationError, so guard
        with typeof + try/catch."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                pct = await page.evaluate("""
                (() => {
                  if (!window.jsPsych) return 0;
                  let p = null;
                  try {
                    if (typeof window.jsPsych.getProgress === 'function') {
                      p = window.jsPsych.getProgress();
                    } else if (typeof window.jsPsych.progress === 'function') {
                      p = window.jsPsych.progress();
                    }
                  } catch (e) {}
                  return (p && p.percent_complete) || 0;
                })()
                """)
            except Exception as e:
                logger.warning("wait_for_completion: page.evaluate raised: %s", e)
                return
            if pct is not None and float(pct) >= 100.0:
                return
            await asyncio.sleep(poll_interval_s)

    async def retrieve_data(self, page: Page) -> ExperimentData:
        """Fetch jsPsych.data.get().json() and wrap as ExperimentData."""
        from experiment_bot.drivers.jspsych.data_export import fetch_data_json
        raw = await fetch_data_json(page)
        if raw is None:
            return ExperimentData(
                trials=[], format="json", raw="[]",
                metadata={"jspsych_version": self._version, "status": "no_data"},
            )
        try:
            import json
            trials = json.loads(raw)
            if not isinstance(trials, list):
                trials = []
        except json.JSONDecodeError as e:
            logger.warning("retrieve_data: JSON decode error: %s", e)
            trials = []
        return ExperimentData(
            trials=trials,
            format="json",
            raw=raw,
            metadata={"jspsych_version": self._version},
        )

    async def teardown(self, page: Page) -> None:
        # Defensive: remove the monkey-patch if possible.
        try:
            await page.evaluate(
                "(() => { if (window.__bot_hook_installed) {"
                " try { delete window.__bot_hook_installed; delete window.__bot_hook; } catch(e) {} } })()"
            )
        except Exception as e:
            logger.debug("teardown encountered: %s", e)

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experiment_bot.llm.protocol import LLMClient

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from experiment_bot.behavior.provider import ClickResponse, stim_response_elements
from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.stimulus import StimulusLookup, StimulusMatch
from experiment_bot.core.pilot_session import PilotSession
from experiment_bot.core.loop_diagnostics import LoopDiagnostics
from experiment_bot.core.outcome import classify_outcome
from experiment_bot.navigation.stuck import StuckDetector
from experiment_bot.output.writer import OutputWriter
from experiment_bot.core.phase_detection import detect_phase
from experiment_bot.output.data_capture import ConfigDrivenCapture
from experiment_bot.output.data_quality import compute_stall_flags, DEFAULT_CEILING_MS

logger = logging.getLogger(__name__)

# SP16: adaptive nav constants
_ADAPTIVE_NAV_STUCK_POLLS = 20
_ADAPTIVE_NAV_BUDGET = 10
# SP16 (generalized in Wave C1): adaptive nav fires only when a non-trial
# screen survives this many consecutive stuck detections without its DOM
# changing. For INSTRUCTIONS-phase screens a "detection" is one standard nav
# re-run; for any other phase label (the LLM-written phase predicates are
# advisory and can misclassify) a "detection" is one throttled advance
# attempt (>= _ADVANCE_MIN_SPACING_S apart) with no stimulus identify hit.
# Gating on a stuck DOM — never on raw stimulus-polling misses — prevents
# false-firing during normal between-trial gaps (fixation, ITI,
# response-window-closed), which would otherwise press keys that skip real
# trials.
_ADAPTIVE_NAV_STUCK_DETECTIONS = 2

# Human-paced advance throttle: minimum spacing (seconds) between two
# "press advance keys" actions on a no-stimulus screen. Documented in the
# commit that introduced this gate (af8cf4d, "human-paced advance throttle
# (_ADVANCE_MIN_SPACING_S=2.0)") but the constant itself was never actually
# defined, leaving a NameError latent in the "no stimulus match" miss branch
# whenever consecutive_misses landed on an advance_interval_polls multiple
# (found while adding A3 loop-diagnostics test coverage for that branch).
_ADVANCE_MIN_SPACING_S = 2.0

# Zero-progress watchdog: abort the trial loop if NO trial has completed
# after this many seconds of session time. The miss-counter guard cannot
# catch pages that never advance, because instructions/feedback handling
# legitimately resets the counter — observed live as a survey page looping
# indefinitely (never a trial, never an exit). Generous bound: slow
# multi-screen tasks reach their first trial within a few minutes.
_ZERO_TRIAL_WATCHDOG_S = 600.0


def _taskcard_to_config(tc):
    """Project a TaskCard into a TaskConfig the executor knows how to drive.

    Reads: tc.task, tc.stimuli, tc.navigation, tc.runtime, tc.task_specific,
    tc.performance. response_distributions are projected structurally (their
    KEYS identify trial-level conditions in _is_trial_stimulus); the naive
    behavior program supplies all behavioral content.
    """
    from experiment_bot.core.config import TaskConfig, DistributionConfig
    return TaskConfig(
        task=tc.task,
        stimuli=tc.stimuli,
        response_distributions={
            k: DistributionConfig(distribution=v.distribution, params={
                pk: pv for pk, pv in v.value.items() if pk != "distribution"
            })
            for k, v in tc.response_distributions.items()
        },
        performance=tc.performance,
        navigation=tc.navigation,
        task_specific=tc.task_specific,
        runtime=tc.runtime,
    )


class TaskExecutor:
    """Drives Playwright through a cognitive task using a pre-generated TaskConfig."""

    def __init__(
        self,
        config,  # TaskCard or TaskConfig
        *,
        seed: int | None = None,
        headless: bool = False,
        llm_client: "LLMClient | None" = None,  # SP16: enables adaptive nav
        keep_open: bool = False,  # leave the browser open after the session ends
        calibrate: bool = True,  # run the startup keypress-latency calibration pass
        behavior_provider=None,  # SP21: BehaviorSession — the behavioral layer (required)
    ):
        # The naive behavior program IS the behavioral layer; the executor
        # supplies only navigation, detection, delivery, and capture.
        if behavior_provider is None:
            raise ValueError(
                "TaskExecutor requires a behavior_provider (BehaviorSession "
                "wrapping a generated participant program). Run with "
                "--behavior-program <path-or-label/hash>."
            )
        self._behavior_provider = behavior_provider
        # If a TaskCard was passed, project to a TaskConfig view the executor knows.
        from experiment_bot.taskcard.types import TaskCard
        if isinstance(config, TaskCard):
            self._taskcard = config
            config = _taskcard_to_config(config)
        else:
            self._taskcard = None
        self._config = config
        self._headless = headless
        self._keep_open = keep_open
        self._calibrate = calibrate
        # Persisted to run_metadata.json for provenance. The seed selects the
        # behavior program's participant; the realized nav path of sessions
        # that invoke SP16 adaptive nav is recorded per-session in
        # bot_log.json (type:'adaptive_nav') for audit.
        self._session_seed = seed

        self._lookup = StimulusLookup(config)
        self._writer = OutputWriter()
        self._trial_count = 0
        self._prev_interrupt_detected: bool = False
        self._response_window_confirmed: bool = False  # Set by trial loop to skip redundant check
        self._last_advance_action: float = 0.0  # human-paced advance throttle (monotonic)
        self._seen_response_keys: set[str] = set()  # Track dynamically resolved keys

        # Resolve static key mappings from task_specific
        self._key_map = self._resolve_key_mapping(config)
        # Per-stimulus-id cache of fallback detection JS, populated lazily by
        # _stimulus_detection_js. Stimuli are immutable for the session so
        # the build cost is paid once per id.
        self._stimulus_detection_js_cache: dict[str, str | None] = {}
        # Cache interrupt JS — config is immutable so this never changes
        self._interrupt_js = self._build_interrupt_check_js()
        # Cache condition names — config is immutable, no need to recompute per trial
        self._navigation_condition_name: str = (
            config.runtime.navigation_stimulus_condition or "navigation"
        )
        self._attention_check_conditions: set[str] = set(
            config.runtime.attention_check.stimulus_conditions
        ) or {"attention_check", "attention_check_response"}

        # SP11 Phase 5a: CDP-channel keypress delivery (instantiated in .run())
        self._cdp_session = None
        self._deliverer = None
        self._calibration_run = None  # set if calibration pass runs
        self._delivery_channel_log: dict[str, int] = {}  # tally by channel
        self._fire_skip_log: list[dict] = []  # per-trial skip metadata

        # SP16: adaptive nav state
        self._llm_client = llm_client
        self._adaptive_nav_uses = 0
        self._adaptive_nav_diffs: list[str] = []
        self._runtime_nav_phases: list[dict] = []
        self._session_start: float = 0.0  # set at run() entry for session_t offsets

        # Task 2: trial-loop exit reason enum.
        # Set at each break in _trial_loop so run_metadata can distinguish a
        # naturally-complete session from one that terminated early (partial).
        # Values: "complete", "window_closed", "max_misses", "budget",
        #         "context_destroyed"
        self._loop_exit_reason: str = "complete"

        # Task 3: count non-Playwright JS eval exceptions by source so a malformed
        # Reasoner-emitted JS expression is visible in run_metadata rather than
        # silently degrading to None / chance keys.
        # Keys: "response_key_js", "response_window_js"
        self._js_eval_errors: dict[str, int] = {}

        # Task 6 (platform-004): data-capture visibility — populated by
        # _wait_for_completion so the run() finally block can write them into
        # run_metadata without needing a return value from the method.
        self._data_capture_written: bool = False
        self._data_capture_method: str = ""
        self._data_capture_failed: bool = False

        # A3: per-poll trial-loop diagnostics — accumulated at the trial
        # loop's existing branch points; written into both run_trace's
        # trial_loop stage and run_metadata.loop_diagnostics.
        self._loop_diagnostics = LoopDiagnostics()

        # A5b: capture-time stall flags — populated by _wait_for_completion
        # after a successful data capture; default explains why it's absent
        # (no capture attempted / capture failed) when never overwritten.
        self._data_quality: dict = {"stall_trials": None, "note": "no data captured"}

    @staticmethod
    def _resolve_key_mapping(config: TaskConfig) -> dict[str, str]:
        """Resolve key mappings from config.task_specific.key_map."""
        ts = config.task_specific
        if "key_map" in ts:
            return dict(ts["key_map"])
        return {}

    @property
    def _bot_log(self) -> list[dict]:
        """SP16: expose the writer's trial list for adaptive_nav logging + test access."""
        return self._writer._trials

    def _narrate(self, stage: str, detail: str) -> None:
        """SP12 Phase 2: narrate one stage transition to stdout.

        Emits a single line per major stage. The full 5-line readout
        is: navigate, calibration, trial_loop, wait_completion, save.
        Suppressible via --verbose (which switches to per-trial DEBUG
        logging via the standard logger; the `[sp12]` prefix makes
        these narration lines greppable in any case).
        """
        print(f"[sp12] {stage}: {detail}", flush=True)

    async def _run_calibration_pass(
        self, page: Page, n_keys: int | None = None,
    ) -> None:
        """SP11 Phase 5a/5b: run a calibration sequence using the
        configured deliverer; record the CalibrationResult in
        run_metadata for latency audit.

        No-op if no deliverer is configured (delivery_channel='none').
        Should be called after navigation completes (so the bot is
        inside a key-accepting state) and before _trial_loop starts.
        """
        if self._deliverer is None:
            logger.info("Calibration pass skipped: no deliverer configured.")
            return
        rt = self._config.runtime
        from experiment_bot.calibration.playwright_gate_dismisser import (
            PlaywrightGateDismisser,
        )
        from experiment_bot.calibration.runner import run_calibration
        if n_keys is None:
            n_keys = int(rt.calibration_n_keys)
        # Build a default keys sequence: cycle the bot's response keys
        # if available, else fall back to Space.
        response_keys = sorted(self._seen_response_keys) or [" "]
        # Pad/cycle to n_keys
        keys = [response_keys[i % len(response_keys)] for i in range(n_keys)]
        # Use the configured dwell as the intended target interval
        dwell = float(rt.timing.cdp_dwell_ms)
        intervals = [dwell] * n_keys
        try:
            self._calibration_run = await run_calibration(
                self._deliverer,
                gate_dismisser=PlaywrightGateDismisser(page),
                keys=keys,
                target_intervals_ms=intervals,
            )
            logger.info(
                f"Calibration pass complete: model="
                f"{self._calibration_run.result.model}, "
                f"n_correctly_recorded="
                f"{self._calibration_run.result.n_events_correctly_recorded}/"
                f"{n_keys}"
            )
        except Exception as e:
            logger.warning(f"Calibration pass failed: {e}; continuing un-calibrated.")
            self._calibration_run = None

    async def _setup_keypress_deliverer(self, page: Page, context) -> None:
        """SP11 Phase 5a: instantiate the configured KeypressDeliverer
        for response fires. Falls through quietly to the legacy
        page.keyboard.press path when channel='none' or when CDP isn't
        available (Firefox, WebKit, mocked tests)."""
        channel = self._config.runtime.delivery_channel
        if channel == "none":
            return
        timing = self._config.runtime.timing
        marker_js = timing.trial_marker_js or None
        records_js = timing.records_js or None
        dwell_ms = float(timing.cdp_dwell_ms)
        if channel == "cdp":
            try:
                from experiment_bot.calibration.cdp_deliverer import (
                    CDPDeliverer, DEFAULT_RECORDS_JS, DEFAULT_TRIAL_MARKER_JS,
                )
                self._cdp_session = await context.new_cdp_session(page)
                self._deliverer = CDPDeliverer(
                    page, self._cdp_session,
                    default_dwell_ms=dwell_ms,
                    trial_marker_js=marker_js or DEFAULT_TRIAL_MARKER_JS,
                    records_js=records_js or DEFAULT_RECORDS_JS,
                )
                return
            except Exception as e:
                logger.warning(
                    f"CDP session unavailable ({e}); falling back to "
                    f"page.keyboard.press path."
                )
                self._cdp_session = None
                self._deliverer = None
                return
        logger.warning(
            f"Unknown delivery_channel={channel!r}; keeping legacy "
            f"page.keyboard.press path."
        )

    async def _fire_response_key(self, page: Page, key: str) -> dict:
        """SP11 Phase 5a: fire a response keypress via the configured
        deliverer (CDP/keyboard) with trial-marker verify; falls back
        to page.keyboard.press when no deliverer is configured.

        Returns a metadata dict for bot_log:
          - channel: "cdp_dispatchKeyEvent" / "keyboard_press_fallback"
            / "page_keyboard_press" (legacy)
          - trial_marker_at_fire: integer or None
          - skipped: bool (verify-step trial-advance check)
          - skip_reason: str or None
        """
        if self._deliverer is None:
            await page.keyboard.press(key)
            self._delivery_channel_log["page_keyboard_press"] = (
                self._delivery_channel_log.get("page_keyboard_press", 0) + 1
            )
            return {
                "channel": "page_keyboard_press",
                "trial_marker_at_fire": None,
                "skipped": False,
                "skip_reason": None,
            }
        rec = await self._deliverer.deliver_at_trial_start(key, dwell_ms=0.0)
        channel = self._deliverer.DELIVERY_CHANNEL
        self._delivery_channel_log[channel] = (
            self._delivery_channel_log.get(channel, 0) + 1
        )
        if rec.skipped:
            self._fire_skip_log.append({
                "trial": self._trial_count,
                "key": key,
                "skip_reason": rec.skip_reason,
                "trial_marker": rec.trial_marker_at_fire,
            })
        return {
            "channel": channel,
            "trial_marker_at_fire": rec.trial_marker_at_fire,
            "skipped": rec.skipped,
            "skip_reason": rec.skip_reason,
        }

    async def _fire_response_click(self, page: Page, selector: str) -> dict:
        """Wave B1: deliver a click response on a response element's
        selector. Mirrors the feedback-selector click pattern (.first /
        visibility wait / click, bounded timeouts). A delivery failure is
        recorded in the metadata, never raised — the trial still logs.
        """
        meta: dict = {"method": "locator_click", "selector": selector}
        try:
            btn = page.locator(selector).first
            await btn.wait_for(state="visible", timeout=1500)
            await btn.click(timeout=1500)
        except Exception as e:
            logger.warning(f"Click delivery failed for {selector!r}: {e}")
            meta["error"] = str(e)
        return meta

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

        Handles None, empty string, the case-insensitive strict sentinels
        ("none", "null", "withhold", …), and compound strings that contain
        a strict sentinel as a whole word — e.g. the Reasoner sometimes
        emits creative phrases like "withhold (null)" or "no_response (null)"
        when refining a TaskCard. The compound is tokenized on non-word
        characters; if any token is a strict sentinel, the value is treated
        as a withhold instruction. Real Playwright key names ("ArrowLeft",
        "Space", letter keys) tokenize to themselves and never match.
        """
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        cleaned = value.strip().lower()
        if cleaned in TaskExecutor._WITHHOLD_SENTINELS:
            return True
        import re
        tokens = re.split(r"\W+", cleaned)
        return any(t and t in TaskExecutor._WITHHOLD_SENTINELS for t in tokens)

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
                except PlaywrightError as e:
                    # Benign: page context torn down by navigation — return None
                    logger.warning(f"response_key_js failed for {match.stimulus_id}: {e}")
                except Exception as e:
                    # Non-Playwright: likely a malformed Reasoner-emitted JS expression.
                    # Log with a stable greppable tag and count for run_metadata visibility.
                    logger.warning(f"[js_eval_error:response_key_js] {match.stimulus_id}: {e}")
                    self._js_eval_errors["response_key_js"] = self._js_eval_errors.get("response_key_js", 0) + 1

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
                except PlaywrightError as e:
                    # Benign: page context torn down by navigation — return None
                    logger.warning(f"task_specific.response_key_js failed: {e}")
                except Exception as e:
                    # Non-Playwright: likely a malformed Reasoner-emitted JS expression.
                    logger.warning(f"[js_eval_error:response_key_js] task_specific: {e}")
                    self._js_eval_errors["response_key_js"] = self._js_eval_errors.get("response_key_js", 0) + 1

        # Static key_map fallback (skip "dynamic" sentinel values and withhold sentinels)
        mapped = self._key_map.get(match.condition)
        if mapped and mapped not in ("dynamic_mapping", "dynamic"):
            if self._is_withhold_sentinel(mapped):
                return None
            self._seen_response_keys.add(mapped)
            return mapped

        return None

    def _is_trial_stimulus(self, match: StimulusMatch) -> bool:
        """Whether a stimulus is a trial the behavior program should answer.

        A stimulus is trial-level unless it plays a structural role: the
        navigation condition, an attention-check condition, or the
        mid-trial interrupt signal (detected inside a trial, never
        trial-initiating). Legacy expert-era cards inferred trial-ness
        from response_distributions; structural-only cards carry an empty
        dict there, which made every stimulus non-trial and silently
        produced 0-trial sessions (held-out flanker, 2026-07-06).
        """
        condition = match.condition
        if condition == self._navigation_condition_name:
            return False
        if condition in self._attention_check_conditions:
            return False
        interrupt_cond = getattr(
            self._config.runtime.trial_interrupt, "detection_condition", None
        )
        if interrupt_cond and condition == interrupt_cond:
            return False
        # Any other declared stimulus is a trial. In particular, key=None is
        # the DOCUMENTED withhold channel ("key name or null to withhold",
        # prompts/system.md) — go/nogo-style withhold trials are real trials
        # the behavior program must decide (respond = commission error).
        # The earlier response-channel requirement silently excluded them:
        # observed live as a 0.000 false-alarm rate because no-go trials
        # never reached the program. Passive displays (fixation, ITI) must
        # not be declared as stimuli at all (see prompts/system.md §1).
        return True

    async def run(self, task_url: str) -> None:
        """Execute the full task."""
        import time as _time
        self._session_start = _time.monotonic()
        task_name = self._config.task.name.replace(" ", "_").lower()
        run_dir = self._writer.create_run(task_name, self._config)

        async with PilotSession(
            headless=self._headless,
            viewport=self._config.runtime.timing.viewport,
            reading_delay_range=(3.0, 8.0),
        ) as session:
            page = session.page
            context = session.context

            try:
                logger.info(f"Navigating to {task_url}")
                _t0 = time.monotonic()
                await page.goto(task_url, wait_until="networkidle")
                self._narrate("navigate", f"loaded {task_url}")
                self._writer.record_trace(
                    "navigate", {"url": task_url},
                    duration_s=time.monotonic() - _t0,
                )

                # SP11 Phase 5a: open CDP session + construct deliverer
                await self._setup_keypress_deliverer(page, context)

                # Phase 1: Navigate instructions (per-phase with skip-on-fail)
                logger.info("Navigating instructions...")
                self._entry_nav_phase_results: list[dict] = []
                _t1 = time.monotonic()
                for nav_phase in self._config.navigation.phases:
                    attempt = await session.try_phase(nav_phase)
                    self._entry_nav_phase_results.append({
                        "phase": nav_phase.phase or "<unnamed>",
                        "action": nav_phase.action,
                        "target": nav_phase.target,
                        "key": nav_phase.key,
                        "success": attempt.success,
                        "error": attempt.error,
                    })
                    if not attempt.success:
                        logger.info(
                            f"Entry nav phase '{nav_phase.phase or '<unnamed>'}' "
                            f"skipped: {attempt.error}"
                        )
                self._writer.record_trace(
                    "entry_navigation",
                    {"phases": self._entry_nav_phase_results},
                    duration_s=time.monotonic() - _t1,
                )

                # SP11 Phase 5b: calibration pass (auto-invoked when a
                # deliverer is configured). Result is always applied to
                # the sampler.
                #
                # SP19: skippable. The pass is behaviorally inert on every
                # supported platform (it reports `too_few_events` because the
                # page never records its probe keypresses — SP7 layer-d /
                # scope L21 — so the applied adjustment is identity). On
                # platforms with no pre-trial idle window (cognition.run,
                # whose first test trial is live immediately) the pass's
                # ~27 s runtime is timestamped by the platform as the first
                # trial's RT, corrupting it. Disabling calibration removes
                # both the cost and that artifact with no behavioral change.
                _t0 = time.monotonic()
                if self._calibrate:
                    await self._run_calibration_pass(page)
                else:
                    logger.info("Calibration pass skipped (calibrate=False).")
                cal = self._calibration_run
                if cal is None:
                    self._narrate("calibration", "skipped")
                    self._writer.record_trace(
                        "calibration", {"status": "skipped"},
                        duration_s=time.monotonic() - _t0,
                    )
                else:
                    self._narrate(
                        "calibration",
                        f"model={cal.result.model} "
                        f"n_paired={cal.result.n_events_correctly_recorded}",
                    )
                    self._writer.record_trace(
                        "calibration",
                        {
                            "model": cal.result.model,
                            "n_paired": cal.result.n_events_correctly_recorded,
                        },
                        duration_s=time.monotonic() - _t0,
                    )

                # Phase 2: Trial loop
                logger.info("Entering trial loop...")
                _t0 = time.monotonic()
                await self._trial_loop(session, page)
                self._narrate("trial_loop", f"trials={self._trial_count}")
                self._writer.record_trace(
                    "trial_loop", {
                        "trials": self._trial_count,
                        "loop_exit_reason": self._loop_exit_reason,
                        "loop_diagnostics": self._loop_diagnostics.as_dict(),
                    },
                    duration_s=time.monotonic() - _t0,
                )

                # Hard-fail when the trial loop captured zero trials.
                # This catches the silent-failure mode where the bot can't
                # reach the experiment (stuck on instructions, navigation
                # incomplete, stimulus detector doesn't match the live DOM,
                # required JS state never set, etc.). Without this guard
                # the executor writes empty bot_log.json and exits 0,
                # which obscures real configuration problems behind
                # "successful" runs.
                if self._trial_count == 0:
                    raise RuntimeError(
                        "Executor captured 0 trials. The bot did not reach "
                        "the experiment's trial stage. Common causes: "
                        "navigation.phases is incomplete (bot couldn't click "
                        "past instructions), stimulus.detection.selector "
                        "doesn't match the live DOM, or required runtime JS "
                        "state (e.g. window.* variables) is never set. "
                        "Inspect the screenshot, the bot log, and "
                        "experiment_data.* in the run dir."
                    )

                # Phase 3: Wait for completion and data
                logger.info("Waiting for task completion...")
                _t0 = time.monotonic()
                await self._wait_for_completion(page)
                self._narrate("wait_completion", "ok")
                self._writer.record_trace(
                    "wait_completion", {"status": "ok"},
                    duration_s=time.monotonic() - _t0,
                )

            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                screenshot = await page.screenshot(type="png")
                self._writer.save_screenshot(screenshot, "error.png")
                raise
            finally:
                # A5a: captured here (not inside _save_outputs) so it reflects
                # the exception that triggered this finally block, not a
                # later save-time error.
                _in_flight_exc = sys.exc_info()[1]
                metadata = {
                    "task_name": task_name,
                    "task_url": task_url,
                    "total_trials": self._trial_count,
                    "headless": self._headless,
                    "session_seed": self._session_seed,
                }
                metadata["behavior_program"] = self._behavior_program_metadata()
                if self._taskcard is not None:
                    pb = getattr(self._taskcard, "produced_by", None)
                    metadata["taskcard_sha256"] = getattr(pb, "taskcard_sha256", "") if pb else ""
                # SP11 Phase 5a: persist delivery-channel + skip diagnostics
                metadata["delivery"] = {
                    "configured_channel": self._config.runtime.delivery_channel,
                    "channel_counts": dict(self._delivery_channel_log),
                    "fire_skip_count": len(self._fire_skip_log),
                    "fire_skip_samples": list(self._fire_skip_log[:20]),
                }
                if self._calibration_run is not None:
                    metadata["calibration"] = {
                        "model": self._calibration_run.result.model,
                        "mean_offset_ms": self._calibration_run.result.mean_offset_ms,
                        "sd_offset_ms": self._calibration_run.result.sd_offset_ms,
                        "n_correctly_recorded": (
                            self._calibration_run.result.n_events_correctly_recorded
                        ),
                        "channel_counts": dict(
                            self._calibration_run.delivery_channel_counts
                        ),
                    }
                # SP16: adaptive nav summary — aggregated counts for analysis scripts
                metadata["adaptive_nav"] = self._compute_adaptive_nav_summary()
                # Task 2: completeness signals — a nonzero partial session is no
                # longer indistinguishable from a whole one.  The ==0 hard-fail
                # above remains unchanged; these fields are ADDITIONAL signals so
                # downstream analysis can filter/flag partial
                # sessions without aborting.  Do NOT raise on early break —
                # held-out paradigms legitimately end early.
                metadata["loop_exit_reason"] = self._loop_exit_reason
                metadata["incomplete"] = self._loop_exit_reason != "complete"
                # A5a: outcome taxonomy — completed/zero_trials/nav_stall/
                # program_error/platform_error. See core/outcome.py for the
                # classification rules.
                metadata["outcome"] = classify_outcome(
                    self._loop_exit_reason, self._trial_count, _in_flight_exc,
                )
                # A3: per-poll trial-loop diagnostics (phase/window/identify/
                # advance/feedback/attention-check/nav-rerun counters).
                metadata["loop_diagnostics"] = self._loop_diagnostics.as_dict()
                # A5b: capture-time stall flags (see _wait_for_completion).
                metadata["data_quality"] = self._data_quality
                # robust-008: flag sessions where adaptive nav ran but the loop
                # didn't complete naturally — adaptive nav may have navigated
                # past trials, inflating/deflating the trial count.
                if self._adaptive_nav_uses > 0 and self._loop_exit_reason != "complete":
                    metadata["suspect_adaptive_nav"] = True
                # Task 3: surface JS-eval errors so a malformed Reasoner-emitted JS
                # expression is visible to the reviewer instead of silently degrading.
                metadata["js_eval_errors_by_source"] = dict(self._js_eval_errors)
                # Task 6 (platform-004): data-capture status so a silent export
                # failure is visible to the reviewer. failed=True means the method
                # was configured but raised an exception (vs. no-method-configured
                # which is written=False, failed=False and is expected).
                metadata["data_capture"] = {
                    "written": self._data_capture_written,
                    "method": self._data_capture_method,
                    "failed": self._data_capture_failed,
                }
                self._save_outputs(metadata)

            # keep_open: hold the browser open after the session finishes so the
            # final experiment state can be inspected. Waits until the user
            # closes the window manually (or the process is interrupted). Lives
            # inside the `async with PilotSession` so the browser is still alive.
            if self._keep_open:
                logger.info(
                    "keep_open: session finished; browser staying open. "
                    "Close the window (or Ctrl+C the process) to exit."
                )
                self._narrate("keep_open", "browser held open; close window to exit")
                try:
                    await page.wait_for_event("close", timeout=0)
                except Exception:
                    # Page/context may already be closed, or wait was interrupted.
                    pass

    def _save_outputs(self, metadata: dict) -> None:
        """Persist run_metadata + bot_log + run_trace, guarded.

        Runs in `run()`'s finally block. Unguarded, a mid-save failure left a
        plausible-looking but partial session directory (run_metadata present,
        bot_log/run_trace missing). Any save failure now writes a best-effort
        `.incomplete` marker — which downstream analysis and the collection
        script exclude as incomplete —
        and the save error is re-raised only when no task exception is already
        propagating (raising inside a finally block would mask the original).
        """
        # Must be captured at entry: inside the except block below,
        # sys.exc_info() would report the just-caught save error itself.
        task_exception_in_flight = sys.exc_info()[0] is not None
        try:
            # record_trace("save") must run BEFORE finalize() so the entry
            # lands in run_trace.json on disk. The "save" stage's duration_s
            # is left None because the work it bookends (save_metadata +
            # finalize itself) happens on either side of this call.
            self._writer.record_trace(
                "save", {"output": str(self._writer.run_dir)},
            )
            self._writer.save_metadata(metadata)
            self._writer.finalize()
        except Exception as save_err:
            self._writer.mark_incomplete(f"save failed: {save_err!r}")
            logger.error(f"Failed to persist session outputs: {save_err!r}")
            if not task_exception_in_flight:
                raise
        else:
            self._narrate("save", f"output={self._writer.run_dir}")

    async def _trial_loop(self, session, page: Page) -> None:
        """Main trial loop: detect stimulus, sample RT, respond."""
        # Task 2: reset exit reason to the expected normal value so each run
        # starts clean even if run() is called multiple times on the same object.
        self._loop_exit_reason = "complete"

        timing = self._config.runtime.timing
        stuck_detector = StuckDetector(timeout_seconds=timing.stuck_timeout_s)
        max_no_stimulus_polls = timing.max_no_stimulus_polls

        consecutive_misses = 0
        instructions_stuck_fp = ""
        instructions_stuck_count = 0
        # Wave C1: stuck-DOM tracking for NON-instructions phase labels (the
        # phase predicates are LLM-written and advisory — a stuck screen can
        # be misclassified as test/practice/loading). Sampled only at
        # throttled advance instants so normal between-trial gaps (changing
        # DOM, or shorter than the advance spacing) never accumulate.
        misc_stuck_fp = ""
        misc_stuck_count = 0
        while True:
            from experiment_bot.core import phase_detection as _pd
            if (self._trial_count == 0
                    and self._session_start > 0  # set by run(); unset in direct-loop tests
                    and (time.monotonic() - self._session_start) > _ZERO_TRIAL_WATCHDOG_S):
                logger.warning(
                    "Zero-progress watchdog: no trial completed after %.0fs — aborting loop",
                    _ZERO_TRIAL_WATCHDOG_S,
                )
                self._loop_exit_reason = "zero_progress_watchdog"
                break
            phase = await detect_phase(page, self._config.runtime.phase_detection)
            self._loop_diagnostics.record_phase(phase.value)
            if phase == TaskPhase.COMPLETE:
                # Capture the page state that triggered completion so post-hoc
                # diagnosis can tell genuine completion from a false-positive
                # (e.g., inter-block instruction text matching the LLM's
                # text-based completion heuristic).
                try:
                    body_snippet = await page.evaluate(
                        "(document.body.innerText || '').slice(0, 400)"
                    )
                except Exception:
                    body_snippet = "<page unavailable>"
                logger.info(
                    "Task complete detected at trial=%d. Body text: %r",
                    self._trial_count, body_snippet,
                )
                # Distinguish genuine COMPLETE from context-destroyed exception.
                if _pd.context_destroyed:
                    self._loop_exit_reason = "context_destroyed"
                else:
                    self._loop_exit_reason = "complete"
                break

            if phase == TaskPhase.ATTENTION_CHECK:
                await self._handle_attention_check(page)
                consecutive_misses = 0
                misc_stuck_fp, misc_stuck_count = "", 0
                continue

            if phase in (TaskPhase.FEEDBACK, TaskPhase.INSTRUCTIONS):
                probe = await self._lookup.identify(page)
                self._loop_diagnostics.record_identify(probe.condition if probe else None)
                if probe is None or not self._is_trial_stimulus(probe):
                    if phase == TaskPhase.FEEDBACK:
                        await self._handle_feedback(page)
                    else:
                        # In-trial nav re-run via the unified engine (skip-on-fail,
                        # same semantics as entry nav).
                        await self._nav_rerun(session)
                        # SP16: if the standard nav re-run left us on the SAME
                        # instruction DOM across consecutive detections, the
                        # TaskCard's fixed nav can't advance this screen — fire
                        # adaptive nav. Gated on a stuck INSTRUCTIONS DOM (not on
                        # stimulus-poll misses) so normal between-trial gaps never
                        # trigger it.
                        _fp = await self._dom_fingerprint(page)
                        if _fp and _fp == instructions_stuck_fp:
                            instructions_stuck_count += 1
                        else:
                            instructions_stuck_fp = _fp
                            instructions_stuck_count = 0
                        if (
                            instructions_stuck_count >= _ADAPTIVE_NAV_STUCK_DETECTIONS
                            and self._llm_client is not None
                            and self._adaptive_nav_uses < _ADAPTIVE_NAV_BUDGET
                        ):
                            await self._adaptive_nav_step(session, page)
                            instructions_stuck_count = 0
                            instructions_stuck_fp = ""
                    consecutive_misses = 0
                    misc_stuck_fp, misc_stuck_count = "", 0
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
                        self._loop_diagnostics.record_window_closed()
                        consecutive_misses += 1
                        ab = self._config.runtime.advance_behavior
                        if consecutive_misses % ab.advance_interval_polls == 0 and consecutive_misses < max_no_stimulus_polls:
                            self._loop_diagnostics.record_advance()
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
                            self._loop_exit_reason = "window_closed"
                            break
                        await asyncio.sleep(timing.poll_interval_ms / 1000.0)
                        continue
                    self._response_window_confirmed = True
                    self._loop_diagnostics.record_window_open()
                    consecutive_misses = 0
                    misc_stuck_fp, misc_stuck_count = "", 0
                except PlaywrightError:
                    # Benign: page context torn down by navigation — treat as window open
                    pass
                except Exception as e:
                    # Non-Playwright: likely a malformed Reasoner-emitted JS expression.
                    # Log with a stable greppable tag, count for run_metadata, treat as open.
                    logger.warning(f"[js_eval_error:response_window_js] {e}")
                    self._js_eval_errors["response_window_js"] = self._js_eval_errors.get("response_window_js", 0) + 1

            if phase in (TaskPhase.FEEDBACK, TaskPhase.INSTRUCTIONS):
                match = probe
            else:
                match = await self._lookup.identify(page)
                self._loop_diagnostics.record_identify(match.condition if match else None)
            if match is None:
                consecutive_misses += 1
                if consecutive_misses > max_no_stimulus_polls:
                    logger.warning("Too many consecutive misses, stopping trial loop")
                    self._loop_exit_reason = "max_misses"
                    break
                # Try pressing advance keys periodically to advance between-block screens.
                # Human-paced: advance actions are spaced >= _ADVANCE_MIN_SPACING_S apart.
                # Poll-cadence advancing trips anti-skim guards ('read the instructions
                # too quickly' re-read loops, seen live on the RDoC flanker flow) that a
                # human — and therefore the Stage-6 replay gate, which models this same
                # pacing — never trips.
                ab = self._config.runtime.advance_behavior
                if (consecutive_misses % ab.advance_interval_polls == 0
                        and consecutive_misses < max_no_stimulus_polls
                        and (time.monotonic() - self._last_advance_action) >= _ADVANCE_MIN_SPACING_S):
                    self._last_advance_action = time.monotonic()
                    self._loop_diagnostics.record_advance()
                    # Wave C1: a stable non-trial DOM across consecutive
                    # throttled advance attempts means the standard advance
                    # keys can't move this screen, whatever the (advisory)
                    # phase predicates labeled it — fire the same nav re-run
                    # + adaptive-nav path the INSTRUCTIONS branch uses.
                    # Never reached during an in-flight trial or when
                    # identify is matching (this is the match-is-None branch).
                    _fp = await self._dom_fingerprint(page)
                    if _fp and _fp == misc_stuck_fp:
                        misc_stuck_count += 1
                    else:
                        misc_stuck_fp = _fp
                        misc_stuck_count = 0
                    if misc_stuck_count >= _ADAPTIVE_NAV_STUCK_DETECTIONS:
                        logger.info(
                            "Stuck non-trial DOM (phase=%s) after %d advance attempts; "
                            "running nav re-run + adaptive nav",
                            phase.value, misc_stuck_count + 1,
                        )
                        await self._nav_rerun(session)
                        if (
                            self._llm_client is not None
                            and self._adaptive_nav_uses < _ADAPTIVE_NAV_BUDGET
                        ):
                            await self._adaptive_nav_step(session, page)
                        stuck_fp_before = misc_stuck_fp
                        misc_stuck_fp, misc_stuck_count = "", 0
                        # If the recovery actually changed the DOM, restart the
                        # miss accounting so the loop keeps polling the new
                        # screen instead of breaking on max_misses.
                        if await self._dom_fingerprint(page) != stuck_fp_before:
                            consecutive_misses = 0
                        await asyncio.sleep(timing.poll_interval_ms / 1000.0)
                        continue
                    logger.info(f"No stimulus for {consecutive_misses} polls, pressing advance keys")
                    if ab.pre_keypress_js:
                        try:
                            await page.evaluate(ab.pre_keypress_js)
                        except Exception:
                            # Page context may be torn down by navigation
                            pass
                    for key in ab.advance_keys:
                        await page.keyboard.press(key)
                    # Also try clicking any LLM-identified feedback/advance selectors
                    # (e.g. "Next" / "Continue" buttons). Reuses the selectors the
                    # Reasoner already wrote into the TaskCard — no paradigm-specific
                    # knowledge added here. Helps recover when navigation.phases is
                    # incomplete and the page expects clicks rather than keypresses.
                    for selector in ab.feedback_selectors:
                        try:
                            locator = page.locator(selector).first
                            if await locator.is_visible(timeout=200):
                                await locator.click(timeout=500)
                                logger.info(f"Clicked advance selector: {selector}")
                                break
                        except Exception:
                            continue
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
            misc_stuck_fp, misc_stuck_count = "", 0
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
            # the wrong trial. Prefer the paradigm's response_window_js when
            # extracted by Stage 1; fall back to the matched stimulus's own
            # detection JS so paradigms without a response_window_js still avoid
            # over-firing (SP5 root-caused this gap for Flanker, n-back, stroop).
            stim_cfg = next(
                (s for s in self._config.stimuli if s.id == match.stimulus_id),
                None,
            )
            fallback = self._stimulus_detection_js(stim_cfg) if stim_cfg else None
            if timing.response_window_js or fallback:
                await self._wait_for_trial_end(
                    page,
                    timing.response_window_js,
                    fallback_js=fallback,
                    timeout_s=timing.trial_end_timeout_s,
                )

    async def _wait_for_trial_end(
        self,
        page: Page,
        response_window_js: str | None,
        *,
        fallback_js: str | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        """Wait for the trial response window to close.

        Prefer `response_window_js` if present (Stage 1 extraction got
        it). Otherwise fall back to `fallback_js` (typically the matched
        stimulus's own detection JS — wait for it to stop matching).
        When both are None, return immediately (no-op behavior preserved
        for paradigms with neither signal).
        """
        js = response_window_js or fallback_js
        if not js:
            return
        poll_s = self._config.runtime.timing.poll_interval_ms / 1000.0
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                still_active = await page.evaluate(js)
                if not still_active:
                    return
            except Exception:
                # Page context may be torn down by navigation — treat as trial ended
                return
            await asyncio.sleep(poll_s)

    def _stimulus_detection_js(self, stim) -> str | None:
        """Return a JS expression that returns truthy while ``stim`` is
        currently on screen. Used as a fallback for `_wait_for_trial_end`
        when the paradigm's `runtime.timing.response_window_js` is
        missing (Stage 1 didn't extract it).

        Caches per-stimulus-id so the build cost is paid once.
        """
        cache_key = stim.id
        if cache_key in self._stimulus_detection_js_cache:
            return self._stimulus_detection_js_cache[cache_key]
        sel = stim.detection.selector
        if not sel:
            result = None
        elif stim.detection.method == "dom_query":
            sel_q = sel.replace("'", "\\'")
            result = f"document.querySelector('{sel_q}') !== null"
        elif stim.detection.method in ("js_eval", "canvas_state"):
            result = f"!!({sel})"
        else:
            result = None
        self._stimulus_detection_js_cache[cache_key] = result
        return result

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

    def _behavior_program_metadata(self) -> dict:
        """run_metadata fragment identifying the wired behavior program.
        Factored out of run()'s finally block so it's unit-testable without
        invoking the full (browser-dependent) run()."""
        return {
            "sha256": self._behavior_provider.program_sha256,
            "path": self._behavior_provider.program_path,
            "seed": self._behavior_provider.seed,
        }

    async def _execute_trial(self, page, match, cue=None) -> None:
        """SP21 naive arm: the behavior program supplies (key, rt); the
        executor supplies navigation, detection, delivery, and logging.
        No omission draw, no accuracy draw, no sampler, no temporal
        effects — a program expresses omission by returning key=None."""
        provider = self._behavior_provider
        trial_start = time.monotonic()
        condition = match.condition
        timing = self._config.runtime.timing
        if timing.response_window_js and not self._response_window_confirmed:
            await self._wait_for_response_window(page, timing.response_window_js)
            trial_start = time.monotonic()

        correct_key = await self._resolve_response_key(match, page)
        provider.observe_key(correct_key)
        # Wave B3: the already-computed trial context text (the logged `cue`)
        # is exposed to the program as ctx.stimulus_text.
        stimulus_text = str(cue) if cue is not None else None
        # Wave B1: clickable response options declared on the matched
        # stimulus — (label, selector) pairs; labels go to the program,
        # selectors resolve a returned click by index.
        stim_cfg = next(
            (s for s in self._config.stimuli if s.id == match.stimulus_id), None)
        response_elements = stim_response_elements(stim_cfg) if stim_cfg else ()
        resp = provider.respond(condition, correct_key, self._trial_count,
                                stimulus_text=stimulus_text,
                                response_elements=tuple(
                                    label for label, _sel in response_elements))
        rt_ms = resp.rt_ms

        interrupt_detected = False
        if self._interrupt_js:
            poll_interval = timing.poll_interval_ms / 1000.0
            while (time.monotonic() - trial_start) < rt_ms / 1000.0:
                if await self._check_interrupt(page, self._interrupt_js):
                    interrupt_detected = True
                    break
                await asyncio.sleep(poll_interval)

        interrupt_cfg = self._config.runtime.trial_interrupt
        if interrupt_detected:
            ssd_ms = (time.monotonic() - trial_start) * 1000
            decision = provider.on_interrupt(ssd_ms)
            # A program may withhold explicitly (decision is None) or commit to
            # respond but with no key (decision.key is None) — both mean "no
            # keypress fires"; treat them as the single withhold path so a
            # None key can never reach _fire_response_key. A ClickResponse
            # decision is always a commission (its index is validated).
            if decision is None or (not isinstance(decision, ClickResponse)
                                    and decision.key is None):
                self._writer.log_trial({
                    "trial": self._trial_count,
                    "stimulus_id": match.stimulus_id,
                    "condition": f"{interrupt_cfg.detection_condition}_withheld",
                    "response_key": None,
                    "sampled_rt_ms": round(rt_ms, 1),
                    "actual_rt_ms": None,
                    "omission": False,
                    "behavior_provider": True,
                })
                provider.record_outcome(condition, correct=True, rt_ms=None,
                                        interrupted=True)
                self._prev_interrupt_detected = True
                await asyncio.sleep(interrupt_cfg.inhibit_wait_ms / 1000.0)
                return
            remaining_s = (decision.rt_ms / 1000.0) - (time.monotonic() - trial_start)
            if remaining_s > 0:
                await asyncio.sleep(remaining_s)
            actual_rt = (time.monotonic() - trial_start) * 1000
            entry = {
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": f"{interrupt_cfg.detection_condition}_responded",
                "sampled_rt_ms": round(decision.rt_ms, 1),
                "actual_rt_ms": round(actual_rt, 1),
                "omission": False,
                "behavior_provider": True,
            }
            if isinstance(decision, ClickResponse):
                label, selector = response_elements[decision.element_index]
                entry["delivery"] = await self._fire_response_click(page, selector)
                entry["response_type"] = "click"
                entry["response_element"] = label
                entry["response_element_index"] = decision.element_index
                entry["response_key"] = None
            else:
                entry["delivery"] = await self._fire_response_key(page, decision.key)
                entry["response_key"] = decision.key
            self._writer.log_trial(entry)
            provider.record_outcome(condition, correct=False,
                                    rt_ms=decision.rt_ms, interrupted=True)
            self._prev_interrupt_detected = True
            return

        remaining = (rt_ms / 1000.0) - (time.monotonic() - trial_start)
        if remaining > 0:
            await asyncio.sleep(remaining)
        actual_rt = (time.monotonic() - trial_start) * 1000

        if isinstance(resp, ClickResponse):
            # Wave B1: click delivery — resolve the element's selector by
            # index and click it. Correctness mirrors the keypress rule:
            # the clicked option's label is compared to the resolved
            # correct key (the structural card carries the correct option's
            # label there for click-response tasks).
            label, selector = response_elements[resp.element_index]
            delivery_meta = await self._fire_response_click(page, selector)
            is_correct = (correct_key is not None and label == correct_key)
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_type": "click",
                "response_element": label,
                "response_element_index": resp.element_index,
                "response_key": None,
                "sampled_rt_ms": round(rt_ms, 1),
                "actual_rt_ms": round(actual_rt, 1),
                "omission": False,
                "delivery": delivery_meta,
                "behavior_provider": True,
                "cue": cue,
            })
            provider.record_outcome(condition, correct=is_correct,
                                    rt_ms=resp.rt_ms, interrupted=False)
            self._prev_interrupt_detected = False
            return

        if resp.key is None:
            self._writer.log_trial({
                "trial": self._trial_count,
                "stimulus_id": match.stimulus_id,
                "condition": condition,
                "response_key": None,
                "sampled_rt_ms": round(rt_ms, 1),
                "actual_rt_ms": None,
                "omission": False,
                "withheld": True,
                "behavior_provider": True,
            })
            provider.record_outcome(condition, correct=(correct_key is None),
                                    rt_ms=None, interrupted=False)
            self._prev_interrupt_detected = False
            return

        delivery_meta = await self._fire_response_key(page, resp.key)
        is_correct = (resp.key == correct_key)
        self._writer.log_trial({
            "trial": self._trial_count,
            "stimulus_id": match.stimulus_id,
            "condition": condition,
            "response_key": resp.key,
            "sampled_rt_ms": round(rt_ms, 1),
            "actual_rt_ms": round(actual_rt, 1),
            "omission": False,
            "delivery": delivery_meta,
            "behavior_provider": True,
            "cue": cue,
        })
        provider.record_outcome(condition, correct=is_correct,
                                rt_ms=resp.rt_ms, interrupted=False)
        self._prev_interrupt_detected = False

    async def _handle_attention_check(self, page: Page) -> None:
        """Handle attention check using config-driven response logic.

        Claude must provide response_js in the attention_check config —
        the executor has no built-in knowledge of attention check formats.
        """
        self._loop_diagnostics.record_attention_check()
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
        self._loop_diagnostics.record_feedback()
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

    async def _dom_fingerprint(self, page) -> str:
        """Short fingerprint of the current DOM head for stuck detection.

        Empty string when the page is unavailable (fingerprint comparisons
        treat "" as never-stuck, so a torn-down context can't trigger
        adaptive nav).
        """
        import hashlib
        try:
            dom = await page.evaluate(
                "document.body ? document.body.outerHTML.slice(0,4000) : ''"
            )
        except Exception:
            dom = ""
        if not isinstance(dom, str):
            dom = ""
        return hashlib.sha256(dom.encode()).hexdigest()[:16] if dom else ""

    async def _nav_rerun(self, session) -> None:
        """In-trial nav re-run via the unified engine (skip-on-fail, same
        semantics as entry nav). Each phase is attempted independently so one
        already-dismissed button can't crash the whole re-run."""
        self._loop_diagnostics.record_nav_rerun()
        for _nav_phase in self._config.navigation.phases:
            _attempt = await session.try_phase(_nav_phase)
            if not _attempt.success:
                logger.info(
                    "In-trial nav re-run phase %r skipped: %s",
                    _nav_phase.phase or "<unnamed>", _attempt.error,
                )

    async def _adaptive_nav_step(self, session, page) -> bool:
        """LLM-driven one-step adaptive nav. Returns True if the bot's DOM
        advanced after the proposed phase executed. Logs the attempt into
        bot_log with type 'adaptive_nav' for full auditability.

        The LLM call is bounded by self._adaptive_nav_uses < _ADAPTIVE_NAV_BUDGET;
        the caller is responsible for checking that gate before invoking.
        """
        import hashlib
        from experiment_bot.core.config import NavigationPhase
        from experiment_bot.reasoner.stage6_pilot import _propose_next_phase

        dom_before = await session.dom_snapshot()
        fp_before = hashlib.sha256(dom_before.encode()).hexdigest()[:16] if dom_before else ""

        try:
            phase_dict = await _propose_next_phase(
                self._llm_client, dom_before,
                self._runtime_nav_phases, self._adaptive_nav_diffs,
            )
        except Exception as e:
            logger.warning("Adaptive nav: LLM proposal failed: %s", e)
            self._adaptive_nav_uses += 1
            return False

        phase_dict.setdefault("steps", [])
        phase_dict.setdefault("key", "")
        phase_dict.setdefault("target", "")
        phase_dict.setdefault("duration_ms", 0)
        phase_dict.setdefault("phase", f"adaptive_{self._adaptive_nav_uses + 1}")
        new_phase = NavigationPhase.from_dict(phase_dict)

        attempt = await session.try_phase(new_phase)
        self._adaptive_nav_uses += 1

        dom_after = await session.dom_snapshot()
        fp_after = hashlib.sha256(dom_after.encode()).hexdigest()[:16] if dom_after else ""
        advanced = bool(fp_before and fp_after and fp_before != fp_after)

        self._runtime_nav_phases.append(phase_dict)
        self._adaptive_nav_diffs.append(
            f"Adaptive {self._adaptive_nav_uses}: "
            f"{phase_dict} (success={attempt.success}, advanced={advanced})"
        )

        # Bot_log audit entry (via writer, exposed as _bot_log property)
        self._writer.log_trial({
            "type": "adaptive_nav",
            "step": self._adaptive_nav_uses,
            "session_t": time.monotonic() - self._session_start,
            "phase": phase_dict,
            "success": attempt.success,
            "advanced": advanced,
            "error": attempt.error,
            "dom_fingerprint_before": fp_before,
            "dom_fingerprint_after": fp_after,
        })

        logger.info(
            "Adaptive nav step %d: action=%s success=%s advanced=%s",
            self._adaptive_nav_uses, phase_dict.get("action"), attempt.success, advanced,
        )
        return advanced

    def _compute_adaptive_nav_summary(self) -> dict:
        """SP16: summarise per-session adaptive nav usage for run_metadata.json.

        Filters bot_log entries by type=='adaptive_nav' to aggregate counts.
        Called from run() finalization so analysis scripts don't need to
        iterate bot_log entries themselves.
        """
        adaptive_entries = [e for e in self._bot_log if e.get("type") == "adaptive_nav"]
        return {
            "uses": self._adaptive_nav_uses,
            "budget": _ADAPTIVE_NAV_BUDGET,
            "successful_proposals": sum(1 for e in adaptive_entries if e.get("success")),
            "dom_advances": sum(1 for e in adaptive_entries if e.get("advanced")),
            "llm_disabled": self._llm_client is None,
        }

    def _stall_ceiling_ms(self) -> float:
        """A5b: the mechanical ceiling used to flag stalled rt values.

        4x the card's configured max response window when derivable from
        ``task_specific.trial_timing.max_response_time_ms`` (Stage 1's
        conventional location for it); otherwise a fixed 10s. This is a
        deliberately loose multiple — it exists to catch a hung poll or
        broken export recorded as a multi-second "response", not to gate on
        anything resembling a real human RT.
        """
        trial_timing = (self._config.task_specific or {}).get("trial_timing") or {}
        max_rw = trial_timing.get("max_response_time_ms") if isinstance(trial_timing, dict) else None
        try:
            max_rw = float(max_rw) if max_rw is not None else None
        except (TypeError, ValueError):
            max_rw = None
        if max_rw and max_rw > 0:
            return max_rw * 4.0
        return DEFAULT_CEILING_MS

    async def _wait_for_completion(self, page: Page) -> None:
        """Wait for task completion and capture experiment data."""
        await asyncio.sleep(
            self._config.runtime.timing.completion_settle_ms / 1000.0
        )

        capturer = ConfigDrivenCapture(self._config.runtime.data_capture)
        capture_result = await capturer.capture(page)
        # Record capture status for run_metadata (populated in run() finally block).
        self._data_capture_written = bool(capture_result.data)
        self._data_capture_method = self._config.runtime.data_capture.method or ""
        self._data_capture_failed = capture_result.failed
        if capture_result.data:
            ext = self._config.runtime.data_capture.format or "csv"
            self._writer.save_task_data(capture_result.data, f"experiment_data.{ext}")
            logger.info("Experiment data saved")
            # A5b: flag (never exclude) trials whose captured rt exceeds a
            # mechanical ceiling — signals a hung poll or bad export, not a
            # real human RT.
            self._data_quality = compute_stall_flags(
                capture_result.data, ext, self._stall_ceiling_ms(),
            )
        else:
            if capture_result.failed:
                logger.warning(
                    "Data capture failed — experiment_data export may be missing; "
                    "check run_metadata.data_capture.failed for details"
                )
            wait_s = self._config.runtime.timing.completion_wait_ms / 1000.0
            logger.info(f"No data captured, waiting {wait_s:.1f}s for platform data save")
            await asyncio.sleep(wait_s)

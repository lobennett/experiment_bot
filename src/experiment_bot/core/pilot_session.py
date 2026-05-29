"""Persistent Playwright session for Stage 6's pilot walker (SP15 Part B).

One browser instance lives for the entire walker loop. The walker calls
try_phase / probe_stimulus / poll_stimuli sequentially against the SAME
page, so each LLM refinement applies a delta to the live DOM rather than
re-running all prior phases on a fresh tab.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from playwright.async_api import (
    Browser, BrowserContext, Error as PlaywrightError, Page, async_playwright,
)

from experiment_bot.core.config import NavigationPhase, TaskPhase
from experiment_bot.core.phase_detection import detect_phase

if TYPE_CHECKING:
    from experiment_bot.core.config import RuntimeConfig

logger = logging.getLogger(__name__)

_PILOT_POLL_MS = 50
_NO_MATCH_EARLY_STOP = 100
_TIMEOUT_S = 300
# When the poll loop is stuck on an INSTRUCTIONS screen, it re-runs the configured
# nav each iteration. If that re-run does not change the DOM for this many
# consecutive iterations, the configured nav genuinely cannot advance the screen —
# break the attempt early (in ~seconds) so the Stage-6 walker can propose a NEW
# phase, instead of spinning the full _TIMEOUT_S (the INSTRUCTIONS branch never
# increments consecutive_misses, so the _NO_MATCH_EARLY_STOP guard cannot fire here).
_INSTRUCTIONS_STUCK_LIMIT = 3


@dataclass
class PhaseAttempt:
    success: bool
    dom_after: str
    error: str | None


@dataclass
class StimulusProbe:
    """One poll across all stimulus selectors. None if no stimulus matched."""
    match: object | None  # StimulusMatch — imported lazily to avoid circular
    dom_at_probe: str


class PilotSession:
    """Async context manager around a single Playwright browser + page.

    Methods are sequential — caller awaits each completion before issuing
    the next. No concurrency within a session.
    """

    def __init__(self, *, headless: bool = True, viewport: dict | None = None,
                 reading_delay_range: tuple[float, float] = (0.5, 1.0)):
        self._headless = headless
        self._viewport = viewport or {"width": 1280, "height": 800}
        self._reading_delay_range = reading_delay_range
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "PilotSession":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(viewport=self._viewport)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._playwright is not None:
                await self._playwright.stop()

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("PilotSession not entered")
        return self._context

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("PilotSession not entered")
        return self._page

    async def goto(self, url: str) -> str:
        await self.page.goto(url, wait_until="domcontentloaded")
        return await self.dom_snapshot()

    async def dom_snapshot(self, container_selector: str = "body") -> str:
        try:
            html = await self.page.evaluate(
                "(sel) => document.querySelector(sel)?.outerHTML || document.body.outerHTML",
                container_selector,
            )
            return (html or "")[:4000]
        except PlaywrightError:
            return "(snapshot failed)"

    async def press(self, key: str) -> None:
        await self.page.keyboard.press(key)

    async def try_phase(self, phase: NavigationPhase) -> PhaseAttempt:
        """Execute one navigation phase against the live page.

        Returns PhaseAttempt(success=True, dom_after=...) on completion,
        or PhaseAttempt(success=False, error=...) if the action failed
        (timeout, missing target, etc.). The session remains usable.
        """
        try:
            if phase.action == "click":
                await self._inject_reading_delay()
                loc = self.page.locator(phase.target).first
                await loc.wait_for(state="visible", timeout=1500)
                await loc.click()
            elif phase.action in ("press", "keypress"):
                await self._inject_reading_delay()
                if getattr(phase, "pre_js", ""):
                    try:
                        await self.page.evaluate(phase.pre_js)
                    except PlaywrightError:
                        pass  # page context may be torn down by prior nav
                await self.page.keyboard.press(phase.key)
            elif phase.action == "wait":
                await asyncio.sleep(phase.duration_ms / 1000.0)
            elif phase.action == "sequence":
                for step in phase.steps:
                    sub = NavigationPhase.from_dict(step)
                    sub_result = await self.try_phase(sub)
                    if not sub_result.success:
                        return PhaseAttempt(
                            success=False,
                            dom_after=await self.dom_snapshot(),
                            error=f"sequence step failed: {sub_result.error}",
                        )
            elif phase.action == "repeat":
                max_iterations = 20
                for _ in range(max_iterations):
                    stop = False
                    for step in phase.steps:
                        sub = NavigationPhase.from_dict(step)
                        sub_result = await self.try_phase(sub)
                        if not sub_result.success:
                            stop = True  # a sub-step failed → stop repeating
                            break
                    if stop:
                        break
            else:
                logger.warning("Unsupported navigation action %r (recorded)", phase.action)
                return PhaseAttempt(
                    success=False,
                    dom_after=await self.dom_snapshot(),
                    error=f"unknown action: {phase.action}",
                )
        except Exception as e:
            return PhaseAttempt(
                success=False,
                dom_after=await self.dom_snapshot(),
                error=str(e),
            )
        return PhaseAttempt(
            success=True,
            dom_after=await self.dom_snapshot(),
            error=None,
        )

    async def probe_stimulus(self, lookup) -> StimulusProbe:
        """Single poll across all stimulus selectors. Returns match or None."""
        match = await lookup.identify(self.page)
        dom = await self.dom_snapshot()
        return StimulusProbe(match=match, dom_at_probe=dom)

    async def poll_stimuli(
        self, lookup, *, max_polls: int = _NO_MATCH_EARLY_STOP,
        advance_keys: list[str] | None = None,
        poll_ms: int = _PILOT_POLL_MS,
    ) -> dict:
        """Multi-poll loop lifted from PilotRunner.run.

        Operates on self._page instead of constructing its own browser.
        Returns a dict with the fields PilotDiagnostics expects:
        trials_completed, trials_with_stimulus_match, conditions_observed,
        selector_results, phase_results, dom_snapshots, anomalies, trial_log.
        """
        config = lookup.config
        pilot_cfg = config.pilot
        target = set(pilot_cfg.target_conditions)
        container_sel = pilot_cfg.stimulus_container_selector or "body"

        selector_results = {stim.id: {"matches": 0, "polls": 0} for stim in config.stimuli}
        pd_cfg = config.runtime.phase_detection
        phase_results: dict[str, dict] = {}
        for phase_name in ["complete", "loading", "instructions", "attention_check",
                           "feedback", "practice", "test"]:
            js_expr = getattr(pd_cfg, phase_name, "")
            if js_expr:
                phase_results[phase_name] = {"fired": False, "first_fire_trial": None}

        dom_snapshots: list[dict] = []
        anomalies: list[str] = []
        trial_log: list[dict] = []
        conditions_seen: set[str] = set()
        trials_completed = 0
        trials_with_match = 0
        consecutive_misses = 0
        instructions_no_advance = 0
        first_match_snapped = False

        start_time = time.monotonic()

        while True:
            if time.monotonic() - start_time > _TIMEOUT_S:
                anomalies.append(f"Hard timeout after {_TIMEOUT_S}s")
                break

            phase = await detect_phase(self._page, config.runtime.phase_detection)
            phase_name = phase.value
            if phase_name in phase_results and not phase_results[phase_name]["fired"]:
                phase_results[phase_name]["fired"] = True
                phase_results[phase_name]["first_fire_trial"] = trials_completed

            if phase == TaskPhase.COMPLETE:
                break

            if phase == TaskPhase.FEEDBACK:
                # Always advance past feedback.
                ab = config.runtime.advance_behavior
                for key in ab.advance_keys:
                    await self._page.keyboard.press(key)
                # Wait for feedback to clear
                for _ in range(50):
                    await asyncio.sleep(0.1)
                    check = await detect_phase(self._page, config.runtime.phase_detection)
                    if check != TaskPhase.FEEDBACK:
                        break
                continue

            if phase == TaskPhase.INSTRUCTIONS:
                _dom_before = await self.dom_snapshot(container_sel)
                for _nav_phase in config.navigation.phases:
                    _attempt = await self.try_phase(_nav_phase)
                    if not _attempt.success:
                        logger.info(
                            "Pilot nav re-run phase %r skipped: %s",
                            _nav_phase.phase or "<unnamed>", _attempt.error,
                        )
                _dom_after = await self.dom_snapshot(container_sel)
                if _dom_after == _dom_before:
                    # Configured nav did not move this instruction screen.
                    instructions_no_advance += 1
                    if instructions_no_advance >= _INSTRUCTIONS_STUCK_LIMIT:
                        anomalies.append(
                            f"INSTRUCTIONS screen did not advance after "
                            f"{instructions_no_advance} nav re-runs; configured "
                            f"navigation cannot get past this screen"
                        )
                        dom_snapshots.append(
                            {"trigger": "instructions_stuck", "html": _dom_after}
                        )
                        break
                else:
                    instructions_no_advance = 0  # progress made; reset
                continue

            # Poll all stimulus selectors individually
            for stim in config.stimuli:
                selector_results[stim.id]["polls"] += 1
                try:
                    matched = False
                    if stim.detection.method == "dom_query":
                        el = await self._page.query_selector(stim.detection.selector)
                        matched = el is not None
                    elif stim.detection.method in ("js_eval", "canvas_state"):
                        result = await self._page.evaluate(stim.detection.selector)
                        matched = bool(result)
                    elif stim.detection.method == "text_content":
                        el = await self._page.query_selector(stim.detection.selector)
                        if el:
                            text = await el.text_content()
                            matched = stim.detection.pattern in (text or "")
                    if matched:
                        selector_results[stim.id]["matches"] += 1
                except Exception as e:
                    logger.debug(f"Pilot selector check failed for {stim.id}: {e}")

            # Use StimulusLookup for the actual match
            match = await lookup.identify(self._page)
            if match is None:
                consecutive_misses += 1
                if consecutive_misses == 50:
                    dom_snapshots.append({
                        "trigger": "no_match_50_polls",
                        "html": await self._snapshot_dom(self._page, container_sel),
                    })
                if consecutive_misses >= max_polls:
                    anomalies.append(f"{consecutive_misses} consecutive polls with no stimulus match")
                    break
                if consecutive_misses % 50 == 0:
                    ab = config.runtime.advance_behavior
                    for key in ab.advance_keys:
                        await self._page.keyboard.press(key)
                await asyncio.sleep(poll_ms / 1000.0)
                continue

            # Match found
            consecutive_misses = 0
            conditions_seen.add(match.condition)
            trials_completed += 1
            trials_with_match += 1

            if not first_match_snapped:
                dom_snapshots.append({
                    "trigger": "first_stimulus_match",
                    "html": await self._snapshot_dom(self._page, container_sel),
                })
                first_match_snapped = True

            trial_log.append({
                "trial": trials_completed,
                "stimulus_id": match.stimulus_id,
                "condition": match.condition,
                "response_key": match.response_key,
            })

            # Press response key (no RT timing). Filter withhold sentinels.
            from experiment_bot.core.executor import TaskExecutor
            key = match.response_key
            if TaskExecutor._is_withhold_sentinel(key) or key in ("dynamic", "dynamic_mapping"):
                km = config.task_specific.get("key_map", {})
                fallback = km.get(match.condition)
                if fallback and fallback not in ("dynamic", "dynamic_mapping") \
                        and not TaskExecutor._is_withhold_sentinel(fallback):
                    await self._page.keyboard.press(fallback)
                # else: skip the keypress entirely (withhold trial)
            else:
                await self._page.keyboard.press(key)

            await asyncio.sleep(poll_ms / 1000.0)

            # Check stopping criteria
            if trials_completed >= pilot_cfg.min_trials and (not target or conditions_seen >= target):
                break

        return {
            "trials_completed": trials_completed,
            "trials_with_stimulus_match": trials_with_match,
            "conditions_observed": sorted(conditions_seen),
            "selector_results": selector_results,
            "phase_results": phase_results,
            "dom_snapshots": dom_snapshots,
            "anomalies": anomalies,
            "trial_log": trial_log,
        }

    async def _inject_reading_delay(self) -> None:
        lo, hi = self._reading_delay_range
        if hi > 0:
            import random
            await asyncio.sleep(random.uniform(lo, hi))

    @staticmethod
    async def _snapshot_dom(page: Page, container_selector: str) -> str:
        try:
            html = await page.evaluate(
                "(sel) => document.querySelector(sel)?.outerHTML || document.body.outerHTML",
                container_selector,
            )
            return html[:2000] if html else "(empty)"
        except Exception:
            return "(snapshot failed)"

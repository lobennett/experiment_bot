from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from playwright.async_api import Page, async_playwright

from experiment_bot.core.config import TaskConfig, TaskPhase
from experiment_bot.core.phase_detection import detect_phase
from experiment_bot.core.stimulus import StimulusLookup
from experiment_bot.navigation.navigator import InstructionNavigator

logger = logging.getLogger(__name__)

_PILOT_POLL_MS = 50
_NO_MATCH_EARLY_STOP = 100
_TIMEOUT_S = 300
# Pilot-side floor on max_blocks so paradigms whose Reasoner-emitted
# pilot_validation_config.max_blocks is 1 (because the practice block
# is "the only block we want to test") still progress past the
# practice-block feedback into the test block. The Reasoner's intent
# is preserved as a lower bound on what the pilot WILL run; this
# floor extends it when the test phase is what we actually need to
# observe to verify selectors.
_MIN_PILOT_BLOCKS = 3


@dataclass
class PilotDiagnostics:
    trials_completed: int
    trials_with_stimulus_match: int
    conditions_observed: list[str]
    conditions_missing: list[str]
    selector_results: dict[str, dict]   # stimulus_id -> {matches, polls}
    phase_results: dict[str, dict]      # phase -> {fired, first_fire_trial}
    dom_snapshots: list[dict]           # [{trigger, html}]
    anomalies: list[str]
    trial_log: list[dict]

    @classmethod
    def crashed(cls, error_message: str) -> PilotDiagnostics:
        return cls(
            trials_completed=0, trials_with_stimulus_match=0,
            conditions_observed=[], conditions_missing=[],
            selector_results={}, phase_results={}, dom_snapshots=[],
            anomalies=[f"Pilot crashed: {error_message}"],
            trial_log=[],
        )

    @property
    def all_conditions_observed(self) -> bool:
        return len(self.conditions_missing) == 0

    @property
    def match_rate(self) -> float:
        return self.trials_with_stimulus_match / max(self.trials_completed, 1)

    def to_report(self) -> str:
        lines = [
            "## Pilot Run Diagnostic Report",
            "",
            "### Summary",
            f"- Trials completed: {self.trials_completed}",
            f"- Trials with stimulus match: {self.trials_with_stimulus_match}/{self.trials_completed}",
            f"- Conditions observed: {self.conditions_observed}",
        ]
        if self.conditions_missing:
            lines.append(f"- Conditions MISSING: {self.conditions_missing}")
        lines.append("")

        # Selector results
        lines.append("### Selector Results")
        for stim_id, result in self.selector_results.items():
            matches = result.get("matches", 0)
            polls = result.get("polls", 0)
            pct = (matches / polls * 100) if polls > 0 else 0
            suffix = "   <- NEVER MATCHED" if matches == 0 and polls > 0 else ""
            lines.append(f"- {stim_id}: {matches} matches / {polls} polls ({pct:.1f}%){suffix}")
        lines.append("")

        # DOM snapshots
        for snap in self.dom_snapshots:
            lines.append(f"### DOM Snapshot ({snap.get('trigger', 'unknown')})")
            lines.append(snap.get("html", "(empty)"))
            lines.append("")

        # Phase detection
        lines.append("### Phase Detection")
        for phase, result in self.phase_results.items():
            fired = result.get("fired", False)
            trial = result.get("first_fire_trial")
            if fired:
                lines.append(f"- {phase}: fired on trial {trial}")
            else:
                lines.append(f"- {phase}: never fired")
        lines.append("")

        # Trial log summary
        if self.trial_log:
            lines.append("### Trial Log (first 20)")
            for entry in self.trial_log[:20]:
                lines.append(f"- Trial {entry.get('trial')}: {entry.get('stimulus_id')} ({entry.get('condition')})")
            if len(self.trial_log) > 20:
                lines.append(f"  ... and {len(self.trial_log) - 20} more")
            lines.append("")

        # Anomalies
        if self.anomalies:
            lines.append("### Anomalies")
            for a in self.anomalies:
                lines.append(f"- {a}")
            lines.append("")

        return "\n".join(lines)


class PilotRunner:
    async def run(self, config: TaskConfig, url: str, headless: bool = False) -> PilotDiagnostics:
        pilot_cfg = config.pilot
        lookup = StimulusLookup(config)
        navigator = InstructionNavigator(reading_delay_range=(1.0, 2.0))

        # Validate target_conditions
        stim_conditions = {stim.response.condition for stim in config.stimuli}
        target = set(pilot_cfg.target_conditions)
        if target and not target.issubset(stim_conditions):
            unknown = target - stim_conditions
            logger.warning(f"Pilot target_conditions {unknown} not in stimulus conditions {stim_conditions}")

        # Tracking state
        selector_results = {stim.id: {"matches": 0, "polls": 0} for stim in config.stimuli}
        pd_cfg = config.runtime.phase_detection
        phase_results: dict[str, dict] = {}
        for phase_name in ["complete", "loading", "instructions", "attention_check", "feedback", "practice", "test"]:
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
        blocks_completed = 0
        container_sel = pilot_cfg.stimulus_container_selector or "body"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(viewport=config.runtime.timing.viewport)
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded")
                await navigator.execute_all(page, config.navigation)

                dom_snapshots.append({
                    "trigger": "after_navigation",
                    "html": await self._snapshot_dom(page, container_sel),
                })

                start_time = time.monotonic()
                first_match_snapped = False

                while True:
                    if time.monotonic() - start_time > _TIMEOUT_S:
                        anomalies.append(f"Hard timeout after {_TIMEOUT_S}s")
                        break

                    phase = await detect_phase(page, config.runtime.phase_detection)
                    phase_name = phase.value
                    if phase_name in phase_results and not phase_results[phase_name]["fired"]:
                        phase_results[phase_name]["fired"] = True
                        phase_results[phase_name]["first_fire_trial"] = trials_completed

                    if phase == TaskPhase.COMPLETE:
                        break

                    if phase == TaskPhase.FEEDBACK:
                        # Always advance past feedback. Stops are bounded by
                        # min_trials + target_conditions, _TIMEOUT_S wall
                        # clock, and _NO_MATCH_EARLY_STOP consecutive misses.
                        # We do NOT use max_blocks as a hard stop because
                        # paradigms with trial-by-trial feedback would never
                        # reach min_trials. (max_blocks is now advisory; it
                        # influences logging only.)
                        blocks_completed += 1
                        ab = config.runtime.advance_behavior
                        for key in ab.advance_keys:
                            await page.keyboard.press(key)
                        # Wait for feedback to clear
                        for _ in range(50):
                            await asyncio.sleep(0.1)
                            check = await detect_phase(page, config.runtime.phase_detection)
                            if check != TaskPhase.FEEDBACK:
                                break
                        continue

                    if phase == TaskPhase.INSTRUCTIONS:
                        await navigator.execute_all(page, config.navigation)
                        continue

                    # Poll all stimulus selectors individually
                    for stim in config.stimuli:
                        selector_results[stim.id]["polls"] += 1
                        try:
                            matched = False
                            if stim.detection.method == "dom_query":
                                el = await page.query_selector(stim.detection.selector)
                                matched = el is not None
                            elif stim.detection.method in ("js_eval", "canvas_state"):
                                result = await page.evaluate(stim.detection.selector)
                                matched = bool(result)
                            elif stim.detection.method == "text_content":
                                el = await page.query_selector(stim.detection.selector)
                                if el:
                                    text = await el.text_content()
                                    matched = stim.detection.pattern in (text or "")
                            if matched:
                                selector_results[stim.id]["matches"] += 1
                        except Exception as e:
                            # Page context may be torn down by navigation
                            logger.debug(f"Pilot selector check failed for {stim.id}: {e}")

                    # Use StimulusLookup for the actual match
                    match = await lookup.identify(page)
                    if match is None:
                        consecutive_misses += 1
                        if consecutive_misses == 50:
                            dom_snapshots.append({
                                "trigger": "no_match_50_polls",
                                "html": await self._snapshot_dom(page, container_sel),
                            })
                        if consecutive_misses >= _NO_MATCH_EARLY_STOP:
                            anomalies.append(f"{consecutive_misses} consecutive polls with no stimulus match")
                            break
                        if consecutive_misses % 50 == 0:
                            ab = config.runtime.advance_behavior
                            for key in ab.advance_keys:
                                await page.keyboard.press(key)
                        await asyncio.sleep(_PILOT_POLL_MS / 1000.0)
                        continue

                    # Match found
                    consecutive_misses = 0
                    conditions_seen.add(match.condition)
                    trials_completed += 1
                    trials_with_match += 1

                    if not first_match_snapped:
                        dom_snapshots.append({
                            "trigger": "first_stimulus_match",
                            "html": await self._snapshot_dom(page, container_sel),
                        })
                        first_match_snapped = True

                    trial_log.append({
                        "trial": trials_completed,
                        "stimulus_id": match.stimulus_id,
                        "condition": match.condition,
                        "response_key": match.response_key,
                    })

                    # Press response key (no RT timing). Filter withhold
                    # sentinels — same set the executor accepts as
                    # "no-keypress" instructions. Pressing the literal
                    # string "withhold" (or "none", etc.) crashes Playwright.
                    from experiment_bot.core.executor import TaskExecutor
                    key = match.response_key
                    if TaskExecutor._is_withhold_sentinel(key) or key in ("dynamic", "dynamic_mapping"):
                        km = config.task_specific.get("key_map", {})
                        fallback = km.get(match.condition)
                        if fallback and fallback not in ("dynamic", "dynamic_mapping") \
                                and not TaskExecutor._is_withhold_sentinel(fallback):
                            await page.keyboard.press(fallback)
                        # else: skip the keypress entirely (withhold trial)
                    else:
                        await page.keyboard.press(key)

                    await asyncio.sleep(_PILOT_POLL_MS / 1000.0)

                    # Check stopping criteria
                    if trials_completed >= pilot_cfg.min_trials and (not target or conditions_seen >= target):
                        break

            finally:
                await browser.close()

        missing = sorted(target - conditions_seen)
        return PilotDiagnostics(
            trials_completed=trials_completed,
            trials_with_stimulus_match=trials_with_match,
            conditions_observed=sorted(conditions_seen),
            conditions_missing=missing,
            selector_results=selector_results,
            phase_results=phase_results,
            dom_snapshots=dom_snapshots,
            anomalies=anomalies,
            trial_log=trial_log,
        )

    @staticmethod
    async def _snapshot_dom(page: Page, container_selector: str) -> str:
        try:
            html = await page.evaluate(
                "(sel) => document.querySelector(sel)?.outerHTML || document.body.outerHTML",
                container_selector,
            )
            return html[:2000] if html else "(empty)"
        except Exception:
            # Page context may be torn down by navigation
            return "(snapshot failed)"

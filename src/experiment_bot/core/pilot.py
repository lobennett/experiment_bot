from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from playwright.async_api import Page

from experiment_bot.core.config import TaskConfig
from experiment_bot.core.pilot_session import PilotSession
from experiment_bot.core.stimulus import StimulusLookup

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

    @property
    def dom_fingerprint(self) -> str:
        """Stable hash of the latest DOM snapshot's HTML. Empty string if
        no snapshots captured. Used by Stage 6's stuck-detection guard
        to recognize when refinements aren't moving the bot off a screen.
        """
        if not self.dom_snapshots:
            return ""
        latest = self.dom_snapshots[-1].get("html", "")
        if not latest:
            return ""
        return hashlib.sha256(latest.encode("utf-8")).hexdigest()[:16]

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
        """Backward-compatible facade. Constructs a PilotSession, runs all
        nav phases serially, polls stimuli with the configured criteria, and
        returns a PilotDiagnostics. Equivalent behavior to the prior
        implementation but uses one persistent browser instance throughout.
        """
        lookup = StimulusLookup(config)
        viewport = config.runtime.timing.viewport
        container_sel = config.pilot.stimulus_container_selector or "body"

        async with PilotSession(headless=headless, viewport=viewport) as session:
            await session.goto(url)
            crash_error: str | None = None
            dom_snapshots: list[dict] = [
                {
                    "trigger": "after_navigation",
                    "html": await session.dom_snapshot(container_sel),
                },
            ]

            # Run nav phases serially
            for phase in config.navigation.phases:
                attempt = await session.try_phase(phase)
                if not attempt.success:
                    crash_error = attempt.error
                    dom_snapshots.append({"trigger": "crash", "html": attempt.dom_after})
                    break

            if crash_error is None:
                result = await session.poll_stimuli(
                    lookup,
                    max_polls=_NO_MATCH_EARLY_STOP,
                    advance_keys=config.runtime.advance_behavior.advance_keys,
                )
                result_snaps = result.pop("dom_snapshots", [])
                dom_snapshots.extend(result_snaps)
                target = set(config.pilot.target_conditions)
                conditions_observed = result.get("conditions_observed", [])
                conditions_missing = sorted(target - set(conditions_observed))
                return PilotDiagnostics(
                    trials_completed=result.get("trials_completed", 0),
                    trials_with_stimulus_match=result.get("trials_with_stimulus_match", 0),
                    conditions_observed=conditions_observed,
                    conditions_missing=conditions_missing,
                    selector_results=result.get("selector_results", {}),
                    phase_results=result.get("phase_results", {}),
                    dom_snapshots=dom_snapshots,
                    anomalies=result.get("anomalies", []),
                    trial_log=result.get("trial_log", []),
                )

            # Crash branch
            return PilotDiagnostics(
                trials_completed=0,
                trials_with_stimulus_match=0,
                conditions_observed=[],
                conditions_missing=sorted(config.pilot.target_conditions),
                selector_results={},
                phase_results={},
                dom_snapshots=dom_snapshots,
                anomalies=[f"Pilot crashed: {crash_error}"],
                trial_log=[],
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
            return "(snapshot failed)"

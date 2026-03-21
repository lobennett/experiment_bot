from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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

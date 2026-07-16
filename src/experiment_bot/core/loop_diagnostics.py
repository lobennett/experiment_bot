"""Per-poll trial-loop diagnostics (A3).

A 0-trial session previously required a hand-built instrumented probe to
diagnose why the bot never reached the experiment. ``LoopDiagnostics``
accumulates cheap counters at the trial loop's existing branch points
(phase detections, response-window checks, stimulus-identify results,
advance actions, feedback/attention-check handling, in-trial nav re-runs)
so a puzzling session can be diagnosed from the saved artifacts alone.

Counters only: no strings per poll, no DOM captures. Written into both
``run_trace.json``'s ``trial_loop`` stage and ``run_metadata.json``'s
``loop_diagnostics`` field.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoopDiagnostics:
    phase_counts: dict[str, int] = field(default_factory=dict)
    response_window_open: int = 0
    response_window_closed: int = 0
    identify_hits: dict[str, int] = field(default_factory=dict)
    identify_misses: int = 0
    advance_actions: int = 0
    feedback_handled: int = 0
    attention_checks_handled: int = 0
    in_trial_nav_reruns: int = 0

    def record_phase(self, phase: str) -> None:
        self.phase_counts[phase] = self.phase_counts.get(phase, 0) + 1

    def record_window_open(self) -> None:
        self.response_window_open += 1

    def record_window_closed(self) -> None:
        self.response_window_closed += 1

    def record_identify(self, condition: str | None) -> None:
        """Record one identify() outcome: a hit (by condition) or a miss."""
        if condition is None:
            self.identify_misses += 1
        else:
            self.identify_hits[condition] = self.identify_hits.get(condition, 0) + 1

    def record_advance(self) -> None:
        self.advance_actions += 1

    def record_feedback(self) -> None:
        self.feedback_handled += 1

    def record_attention_check(self) -> None:
        self.attention_checks_handled += 1

    def record_nav_rerun(self) -> None:
        self.in_trial_nav_reruns += 1

    def as_dict(self) -> dict:
        return {
            "phase_counts": dict(self.phase_counts),
            "response_window_open": self.response_window_open,
            "response_window_closed": self.response_window_closed,
            "identify_hits": dict(self.identify_hits),
            "identify_misses": self.identify_misses,
            "advance_actions": self.advance_actions,
            "feedback_handled": self.feedback_handled,
            "attention_checks_handled": self.attention_checks_handled,
            "in_trial_nav_reruns": self.in_trial_nav_reruns,
        }

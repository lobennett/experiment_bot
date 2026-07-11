"""Session outcome classification (A5a).

``classify_outcome`` is a small pure function so every combination is
unit-testable without a browser. It is called once, from ``run()``'s
``finally`` block, with the trial loop's exit reason, the trial count, and
the in-flight exception (``None`` on a clean run).

Taxonomy (mutually exclusive, in priority order):
  - platform_error: the exception is a Playwright error (browser/network).
  - zero_trials / nav_stall: the exception is the executor's own 0-trial
    hard-fail RuntimeError (raised only when trial_count == 0). Both cases
    hit that same RuntimeError; ``nav_stall`` is the more specific label
    used when the loop's own exit reason was ``max_misses`` (the bot polled
    for a stimulus and never found one — a navigation problem). Any other
    exit reason (e.g. ``window_closed``, ``context_destroyed``) with zero
    trials stays the generic ``zero_trials``.
  - program_error: any other exception. Exceptions raised while calling
    into the generated behavior program (``ProtocolViolation`` from
    ``behavior.provider``, or any exception the program's own code raises)
    fall here; so does a RuntimeError with trial_count > 0, since the
    0-trial hard-fail is the only RuntimeError the executor itself raises.
  - completed: no exception and at least one trial was recorded.
"""
from __future__ import annotations

from playwright.async_api import Error as PlaywrightError


def classify_outcome(
    loop_exit_reason: str,
    trial_count: int,
    exc: BaseException | None,
) -> str:
    if exc is not None:
        if isinstance(exc, PlaywrightError):
            return "platform_error"
        if isinstance(exc, RuntimeError) and trial_count == 0:
            if loop_exit_reason in ("max_misses", "zero_progress_watchdog"):
                return "nav_stall"
            return "zero_trials"
        return "program_error"
    if trial_count > 0:
        return "completed"
    if loop_exit_reason in ("max_misses", "zero_progress_watchdog"):
        return "nav_stall"
    return "zero_trials"

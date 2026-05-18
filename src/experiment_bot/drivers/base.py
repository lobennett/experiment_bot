"""SP10 driver base types + Protocol contract.

A PlatformDriver implements the interface the bot library uses to talk to
a specific platform (jsPsych, cognition.run, PsychoJS, ...). Concrete
drivers implement these methods; the bot library never depends on any
specific platform.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

from playwright.async_api import Page


class TrialLoopState(Enum):
    NEEDS_NAVIGATION = "needs_navigation"
    READY_FOR_TRIAL = "ready_for_trial"
    COMPLETE = "complete"


@dataclass(frozen=True)
class TrialContext:
    """Per-trial state the driver hands to the bot library."""
    stimulus_id: str
    condition: str
    allowed_responses: tuple[str, ...]
    expected_correct: str | None
    response_window_ms: int | None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryResult:
    """Telemetry from `deliver_response`."""
    success: bool
    delivered_at_ms: float
    actual_rt_ms: float
    method: str
    error: str | None = None


@dataclass(frozen=True)
class NavigationOutcome:
    """Telemetry from `navigate`."""
    action: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentData:
    """Output of `retrieve_data`. The Oracle reads `trials` for analysis."""
    trials: list[Mapping[str, Any]]
    format: Literal["csv", "json"]
    raw: bytes | str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class DriverError(Exception):
    """Structured error from a driver method.

    `recoverable=True` signals the bot library may retry the operation
    once; `recoverable=False` aborts the session.
    """
    def __init__(
        self, kind: str, context: Mapping[str, Any] | None = None,
        recoverable: bool = False,
    ):
        super().__init__(f"{kind}: {context}")
        self.kind = kind
        self.context = dict(context or {})
        self.recoverable = recoverable


class UnsupportedVersionError(DriverError):
    """Raised by Driver.create() when the live platform version isn't
    anchored. Bot library catches and switches to DiagnosticDriver."""
    def __init__(
        self, detected_version: str, supported_versions: tuple[str, ...],
        missing_anchors: list[str],
    ):
        super().__init__(
            kind="unsupported_version",
            context={
                "detected_version": detected_version,
                "supported_versions": supported_versions,
                "missing_anchors": missing_anchors,
            },
            recoverable=False,
        )
        self.detected_version = detected_version
        self.supported_versions = supported_versions
        self.missing_anchors = missing_anchors


@runtime_checkable
class PlatformDriver(Protocol):
    """Contract every platform driver implements.

    Methods are async. Concrete drivers may also expose driver-specific
    init logic (e.g., `JsPsychDriver.create(page)` classmethod for the
    version-check construction path).
    """

    @classmethod
    async def can_handle(cls, page: Page) -> bool:
        """Cheap DOM/window inspection. No LLM, no side effects."""
        ...

    async def setup(self, page: Page) -> None:
        """One-time per-session driver init. May install runtime hooks
        (e.g., monkey-patch the platform's keyboard handler), set focus."""
        ...

    async def loop_state(self, page: Page) -> TrialLoopState:
        """Polled by the bot library's outer loop. Cheap."""
        ...

    async def navigate(self, page: Page) -> NavigationOutcome:
        """When loop_state == NEEDS_NAVIGATION, advance the page state.
        May click instructions, dismiss feedback, respond to attention
        checks. Returns telemetry."""
        ...

    async def get_trial_context(self, page: Page) -> TrialContext:
        """When READY_FOR_TRIAL, return the active trial's context."""
        ...

    async def deliver_response(
        self, page: Page, response: str | None, rt_ms: float | None,
    ) -> DeliveryResult:
        """Make the platform record (response, rt_ms). response=None
        means withhold."""
        ...

    async def wait_for_trial_end(self, page: Page) -> None:
        """Block until the platform has moved past the current trial."""
        ...

    async def wait_for_completion(self, page: Page) -> None:
        """Block until the experiment is over."""
        ...

    async def retrieve_data(self, page: Page) -> ExperimentData:
        """Pull the platform's exported data."""
        ...

    async def teardown(self, page: Page) -> None:
        """Pre-close cleanup. Often no-op."""
        ...

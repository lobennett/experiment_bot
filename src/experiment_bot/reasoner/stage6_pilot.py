"""SP10 Stage 6 pilot — thin driver-based smoke.

Under SP10, the platform driver owns all page-touching concerns
(identification, phase recognition, stimulus detection, response
delivery, data export). Stage 6's job shrinks to: instantiate the
SP10 TaskExecutor against the source URL with the provided TaskCard,
let it run for a short window, and confirm:

  - identify_driver returned a registered driver (not DiagnosticDriver)
  - the session reached the trial loop (>= MIN_TRIALS trials logged)
  - the driver retrieved non-empty experiment_data

If any check fails, the pilot returns status="fail" with the diagnostic
report path (when DiagnosticDriver fired) or a structured reason. The
old SP1-era iterative refinement loop (pilot_refinement_N.diff) is
removed — under SP10 the failure modes are localized to the driver,
so refining a TaskCard rarely helps; a driver fix is the right action.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


MIN_TRIALS = 3  # minimum trial count to declare a pilot pass


@dataclass
class PilotResult:
    """Pilot outcome shape consumed by the Reasoner pipeline."""
    status: str  # "pass" | "fail"
    n_trials: int
    diagnostic_report_path: str | None
    error: str | None
    pilot_md: str


def _build_pilot_md(taskcard_dict: dict, result: PilotResult) -> str:
    """Compose the pilot.md report alongside the TaskCard."""
    lines = [
        f"# Pilot — {taskcard_dict.get('task', {}).get('name', '?')}",
        "",
        f"Status: **{result.status.upper()}**",
        f"Trials reached: {result.n_trials}",
        f"Diagnostic report: {result.diagnostic_report_path or 'n/a'}",
        f"Recommended driver: {taskcard_dict.get('recommended_driver', 'unknown')}",
        "",
    ]
    if result.error:
        lines.append("## Error")
        lines.append("```")
        lines.append(result.error)
        lines.append("```")
    lines.append("")
    lines.append(
        "Under SP10, pilot is a thin driver-based smoke. Failure -> "
        "investigate the driver (or write a new one if DiagnosticDriver "
        "fired). Iterative TaskCard refinement is no longer attempted."
    )
    return "\n".join(lines)


async def run_pilot(
    taskcard,
    url: str,
    *,
    max_runtime_s: float = 90.0,
    headless: bool = True,
) -> PilotResult:
    """Run a thin driver-based smoke and return PilotResult.

    The TaskExecutor's run() handles driver identification, session
    execution, and data retrieval. We import locally to avoid a circular
    dependency with the executor package.

    Best-effort timeout: if the executor hangs (e.g. driver hook fails
    to arm), the pilot returns status="fail" with a timeout reason.
    """
    from experiment_bot.core.executor import TaskExecutor

    executor = TaskExecutor(taskcard, headless=headless)
    try:
        await asyncio.wait_for(executor.run(url), timeout=max_runtime_s)
    except asyncio.TimeoutError:
        result = PilotResult(
            status="fail",
            n_trials=executor._trial_count,
            diagnostic_report_path=None,
            error=f"pilot exceeded max_runtime_s={max_runtime_s}",
            pilot_md="",
        )
        result.pilot_md = _build_pilot_md(
            taskcard.to_dict() if hasattr(taskcard, "to_dict") else {}, result,
        )
        return result
    except Exception as e:
        result = PilotResult(
            status="fail",
            n_trials=executor._trial_count,
            diagnostic_report_path=None,
            error=str(e),
            pilot_md="",
        )
        result.pilot_md = _build_pilot_md(
            taskcard.to_dict() if hasattr(taskcard, "to_dict") else {}, result,
        )
        return result

    # Inspect run_metadata for status + diagnostic_report_path
    run_dir = executor._writer.run_dir
    status = "fail"
    diagnostic_path = None
    error = None
    if run_dir:
        meta_path = Path(run_dir) / "run_metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                if meta.get("status") == "diagnostic_mode":
                    diagnostic_path = meta.get("diagnostic_report_path")
                    error = "DiagnosticDriver fired"
                elif meta.get("status") == "ok" and executor._trial_count >= MIN_TRIALS:
                    status = "pass"
                else:
                    error = (
                        f"status={meta.get('status')!r}, "
                        f"trials={executor._trial_count} (need >= {MIN_TRIALS})"
                    )
            except Exception as e:
                error = f"could not read run_metadata.json: {e}"

    result = PilotResult(
        status=status,
        n_trials=executor._trial_count,
        diagnostic_report_path=diagnostic_path,
        error=error,
        pilot_md="",
    )
    result.pilot_md = _build_pilot_md(
        taskcard.to_dict() if hasattr(taskcard, "to_dict") else {}, result,
    )
    return result


def run_stage6(taskcard, url: str, **kwargs: Any) -> PilotResult:
    """Sync entry point for the pipeline. Wraps run_pilot in asyncio.run."""
    return asyncio.run(run_pilot(taskcard, url, **kwargs))

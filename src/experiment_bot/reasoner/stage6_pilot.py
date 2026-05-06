"""Stage 6: live-DOM pilot validation of the Reasoner's structural output.

Runs the partial TaskCard against the live experiment URL via Playwright,
captures diagnostics (selector match rates, phase firings, DOM snapshots,
condition coverage), and on failure either refines the partial via Claude
or hard-fails — depending on `max_retries`.

The pilot exercises only structural fields (stimuli, navigation,
runtime). It does not sample RTs or check temporal effects. Pilot runs
between Stage 5 (sensitivity) and TaskCard finalization, so refinements
target the same fields Stage 1 produced.
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

from experiment_bot.core.config import (
    NavigationConfig, PerformanceConfig, PilotConfig, RuntimeConfig,
    SourceBundle, StimulusConfig, TaskConfig, TaskMetadata,
)
from experiment_bot.core.pilot import PilotDiagnostics, PilotRunner
from experiment_bot.llm.protocol import LLMClient
from experiment_bot.reasoner.normalize import normalize_partial
from experiment_bot.reasoner.stage1_structural import _extract_json
from experiment_bot.reasoner.validate import validate_stage1_output
from experiment_bot.taskcard.types import ReasoningStep

logger = logging.getLogger(__name__)


class PilotValidationError(RuntimeError):
    """Raised when pilot validation fails after exhausting refinement retries."""


REFINEMENT_PROMPT = """\
You previously produced structural fields for an experiment-bot TaskCard.
A pilot run executed those fields against the live experiment URL via
Playwright and captured diagnostics. Below are the original fields, the
pilot's diagnostic report, and the experiment source. Fix the structural
fields based on the pilot evidence.

## Your Original Structural Fields
{partial_json}

## Pilot Diagnostic Report
{diagnostic_report}

## Original Experiment Source (excerpt)
{source_summary}

## Instructions

The pilot's evidence is ground truth — selectors that NEVER MATCHED do
not match the live DOM, phases that NEVER FIRED do not match, conditions
listed as MISSING were not produced by the live experiment with your
configuration. Fix accordingly:

1. **Stimuli with NEVER MATCHED selectors:** rewrite using the actual
   DOM structure shown in the snapshots. Read the snapshot HTML and
   write a CSS or JS expression that matches what's actually rendered.
2. **Missing conditions:** the pilot couldn't reach trials of these
   conditions. Either the navigation isn't getting past instructions
   to the test phase, or the stimulus detector for those conditions
   doesn't match.
3. **Phase expressions that never fired:** check against the snapshots
   and fix the JS expression for the affected phase.
4. **Empty navigation.phases when the page has multi-screen entry
   flow:** examine the DOM snapshots for fullscreen prompts, instruction
   carousels, consent screens, etc. Each requires a navigation phase
   (click on the right selector or press the right key).

Fix ONLY structural fields: stimuli, navigation, runtime.advance_behavior,
runtime.phase_detection, runtime.data_capture, task_specific. Do NOT
modify response_distributions, temporal_effects, between_subject_jitter,
or performance.accuracy/omission_rate — those are set by later Reasoner
stages and the pilot's evidence does not bear on them.

Return ONLY a JSON object containing the fields you changed. Unchanged
fields can be omitted; the pipeline will splice your output into the
existing partial. Return JSON only, no preamble.
"""


def _partial_to_pilot_config(partial: dict) -> TaskConfig:
    """Build a TaskConfig from a Reasoner partial that's runnable for pilot.

    Only structural fields are populated; response_distributions and
    temporal_effects are left empty since pilot doesn't sample RTs.
    """
    pilot_dict = partial.get("pilot_validation_config", partial.get("pilot", {}))
    return TaskConfig(
        task=TaskMetadata.from_dict(partial.get("task", {})),
        stimuli=[StimulusConfig.from_dict(s) for s in partial.get("stimuli", [])],
        response_distributions={},  # pilot doesn't sample RTs
        performance=PerformanceConfig.from_dict(
            partial.get("performance", {"accuracy": {}})
        ),
        navigation=NavigationConfig.from_dict(partial.get("navigation", {"phases": []})),
        task_specific=partial.get("task_specific", {}),
        pilot=PilotConfig.from_dict(pilot_dict),
        runtime=RuntimeConfig.from_dict(partial.get("runtime", {})),
    )


def _pilot_passed(diagnostics: PilotDiagnostics, config: TaskConfig) -> tuple[bool, list[str]]:
    """Return (passed, reasons_failed). Pass criteria:

    - At least pilot.min_trials trials completed with stimulus matches.
    - All target_conditions observed (if specified).
    - No anomalies of severity (the pilot runner currently logs all
      anomalies as strings; we treat any non-empty anomalies list as
      a failure signal but the diagnostic report is the ground truth).
    """
    reasons: list[str] = []
    min_trials = max(1, config.pilot.min_trials)
    if diagnostics.trials_with_stimulus_match < min_trials:
        reasons.append(
            f"only {diagnostics.trials_with_stimulus_match} trials matched a "
            f"stimulus (need at least {min_trials})"
        )
    if diagnostics.conditions_missing:
        reasons.append(
            f"target conditions never observed: {diagnostics.conditions_missing}"
        )
    if diagnostics.anomalies:
        reasons.append(
            f"pilot recorded {len(diagnostics.anomalies)} anomaly/anomalies: "
            f"{diagnostics.anomalies[:3]}"
        )
    return (len(reasons) == 0, reasons)


async def _refine_partial(
    client: LLMClient, partial: dict, diagnostics: PilotDiagnostics, bundle: SourceBundle,
) -> dict:
    """Ask Claude to fix structural fields based on the pilot diagnostic.

    Returns a NEW partial with refined structural fields spliced in;
    behavioral fields (response_distributions, temporal_effects, etc.)
    are preserved unchanged.
    """
    # Build a minimal source summary (same shape Stage 1 sees)
    source_parts = [f"## Page HTML\n{bundle.description_text[:5000]}"]
    for fname, content in bundle.source_files.items():
        source_parts.append(f"## File: {fname}\n{content[:30000]}")
    source_summary = "\n\n".join(source_parts)

    structural_only = {
        k: v for k, v in partial.items()
        if k in {
            "task", "stimuli", "navigation", "runtime", "task_specific",
            "performance", "pilot_validation_config",
        }
    }
    user = REFINEMENT_PROMPT.format(
        partial_json=json.dumps(structural_only, indent=2),
        diagnostic_report=diagnostics.to_report(),
        source_summary=source_summary,
    )
    resp = await client.complete(system="", user=user, output_format="json")
    refined = json.loads(_extract_json(resp.text))

    # Splice: copy partial, overwrite only the structural fields the LLM returned.
    out = copy.deepcopy(partial)
    for key in (
        "stimuli", "navigation", "runtime", "task_specific",
        "performance", "pilot_validation_config",
    ):
        if key in refined:
            out[key] = refined[key]
    out = normalize_partial(out)
    validate_stage1_output(out)
    return out


def _save_diagnostic(diagnostics: PilotDiagnostics, taskcards_dir: Path, label: str) -> None:
    """Persist pilot diagnostic markdown alongside the TaskCard JSON."""
    out_dir = Path(taskcards_dir) / label
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot.md").write_text(diagnostics.to_report())


async def run_stage6(
    client: LLMClient,
    partial: dict,
    bundle: SourceBundle,
    *,
    label: str,
    taskcards_dir: Path,
    headless: bool = True,
    max_retries: int = 1,
) -> tuple[dict, ReasoningStep]:
    """Run pilot validation; refine on failure; persist diagnostic.

    Returns the (possibly refined) partial plus a ReasoningStep entry.
    Raises PilotValidationError if pilot fails after max_retries refinements.
    """
    pilot_runner = PilotRunner()
    history: list[str] = []

    for attempt in range(max_retries + 1):
        config = _partial_to_pilot_config(partial)
        try:
            diagnostics = await pilot_runner.run(config, bundle.url, headless=headless)
        except Exception as e:
            diagnostics = PilotDiagnostics.crashed(str(e))

        passed, reasons = _pilot_passed(diagnostics, config)
        if passed:
            _save_diagnostic(diagnostics, taskcards_dir, label)
            inference = (
                f"Pilot passed: {diagnostics.trials_with_stimulus_match} trials, "
                f"conditions {diagnostics.conditions_observed}."
                + (f" Refined {attempt} time(s)." if attempt > 0 else "")
            )
            return partial, ReasoningStep(
                step="stage6_pilot",
                inference=inference,
                evidence_lines=[],
                confidence="high",
            )

        history.append(f"Attempt {attempt + 1}: " + "; ".join(reasons))
        logger.warning("Pilot attempt %d failed: %s", attempt + 1, "; ".join(reasons))

        if attempt == max_retries:
            _save_diagnostic(diagnostics, taskcards_dir, label)
            raise PilotValidationError(
                f"Pilot failed after {max_retries + 1} attempts:\n  - "
                + "\n  - ".join(history)
                + f"\n\nLatest diagnostic saved to {taskcards_dir}/{label}/pilot.md"
            )

        # Refine and retry
        partial = await _refine_partial(client, partial, diagnostics, bundle)

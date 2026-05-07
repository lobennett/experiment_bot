"""Tests for Stage 6 (live-DOM pilot validation + refinement).

These tests stub PilotRunner so no real Playwright session runs. The
LLM is mocked; we verify pass/fail logic, refinement-on-failure flow,
diagnostic persistence, and that retry exhaustion raises with the
accumulated history.
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from experiment_bot.core.config import SourceBundle
from experiment_bot.core.pilot import PilotDiagnostics
from experiment_bot.llm.protocol import LLMResponse
from experiment_bot.reasoner.stage6_pilot import (
    PilotValidationError, run_stage6,
)


def _stage5_partial() -> dict:
    """Minimal partial that survives Stage 1 validator and pilot config build."""
    return {
        "task": {"name": "FakeTask", "constructs": [], "paradigm_classes": ["x"]},
        "stimuli": [
            {"id": "go", "description": "go cue",
             "detection": {"method": "dom_query", "selector": "#go"},
             "response": {"key": "f", "condition": "go"}}
        ],
        "navigation": {"phases": []},
        "runtime": {
            "advance_behavior": {
                "advance_keys": [" "],
                "feedback_fallback_keys": ["Enter"],
                "feedback_selectors": [],
            },
            "data_capture": {
                "method": "js_expression",
                "expression": "jsPsych.data.get().json()",
                "format": "json",
            },
        },
        "task_specific": {"key_map": {"go": "f"}},
        "performance": {"accuracy": {"go": 0.95}},
        "pilot_validation_config": {"min_trials": 5, "target_conditions": ["go"]},
    }


def _bundle() -> SourceBundle:
    return SourceBundle(
        url="http://example.com/fake-task",
        source_files={"main.js": "// stub"},
        description_text="<html></html>",
    )


def _passing_diagnostic() -> PilotDiagnostics:
    return PilotDiagnostics(
        trials_completed=5,
        trials_with_stimulus_match=5,
        conditions_observed=["go"],
        conditions_missing=[],
        selector_results={"go": {"matches": 5, "polls": 5}},
        phase_results={},
        dom_snapshots=[],
        anomalies=[],
        trial_log=[],
    )


def _failing_diagnostic() -> PilotDiagnostics:
    return PilotDiagnostics(
        trials_completed=0,
        trials_with_stimulus_match=0,
        conditions_observed=[],
        conditions_missing=["go"],
        selector_results={"go": {"matches": 0, "polls": 100}},
        phase_results={},
        dom_snapshots=[{"trigger": "no_match_50_polls", "html": "<div>fullscreen prompt</div>"}],
        anomalies=["100 consecutive polls with no stimulus match"],
        trial_log=[],
    )


@pytest.mark.asyncio
async def test_stage6_passes_when_pilot_meets_criteria(tmp_path):
    """Pilot reports trials + all target conditions: stage 6 passes, returns
    the partial unchanged (no refinement) and a high-confidence ReasoningStep.
    """
    fake_client = AsyncMock()
    partial = _stage5_partial()
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(return_value=_passing_diagnostic())
        pr_cls.return_value = pr
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()
    # Partial unchanged — no refinement happened
    assert out == partial
    # Diagnostic persisted
    assert (tmp_path / "fake_task" / "pilot.md").exists()
    # LLM was never called for refinement
    assert fake_client.complete.await_count == 0


@pytest.mark.asyncio
async def test_stage6_refines_on_failure_then_passes(tmp_path):
    """Pilot fails first attempt, LLM-refined partial passes second attempt."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "navigation": {"phases": [{"action": "click", "target": "#start"}]}
    }"""))
    partial = _stage5_partial()
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=[_failing_diagnostic(), _passing_diagnostic()])
        pr_cls.return_value = pr
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=2,
        )
    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()
    assert "1 refinement" in step.inference.lower() or "refinement(s)" in step.inference.lower()
    # Refinement spliced into the partial
    assert out["navigation"]["phases"], "navigation phases populated by refinement"
    # Task name preserved across refinement (refinement only touches structural fields)
    assert out["task"]["name"] == partial["task"]["name"]
    assert out["task"].get("paradigm_classes") == partial["task"]["paradigm_classes"]
    # LLM called once for refinement
    assert fake_client.complete.await_count == 1


@pytest.mark.asyncio
async def test_stage6_raises_after_max_retries_exhausted(tmp_path):
    """Pilot keeps failing through all retries; PilotValidationError raised
    with accumulated history."""
    fake_client = AsyncMock()
    # Refinement returns a partial that still fails
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(return_value=_failing_diagnostic())
        pr_cls.return_value = pr
        with pytest.raises(PilotValidationError, match="2 attempts"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )
    # Diagnostic still saved (so the user can see what failed)
    assert (tmp_path / "fake_task" / "pilot.md").exists()


@pytest.mark.asyncio
async def test_stage6_persists_refinements_via_save_partial_callback(tmp_path):
    """When pilot fails and run_stage6 raises, the save_partial callback
    must have been invoked after each refinement so --resume can pick
    up the refined state. Without persistence each resume re-walks the
    same refinements from scratch."""
    fake_client = AsyncMock()
    # Each refinement returns a non-empty modification so the partial
    # changes between attempts.
    fake_client.complete = AsyncMock(side_effect=[
        LLMResponse(text='{"refined_attempt_1": "added_navigation"}'),
        LLMResponse(text='{"refined_attempt_1": "added_navigation",'
                         ' "refined_attempt_2": "fixed_detection"}'),
    ])
    partial = _stage5_partial()

    saved_partials: list[dict] = []
    def cb(p: dict) -> None:
        # Record a deep snapshot so we can verify refinements accumulated.
        import copy
        saved_partials.append(copy.deepcopy(p))

    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls, \
         patch("experiment_bot.reasoner.stage6_pilot._refine_partial") as refine_mock:
        pr = AsyncMock()
        pr.run = AsyncMock(return_value=_failing_diagnostic())
        pr_cls.return_value = pr
        # Each refinement adds a marker key so we can verify it propagated.
        async def fake_refine(client, p, diag, bundle):
            import copy
            new_p = copy.deepcopy(p)
            new_p[f"_refinement_{len(saved_partials) + 1}"] = "applied"
            return new_p
        refine_mock.side_effect = fake_refine
        with pytest.raises(PilotValidationError):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=2,
                save_partial=cb,
            )
    # 2 retries → 2 refinements → 2 callback invocations.
    assert len(saved_partials) == 2
    # Refinements accumulate: callback 1 sees refinement 1; callback 2 sees both.
    assert "_refinement_1" in saved_partials[0]
    assert "_refinement_1" in saved_partials[1]
    assert "_refinement_2" in saved_partials[1]


@pytest.mark.asyncio
async def test_stage6_save_partial_optional(tmp_path):
    """save_partial defaults to None and is not required for stage 6 to
    function. Existing call sites without the kwarg still work."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(return_value=_passing_diagnostic())
        pr_cls.return_value = pr
        # No save_partial kwarg → must not raise.
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True,
        )
    assert step.step == "stage6_pilot"


@pytest.mark.asyncio
async def test_stage6_persists_diagnostic_to_taskcards_dir(tmp_path):
    """Pilot diagnostic markdown is saved alongside the TaskCard JSON."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(return_value=_passing_diagnostic())
        pr_cls.return_value = pr
        await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True,
        )
    diag_path = tmp_path / "fake_task" / "pilot.md"
    assert diag_path.exists()
    text = diag_path.read_text()
    assert "Pilot Run Diagnostic Report" in text
    assert "Trials completed: 5" in text


@pytest.mark.asyncio
async def test_stage6_pilot_crash_treated_as_failure(tmp_path):
    """If PilotRunner.run raises (e.g. Playwright launch failed), Stage 6
    treats it as a failed pilot rather than crashing the whole pipeline."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=RuntimeError("Playwright failed to launch"))
        pr_cls.return_value = pr
        with pytest.raises(PilotValidationError):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=0,
            )
    diag = (tmp_path / "fake_task" / "pilot.md").read_text()
    assert "Pilot crashed" in diag

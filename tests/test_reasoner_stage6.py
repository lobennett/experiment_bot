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

    # Use distinct DOM snapshots so stuck-detection doesn't fire early.
    def _failing_with_html(html: str) -> PilotDiagnostics:
        return PilotDiagnostics(
            trials_completed=0, trials_with_stimulus_match=0,
            conditions_observed=[], conditions_missing=["go"],
            selector_results={"go": {"matches": 0, "polls": 100}},
            phase_results={},
            dom_snapshots=[{"trigger": "no_match_50_polls", "html": html}],
            anomalies=["100 consecutive polls with no stimulus match"],
            trial_log=[],
        )

    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls, \
         patch("experiment_bot.reasoner.stage6_pilot._refine_partial") as refine_mock:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=[
            _failing_with_html("<div>screen-1</div>"),
            _failing_with_html("<div>screen-2</div>"),
            _failing_with_html("<div>screen-3</div>"),
        ])
        pr_cls.return_value = pr
        # Each refinement adds a marker key so we can verify it propagated.
        async def fake_refine(client, p, diag, bundle, *, prior_diffs):
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


@pytest.mark.asyncio
async def test_refinement_prompt_uses_sequential_framing(tmp_path):
    """REFINEMENT_PROMPT must instruct the LLM to propose the SMALLEST next
    advance and reference 'Prior Refinement Attempts' for history."""
    from experiment_bot.reasoner.stage6_pilot import REFINEMENT_PROMPT
    assert "smallest" in REFINEMENT_PROMPT.lower(), \
        "prompt must instruct LLM to propose smallest advance"
    assert "Prior Refinement Attempts" in REFINEMENT_PROMPT, \
        "prompt must have a section for prior attempts"
    # Anti-regression: the old "fix all structural fields" framing should be gone.
    assert "Fix accordingly" not in REFINEMENT_PROMPT, \
        "old whole-fix framing should be removed"


@pytest.mark.asyncio
async def test_refinement_prompt_includes_navigation_phase_schema(tmp_path):
    """SP14: REFINEMENT_PROMPT must show the LLM the FLAT navigation-phase
    schema (action/target/key/duration_ms/steps), not the nested
    action.type/action.selector shape that the navigator silently ignores.
    Held-out paradigm stop_signal_with_integrated_memory failed under SP13
    because the LLM produced nested-action diffs; SP14 closes that gap by
    showing concrete schema examples in the prompt itself."""
    from experiment_bot.reasoner.stage6_pilot import REFINEMENT_PROMPT
    assert "Navigation phase JSON schema" in REFINEMENT_PROMPT
    # Anti-pattern called out explicitly so the LLM doesn't reinvent it
    assert "action.type" in REFINEMENT_PROMPT and "silently ignored" in REFINEMENT_PROMPT, \
        "prompt must explicitly warn against the nested action.type/selector shape"
    # The 4 supported actions each have at least one example
    for action_name in ("click", "keypress", "wait", "sequence"):
        assert f'"action": "{action_name}"' in REFINEMENT_PROMPT, \
            f"prompt must include a concrete example of action={action_name}"
    # APPEND ordering rule: SP14 re-test showed the LLM prepending a new phase
    # to the array (breaking execution order). Prompt must explicitly say APPEND.
    assert "APPEND" in REFINEMENT_PROMPT, \
        "prompt must teach the LLM to APPEND new phases to the end of the array"
    assert "never prepend" in REFINEMENT_PROMPT, \
        "prompt must explicitly forbid prepending/reordering"


@pytest.mark.asyncio
async def test_refine_partial_includes_prior_diffs_in_prompt(tmp_path):
    """When prior_diffs is non-empty, the refinement prompt rendered to the
    LLM must contain the prior diff text so the LLM can see what was tried."""
    from experiment_bot.reasoner.stage6_pilot import _refine_partial
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    prior_diff = "--- before_attempt_1\n+++ after_attempt_1\n+ added fullscreen click\n"
    await _refine_partial(
        fake_client, partial, _failing_diagnostic(), _bundle(),
        prior_diffs=[prior_diff],
    )
    # Inspect the prompt that was sent to the LLM
    sent_user = fake_client.complete.await_args.kwargs.get("user") \
                or fake_client.complete.await_args.args[1]
    assert "added fullscreen click" in sent_user, \
        "prior diff text must appear in the refinement prompt"
    assert "Prior Refinement Attempts" in sent_user


@pytest.mark.asyncio
async def test_stage6_stuck_detection_aborts_early(tmp_path):
    """When two consecutive failed attempts produce the same dom_fingerprint,
    Stage 6 raises PilotValidationError without consuming the rest of the
    budget — refinements that don't move the bot won't move it by trying
    again. The error message names the stuck state."""
    fake_client = AsyncMock()
    # Refinement returns a no-op so the partial doesn't actually change
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()

    stuck_diag = PilotDiagnostics(
        trials_completed=0,
        trials_with_stimulus_match=0,
        conditions_observed=[],
        conditions_missing=["go"],
        selector_results={"go": {"matches": 0, "polls": 100}},
        phase_results={},
        dom_snapshots=[{"trigger": "no_match_50_polls",
                        "html": "<div>same screen each time</div>"}],
        anomalies=["100 consecutive polls with no stimulus match"],
        trial_log=[],
    )

    pilot_call_count = 0
    async def fake_pilot_run(*args, **kwargs):
        nonlocal pilot_call_count
        pilot_call_count += 1
        return stuck_diag  # identical fingerprint every call

    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=fake_pilot_run)
        pr_cls.return_value = pr
        with pytest.raises(PilotValidationError, match="stuck"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=11,  # large budget; guard should fire first
            )
    # Stuck-detection fires after 2nd identical fingerprint → pilot called 2x, NOT 12x.
    assert pilot_call_count == 2, \
        f"expected stuck-detection to abort after 2 pilots, got {pilot_call_count}"


@pytest.mark.asyncio
async def test_stage6_max_retries_override_respected(tmp_path):
    """Caller-supplied max_retries overrides the function-signature default.
    Verifies the budget is still configurable from the CLI / pipeline."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="{}"))
    partial = _stage5_partial()
    # Use varying fingerprints so stuck-detection doesn't short-circuit.
    diags = [
        PilotDiagnostics(
            trials_completed=0, trials_with_stimulus_match=0,
            conditions_observed=[], conditions_missing=["go"],
            selector_results={"go": {"matches": 0, "polls": 100}},
            phase_results={}, dom_snapshots=[
                {"trigger": "no_match_50_polls", "html": f"<div>screen-{i}</div>"}],
            anomalies=[], trial_log=[],
        )
        for i in range(5)
    ]
    with patch("experiment_bot.reasoner.stage6_pilot.PilotRunner") as pr_cls:
        pr = AsyncMock()
        pr.run = AsyncMock(side_effect=diags)
        pr_cls.return_value = pr
        with pytest.raises(PilotValidationError, match="4 attempts"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=3,  # override → 4 total attempts
            )

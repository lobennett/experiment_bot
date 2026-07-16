"""Tests for Stage 6 (live-DOM pilot validation + refinement).

These tests stub PilotSession so no real Playwright session runs. The
LLM is mocked; we verify pass/fail logic, refinement-on-failure flow,
diagnostic persistence, and that retry exhaustion raises with the
accumulated history.
"""
from __future__ import annotations
import copy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from experiment_bot.core.config import SourceBundle
from experiment_bot.core.pilot import PilotDiagnostics
from experiment_bot.core.pilot_session import PhaseAttempt, StimulusProbe
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


def _passing_dict() -> dict:
    """poll_stimuli result dict that satisfies pilot pass criteria."""
    return {
        "trials_completed": 5,
        "trials_with_stimulus_match": 5,
        "conditions_observed": ["go"],
        "selector_results": {"go": {"matches": 5, "polls": 5}},
        "phase_results": {},
        "dom_snapshots": [{"trigger": "first_stimulus_match", "html": "<div>trial</div>"}],
        "anomalies": [],
        "trial_log": [],
    }


def _failing_dict(html: str = "<div>fullscreen prompt</div>") -> dict:
    """poll_stimuli result dict that fails pilot pass criteria (0 matches)."""
    return {
        "trials_completed": 0,
        "trials_with_stimulus_match": 0,
        "conditions_observed": [],
        "selector_results": {"go": {"matches": 0, "polls": 100}},
        "phase_results": {},
        "dom_snapshots": [{"trigger": "no_match_50_polls", "html": html}],
        "anomalies": ["100 consecutive polls with no stimulus match"],
        "trial_log": [],
    }


def _failing_diagnostic() -> PilotDiagnostics:
    """PilotDiagnostics instance (used by tests calling _refine_partial directly)."""
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


def _make_session_mock(poll_side_effect=None, dom_snapshot_html="<div>test</div>"):
    """Build a session mock suitable for PilotSession.__aenter__ return value.

    probe_stimulus returns a non-None match by default so the C3 replay gate
    passes without a real browser. Tests that need a no-match probe (e.g. the
    trial-response classifier test) override it explicitly.
    """
    session = AsyncMock()
    session.goto = AsyncMock(return_value=dom_snapshot_html)
    session.dom_snapshot = AsyncMock(return_value=dom_snapshot_html)
    session.try_phase = AsyncMock(return_value=PhaseAttempt(
        success=True, dom_after=dom_snapshot_html, error=None
    ))
    # Non-None match so replay_navigation returns True (C3 gate passes).
    _sentinel_match = object()
    session.probe_stimulus = AsyncMock(
        return_value=StimulusProbe(match=_sentinel_match, dom_at_probe=dom_snapshot_html)
    )
    # Live-page eval returns one parseable trial row so the Wave-A1
    # data-capture gate passes by default (tests override to exercise it).
    session.page = AsyncMock()
    session.page.evaluate = AsyncMock(return_value='[{"trial": 1}]')
    if poll_side_effect is not None:
        session.poll_stimuli = AsyncMock(side_effect=poll_side_effect)
    else:
        session.poll_stimuli = AsyncMock(return_value=_passing_dict())
    return session


def _patch_pilot_session(session_mock):
    """Return a context-manager patch for PilotSession that yields session_mock."""
    ps_cls = MagicMock()
    ps_cls.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    ps_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return patch("experiment_bot.reasoner.stage6_pilot.PilotSession", ps_cls)


@pytest.mark.asyncio
async def test_stage6_passes_when_pilot_meets_criteria(tmp_path):
    """Pilot reports trials + all target conditions: stage 6 passes, returns
    the partial unchanged (no refinement) and a high-confidence ReasoningStep.
    """
    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()
    # Diagnostic persisted
    assert (tmp_path / "fake_task" / "pilot.md").exists()
    # LLM was never called for refinement
    assert fake_client.complete.await_count == 0


@pytest.mark.asyncio
async def test_stage6_refines_on_failure_then_passes(tmp_path):
    """Pilot fails first attempt, LLM proposes nav phase, second attempt passes."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "start", "action": "click", "target": "#start",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    partial = _stage5_partial()
    session_mock = _make_session_mock(
        poll_side_effect=[_failing_dict(), _passing_dict()],
    )
    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=2,
        )
    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()
    assert "refinement" in step.inference.lower()
    # Navigation phases populated by refinement
    assert out["navigation"]["phases"], "navigation phases populated by refinement"
    # Task name preserved across refinement
    assert out["task"]["name"] == partial["task"]["name"]
    assert out["task"].get("paradigm_classes") == partial["task"]["paradigm_classes"]
    # LLM called once for refinement
    assert fake_client.complete.await_count == 1


@pytest.mark.asyncio
async def test_stage6_raises_after_max_retries_exhausted(tmp_path):
    """Pilot keeps failing through all retries; PilotValidationError raised
    with accumulated history."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "x", "action": "click", "target": "#x",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    partial = _stage5_partial()
    # Two failing dicts with different DOM so stuck-detection doesn't fire
    session_mock = _make_session_mock(
        poll_side_effect=[_failing_dict("<div>screen-1</div>"), _failing_dict("<div>screen-2</div>")],
    )
    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="2 attempts"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )
    # Diagnostic still saved (so the user can see what failed)
    assert (tmp_path / "fake_task" / "pilot.md").exists()


@pytest.mark.asyncio
async def test_stage6_stuck_detection_aborts_early(tmp_path):
    """When three consecutive failed attempts produce the same dom_fingerprint,
    Stage 6 raises PilotValidationError without consuming the rest of the
    budget. A review raised the threshold from 2 to 3 so the LLM gets one chance
    after a no-op refinement to try a different action (some refinements
    succeed at session.try_phase but don't actually advance the DOM, e.g.,
    keypress Enter on a screen that ignores it)."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "x", "action": "click", "target": "#x",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    partial = _stage5_partial()
    # Same HTML → same dom_fingerprint → stuck after 3 consecutive
    stuck_html = "<div>same screen each time</div>"
    poll_call_count = 0

    async def stuck_poll(*args, **kwargs):
        nonlocal poll_call_count
        poll_call_count += 1
        return _failing_dict(stuck_html)

    session_mock = _make_session_mock()
    session_mock.poll_stimuli = AsyncMock(side_effect=stuck_poll)

    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="stuck"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=11,
            )
    # Stuck-detection fires after 3rd identical fingerprint → poll called 3x, NOT 12x.
    assert poll_call_count == 3, \
        f"expected stuck-detection to abort after 3 polls, got {poll_call_count}"


@pytest.mark.asyncio
async def test_stage6_persists_refinements_via_save_partial_callback(tmp_path):
    """save_partial callback is invoked after each successful nav-phase append."""
    fake_client = AsyncMock()
    # LLM returns valid nav phase each time
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "nav", "action": "click", "target": "#btn",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    partial = _stage5_partial()

    saved_partials: list[dict] = []
    def cb(p: dict) -> None:
        saved_partials.append(copy.deepcopy(p))

    # 3 failing dicts with distinct DOMs, then pass — triggers 2 nav refinements
    session_mock = _make_session_mock(
        poll_side_effect=[
            _failing_dict("<div>screen-1</div>"),
            _failing_dict("<div>screen-2</div>"),
            _passing_dict(),
        ],
    )
    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=3,
            save_partial=cb,
        )
    # 2 nav refinements → 2 callback invocations (one per successful try_phase)
    assert len(saved_partials) == 2
    # Each saved partial has navigation phases
    assert saved_partials[0]["navigation"]["phases"]
    assert saved_partials[1]["navigation"]["phases"]
    # Second save has more phases than first
    assert len(saved_partials[1]["navigation"]["phases"]) >= len(saved_partials[0]["navigation"]["phases"])


@pytest.mark.asyncio
async def test_stage6_save_partial_optional(tmp_path):
    """save_partial defaults to None and is not required for stage 6 to
    function. Existing call sites without the kwarg still work."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
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
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
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
    """If session.poll_stimuli raises, Stage 6 treats it as a failed attempt
    (crash → PilotValidationError after budget exhausted or stuck)."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "x", "action": "click", "target": "#x",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    session_mock.poll_stimuli = AsyncMock(side_effect=RuntimeError("poll crashed"))

    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=0,
            )
    diag = (tmp_path / "fake_task" / "pilot.md").read_text()
    assert "poll_stimuli crashed" in diag or "crashed" in diag.lower()


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
    """REFINEMENT_PROMPT must show the LLM the FLAT navigation-phase
    schema (action/target/key/duration_ms/steps), not the nested
    action.type/action.selector shape that the navigator silently ignores."""
    from experiment_bot.reasoner.stage6_pilot import REFINEMENT_PROMPT
    assert "Navigation phase JSON schema" in REFINEMENT_PROMPT
    # Anti-pattern called out explicitly so the LLM doesn't reinvent it
    assert "action.type" in REFINEMENT_PROMPT and "silently ignored" in REFINEMENT_PROMPT, \
        "prompt must explicitly warn against the nested action.type/selector shape"
    # The 4 supported actions each have at least one example
    for action_name in ("click", "keypress", "wait", "sequence"):
        assert f'"action": "{action_name}"' in REFINEMENT_PROMPT, \
            f"prompt must include a concrete example of action={action_name}"
    # APPEND ordering rule
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
async def test_navigation_refinement_prompt_has_schema_section():
    from experiment_bot.reasoner.stage6_pilot import NAVIGATION_REFINEMENT_PROMPT
    assert "Navigation phase JSON schema" in NAVIGATION_REFINEMENT_PROMPT
    assert "APPEND" in NAVIGATION_REFINEMENT_PROMPT
    for a in ("click", "keypress", "wait", "sequence"):
        assert f'"action": "{a}"' in NAVIGATION_REFINEMENT_PROMPT


@pytest.mark.asyncio
async def test_refinement_prompts_document_form_actions():
    """Both nav-refinement prompts must document the fill/select
    form actions (with the `value` field) so the walker/adaptive-nav LLM
    can propose form fills when a consent/demographic form blocks progress."""
    from experiment_bot.reasoner.stage6_pilot import (
        NAVIGATION_REFINEMENT_PROMPT, REFINEMENT_PROMPT,
    )
    for prompt in (REFINEMENT_PROMPT, NAVIGATION_REFINEMENT_PROMPT):
        for action_name in ("fill", "select"):
            assert f'"action": "{action_name}"' in prompt, \
                f"prompt must include a concrete example of action={action_name}"
        assert "`value`" in prompt, "prompt must document the value field"
        assert "plausible neutral values" in prompt, \
            "prompt must tell the LLM to propose plausible neutral form values"


@pytest.mark.asyncio
async def test_walker_navigation_refinement_splices_fill_phase(tmp_path):
    """A proposed fill phase (form field blocking progress) is
    executed via try_phase and spliced into navigation.phases on success."""
    fake_client = AsyncMock()
    fill_phase_json = ('{"phase": "consent_form", "action": "fill", '
                       '"target": "#participant-age", "key": "", '
                       '"value": "anon", "duration_ms": 0, "steps": []}')
    fake_client.complete = AsyncMock(return_value=LLMResponse(text=fill_phase_json))

    partial = _stage5_partial()
    session_mock = _make_session_mock(
        poll_side_effect=[_failing_dict("<form>consent</form>"), _passing_dict()],
    )
    session_mock.try_phase = AsyncMock(return_value=PhaseAttempt(
        success=True, dom_after="<div>instructions</div>", error=None,
    ))

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=2,
        )

    phases = out["navigation"]["phases"]
    assert len(phases) == 1, f"expected 1 nav phase appended, got {phases}"
    assert phases[0]["action"] == "fill"
    assert phases[0]["target"] == "#participant-age"
    assert phases[0]["value"] == "anon"
    # try_phase received the typed phase with the value threaded through
    tried = session_mock.try_phase.await_args_list[-1].args[0]
    assert tried.action == "fill" and tried.value == "anon"


@pytest.mark.asyncio
async def test_stimulus_refinement_prompt_has_expected_fields():
    from experiment_bot.reasoner.stage6_pilot import STIMULUS_REFINEMENT_PROMPT
    assert "stim_id" in STIMULUS_REFINEMENT_PROMPT
    assert "new_selector" in STIMULUS_REFINEMENT_PROMPT
    assert "detection_method" in STIMULUS_REFINEMENT_PROMPT


@pytest.mark.asyncio
async def test_stage6_max_retries_override_respected(tmp_path):
    """Caller-supplied max_retries overrides the function-signature default.
    Verifies the budget is still configurable from the CLI / pipeline."""
    fake_client = AsyncMock()
    fake_client.complete = AsyncMock(return_value=LLMResponse(text="""{
        "phase": "x", "action": "click", "target": "#x",
        "key": "", "duration_ms": 0, "steps": []
    }"""))
    partial = _stage5_partial()
    # Varying HTML so stuck-detection doesn't short-circuit.
    attempt_idx = 0
    async def varying_fail(*args, **kwargs):
        nonlocal attempt_idx
        attempt_idx += 1
        return _failing_dict(f"<div>screen-{attempt_idx}</div>")

    session_mock = _make_session_mock()
    session_mock.poll_stimuli = AsyncMock(side_effect=varying_fail)

    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="4 attempts"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=3,  # override → 4 total attempts
            )


# --- New walker-flow tests ---

@pytest.mark.asyncio
async def test_walker_navigation_refinement_appends_phase(tmp_path):
    """Walker: first poll fails (nav stuck), LLM proposes nav phase,
    session.try_phase succeeds, second poll passes. Resulting partial
    has the proposed phase in navigation.phases."""
    fake_client = AsyncMock()
    nav_phase_json = '{"phase": "fullscreen", "action": "click", "target": "#jspsych-fullscreen-btn", "key": "", "duration_ms": 0, "steps": []}'
    fake_client.complete = AsyncMock(return_value=LLMResponse(text=nav_phase_json))

    partial = _stage5_partial()
    session_mock = _make_session_mock(
        poll_side_effect=[_failing_dict("<div>fullscreen</div>"), _passing_dict()],
    )
    session_mock.try_phase = AsyncMock(return_value=PhaseAttempt(
        success=True, dom_after="<div>instructions</div>", error=None,
    ))

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=2,
        )

    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()
    phases = out["navigation"]["phases"]
    assert len(phases) == 1, f"expected 1 nav phase appended, got {phases}"
    assert phases[0]["action"] == "click"
    assert phases[0]["target"] == "#jspsych-fullscreen-btn"


@pytest.mark.asyncio
async def test_walker_stimulus_refinement_updates_lookup(tmp_path):
    """Walker: first poll has trials_completed>0 but 0 matches (selector wrong),
    LLM proposes selector update, second poll passes. Resulting partial has the
    updated selector in stimuli[0]['detection']['selector']."""
    fake_client = AsyncMock()
    stim_update_json = '{"stim_id": "go", "new_selector": "#new-go-selector", "detection_method": "dom_query"}'
    fake_client.complete = AsyncMock(return_value=LLMResponse(text=stim_update_json))

    partial = _stage5_partial()
    # First poll: trials rendered (trials_completed > 0) but 0 selector matches
    stim_fail = {
        "trials_completed": 10,
        "trials_with_stimulus_match": 0,
        "conditions_observed": [],
        "selector_results": {"go": {"matches": 0, "polls": 100}},
        "phase_results": {},
        "dom_snapshots": [{"trigger": "no_match_50_polls", "html": "<div>trial-screen</div>"}],
        "anomalies": [],
        "trial_log": [],
    }
    session_mock = _make_session_mock(
        poll_side_effect=[stim_fail, _passing_dict()],
    )

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=2,
        )

    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()
    # Selector update spliced into partial on success
    stim = out["stimuli"][0]
    assert stim["detection"]["selector"] == "#new-go-selector", \
        f"expected updated selector in partial, got {stim['detection']['selector']}"


@pytest.mark.asyncio
async def test_walker_does_not_append_trial_response_phase(tmp_path):
    """Walker: when probe_stimulus returns a trial stimulus match BEFORE the
    proposed phase and the phase is a response-key keypress, the classify helper
    returns 'trial_response' and the phase must NOT be appended to
    navigation.phases. Spec C2 / audit genbottle-001."""
    fake_client = AsyncMock()
    # LLM proposes a response-key keypress (key="f" matches task_specific.key_map)
    response_key_phase_json = (
        '{"phase": "trial_key", "action": "keypress", "key": "f", '
        '"target": "", "duration_ms": 0, "steps": []}'
    )
    fake_client.complete = AsyncMock(return_value=LLMResponse(text=response_key_phase_json))

    partial = _stage5_partial()
    # partial already has task_specific.key_map = {"go": "f"}, so response_keys = {"f"}

    # probe_stimulus: first call (before) returns a trial match; second call (after)
    # returns no match (stimulus consumed by the keypress).
    sentinel_match = object()  # non-None → "trial stimulus present"
    probe_with_match = StimulusProbe(match=sentinel_match, dom_at_probe="<div>trial</div>")
    probe_no_match = StimulusProbe(match=None, dom_at_probe="<div>iti</div>")

    session_mock = _make_session_mock(
        poll_side_effect=[_failing_dict("<div>trial-screen</div>"), _passing_dict()],
    )
    session_mock.try_phase = AsyncMock(return_value=PhaseAttempt(
        success=True, dom_after="<div>iti</div>", error=None,
    ))
    # probe returns trial-match before, then no-match after the keypress; the 3rd
    # call comes from the C3 replay gate (probe_stimulus in the replay loop) and
    # must return a match so the gate passes (we're testing the classify logic, not
    # the replay gate, here).
    replay_sentinel = object()
    session_mock.probe_stimulus = AsyncMock(side_effect=[
        probe_with_match,                                         # before keypress (walker)
        probe_no_match,                                           # after keypress (walker)
        StimulusProbe(match=replay_sentinel, dom_at_probe=""),    # replay gate probe
    ])

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=2,
        )

    # The keypress was classified as trial_response → must NOT appear in navigation.phases
    phases = out["navigation"]["phases"]
    response_key_phases = [p for p in phases if p.get("action") == "keypress" and p.get("key") == "f"]
    assert not response_key_phases, (
        f"trial-response keypress must not be in navigation.phases; got phases={phases}"
    )


@pytest.mark.asyncio
async def test_stage6_fails_when_replay_cannot_reach_trials(tmp_path, monkeypatch):
    """C3 replay gate: if replay_navigation returns False, run_stage6 raises
    PilotValidationError with 'replay' in the message."""
    import experiment_bot.reasoner.stage6_pilot as s6

    async def _replay_fail(*a, **k):
        return False, "<div>stuck interstitial</div>"

    monkeypatch.setattr(s6, "replay_navigation", _replay_fail)

    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="replay"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )


@pytest.mark.asyncio
async def test_stage6_passes_when_replay_succeeds(tmp_path, monkeypatch):
    """C3 replay gate: if replay_navigation returns True, run_stage6 returns
    normally (the existing pass criteria are met)."""
    import experiment_bot.reasoner.stage6_pilot as s6

    async def _replay_pass(*a, **k):
        return True, ""

    monkeypatch.setattr(s6, "replay_navigation", _replay_pass)

    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert step.step == "stage6_pilot"
    assert "passed" in step.inference.lower()


@pytest.mark.asyncio
async def test_replay_navigation_presses_advance_keys_to_reach_trials():
    """REGRESSION (held-out C3 false-negative): nav phases leave the bot on a
    'press enter to begin practice' interstitial; the trial only renders after an
    advance-key press. replay_navigation must press advance_keys periodically
    (mirroring the executor's trial loop), not just bare-probe, or it rejects
    cards the executor can actually run."""
    import experiment_bot.reasoner.stage6_pilot as s6

    pressed = []
    state = {"advanced": False}

    session = AsyncMock()
    session.goto = AsyncMock(return_value="<div>begin practice</div>")
    session.try_phase = AsyncMock(return_value=PhaseAttempt(success=True, dom_after="", error=None))

    async def _press(k):
        pressed.append(k)
        state["advanced"] = True  # pressing Enter starts practice -> trial renders
    session.press = AsyncMock(side_effect=_press)

    async def _probe(_lookup):
        return StimulusProbe(match=(object() if state["advanced"] else None), dom_at_probe="")
    session.probe_stimulus = AsyncMock(side_effect=_probe)

    class _AB:
        advance_keys = ["Enter"]
        advance_interval_polls = 5

    class _Nav:
        phases = []

    with _patch_pilot_session(session):
        reached, final_dom = await s6.replay_navigation(
            "http://x", _Nav(), object(), advance_behavior=_AB(),
            headless=True, max_polls=50,
        )
    assert reached is True
    assert final_dom == ""
    assert "Enter" in pressed, "replay must press advance_keys to clear the interstitial"


@pytest.mark.asyncio
async def test_replay_gate_failure_heals_via_proposed_phase(tmp_path, monkeypatch):
    """Held-out flanker regression: live pilot passes but the replay stalls
    on a final interstitial. One replay-refine round (proposed phase from
    the stuck DOM) must heal the gate rather than hard-failing."""
    import experiment_bot.reasoner.stage6_pilot as s6

    calls = {"n": 0}

    async def _replay(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "<p>Press enter to begin practice.</p>"
        return True, ""

    async def _propose(client, dom, phases, diffs):
        assert "Press enter" in dom
        return {"phase": "begin_practice", "action": "keypress",
                "target": "", "key": "Enter", "duration_ms": 0, "steps": []}

    monkeypatch.setattr(s6, "replay_navigation", _replay)
    monkeypatch.setattr(s6, "_propose_next_phase", _propose)

    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
        result, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert calls["n"] == 2
    phases = result["navigation"]["phases"]
    assert any(p.get("phase") == "begin_practice" and p.get("key") == "Enter"
               for p in phases)
    assert (tmp_path / "fake_task" / "pilot_replay_refinement_1.diff").exists()


@pytest.mark.asyncio
async def test_replay_navigation_clicks_feedback_selectors():
    """Held-out flanker regression: an instructions PAGER advances by button
    click, not keypress. The replay must mirror the executor's full advance
    behavior (keys + first visible feedback selector) or it is stricter than
    the executor and rejects runnable cards."""
    import experiment_bot.reasoner.stage6_pilot as s6

    state = {"clicks": 0}
    session = _make_session_mock()

    class _Locator:
        @property
        def first(self):
            return self
        async def is_visible(self, timeout=None):
            return True
        async def click(self, timeout=None):
            state["clicks"] += 1

    class _Page:
        def locator(self, sel):
            return _Locator()
        class keyboard:
            @staticmethod
            async def press(k): pass
    session.page = _Page()
    session.press = AsyncMock()
    # replay_navigation routes advance clicks through the session's
    # click_advance_control (instructions-pager capability); bind the REAL
    # implementation so the mocked page's locator clicks are exercised.
    import types
    from experiment_bot.core.pilot_session import PilotSession
    session.click_advance_control = types.MethodType(
        PilotSession.click_advance_control, session)

    async def _probe(_lookup):
        # advances only after two selector clicks (multi-page pager)
        return StimulusProbe(match=(object() if state["clicks"] >= 2 else None),
                             dom_at_probe="")
    session.probe_stimulus = AsyncMock(side_effect=_probe)

    class _AB:
        advance_keys = ["Enter"]
        feedback_selectors = ["#jspsych-instructions-next"]
        advance_interval_polls = 5

    class _Nav:
        phases = []

    with _patch_pilot_session(session):
        reached, _ = await s6.replay_navigation(
            "http://x", _Nav(), object(), advance_behavior=_AB(),
            headless=True, max_polls=50,
        )
    assert reached is True
    assert state["clicks"] >= 2, "replay must click feedback selectors like the executor"


# --- pilot-observed condition stream persisted as sidecar ---

@pytest.mark.asyncio
async def test_stage6_persists_pilot_observed_condition_stream(tmp_path):
    """A passing pilot writes pilot_observations.json (sidecar — NOT a card
    field, so committed card hashes stay stable) with the observed per-trial
    condition sequence in encounter order."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    passing = _passing_dict()
    passing["trial_log"] = [
        {"trial": 1, "stimulus_id": "go", "condition": "go", "response_key": "f"},
        {"trial": 2, "stimulus_id": "go", "condition": "go", "response_key": "f"},
        {"trial": 3, "stimulus_id": "go", "condition": "other", "response_key": "j"},
    ]
    session_mock = _make_session_mock(poll_side_effect=[passing])
    with _patch_pilot_session(session_mock):
        await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    import json as _json
    sidecar = tmp_path / "fake_task" / "pilot_observations.json"
    assert sidecar.exists()
    obs = _json.loads(sidecar.read_text())
    assert obs["condition_stream"] == ["go", "go", "other"]


@pytest.mark.asyncio
async def test_stage6_skips_sidecar_when_trial_log_empty(tmp_path):
    """No observed trials in the log -> no sidecar (nothing to replay)."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()  # _passing_dict has trial_log=[]
    with _patch_pilot_session(session_mock):
        await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert not (tmp_path / "fake_task" / "pilot_observations.json").exists()


# --- data-capture gate ---

def _mock_capture_eval(session_mock, value):
    """Point the walker session's live page at a canned capture result."""
    session_mock.page = AsyncMock()
    session_mock.page.evaluate = AsyncMock(return_value=value)


@pytest.mark.asyncio
async def test_capture_gate_passes_on_parseable_rows(tmp_path):
    """Pilot + replay pass and the capture expression returns >=1 parseable
    trial row: stage 6 passes and records the gate in the evidence."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    _mock_capture_eval(session_mock, '[{"trial": 1}, {"trial": 2}]')
    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert any("data_capture_gate" in e for e in step.evidence_lines)


@pytest.mark.asyncio
async def test_capture_gate_fails_on_empty_output(tmp_path):
    """Capture method configured but returns nothing: hard fail naming the
    method and that the output was empty."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    _mock_capture_eval(session_mock, "")
    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="js_expression") as exc:
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )
    assert "empty" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_capture_gate_fails_on_unparseable_output(tmp_path):
    fake_client = AsyncMock()
    partial = _stage5_partial()  # data_capture.format == "json"
    session_mock = _make_session_mock()
    _mock_capture_eval(session_mock, "this is not json {")
    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="unparseable"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )


@pytest.mark.asyncio
async def test_capture_gate_fails_on_zero_rows(tmp_path):
    """A parseable but EMPTY export (e.g. '[]') is the exact silent-failure
    mode this gate exists for."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    session_mock = _make_session_mock()
    _mock_capture_eval(session_mock, "[]")
    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="0 trial rows"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )


@pytest.mark.asyncio
async def test_capture_gate_skips_when_no_method_configured(tmp_path):
    """No capture method on the card == platform saves server-side; the
    executor treats that as expected, so the gate must not fail it."""
    fake_client = AsyncMock()
    partial = _stage5_partial()
    partial["runtime"]["data_capture"] = {}
    session_mock = _make_session_mock()
    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert any("data_capture_gate: skipped" in e for e in step.evidence_lines)


def test_capture_row_count_variants():
    from experiment_bot.reasoner.stage6_pilot import _capture_row_count
    # JSON list / wrapper dict / scalar
    assert _capture_row_count('[{"a": 1}, {"a": 2}]', "json") == 2
    assert _capture_row_count('{"trials": [1, 2, 3], "meta": "x"}', "json") == 3
    assert _capture_row_count('"just a string"', "json") == 0
    with pytest.raises(ValueError, match="unparseable"):
        _capture_row_count("not json {", "json")
    # Delimited: header line assumed
    assert _capture_row_count("rt,correct\n512,1\n498,1\n", "csv") == 2
    assert _capture_row_count("rt,correct\n", "csv") == 0
    assert _capture_row_count("", "csv") == 0
    assert _capture_row_count("a\tb\n1\t2", "tsv") == 1


# --- phase-predicate validation against recorded DOM snapshots ---

def _partial_with_predicates(complete_js: str, test_js: str = "", practice_js: str = "") -> dict:
    p = _stage5_partial()
    p["runtime"]["phase_detection"] = {
        "complete": complete_js, "test": test_js, "practice": practice_js,
    }
    return p


def _throwaway_page(session_mock, evaluate_fn):
    """Wire session.context.new_page() to a throwaway page mock whose
    evaluate() runs evaluate_fn(wrapped_expr)."""
    page = AsyncMock()
    page.set_content = AsyncMock()
    page.evaluate = AsyncMock(side_effect=evaluate_fn)
    page.close = AsyncMock()
    session_mock.context = MagicMock()
    session_mock.context.new_page = AsyncMock(return_value=page)
    return page


@pytest.mark.asyncio
async def test_complete_predicate_true_on_trial_dom_hard_fails(tmp_path):
    """A 'complete' predicate that fires on the trial DOM would end live
    sessions mid-task — hard failure, not a warning."""
    fake_client = AsyncMock()
    partial = _partial_with_predicates(
        complete_js="document.querySelector('#stim') !== null",  # true during trials!
        test_js="window.phase === 'test'",
    )
    session_mock = _make_session_mock()

    async def _eval(expr):
        return "#stim" in expr  # complete-predicate truthy, others false
    _throwaway_page(session_mock, _eval)

    with _patch_pilot_session(session_mock):
        with pytest.raises(PilotValidationError, match="complete"):
            await run_stage6(
                fake_client, partial, _bundle(),
                label="fake_task", taskcards_dir=tmp_path,
                headless=True, max_retries=1,
            )


@pytest.mark.asyncio
async def test_complete_true_on_after_nav_dom_is_warning(tmp_path):
    """'complete' TRUE on the after-navigation DOM (but false on trial DOM)
    is a WARNING in evidence + pilot.md, not a failure."""
    fake_client = AsyncMock()
    partial = _partial_with_predicates(
        complete_js="window.finished === true",
        test_js="window.phase === 'test'",
    )
    session_mock = _make_session_mock()
    # _passing_dict trial snapshot html is '<div>trial</div>'; after-nav DOM
    # comes from dom_snapshot() = '<div>test</div>'. Key the eval off the
    # set_content'ed html instead of the expr.
    state = {"html": ""}

    async def _set_content(html):
        state["html"] = html

    async def _eval(expr):
        if "finished" in expr:
            return "test" in state["html"]  # true only on the after-nav DOM
        if "phase" in expr:
            return "trial" in state["html"]  # trial predicate ok on trial DOM
        return False

    page = _throwaway_page(session_mock, _eval)
    page.set_content = AsyncMock(side_effect=_set_content)

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    warnings = [e for e in step.evidence_lines if "phase_predicate_warning" in e]
    assert any("complete" in w and "after" in w.lower() for w in warnings), warnings
    assert "phase_predicate_warning" in (tmp_path / "fake_task" / "pilot.md").read_text()


@pytest.mark.asyncio
async def test_no_trialish_predicate_true_on_trial_dom_is_warning(tmp_path):
    """Neither 'test' nor 'practice' fires on the recorded trial DOM (the
    observed live failure): WARNING, since trial-ness no longer depends on
    the predicates."""
    fake_client = AsyncMock()
    partial = _partial_with_predicates(
        complete_js="window.finished === true",
        test_js="document.querySelector('#never-there') !== null",
    )
    session_mock = _make_session_mock()

    async def _eval(expr):
        return False  # nothing fires anywhere
    _throwaway_page(session_mock, _eval)

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    warnings = [e for e in step.evidence_lines if "phase_predicate_warning" in e]
    assert any("trial DOM" in w for w in warnings), warnings


@pytest.mark.asyncio
async def test_predicates_all_consistent_no_warnings(tmp_path):
    fake_client = AsyncMock()
    partial = _partial_with_predicates(
        complete_js="window.finished === true",
        test_js="window.phase === 'test'",
    )
    session_mock = _make_session_mock()

    async def _eval(expr):
        return "phase" in expr  # trial-ish true, complete false
    _throwaway_page(session_mock, _eval)

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert not any("phase_predicate_warning" in e for e in step.evidence_lines)


@pytest.mark.asyncio
async def test_predicate_validation_degrades_to_warning_on_page_error(tmp_path):
    """If the throwaway page can't be built, the check degrades to a warning
    (advisory) rather than failing an otherwise-passing pilot."""
    fake_client = AsyncMock()
    partial = _partial_with_predicates(complete_js="window.finished === true")
    session_mock = _make_session_mock()
    session_mock.context = MagicMock()
    session_mock.context.new_page = AsyncMock(side_effect=RuntimeError("no context"))

    with _patch_pilot_session(session_mock):
        out, step = await run_stage6(
            fake_client, partial, _bundle(),
            label="fake_task", taskcards_dir=tmp_path,
            headless=True, max_retries=1,
        )
    assert any("phase_predicate" in e and "skipped" in e for e in step.evidence_lines)

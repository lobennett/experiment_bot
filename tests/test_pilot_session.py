"""Tests for PilotSession (SP15 Part B substrate).

Uses a local HTML fixture rather than mocking Playwright — the test isolates
session-lifecycle behavior, not Playwright internals.
"""
import pytest
from pathlib import Path

from experiment_bot.core.config import NavigationPhase
from experiment_bot.core.pilot_session import PilotSession


FIXTURE_HTML = """<!DOCTYPE html>
<html><body>
<button id="advance" onclick="document.body.dataset.state='advanced'">Advance</button>
<button id="one-shot-btn" onclick="this.remove()">x</button>
<div id="stim-target" style="display:none">stimulus</div>
<form id="consent-form">
  <input type="text" id="participant-id" name="pid">
  <select id="country" onchange="document.body.dataset.country=this.value">
    <option value="">--</option>
    <option value="aa">Option AA</option>
    <option value="bb">Option BB</option>
  </select>
  <input type="checkbox" id="agree-box"
         onclick="document.body.dataset.agreed='yes'">
</form>
<script>
document.body.dataset.state = 'initial';
document.addEventListener('keydown', e => {
  if (e.key === ' ') document.body.dataset.state = 'space-pressed';
});
</script>
</body></html>
"""


@pytest.fixture
def fixture_url(tmp_path):
    p = tmp_path / "fixture.html"
    p.write_text(FIXTURE_HTML)
    return f"file://{p}"


@pytest.mark.asyncio
async def test_pilot_session_opens_and_closes_cleanly(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        dom = await session.dom_snapshot()
        assert "advance" in dom
    # No assertion needed — if __aexit__ raised, the test fails.


@pytest.mark.asyncio
async def test_pilot_session_try_phase_click_succeeds(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "advance", "action": "click", "target": "#advance",
            "key": "", "duration_ms": 0, "steps": [],
        })
        result = await session.try_phase(phase)
        assert result.success is True
        assert result.error is None
        # DOM reflects the click
        assert 'data-state="advanced"' in result.dom_after


@pytest.mark.asyncio
async def test_pilot_session_try_phase_click_times_out_gracefully(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "missing", "action": "click", "target": "#does-not-exist",
            "key": "", "duration_ms": 0, "steps": [],
        })
        result = await session.try_phase(phase)
        assert result.success is False
        assert result.error and "Timeout" in result.error
        # Session is still usable after a failed phase
        dom = await session.dom_snapshot()
        assert dom  # didn't crash


@pytest.mark.asyncio
async def test_pilot_session_try_phase_keypress(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "press", "action": "keypress", "target": "", "key": " ",
            "duration_ms": 0, "steps": [],
        })
        result = await session.try_phase(phase)
        assert result.success is True
        assert 'data-state="space-pressed"' in result.dom_after


@pytest.mark.asyncio
async def test_pilot_session_dom_snapshot_is_stable_when_page_unchanged(fixture_url):
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        a = await session.dom_snapshot()
        b = await session.dom_snapshot()
        assert a == b


@pytest.mark.asyncio
async def test_pilot_session_context_manager_cleans_up_on_exception(fixture_url):
    """If the walker body raises mid-session, the browser must still close."""
    raised = False
    try:
        async with PilotSession(headless=True) as session:
            await session.goto(fixture_url)
            raise RuntimeError("simulated walker failure")
    except RuntimeError:
        raised = True
    assert raised
    # No assertion on browser-closed (Playwright cleanup is implicit in __aexit__);
    # this test passes if no resource leak warnings appear.


@pytest.mark.asyncio
async def test_pilot_session_exposes_context(fixture_url):
    """SP16 prerequisite: PilotSession.context returns the BrowserContext
    so callers (TaskExecutor) can create CDP sessions on it."""
    async with PilotSession(headless=True) as session:
        await session.goto(fixture_url)
        ctx = session.context
        assert ctx is not None
        # Smoke: context can spawn a CDP session
        cdp = await ctx.new_cdp_session(session.page)
        assert cdp is not None
        await cdp.detach()


@pytest.mark.asyncio
async def test_try_phase_repeat_runs_steps_until_substep_fails(fixture_url):
    """`repeat` runs its steps repeatedly, stopping when a sub-step fails
    (mirrors InstructionNavigator semantics, max 20 iterations)."""
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        # fixture has a button that exists once; a repeat of click+wait should
        # click it then fail on the second iteration (button gone) and stop.
        phase = NavigationPhase.from_dict({
            "action": "repeat", "phase": "advance_all", "target": "", "key": "",
            "duration_ms": 0,
            "steps": [
                {"action": "click", "target": "#one-shot-btn", "key": "", "duration_ms": 0, "steps": []},
                {"action": "wait", "target": "", "key": "", "duration_ms": 10, "steps": []},
            ],
        })
        result = await s.try_phase(phase)
        assert result.success is True  # repeat itself never raises; it stops on sub-fail


@pytest.mark.asyncio
async def test_try_phase_unknown_action_records_to_run_trace(fixture_url):
    """An unsupported action is a loud WARNING + recorded, not a silent info log."""
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "action": "teleport", "phase": "x", "target": "", "key": "",
            "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is False
        assert "unknown action" in (result.error or "").lower()


# --- Wave B2: form actions (fill / select) ---

@pytest.mark.asyncio
async def test_try_phase_fill_text_input(fixture_url):
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "consent", "action": "fill", "target": "#participant-id",
            "key": "", "value": "anon-1", "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is True, result.error
        val = await s.page.evaluate("document.querySelector('#participant-id').value")
        assert val == "anon-1"


@pytest.mark.asyncio
async def test_try_phase_fill_missing_target_fails_gracefully(fixture_url):
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "consent", "action": "fill", "target": "#no-such-input",
            "key": "", "value": "x", "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is False
        assert result.error
        # Session remains usable
        assert await s.dom_snapshot()


@pytest.mark.asyncio
async def test_try_phase_select_dropdown_by_value(fixture_url):
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "demographics", "action": "select", "target": "#country",
            "key": "", "value": "bb", "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is True, result.error
        assert 'data-country="bb"' in result.dom_after


@pytest.mark.asyncio
async def test_try_phase_select_dropdown_by_label(fixture_url):
    """A value that matches no option value falls back to option label."""
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "demographics", "action": "select", "target": "#country",
            "key": "", "value": "Option AA", "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is True, result.error
        assert 'data-country="aa"' in result.dom_after


@pytest.mark.asyncio
async def test_try_phase_select_empty_value_clicks_target(fixture_url):
    """select with an empty value clicks the target — radio/checkbox path."""
    async with PilotSession(headless=True) as s:
        await s.goto(fixture_url)
        phase = NavigationPhase.from_dict({
            "phase": "consent", "action": "select", "target": "#agree-box",
            "key": "", "value": "", "duration_ms": 0, "steps": [],
        })
        result = await s.try_phase(phase)
        assert result.success is True, result.error
        assert 'data-agreed="yes"' in result.dom_after


@pytest.mark.asyncio
async def test_poll_stimuli_skips_non_pressable_resolved_key(monkeypatch):
    """REGRESSION (span recall): a sequence-response stimulus resolves to a
    non-pressable key (e.g. a card whose key_map placeholder is the literal
    'sequence'). The executor never presses it (it routes to
    _deliver_sequence); poll_stimuli must skip the press too, not crash with
    Playwright's 'Unknown key' error. The display auto-advances on its own
    timer, so skipping is correct."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    import experiment_bot.core.pilot_session as ps_mod
    from experiment_bot.core.config import TaskPhase

    async def _always_test(page, pd):
        return TaskPhase.TEST
    monkeypatch.setattr(ps_mod, "detect_phase", _always_test)

    pd = SimpleNamespace(complete="", loading="", instructions="", attention_check="",
                         feedback="", practice="", test="x")
    ab = SimpleNamespace(advance_keys=[], advance_interval_polls=10,
                         feedback_selectors=[])
    runtime = SimpleNamespace(phase_detection=pd, advance_behavior=ab)
    pilot = SimpleNamespace(target_conditions=["simple"],
                            stimulus_container_selector="body", min_trials=1)
    stim = SimpleNamespace(
        id="simple",
        detection=SimpleNamespace(method="js_eval", selector="true"))
    nav = SimpleNamespace(phases=[])
    config = SimpleNamespace(pilot=pilot, stimuli=[stim], runtime=runtime,
                             navigation=nav,
                             task_specific={"key_map": {"simple": "sequence"}})
    match = SimpleNamespace(stimulus_id="simple", condition="simple",
                            response_key="sequence")
    lookup = SimpleNamespace(config=config, identify=AsyncMock(return_value=match))

    session = PilotSession(headless=True)
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=True)  # detection selector truthy
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    session._page = page
    session.dom_snapshot = AsyncMock(return_value="<div>recall</div>")

    result = await session.poll_stimuli(lookup, max_polls=50)
    assert result["trials_with_stimulus_match"] >= 1
    assert result["conditions_observed"] == ["simple"]
    # The non-pressable "sequence" key was NEVER pressed.
    for call in page.keyboard.press.await_args_list:
        assert call.args[0] != "sequence"


@pytest.mark.asyncio
async def test_poll_stimuli_breaks_early_when_instructions_never_advance(monkeypatch):
    """REGRESSION (held-out 300s spin): when the poll loop is stuck on an
    INSTRUCTIONS screen and re-running nav never changes the DOM, it must break
    in a few iterations (with a 'did not advance' anomaly), NOT spin the full
    _TIMEOUT_S. The INSTRUCTIONS branch never increments consecutive_misses, so
    the 100-miss early-stop cannot bound it — the no-advance guard must."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    import experiment_bot.core.pilot_session as ps_mod
    from experiment_bot.core.config import TaskPhase
    from experiment_bot.core.pilot_session import PhaseAttempt

    async def _always_instructions(page, pd):
        return TaskPhase.INSTRUCTIONS
    monkeypatch.setattr(ps_mod, "detect_phase", _always_instructions)

    pd = SimpleNamespace(complete="", loading="", instructions="x", attention_check="",
                         feedback="", practice="", test="")
    ab = SimpleNamespace(advance_keys=[" "], advance_interval_polls=10)
    runtime = SimpleNamespace(phase_detection=pd, advance_behavior=ab)
    pilot = SimpleNamespace(target_conditions=[], stimulus_container_selector="body", min_trials=5)
    nav = SimpleNamespace(phases=[NavigationPhase.from_dict(
        {"action": "click", "target": "#x", "key": "", "duration_ms": 0, "steps": []})])
    config = SimpleNamespace(pilot=pilot, stimuli=[], runtime=runtime, navigation=nav)
    lookup = SimpleNamespace(config=config, identify=AsyncMock(return_value=None))

    session = PilotSession(headless=True)
    session._page = MagicMock()
    session.dom_snapshot = AsyncMock(return_value="<div>stuck instructions</div>")
    session.try_phase = AsyncMock(return_value=PhaseAttempt(success=True, dom_after="", error=None))

    result = await session.poll_stimuli(lookup, max_polls=100)
    assert any("did not advance" in a for a in result["anomalies"]), result["anomalies"]
    assert not any("Hard timeout" in a for a in result["anomalies"]), "must break early, not at 300s"
    # try_phase called only a few times (3 stuck iterations × 1 nav phase), not hundreds
    assert session.try_phase.await_count <= 5, session.try_phase.await_count

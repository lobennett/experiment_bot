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
<div id="stim-target" style="display:none">stimulus</div>
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

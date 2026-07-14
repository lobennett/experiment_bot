"""General jsPsych multi-page instructions paging.

jsPsych's instructions plugin renders multi-page viewers whose pages advance
ONLY by clicking the pager's Next control when key-advancing is disabled
(``allow_keys: false``). The pager controls are PLATFORM mechanics — any
jsPsych task with such a viewer renders ``#jspsych-instructions-next`` inside
``.jspsych-instructions-nav`` — so the generic advance path tries them after
the card's own advance selectors. Surfaced by the RDoC span tasks (pilots
stalled at 0 trials on the pager), but the capability is task-agnostic.

The fixture below is a synthetic multi-page pager: three pages advanced by
the Next control; after the last page the pager is replaced by a trial
stimulus. No task-specific vocabulary anywhere.
"""
import pytest

from experiment_bot.core.config import NavigationConfig, TaskConfig
from experiment_bot.core.pilot_session import (
    INSTRUCTIONS_PAGER_SELECTORS, PilotSession,
)
from experiment_bot.core.stimulus import StimulusLookup


PAGER_HTML = """<!DOCTYPE html>
<html><body>
<div id="jspsych-content">
  <div id="pager">
    <p id="page-text">Page 1 of 3</p>
    <div class="jspsych-instructions-nav">
      <button id="jspsych-instructions-back" class="jspsych-btn" disabled>Previous</button>
      <button id="jspsych-instructions-next" class="jspsych-btn">Next</button>
    </div>
  </div>
</div>
<script>
let page = 1;
const LAST = 3;
document.getElementById('jspsych-instructions-next').addEventListener('click', () => {
  page += 1;
  if (page > LAST) {
    document.getElementById('pager').remove();
    const stim = document.createElement('div');
    stim.id = 'trial-stimulus';
    stim.textContent = 'STIM';
    document.getElementById('jspsych-content').appendChild(stim);
  } else {
    document.getElementById('page-text').textContent = 'Page ' + page + ' of ' + LAST;
  }
});
</script>
</body></html>
"""

NO_CONTROL_HTML = """<!DOCTYPE html>
<html><body><div id="jspsych-content"><p>Just text, nothing clickable.</p></div></body></html>
"""


@pytest.fixture
def pager_url(tmp_path):
    p = tmp_path / "pager.html"
    p.write_text(PAGER_HTML)
    return f"file://{p}"


@pytest.fixture
def no_control_url(tmp_path):
    p = tmp_path / "plain.html"
    p.write_text(NO_CONTROL_HTML)
    return f"file://{p}"


def _fast_session():
    """Session with near-zero reading delay so pager tests stay quick."""
    return PilotSession(headless=True, reading_delay_range=(0.01, 0.02))


def test_pager_selectors_are_platform_generic():
    """The built-in selectors name the jsPsych pager controls (platform
    mechanics), nothing else — no task/paradigm vocabulary."""
    assert "#jspsych-instructions-next" in INSTRUCTIONS_PAGER_SELECTORS
    for sel in INSTRUCTIONS_PAGER_SELECTORS:
        assert "jspsych" in sel  # platform-mechanic namespace only


@pytest.mark.asyncio
async def test_click_advance_control_clicks_visible_pager_next(pager_url):
    async with _fast_session() as s:
        await s.goto(pager_url)
        clicked = await s.click_advance_control()
        assert clicked is True
        dom = await s.dom_snapshot()
        assert "Page 2 of 3" in dom


@pytest.mark.asyncio
async def test_click_advance_control_returns_false_without_controls(no_control_url):
    async with _fast_session() as s:
        await s.goto(no_control_url)
        assert await s.click_advance_control() is False
        # Card selectors that match nothing also yield False.
        assert await s.click_advance_control(("#nope", ".missing")) is False


@pytest.mark.asyncio
async def test_click_advance_control_tries_card_selectors_first(pager_url):
    """Card-provided advance selectors take precedence over the built-in
    pager controls (the card's knowledge of ITS screens wins)."""
    async with _fast_session() as s:
        await s.goto(pager_url)
        # #jspsych-instructions-back is visible but disabled=clickable-no-op?
        # Use the page-text element as a harmless card-selector target: the
        # click lands there (no effect on the page), proving precedence.
        clicked = await s.click_advance_control(("#page-text",))
        assert clicked is True
        dom = await s.dom_snapshot()
        assert "Page 1 of 3" in dom  # card selector clicked, pager NOT advanced


def _pager_config() -> TaskConfig:
    """Structural config for the synthetic pager task: one trial stimulus,
    no nav phases, an instructions predicate that fires while the pager is
    on screen."""
    return TaskConfig.from_dict({
        "task": {"name": "pager fixture", "platform": "", "constructs": [],
                 "reference_literature": []},
        "stimuli": [{
            "id": "x",
            "description": "post-pager trial stimulus",
            "detection": {"method": "dom_query", "selector": "#trial-stimulus"},
            "response": {"key": "Enter", "condition": "x"},
        }],
        "response_distributions": {},
        "performance": {"accuracy": {}},
        "navigation": {"phases": []},
        "task_specific": {},
        "pilot": {"min_trials": 1, "target_conditions": ["x"],
                  "stimulus_container_selector": "#jspsych-content"},
        "runtime": {
            "phase_detection": {
                "instructions": "!!document.querySelector('#jspsych-instructions-next')",
            },
            "advance_behavior": {"advance_keys": [], "feedback_selectors": []},
        },
    })


@pytest.mark.asyncio
async def test_poll_stimuli_pages_through_multipage_instructions(pager_url):
    """REGRESSION: the pilot walker must page through a jsPsych multi-page
    instructions viewer (Next x pages) and reach the trial stimulus, instead
    of stalling at 0 trials / 'did not advance'."""
    config = _pager_config()
    lookup = StimulusLookup(config)
    async with _fast_session() as s:
        await s.goto(pager_url)
        result = await s.poll_stimuli(lookup, max_polls=100)
    assert result["trials_with_stimulus_match"] >= 1, result["anomalies"]
    assert result["conditions_observed"] == ["x"]
    assert not any("did not advance" in a for a in result["anomalies"])


@pytest.mark.asyncio
async def test_replay_navigation_pages_through_multipage_instructions(pager_url):
    """The Stage-6 fresh-browser replay gate models the same paging, so a
    card that needs the pager is not rejected as executor-unreplayable."""
    from experiment_bot.reasoner.stage6_pilot import replay_navigation
    config = _pager_config()
    lookup = StimulusLookup(config)
    ab = config.runtime.advance_behavior
    ab.advance_interval_polls = 5
    reached, final_dom = await replay_navigation(
        pager_url, NavigationConfig.from_dict({"phases": []}), lookup,
        advance_behavior=ab, headless=True, max_polls=400,
        reading_delay_range=(0.01, 0.02),  # keep the test fast
    )
    assert reached is True, f"replay never reached the stimulus: {final_dom[:400]}"


@pytest.mark.asyncio
async def test_executor_miss_branch_tries_pager_selectors():
    """The executor's no-stimulus advance path attempts the built-in pager
    controls after the card's feedback selectors."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from experiment_bot.core.config import TaskPhase
    from experiment_bot.core.executor import TaskExecutor

    config = _pager_config()
    config.runtime.timing.max_no_stimulus_polls = 3
    config.runtime.timing.poll_interval_ms = 1
    config.runtime.advance_behavior.advance_interval_polls = 1
    config.runtime.advance_behavior.feedback_selectors = ["#card-btn"]

    bp = MagicMock()
    bp.program_sha256 = "00" * 32
    bp.program_path = "stub.py"
    bp.seed = 0
    executor = TaskExecutor(config, headless=True, seed=1,
                            behavior_provider=bp)
    executor._lookup = MagicMock()
    executor._lookup.identify = AsyncMock(return_value=None)

    attempted: list[str] = []

    class _Loc:
        def __init__(self, sel):
            self._sel = sel

        @property
        def first(self):
            return self

        async def is_visible(self, timeout=0):
            attempted.append(self._sel)
            return False

    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="<div>stuck</div>")
    page.locator = lambda sel: _Loc(sel)

    with patch("experiment_bot.core.executor.detect_phase",
               new=AsyncMock(return_value=TaskPhase.TEST)):
        await executor._trial_loop(MagicMock(), page)

    assert "#card-btn" in attempted
    for sel in INSTRUCTIONS_PAGER_SELECTORS:
        assert sel in attempted
    # Card selectors come first in every advance pass.
    assert attempted.index("#card-btn") < attempted.index(
        INSTRUCTIONS_PAGER_SELECTORS[0])

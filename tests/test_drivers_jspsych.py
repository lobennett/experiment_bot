"""SP10: JsPsychDriver tests with stubbed Playwright page."""
from __future__ import annotations
from unittest.mock import AsyncMock

import pytest

from experiment_bot.drivers.base import UnsupportedVersionError
from experiment_bot.drivers.jspsych import JsPsychDriver


@pytest.mark.asyncio
async def test_can_handle_returns_true_when_window_jspsych_present():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    assert await JsPsychDriver.can_handle(page) is True


@pytest.mark.asyncio
async def test_can_handle_returns_false_when_window_jspsych_absent():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    assert await JsPsychDriver.can_handle(page) is False


@pytest.mark.asyncio
async def test_can_handle_returns_false_on_evaluate_error():
    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=Exception("page torn down"))
    assert await JsPsychDriver.can_handle(page) is False


@pytest.mark.asyncio
async def test_create_succeeds_for_supported_version():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="7.3.1")
    driver = await JsPsychDriver.create(page)
    assert driver._version == "7.3.1"


@pytest.mark.asyncio
async def test_create_raises_for_unsupported_version():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value="6.3.1")
    with pytest.raises(UnsupportedVersionError) as excinfo:
        await JsPsychDriver.create(page)
    assert excinfo.value.detected_version == "6.3.1"
    assert "7.3.1" in excinfo.value.supported_versions


@pytest.mark.asyncio
async def test_create_raises_for_null_version():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    with pytest.raises(UnsupportedVersionError):
        await JsPsychDriver.create(page)


@pytest.mark.asyncio
async def test_setup_invokes_install_hook_js():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    driver = JsPsychDriver(version="7.3.1")
    await driver.setup(page)
    # setup should call page.evaluate at least once (to install the hook)
    assert page.evaluate.await_count >= 1


import json as _json
from unittest.mock import AsyncMock as _AsyncMock

from experiment_bot.drivers.base import DeliveryResult as _DeliveryResult
from experiment_bot.drivers.jspsych.responses import deliver as _deliver


@pytest.mark.asyncio
async def test_responses_deliver_invokes_captured_callback():
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={"ok": True})
    result = await _deliver(page, ",", 350.0)
    assert result == {"ok": True}
    js = page.evaluate.call_args.args[0]
    assert "callback_function(info)" in js
    assert '"key": ","' in js or "'key': ','" in js or '"key":","' in js or 'key: ","' in js
    assert "350.0" in js or "350" in js


@pytest.mark.asyncio
async def test_responses_deliver_handles_no_active_listener():
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={"ok": False, "reason": "no_active_listener"})
    result = await _deliver(page, ",", 350.0)
    assert result["ok"] is False
    assert result["reason"] == "no_active_listener"


@pytest.mark.asyncio
async def test_responses_deliver_handles_evaluate_exception():
    page = _AsyncMock()
    page.evaluate = _AsyncMock(side_effect=Exception("page closed"))
    result = await _deliver(page, ",", 350.0)
    assert result["ok"] is False
    assert result["reason"] == "evaluate_raised"


@pytest.mark.asyncio
async def test_driver_deliver_response_uses_callback_hook():
    """Wire deliver_response on the driver: success path returns DeliveryResult
    with method='jspsych_callback_hook' and propagates the bot's rt_ms."""
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={"ok": True})
    driver = JsPsychDriver(version="7.3.1")
    result = await driver.deliver_response(page, ",", 350.0)
    assert isinstance(result, _DeliveryResult)
    assert result.success is True
    assert result.actual_rt_ms == 350.0
    assert result.method == "jspsych_callback_hook"
    assert result.error is None


@pytest.mark.asyncio
async def test_driver_deliver_response_response_none_means_withhold():
    """When response=None (e.g. stop-signal stop trial), deliver_response
    is a no-op that returns success with method='withhold_no_op'."""
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock()
    driver = JsPsychDriver(version="7.3.1")
    result = await driver.deliver_response(page, None, 1000.0)
    assert result.success is True
    assert result.method == "withhold_no_op"
    # Importantly: evaluate was NOT called.
    page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_driver_deliver_response_failure_propagates_reason():
    """When the hook reports no_active_listener, deliver_response returns
    DeliveryResult(success=False) carrying the reason."""
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={"ok": False, "reason": "no_active_listener"})
    driver = JsPsychDriver(version="7.3.1")
    result = await driver.deliver_response(page, ",", 350.0)
    assert result.success is False
    assert result.error == "no_active_listener"


from experiment_bot.drivers.base import TrialContext as _TrialContext
from experiment_bot.drivers.base import TrialLoopState as _TrialLoopState


@pytest.mark.asyncio
async def test_loop_state_returns_complete_when_progress_at_100():
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={"state": "complete"})
    driver = JsPsychDriver(version="7.3.1")
    assert await driver.loop_state(page) == _TrialLoopState.COMPLETE


@pytest.mark.asyncio
async def test_loop_state_returns_ready_when_hook_armed_on_keyboard_trial():
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={
        "state": "ready_for_trial", "type": "html-keyboard-response",
    })
    driver = JsPsychDriver(version="7.3.1")
    assert await driver.loop_state(page) == _TrialLoopState.READY_FOR_TRIAL


@pytest.mark.asyncio
async def test_loop_state_returns_navigation_when_hook_unarmed():
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={
        "state": "needs_navigation", "type": "html-keyboard-response",
        "reason": "hook_not_yet_armed",
    })
    driver = JsPsychDriver(version="7.3.1")
    assert await driver.loop_state(page) == _TrialLoopState.NEEDS_NAVIGATION


@pytest.mark.asyncio
async def test_loop_state_returns_navigation_for_instructions():
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={
        "state": "needs_navigation", "type": "instructions",
    })
    driver = JsPsychDriver(version="7.3.1")
    assert await driver.loop_state(page) == _TrialLoopState.NEEDS_NAVIGATION


@pytest.mark.asyncio
async def test_loop_state_returns_navigation_on_evaluate_error():
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(side_effect=Exception("page closed"))
    driver = JsPsychDriver(version="7.3.1")
    state = await driver.loop_state(page)
    # Defaults to NEEDS_NAVIGATION when state is anything other than
    # 'complete' or 'ready_for_trial'.
    assert state == _TrialLoopState.NEEDS_NAVIGATION


@pytest.mark.asyncio
async def test_get_trial_context_returns_TrialContext_from_jspsych_state():
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value={
        "stimulus_id": "congruent_red",
        "condition": "congruent",
        "allowed_responses": [",", ".", "/"],
        "expected_correct": ",",
        "response_window_ms": 1500,
        "metadata": {"type_name": "html-keyboard-response",
                     "valid_responses_raw": None},
    })
    driver = JsPsychDriver(version="7.3.1")
    ctx = await driver.get_trial_context(page)
    assert isinstance(ctx, _TrialContext)
    assert ctx.stimulus_id == "congruent_red"
    assert ctx.condition == "congruent"
    assert ctx.allowed_responses == (",", ".", "/")
    assert ctx.expected_correct == ","
    assert ctx.response_window_ms == 1500
    assert ctx.metadata["type_name"] == "html-keyboard-response"


@pytest.mark.asyncio
async def test_get_trial_context_raises_when_no_active_trial():
    from experiment_bot.drivers.base import DriverError
    from experiment_bot.drivers.jspsych import JsPsychDriver
    page = _AsyncMock()
    page.evaluate = _AsyncMock(return_value=None)
    driver = JsPsychDriver(version="7.3.1")
    with pytest.raises(DriverError) as excinfo:
        await driver.get_trial_context(page)
    assert excinfo.value.kind == "no_active_trial"
    assert excinfo.value.recoverable is True

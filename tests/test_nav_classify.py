from experiment_bot.reasoner.nav_classify import classify_phase_outcome


def _phase(action, key=""):
    return {"action": action, "key": key, "target": "", "duration_ms": 0, "steps": []}


def test_trial_response_when_stimulus_present_then_consumed():
    # A trial stimulus was on screen before; after a keypress it's gone → trial response.
    assert classify_phase_outcome(
        before_match=object(), after_match=None,
        phase=_phase("keypress", key="f"), response_keys={"f", "j"},
    ) == "trial_response"


def test_trial_response_when_keypress_matches_response_key_during_stimulus():
    # Stimulus present and the pressed key is a known response key → trial response,
    # even if a (different) stimulus is still present after.
    assert classify_phase_outcome(
        before_match=object(), after_match=object(),
        phase=_phase("keypress", key="j"), response_keys={"f", "j"},
    ) == "trial_response"


def test_nav_advance_when_no_stimulus_before():
    # No trial stimulus before the action → it advanced an interstitial → nav advance.
    assert classify_phase_outcome(
        before_match=None, after_match=None,
        phase=_phase("click"), response_keys={"f", "j"},
    ) == "nav_advance"


def test_nav_advance_when_ambiguous():
    # Stimulus present before AND after, action is NOT a response key (e.g. a click
    # or a non-response keypress) → ambiguous → bias to nav_advance (C3 backstops).
    assert classify_phase_outcome(
        before_match=object(), after_match=object(),
        phase=_phase("click"), response_keys={"f", "j"},
    ) == "nav_advance"

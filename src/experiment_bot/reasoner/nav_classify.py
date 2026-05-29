"""Classify a walker-proposed navigation phase as a genuine nav advance vs a
trial response, so the Stage-6 walker never bakes demo-trial keypresses into
navigation.phases (which would make the TaskCard unreplayable by the executor).

Pure + browser-free: takes the stimulus-probe matches before/after the action.
"""
from __future__ import annotations


def classify_phase_outcome(before_match, after_match, phase: dict, response_keys: set[str]) -> str:
    """Return "trial_response" or "nav_advance".

    A configured (trial) stimulus is identified by `before_match`/`after_match`
    being non-None (the walker's StimulusLookup matched a configured stimulus).

    Rules (require a positive trial signal to call something a trial response;
    bias to nav_advance when ambiguous — the Stage-6 replay gate is the backstop):
      - Trial stimulus present before AND the action is a keypress whose key is a
        known response key  -> trial_response.
      - Trial stimulus present before AND gone/changed after a keypress
        -> trial_response.
      - Otherwise -> nav_advance.
    """
    action = phase.get("action", "")
    key = phase.get("key", "")
    is_keypress = action in ("press", "keypress")
    stim_before = before_match is not None

    if stim_before and is_keypress and key in response_keys:
        return "trial_response"
    if stim_before and is_keypress and after_match is None:
        return "trial_response"
    return "nav_advance"

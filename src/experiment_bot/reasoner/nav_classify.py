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

    Rules:
      - A keypress whose key is a configured RESPONSE key is a trial response by
        definition — the executor's trial loop emits responses, so a response
        key never belongs in navigation.phases. This holds REGARDLESS of whether
        a stimulus was detected at the probe instant, because stimulus detection
        is timing-flaky (a response can land in an ITI/fixation gap where the
        probe misses the stimulus). This is the load-bearing rule: gating it on
        `before_match` let demo-trial responses (e.g. "." for circle) leak into
        nav, which the C3 replay gate then rejected.
      - A keypress that consumed a trial (stimulus present before, gone after) is
        a trial response even with a non-standard key.
      - Otherwise -> nav_advance (bias to nav_advance when ambiguous; the C3
        replay gate is the backstop against a wrongly-kept phase).
    """
    action = phase.get("action", "")
    key = phase.get("key", "")
    is_keypress = action in ("press", "keypress")
    stim_before = before_match is not None

    if is_keypress and key in response_keys:
        return "trial_response"
    if stim_before and is_keypress and after_match is None:
        return "trial_response"
    return "nav_advance"

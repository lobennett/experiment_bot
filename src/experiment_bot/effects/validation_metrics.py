"""Validation-time metric computations.

Each metric: takes a list of bot trials (dicts) and returns a float (the
metric value). Used by the validation oracle to compare bot output against
published canonical norms.
"""
from __future__ import annotations
from statistics import mean


def cse_magnitude(trials: list[dict]) -> float:
    """Mean RT on incongruent-after-incongruent minus mean RT on incongruent-after-congruent.

    Negative values mean facilitation (the conventional CSE direction).
    Returns NaN when either iI or cI pair set is empty (insufficient data).

    Trials list element keys expected: "condition" (str) and "rt" (float).
    """
    iI_rts: list[float] = []
    cI_rts: list[float] = []
    for i, trial in enumerate(trials):
        if i == 0:
            continue
        prev = trials[i - 1]
        if trial.get("condition") != "incongruent":
            continue
        if prev.get("condition") == "incongruent":
            iI_rts.append(trial["rt"])
        elif prev.get("condition") == "congruent":
            cI_rts.append(trial["rt"])
    if not iI_rts or not cI_rts:
        return float("nan")
    return mean(iI_rts) - mean(cI_rts)

from experiment_bot.effects.validation_metrics import cse_magnitude


def test_cse_magnitude_computes_canonical_difference():
    """cse_magnitude(trials) returns mean RT(iI) - mean RT(cI).

    Negative values mean facilitation (the conventional CSE direction).
    """
    trials = [
        {"condition": "congruent",   "rt": 500},
        {"condition": "incongruent", "rt": 580},  # cI: high
        {"condition": "incongruent", "rt": 540},  # iI: lower (facilitation)
        {"condition": "congruent",   "rt": 490},
        {"condition": "incongruent", "rt": 590},  # cI
        {"condition": "incongruent", "rt": 530},  # iI
    ]
    cse = cse_magnitude(trials)
    # iI mean = (540+530)/2 = 535
    # cI mean = (580+590)/2 = 585
    # CSE = 535 - 585 = -50 (50ms facilitation)
    assert cse == -50.0


def test_cse_magnitude_returns_nan_with_insufficient_data():
    """If no iI or no cI pairs exist, returns NaN."""
    import math
    trials = [
        {"condition": "congruent", "rt": 500},
        {"condition": "incongruent", "rt": 580},  # cI exists
        {"condition": "congruent", "rt": 510},   # next is congruent — not iI
    ]
    result = cse_magnitude(trials)
    # Has cI but no iI → NaN
    assert math.isnan(result)


def test_cse_magnitude_in_registry():
    """The registry's congruency_sequence entry has cse_magnitude as its validation_metric."""
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    et = EFFECT_REGISTRY["congruency_sequence"]
    assert et.validation_metric is not None
    assert et.validation_metric is cse_magnitude


# ---------------------------------------------------------------------------
# Generalization (audit finding H1) — metric must accept TaskCard-named
# condition labels rather than assuming "congruent"/"incongruent".
# ---------------------------------------------------------------------------

def test_cse_magnitude_uses_custom_condition_labels():
    trials = [
        {"condition": "compatible",   "rt": 500},
        {"condition": "incompatible", "rt": 580},  # cI: high after low
        {"condition": "incompatible", "rt": 540},  # iI: high after high (facilitation)
        {"condition": "compatible",   "rt": 490},
        {"condition": "incompatible", "rt": 590},  # cI
        {"condition": "incompatible", "rt": 530},  # iI
    ]
    cse = cse_magnitude(trials, high_conflict="incompatible", low_conflict="compatible")
    # iI mean = 535, cI mean = 585 → -50
    assert cse == -50.0


def test_cse_magnitude_default_labels_match_existing_taskcards():
    """Without explicit labels, default to incongruent/congruent for back-compat."""
    trials = [
        {"condition": "congruent",   "rt": 500},
        {"condition": "incongruent", "rt": 580},
        {"condition": "incongruent", "rt": 540},
    ]
    # Should compute as before — no label kwargs needed for the existing 4 dev TaskCards
    cse = cse_magnitude(trials)
    # Only one iI pair (540) and one cI pair (580); cse = 540 - 580 = -40
    assert cse == -40.0

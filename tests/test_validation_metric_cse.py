from experiment_bot.effects.validation_metrics import cse_magnitude


def test_cse_magnitude_computes_canonical_difference():
    """cse_magnitude(trials, high, low) returns mean RT(high-after-high) -
    mean RT(high-after-low). Negative values mean facilitation.
    """
    trials = [
        {"condition": "congruent",   "rt": 500},
        {"condition": "incongruent", "rt": 580},  # cI: high after low
        {"condition": "incongruent", "rt": 540},  # iI: high after high
        {"condition": "congruent",   "rt": 490},
        {"condition": "incongruent", "rt": 590},  # cI
        {"condition": "incongruent", "rt": 530},  # iI
    ]
    cse = cse_magnitude(trials, high_conflict="incongruent", low_conflict="congruent")
    # iI mean = 535, cI mean = 585 → -50ms (facilitation)
    assert cse == -50.0


def test_cse_magnitude_returns_nan_with_insufficient_data():
    """If no iI or no cI pairs exist, returns NaN."""
    import math
    trials = [
        {"condition": "congruent", "rt": 500},
        {"condition": "incongruent", "rt": 580},  # cI exists
        {"condition": "congruent", "rt": 510},   # next is congruent — not iI
    ]
    result = cse_magnitude(trials, high_conflict="incongruent", low_conflict="congruent")
    assert math.isnan(result)


def test_cse_magnitude_works_with_arbitrary_label_vocabulary():
    """The wrapper has no Stroop-specific defaults: any (high, low) label
    pair the caller provides is honored verbatim."""
    trials = [
        {"condition": "compatible",   "rt": 500},
        {"condition": "incompatible", "rt": 580},
        {"condition": "incompatible", "rt": 540},
        {"condition": "compatible",   "rt": 490},
        {"condition": "incompatible", "rt": 590},
        {"condition": "incompatible", "rt": 530},
    ]
    cse = cse_magnitude(trials, high_conflict="incompatible", low_conflict="compatible")
    assert cse == -50.0


def test_lag1_pair_modulation_validation_metric_in_registry():
    """The bot's library exposes the generic lag1_pair_contrast metric. The
    paradigm-named cse_magnitude is a thin wrapper for callers using the
    conflict-paradigm conventional name."""
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    from experiment_bot.effects.validation_metrics import lag1_pair_contrast
    et = EFFECT_REGISTRY["lag1_pair_modulation"]
    assert et.validation_metric is lag1_pair_contrast

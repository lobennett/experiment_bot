"""SP11 Phase 2.5 — Gratton 2×2 verification via lag1_pair_modulation.

lag1_pair_modulation with a modulation_table produces the cell-level
2×2 pattern that real conflict-task literature reports. The handler
already exists since SP2; SP11 explicitly tests the Stroop-class cell
arithmetic to lock the behavior in before Phase 5 TaskCard
regeneration.

Canonical conflict-class pattern (e.g., Gratton 1992, Botvinick 2001):
- ``cC`` (congruent after congruent): fast, near-baseline
- ``iI`` (incongruent after incongruent): faster than iC because of
  conflict adaptation
- ``cI`` (incongruent after congruent): slowest — full conflict cost
  without adaptation
- ``iC`` (congruent after incongruent): near-baseline, sometimes
  slight slowing

A table that encodes this pattern correctly produces:
  cell delta arithmetic: iI < cI; cC ≈ iC (within a few ms).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from experiment_bot.effects.handlers import (
    SamplerState, apply_lag1_pair_modulation,
)


def _make_state(prev_cond: str | None, curr_cond: str) -> SamplerState:
    return SamplerState(
        mu=500.0, sigma=50.0, tau=100.0,
        prev_rt=600.0, prev_condition=prev_cond,
        trial_index=10, prev_error=False,
        prev_interrupt_detected=False, condition=curr_cond,
    )


# Stroop-class Gratton table that produces the canonical 2×2 pattern.
# Numbers from sp9c-era expfactory_stroop TaskCard (sp10's f099a88b.json):
#   cC: 0 (no modulation; congruent after congruent is the baseline)
#   iI: -22 (facilitation — repeated incongruent gets adapted)
#   cI: +8  (full conflict cost on alternation)
#   iC: +6  (mild slowing on alternation)
# CSE magnitude = iI − cI = -22 − 8 = -30 ms (in [-45, -10] norm range).
STROOP_GRATTON_TABLE = [
    {"prev": "congruent", "curr": "congruent", "delta_ms": 0},
    {"prev": "incongruent", "curr": "incongruent", "delta_ms": -22},
    {"prev": "congruent", "curr": "incongruent", "delta_ms": 8},
    {"prev": "incongruent", "curr": "congruent", "delta_ms": 6},
]


def _cfg(table, enabled=True, skip_after_error=True):
    return SimpleNamespace(
        enabled=enabled,
        skip_after_error=skip_after_error,
        modulation_table=table,
    )


def test_gratton_cc_cell_returns_baseline():
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(_make_state("congruent", "congruent"), cfg, rng)
    assert delta == 0.0


def test_gratton_ii_cell_returns_facilitation():
    """Incongruent after incongruent → faster (negative delta)."""
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(_make_state("incongruent", "incongruent"), cfg, rng)
    assert delta == -22.0


def test_gratton_ci_cell_returns_full_conflict_cost():
    """Incongruent after congruent → slowest (positive delta, no adaptation)."""
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(_make_state("congruent", "incongruent"), cfg, rng)
    assert delta == 8.0


def test_gratton_ic_cell_returns_mild_slowing():
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(_make_state("incongruent", "congruent"), cfg, rng)
    assert delta == 6.0


def test_gratton_pattern_ii_faster_than_ci():
    """Lock the canonical Gratton-effect inequality: iI < cI."""
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    ii = apply_lag1_pair_modulation(_make_state("incongruent", "incongruent"), cfg, rng)
    ci = apply_lag1_pair_modulation(_make_state("congruent", "incongruent"), cfg, rng)
    assert ii < ci, f"Gratton inequality violated: iI={ii}, cI={ci}"


def test_gratton_pattern_cc_approximately_ic():
    """The canonical pattern has cC ≈ iC (both congruent-current trials
    are at or near baseline). Within ±10ms is the published-range
    convention."""
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    cc = apply_lag1_pair_modulation(_make_state("congruent", "congruent"), cfg, rng)
    ic = apply_lag1_pair_modulation(_make_state("incongruent", "congruent"), cfg, rng)
    assert abs(cc - ic) < 10.0, f"cC={cc}, iC={ic} — pattern should be cC ≈ iC"


def test_gratton_cse_magnitude_in_published_range():
    """CSE magnitude = iI − cI. Published conflict-class range [-45, -10]
    per norms/conflict.json."""
    cfg = _cfg(STROOP_GRATTON_TABLE)
    rng = np.random.default_rng(0)
    ii = apply_lag1_pair_modulation(_make_state("incongruent", "incongruent"), cfg, rng)
    ci = apply_lag1_pair_modulation(_make_state("congruent", "incongruent"), cfg, rng)
    cse = ii - ci
    assert -45 <= cse <= -10, f"cse_magnitude={cse} outside published [-45, -10]"


def test_gratton_skip_after_error_suppresses_modulation():
    """When skip_after_error=True (default), no modulation on the trial
    after an error — error-contamination confound suppressed."""
    cfg = _cfg(STROOP_GRATTON_TABLE, skip_after_error=True)
    state = _make_state("incongruent", "incongruent")
    state.prev_error = True
    rng = np.random.default_rng(0)
    delta = apply_lag1_pair_modulation(state, cfg, rng)
    assert delta == 0.0


def test_gratton_no_modulation_on_first_trial():
    cfg = _cfg(STROOP_GRATTON_TABLE)
    state = _make_state(None, "congruent")  # prev_condition = None
    rng = np.random.default_rng(0)
    assert apply_lag1_pair_modulation(state, cfg, rng) == 0.0


def test_gratton_disabled_returns_zero():
    cfg = _cfg(STROOP_GRATTON_TABLE, enabled=False)
    rng = np.random.default_rng(0)
    for prev in ("congruent", "incongruent", None):
        for curr in ("congruent", "incongruent"):
            assert apply_lag1_pair_modulation(_make_state(prev, curr), cfg, rng) == 0.0


def test_gratton_random_delta_range_supported():
    """Verify the uniform-random delta form (delta_ms_min / delta_ms_max)
    works, in case a paradigm's TaskCard emits a range."""
    table = [
        {"prev": "incongruent", "curr": "incongruent",
         "delta_ms_min": -30, "delta_ms_max": -10},
    ]
    cfg = _cfg(table)
    rng = np.random.default_rng(0)
    # Take many samples and verify they all fall in the range
    state = _make_state("incongruent", "incongruent")
    for _ in range(100):
        delta = apply_lag1_pair_modulation(state, cfg, rng)
        assert -30 <= delta <= -10, f"random delta {delta} outside [-30, -10]"

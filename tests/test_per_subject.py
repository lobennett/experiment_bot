"""Per-subject metric exporter: unit tests on synthetic canonical trials +
an end-to-end reproduction check against the submitted abstract's HUMAN
numbers (the strongest correctness anchor — the abstract's human Stroop
reference must fall out of the committed Eisenberg data)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiment_bot.analysis import per_subject as ps

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Estimator unit tests on hand-built canonical tables
# --------------------------------------------------------------------------- #

def test_stop_signal_metrics_basic():
    trials = pd.DataFrame({
        "order": range(6),
        "condition": ["go", "go", "stop", "go", "stop", "go"],
        "rt":        [500.0, 520.0, np.nan, 480.0, 300.0, np.nan],
        "correct":   [1, 1, 1, 0, 0, 0],   # last go: omission(incorrect); stop2: failed-stop
        "omission":  [False, False, False, False, False, True],
        "ssd":       [np.nan, np.nan, 200.0, np.nan, 250.0, np.nan],
    })
    m = ps.stop_signal_metrics(trials)
    assert m["n_go"] == 4 and m["n_stop"] == 2
    assert m["go_rt"] == pytest.approx((500 + 520) / 2)        # correct go only
    assert m["stop_accuracy"] == pytest.approx(0.5)            # 1 of 2 stops correct
    assert m["mean_stop_failure_RT"] == pytest.approx(300.0)   # the failed stop's RT
    assert m["mean_SSD"] == pytest.approx(225.0)
    assert m["ssrt"] == pytest.approx(510.0 - 225.0)
    assert m["go_omission_rate"] == pytest.approx(0.25)        # 1 of 4 go omitted


def test_stroop_metrics_and_effect():
    trials = pd.DataFrame({
        "order": range(4),
        "condition": ["congruent", "congruent", "incongruent", "incongruent"],
        "rt":        [500.0, 520.0, 600.0, 640.0],
        "correct":   [1, 1, 1, 1],
        "omission":  [False, False, False, False],
    })
    m = ps.stroop_metrics(trials)
    assert m["congruent_rt"] == pytest.approx(510.0)
    assert m["incongruent_rt"] == pytest.approx(620.0)
    assert m["stroop_effect"] == pytest.approx(110.0)


def test_post_error_slowing_and_lag1_within_block():
    # correct/incorrect sequence; omissions are NaN in real data (not 0).
    trials = pd.DataFrame({
        "order": range(5),
        "condition": ["go"] * 5,
        "rt":       [500.0, 510.0, 490.0, 560.0, 520.0],
        "correct":  [1,     1,     0,     1,     1],
        "omission": [False, False, False, False, False],
    })
    # pairs by prev-trial correctness:
    #   (500,510) prev=1 -> after_correct 510
    #   (510,490) prev=1 -> after_correct 490
    #   (490,560) prev=0 -> after_error  560
    #   (560,520) prev=1 -> after_correct 520
    # PES = 560 - mean(510,490,520) = 560 - 506.667 = 53.33
    assert ps.post_error_slowing(trials) == pytest.approx(53.333, abs=0.01)
    # 4 valid within-block pairs (>=3) -> a finite Pearson r
    assert not np.isnan(ps.lag1_autocorr(trials))


def test_lag1_nan_under_three_pairs():
    trials = pd.DataFrame({
        "order": range(2), "condition": ["go", "go"], "rt": [500.0, 520.0],
        "correct": [1, 1], "omission": [False, False],
    })
    assert np.isnan(ps.lag1_autocorr(trials))


def test_within_block_pairs_skip_cross_block():
    trials = pd.DataFrame({
        "order": range(4), "condition": ["go"] * 4,
        "rt": [500.0, 510.0, 520.0, 530.0], "correct": [1, 1, 1, 1],
        "omission": [False] * 4, "block_num": [1, 1, 2, 2],
    })
    pairs = list(ps._within_block_pairs(trials))
    assert len(pairs) == 2  # (0,1) and (2,3); the (1,2) cross-block pair is skipped


def test_omission_excluded_from_pes():
    # an omission between error and next should break that pairing
    trials = pd.DataFrame({
        "order": range(4), "condition": ["go"] * 4,
        "rt": [600.0, 550.0, 500.0, 700.0],
        "correct": [1, 0, 1, 1],
        "omission": [False, True, False, False],  # idx1 is an omission
    })
    # pair (idx1 err, idx2): idx1 omission -> skipped; (idx0 correct, idx1): idx1 omission -> skipped;
    # (idx2 correct, idx3): after_correct 700. after_error empty -> NaN.
    assert np.isnan(ps.post_error_slowing(trials))


# --------------------------------------------------------------------------- #
# Bot canonical loaders on synthetic exports
# --------------------------------------------------------------------------- #

def test_canon_ss_rdoc_and_metrics(tmp_path):
    rows = []
    for i in range(4):
        rows.append({"trial_id": "test_trial", "condition": "go", "rt": 500 + i, "correct_trial": 1, "SSD": ""})
    rows.append({"trial_id": "test_trial", "condition": "stop", "rt": "", "correct_trial": 1, "SSD": 200})
    rows.append({"trial_id": "fixation", "condition": "go", "rt": 1, "correct_trial": 1, "SSD": ""})  # dropped
    df = pd.DataFrame(rows)
    canon = ps._canon_ss_rdoc(df)
    assert len(canon) == 5  # fixation dropped
    m = ps.stop_signal_metrics(canon)
    assert m["n_go"] == 4 and m["n_stop"] == 1
    assert m["mean_SSD"] == pytest.approx(200.0)


def test_canon_cogrun_correctness_from_colour(tmp_path):
    df = pd.DataFrame({
        "text": ["red", "blue"], "colour": ["red", "green"],
        "rt": [500, 600], "response": ["r", "x"],
    })
    canon = ps._canon_cogrun(df)
    assert list(canon["condition"]) == ["congruent", "incongruent"]
    # row0: response 'r' == 'red'[0] -> correct; row1: 'x' != 'green'[0]='g' -> incorrect
    assert list(canon["correct"]) == [1.0, 0.0]


# --------------------------------------------------------------------------- #
# END-TO-END reproduction: human Stroop must match the abstract (672/795/123)
# --------------------------------------------------------------------------- #

_EIS_STROOP = REPO / "data" / "human" / "stroop_eisenberg.csv"
_EIS_STOP = REPO / "data" / "human" / "stop_signal_eisenberg.csv"


@pytest.mark.skipif(not _EIS_STROOP.exists(), reason="Eisenberg Stroop CSV not present (fetched, gitignored)")
def test_human_stroop_reproduces_abstract():
    h = ps.human_stroop_per_subject(_EIS_STROOP)
    s = ps.summarize(h, ["congruent_rt", "incongruent_rt", "stroop_effect"])
    # Abstract: congruent 672±102, incongruent 795±123, effect 123±61
    assert s.loc["congruent_rt", "mean"] == pytest.approx(672, abs=3)
    assert s.loc["incongruent_rt", "mean"] == pytest.approx(795, abs=3)
    assert s.loc["stroop_effect", "mean"] == pytest.approx(123, abs=3)
    assert s.loc["congruent_rt", "n"] >= 480  # ~502 after NaN drop


@pytest.mark.skipif(not _EIS_STOP.exists(), reason="Eisenberg stop CSV not present (fetched, gitignored)")
def test_human_stop_go_rt_reproduces_abstract():
    h = ps.human_stop_signal_per_subject(_EIS_STOP)
    s = ps.summarize(h, ["go_rt"])
    # Abstract go RT human mean 585 (SD differs because the abstract's N=447
    # exclusion does not reproduce — see docs/paper-roadmap.md).
    assert s.loc["go_rt", "mean"] == pytest.approx(585, abs=5)
    assert "stop_acc_in_band" in h.columns


def test_comparison_rows_z_math():
    bot = pd.DataFrame({"congruent_rt": [700.0, 720.0]})       # mean 710
    human = pd.DataFrame({"congruent_rt": [500.0, 600.0, 700.0]})  # mean 600, sd 100
    r = {x["metric"]: x for x in ps.comparison_rows(bot, human, ["congruent_rt"])}["congruent_rt"]
    assert r["bot_mean"] == pytest.approx(710.0)
    assert r["human_mean"] == pytest.approx(600.0)
    assert r["z"] == pytest.approx((710.0 - 600.0) / r["human_sd"])
    assert r["within_1sd"] is False  # |710-600|=110 > sd(100)


# --- SP20: exploratory distribution-level fields (pre-reg planned) ---

def test_comparison_rows_sd_ratio_and_ks():
    rng = __import__("numpy").random.default_rng(7)
    same = rng.normal(600, 80, 200)
    bot = pd.DataFrame({"go_rt": same[:100]})
    human = pd.DataFrame({"go_rt": same[100:]})
    r = {x["metric"]: x for x in ps.comparison_rows(bot, human, ["go_rt"])}["go_rt"]
    # Same-distribution draws: SD ratio near 1, KS non-significant.
    assert r["sd_ratio"] == pytest.approx(r["bot_sd"] / r["human_sd"])
    assert 0.7 < r["sd_ratio"] < 1.4
    assert r["ks_p"] > 0.05

    # Under-dispersed bot cohort (the frozen-dataset failure mode): tiny
    # sd_ratio and a KS rejection even with matched means.
    tight = pd.DataFrame({"go_rt": rng.normal(600, 8, 30)})
    wide = pd.DataFrame({"go_rt": rng.normal(600, 80, 500)})
    r2 = {x["metric"]: x for x in ps.comparison_rows(tight, wide, ["go_rt"])}["go_rt"]
    assert r2["sd_ratio"] < 0.25
    assert r2["ks_p"] < 0.01
    assert abs(r2["z"]) < 1  # ...while the confirmatory mean-location gate passes


def test_comparison_rows_ks_nan_when_insufficient():
    bot = pd.DataFrame({"go_rt": [700.0]})
    human = pd.DataFrame({"go_rt": [500.0, 600.0, 700.0]})
    r = {x["metric"]: x for x in ps.comparison_rows(bot, human, ["go_rt"])}["go_rt"]
    assert np.isnan(r["ks_p"]) and np.isnan(r["sd_ratio"])

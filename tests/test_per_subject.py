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
# Wave C3a: declarative export mapping (runtime.platform_export DSL)
# --------------------------------------------------------------------------- #

def test_canon_from_export_mapping_csv_row_filter_and_fields():
    df = pd.DataFrame({
        "trial_id": ["test_trial", "test_trial", "fixation", "test_trial"],
        "condition": ["congruent", "incongruent", "congruent", "incongruent"],
        "rt": ["500", "600", "1", ""],
        "correct_trial": ["1", "0", "1", "0"],
    })
    mapping = {
        "row_filter": {"equals": {"trial_id": "test_trial"}},
        "fields": {
            "condition": {"column": "condition"},
            "rt": {"column": "rt", "parse": "float"},
            "correct": {"column": "correct_trial", "parse": "truthy"},
        },
    }
    canon = ps.canon_from_export_mapping(df, mapping)
    assert len(canon) == 3  # fixation row dropped
    assert list(canon["condition"]) == ["congruent", "incongruent", "incongruent"]
    assert canon["rt"].tolist()[:2] == [500.0, 600.0]
    # omission derived from missing rt, never mapped directly
    assert np.isnan(canon["rt"].iloc[2]) and bool(canon["omission"].iloc[2])
    assert not canon["omission"].iloc[0]
    assert canon["correct"].tolist()[:2] == [1.0, 0.0]
    assert list(canon["order"]) == [0, 1, 2]


def test_canon_from_export_mapping_json_value_map_one_of_and_passthrough(tmp_path):
    rows = [
        {"phase": "test", "signal": "no", "rt": 450, "acc": True, "delay": None},
        {"phase": "test", "signal": "yes", "rt": None, "acc": True, "delay": 200},
        {"phase": "practice", "signal": "no", "rt": 400, "acc": True, "delay": None},
        {"phase": "test", "signal": "noise", "rt": 999, "acc": False, "delay": None},
    ]
    (tmp_path / "experiment_data.json").write_text(json.dumps(rows))
    df = ps.load_experiment_df(tmp_path)
    mapping = {
        "row_filter": {"equals": {"phase": "test"},
                       "one_of": {"signal": ["no", "yes"]}},
        "fields": {
            "condition": {"column": "signal",
                          "value_map": {"no": "go", "yes": "stop"}},
            "rt": {"column": "rt", "parse": "float"},
            "correct": {"column": "acc", "parse": "truthy"},
            "ssd": {"column": "delay", "parse": "float"},
        },
    }
    canon = ps.canon_from_export_mapping(df, mapping)
    assert len(canon) == 2  # practice + out-of-one_of rows dropped
    assert list(canon["condition"]) == ["go", "stop"]
    assert canon["correct"].tolist() == [1.0, 1.0]
    # extra numeric column passes through under the chosen field name
    assert np.isnan(canon["ssd"].iloc[0]) and canon["ssd"].iloc[1] == 200.0


def test_canon_from_export_mapping_requires_condition_and_rt():
    df = pd.DataFrame({"rt": [1.0]})
    with pytest.raises(ValueError, match="condition"):
        ps.canon_from_export_mapping(df, {"fields": {"rt": {"column": "rt"}}})
    with pytest.raises(ValueError, match="rt"):
        ps.canon_from_export_mapping(df, {"fields": {"condition": {"column": "rt"}}})


def test_canon_from_export_mapping_missing_column_raises():
    df = pd.DataFrame({"cond": ["a"], "rt": [1.0]})
    mapping = {"fields": {"condition": {"column": "nope"},
                          "rt": {"column": "rt", "parse": "float"}}}
    with pytest.raises(ValueError, match="nope"):
        ps.canon_from_export_mapping(df, mapping)


# --------------------------------------------------------------------------- #
# Wave C3b: generic per-subject metrics for unknown paradigms
# --------------------------------------------------------------------------- #

def test_generic_metrics_per_condition_and_temporal():
    # Same RT/correct series as test_post_error_slowing_and_lag1_within_block,
    # so the temporal estimator expectations carry over verbatim.
    trials = pd.DataFrame({
        "order": range(5),
        "condition": ["a", "a", "b", "a", "b"],
        "rt":       [500.0, 510.0, 490.0, 560.0, 520.0],
        "correct":  [1,     1,     0,     1,     1],
        "omission": [False] * 5,
    })
    m = ps.generic_metrics(trials)
    assert m["n_trials"] == 5
    assert m["n_a"] == 3 and m["n_b"] == 2
    assert m["a_rt"] == pytest.approx((500 + 510 + 560) / 3)  # correct-trial RTs
    assert m["b_rt"] == pytest.approx(520.0)                  # the correct b trial
    assert m["a_accuracy"] == pytest.approx(1.0)
    assert m["b_accuracy"] == pytest.approx(0.5)
    assert m["a_omission_rate"] == pytest.approx(0.0)
    assert m["post_error_slowing_ms"] == pytest.approx(53.333, abs=0.01)
    assert not np.isnan(m["lag1_autocorr"])


def test_generic_metrics_without_correct_column_uses_responded_rts():
    trials = pd.DataFrame({
        "order": range(3), "condition": ["a"] * 3,
        "rt": [500.0, np.nan, 520.0],
        "correct": [np.nan] * 3,
        "omission": [False, True, False],
    })
    m = ps.generic_metrics(trials)
    assert m["a_rt"] == pytest.approx(510.0)  # all responded RTs
    assert np.isnan(m["a_accuracy"])
    assert m["a_omission_rate"] == pytest.approx(1 / 3)


# --------------------------------------------------------------------------- #
# Wave C3: card-declared mapping drives collect_bot_per_subject for labels
# with no hand-written loader
# --------------------------------------------------------------------------- #

_FLANKER_CARD = REPO / "taskcards" / "expfactory_flanker" / "41e68e61.json"


@pytest.mark.skipif(not _FLANKER_CARD.exists(), reason="committed flanker card absent")
def test_collect_bot_generic_resolves_card_and_computes_generic_metrics(tmp_path):
    import shutil
    from experiment_bot.taskcard.hashing import taskcard_sha256
    tdir = tmp_path / "taskcards" / "expfactory_flanker"
    tdir.mkdir(parents=True)
    shutil.copy(_FLANKER_CARD, tdir / "41e68e61.json")
    full_hash = taskcard_sha256(json.loads(_FLANKER_CARD.read_text()))

    sd = tmp_path / "out" / "flanker_rdoc" / "2026-01-01_00-00-00"
    sd.mkdir(parents=True)
    pd.DataFrame({
        "trial_id": ["test_trial"] * 4 + ["fixation"],
        "condition": ["congruent", "congruent", "incongruent", "incongruent", "congruent"],
        "rt": [400.0, 420.0, 500.0, np.nan, 1.0],
        "correct_trial": [1, 1, 1, 0, 1],
    }).to_csv(sd / "experiment_data.csv", index=False)
    (sd / "run_metadata.json").write_text(json.dumps({"taskcard_sha256": full_hash}))

    # decoy session whose card hash does NOT resolve under this label
    decoy = tmp_path / "out" / "other_task" / "2026-01-01_00-00-01"
    decoy.mkdir(parents=True)
    (decoy / "experiment_data.csv").write_text("x\n1\n")
    (decoy / "run_metadata.json").write_text(json.dumps({"taskcard_sha256": "ff" * 32}))

    df = ps.collect_bot_per_subject(tmp_path / "out", "expfactory_flanker",
                                    taskcards_dir=tmp_path / "taskcards")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["metrics"] == "generic"
    assert row["n_trials"] == 4  # fixation filtered by the card's row_filter
    assert row["congruent_rt"] == pytest.approx(410.0)
    assert row["incongruent_rt"] == pytest.approx(500.0)
    assert row["incongruent_omission_rate"] == pytest.approx(0.5)


def test_collect_bot_generic_records_error_when_card_lacks_mapping(tmp_path):
    """A resolvable card WITHOUT platform_export yields an error row, not a
    crash (graceful fallback)."""
    import shutil
    from experiment_bot.taskcard.hashing import taskcard_sha256
    payload = json.loads(_FLANKER_CARD.read_text())
    payload["runtime"].pop("platform_export", None)
    tdir = tmp_path / "taskcards" / "mylabel"
    tdir.mkdir(parents=True)
    (tdir / "card.json").write_text(json.dumps(payload))
    full_hash = taskcard_sha256(payload)

    sd = tmp_path / "out" / "flanker_rdoc" / "2026-01-01_00-00-00"
    sd.mkdir(parents=True)
    (sd / "experiment_data.csv").write_text("a,b\n1,2\n")
    (sd / "run_metadata.json").write_text(json.dumps({"taskcard_sha256": full_hash}))

    df = ps.collect_bot_per_subject(tmp_path / "out", "mylabel",
                                    taskcards_dir=tmp_path / "taskcards")
    assert len(df) == 1
    assert "platform_export" in df.iloc[0]["error"]


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

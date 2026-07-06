"""Per-subject metric computation for bot sessions and the human reference.

Design: each paradigm's raw export is normalized into a *canonical trial
table* (columns: ``order, condition, rt, correct, omission`` and, for
stop-signal, ``ssd``; optional ``block_num``). Generic estimators then compute
one metric row from a canonical table, so bot and human flow through identical
code.

Estimator definitions match the submitted abstract's analysis exactly:
  * go/congruent/incongruent RT = mean RT of CORRECT trials in that condition;
  * SSRT = mean-method ``go_rt - mean_SSD`` (NOT the integration method).
    WARNING: this deliberately DIFFERS from the expert pipeline's validation
    oracle (main branch), which computes SSRT by the INTEGRATION method with
    Verbruggen-2019 validity abstention. The two estimators produce
    different numbers from the same sessions by construction; never compare
    an integration-method SSRT with a per-subject SSRT without naming the
    estimator;
  * post-error slowing = ``mean(RT | prev incorrect) - mean(RT | prev correct)``
    over within-block consecutive pairs with valid RTs, excluding omissions;
  * lag-1 autocorrelation = Pearson r of (RT_t, RT_{t+1}) over within-block
    pairs with valid RTs.
These are the "current estimators" the abstract used; field-standard
alternatives (integration SSRT, Dutilh robust PES) are deferred (see
docs/paper-roadmap.md P1-4).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Raw export loading
# --------------------------------------------------------------------------- #

def load_experiment_df(run_dir: Path) -> pd.DataFrame:
    """Load a session's platform export (``experiment_data.csv`` or ``.json``)."""
    run_dir = Path(run_dir)
    files = list(run_dir.glob("experiment_data.*"))
    if not files:
        raise FileNotFoundError(f"no experiment_data.* in {run_dir}")
    f = files[0]
    if f.suffix == ".json":
        return pd.DataFrame(json.loads(f.read_text()))
    return pd.read_csv(f)


def _mean_responded(rt: pd.Series) -> float:
    """Mean of responded RTs (drops NaN and non-positive sentinels)."""
    rt = pd.to_numeric(rt, errors="coerce")
    rt = rt[rt > 0]
    return float(rt.mean()) if len(rt) else float("nan")


# --------------------------------------------------------------------------- #
# Temporal effects (ported verbatim from analysis.ipynb; "current" estimators)
# --------------------------------------------------------------------------- #

def _within_block_pairs(trials: pd.DataFrame):
    """Yield (rt0, rt1, correct0, correct1, omission0, omission1) for
    consecutive trial pairs that share a block. Single block if no block_num."""
    rt = pd.to_numeric(trials["rt"], errors="coerce").to_numpy(dtype=float)
    correct = pd.to_numeric(trials["correct"], errors="coerce").to_numpy(dtype=float)
    omission = (
        trials["omission"].to_numpy()
        if "omission" in trials.columns
        else np.zeros(len(trials), dtype=bool)
    )
    blocks = (
        trials["block_num"].to_numpy()
        if "block_num" in trials.columns
        else np.zeros(len(trials))
    )
    for i in range(len(trials) - 1):
        if blocks[i] != blocks[i + 1]:
            continue
        yield rt[i], rt[i + 1], correct[i], correct[i + 1], bool(omission[i]), bool(omission[i + 1])


def lag1_autocorr(trials: pd.DataFrame) -> float:
    """Lag-1 Pearson autocorrelation of the within-block valid-RT series."""
    prev, curr = [], []
    for r0, r1, _c0, _c1, _o0, _o1 in _within_block_pairs(trials):
        if np.isnan(r0) or np.isnan(r1):
            continue
        prev.append(r0)
        curr.append(r1)
    if len(prev) < 3:
        return float("nan")
    return float(np.corrcoef(prev, curr)[0, 1])


def post_error_slowing(trials: pd.DataFrame) -> float:
    """mean(RT after error) - mean(RT after correct), within-block, valid RTs,
    omissions excluded."""
    after_err, after_cor = [], []
    for r0, r1, c0, _c1, o0, o1 in _within_block_pairs(trials):
        if np.isnan(r0) or np.isnan(r1) or o0 or o1:
            continue
        if c0 == 0:
            after_err.append(r1)
        elif c0 == 1:
            after_cor.append(r1)
    if not after_err or not after_cor:
        return float("nan")
    return float(np.mean(after_err) - np.mean(after_cor))


# --------------------------------------------------------------------------- #
# Generic metric computers over a canonical trial table
# --------------------------------------------------------------------------- #

STOP_SIGNAL_METRICS = [
    "go_accuracy", "go_omission_rate", "go_rt", "go_rt_all_responses",
    "mean_stop_failure_RT", "stop_accuracy", "max_SSD", "mean_SSD", "min_SSD",
    "final_SSD", "ssrt", "lag1_autocorr", "post_error_slowing_ms",
]
STROOP_METRICS = [
    "congruent_accuracy", "congruent_omission_rate", "congruent_rt",
    "incongruent_accuracy", "incongruent_omission_rate", "incongruent_rt",
    "stroop_effect", "lag1_autocorr", "post_error_slowing_ms",
]


def stop_signal_metrics(trials: pd.DataFrame) -> dict:
    """One stop-signal metric row from a canonical trial table."""
    go = trials[trials["condition"] == "go"]
    stop = trials[trials["condition"] == "stop"]
    correct_go = go[go["correct"] == 1]
    failed_stop = stop[stop["correct"] == 0]
    ssd = pd.to_numeric(stop["ssd"], errors="coerce") if "ssd" in stop.columns else pd.Series(dtype=float)
    go_rt = _mean_responded(correct_go["rt"])
    mean_ssd = float(ssd.mean()) if len(ssd.dropna()) else float("nan")
    return {
        "n_trials": int(len(trials)),
        "n_go": int(len(go)),
        "n_stop": int(len(stop)),
        "go_accuracy": float(pd.to_numeric(go["correct"], errors="coerce").mean()) if len(go) else float("nan"),
        "go_omission_rate": float(go["omission"].mean()) if len(go) else float("nan"),
        "go_rt": go_rt,
        "go_rt_all_responses": _mean_responded(go["rt"]),
        "mean_stop_failure_RT": _mean_responded(failed_stop["rt"]) if len(failed_stop) else float("nan"),
        "stop_accuracy": float((pd.to_numeric(stop["correct"], errors="coerce") == 1).mean()) if len(stop) else float("nan"),
        "max_SSD": float(ssd.max()) if len(ssd.dropna()) else float("nan"),
        "mean_SSD": mean_ssd,
        "min_SSD": float(ssd.min()) if len(ssd.dropna()) else float("nan"),
        "final_SSD": float(ssd.dropna().iloc[-1]) if len(ssd.dropna()) else float("nan"),
        "ssrt": go_rt - mean_ssd if not (np.isnan(go_rt) or np.isnan(mean_ssd)) else float("nan"),
        "lag1_autocorr": lag1_autocorr(trials),
        "post_error_slowing_ms": post_error_slowing(trials),
    }


def stroop_metrics(trials: pd.DataFrame) -> dict:
    """One Stroop metric row from a canonical trial table."""
    cong = trials[trials["condition"] == "congruent"]
    incong = trials[trials["condition"] == "incongruent"]
    cong_rt = _mean_responded(cong[cong["correct"] == 1]["rt"])
    incong_rt = _mean_responded(incong[incong["correct"] == 1]["rt"])
    return {
        "n_trials": int(len(trials)),
        "n_congruent": int(len(cong)),
        "n_incongruent": int(len(incong)),
        "congruent_accuracy": float(pd.to_numeric(cong["correct"], errors="coerce").mean()) if len(cong) else float("nan"),
        "congruent_omission_rate": float(cong["omission"].mean()) if len(cong) else float("nan"),
        "congruent_rt": cong_rt,
        "incongruent_accuracy": float(pd.to_numeric(incong["correct"], errors="coerce").mean()) if len(incong) else float("nan"),
        "incongruent_omission_rate": float(incong["omission"].mean()) if len(incong) else float("nan"),
        "incongruent_rt": incong_rt,
        "stroop_effect": incong_rt - cong_rt if not (np.isnan(incong_rt) or np.isnan(cong_rt)) else float("nan"),
        "lag1_autocorr": lag1_autocorr(trials),
        "post_error_slowing_ms": post_error_slowing(trials),
    }


# --------------------------------------------------------------------------- #
# Bot canonical-trial loaders (one per paradigm; match analysis.ipynb)
# --------------------------------------------------------------------------- #

def _canon_ss_rdoc(df: pd.DataFrame) -> pd.DataFrame:
    t = df[df["trial_id"] == "test_trial"].copy()
    rt = pd.to_numeric(t["rt"], errors="coerce")
    out = pd.DataFrame({
        "order": range(len(t)),
        "condition": t["condition"].to_numpy(),
        "rt": rt.to_numpy(),
        "correct": pd.to_numeric(t["correct_trial"], errors="coerce").to_numpy(),
        "omission": rt.isna().to_numpy(),
        "ssd": pd.to_numeric(t["SSD"], errors="coerce").to_numpy(),
    })
    if "block_num" in t.columns:
        out["block_num"] = t["block_num"].to_numpy()
    return out


def _canon_stopit(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    rt = pd.to_numeric(d["rt"], errors="coerce")
    condition = np.where(d["signal"] == "no", "go", np.where(d["signal"] == "yes", "stop", ""))
    correct = d["correct"].astype(str).str.lower().map({"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0})
    omission = ((d["signal"] == "no") & (d["response"].astype(str) == "undefined")).to_numpy()
    out = pd.DataFrame({
        "order": range(len(d)),
        "condition": condition,
        "rt": rt.to_numpy(),
        "correct": correct.to_numpy(),
        "omission": omission,
        "ssd": pd.to_numeric(d["SSD"], errors="coerce").to_numpy(),
    })
    if "block_num" in d.columns:
        out["block_num"] = d["block_num"].to_numpy()
    return out


def _canon_stroop_rdoc(df: pd.DataFrame) -> pd.DataFrame:
    t = df[df["trial_id"] == "test_trial"].copy()
    rt = pd.to_numeric(t["rt"], errors="coerce")
    out = pd.DataFrame({
        "order": range(len(t)),
        "condition": t["condition"].to_numpy(),
        "rt": rt.to_numpy(),
        "correct": pd.to_numeric(t["correct_trial"], errors="coerce").to_numpy(),
        "omission": rt.isna().to_numpy(),
    })
    if "block_num" in t.columns:
        out["block_num"] = t["block_num"].to_numpy()
    return out


def _canon_cogrun(df: pd.DataFrame) -> pd.DataFrame:
    t = df[df["text"].notna()].copy()
    rt = pd.to_numeric(t["rt"], errors="coerce")
    text = t["text"].astype(str).str.lower()
    colour = t["colour"].astype(str).str.lower()
    condition = np.where(text == colour, "congruent", "incongruent")
    # correctness: pressed key == first letter of the ink colour (analysis.ipynb)
    resp = t["response"].astype(str).str.lower()
    correct = (resp == colour.str[0]).astype(float).to_numpy()
    return pd.DataFrame({
        "order": range(len(t)),
        "condition": condition,
        "rt": rt.to_numpy(),
        "correct": correct,
        "omission": rt.isna().to_numpy(),
    })


# label -> (candidate output dir names, canonical-loader, kind, platform, expected_n)
PARADIGMS = {
    "stop_signal_rdoc": {
        "dirs": ["stop_signal_task_(rdoc)", "stop_signal_rdoc"],
        "loader": _canon_ss_rdoc, "kind": "stop_signal", "platform": "expfactory", "expected_n": 180,
    },
    "stopit_stop_signal": {
        "dirs": ["stop-signal_task_(stop-it)", "stop-it_stop-signal_task_(jspsych)",
                 "stop-it_stop_signal_task_(jspsych)", "stop_signal_kywch_jspsych"],
        "loader": _canon_stopit, "kind": "stop_signal", "platform": "stopit", "expected_n": 288,
    },
    "stroop_rdoc": {
        "dirs": ["stroop_(rdoc)", "stroop_rdoc"],
        "loader": _canon_stroop_rdoc, "kind": "stroop", "platform": "expfactory", "expected_n": 120,
    },
    "cognitionrun_stroop": {
        "dirs": ["stroop_online", "stroop_online_(cognition.run)"],
        "loader": _canon_cogrun, "kind": "stroop", "platform": "cognitionrun", "expected_n": 15,
    },
}

_METRIC_FN = {"stop_signal": stop_signal_metrics, "stroop": stroop_metrics}


def session_dirs_for(output_dir: Path, label: str) -> list[Path]:
    """All session dirs (with an export) for a paradigm label, across its
    known output-dir name variants, excluding ``.incomplete`` saves."""
    spec = PARADIGMS[label]
    out = []
    for name in spec["dirs"]:
        d = Path(output_dir) / name
        if not d.exists():
            continue
        for sub in sorted(d.iterdir()):
            if sub.is_dir() and list(sub.glob("experiment_data.*")) and not (sub / ".incomplete").exists():
                out.append(sub)
    return out


def collect_bot_per_subject(output_dir: Path, label: str) -> pd.DataFrame:
    """One metric row per bot session for ``label``. Off-count sessions are
    KEPT (transparency) and flagged via ``complete``; the legacy notebook
    silently dropped them."""
    spec = PARADIGMS[label]
    metric_fn = _METRIC_FN[spec["kind"]]
    rows = []
    for sd in session_dirs_for(output_dir, label):
        try:
            canon = spec["loader"](load_experiment_df(sd))
        except Exception as e:  # malformed export -> record, don't crash
            rows.append({"sub_id": sd.name, "platform": spec["platform"],
                         "source": "bot", "error": str(e)[:120]})
            continue
        m = metric_fn(canon)
        rows.append({
            "sub_id": sd.name, "source": "bot", "platform": spec["platform"],
            "complete": m["n_trials"] == spec["expected_n"], **m,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Human reference (Eisenberg 2019 trial-level) per subject
# --------------------------------------------------------------------------- #

def human_stop_signal_per_subject(csv_path: Path) -> pd.DataFrame:
    """Per-worker stop-signal metrics from the Eisenberg trial-level CSV.

    Adds a documented QC flag ``stop_acc_in_band`` (p(respond|signal) within
    Verbruggen [0.25,0.75]); the abstract's N=447 used an undocumented
    exclusion that does not reproduce — exporting all workers with a
    transparent flag is the defensible alternative (see docs/paper-roadmap.md).
    """
    df = pd.read_csv(csv_path)
    test = df[df["exp_stage"] == "test"].copy()
    test["rt"] = pd.to_numeric(test["rt"], errors="coerce")
    rows = []
    for subj, d in test.groupby("worker_id"):
        d = d.sort_values("trial_num")
        canon = pd.DataFrame({
            "order": range(len(d)),
            "condition": np.where(d["SS_trial_type"] == "go", "go",
                                  np.where(d["SS_trial_type"] == "stop", "stop", "")),
            "rt": d["rt"].to_numpy(),
            "correct": pd.to_numeric(d["correct"], errors="coerce").to_numpy(),
            # human go omissions are flagged by the platform's `stopped` column
            "omission": ((d["SS_trial_type"] == "go") & (d["stopped"] == True)).to_numpy(),  # noqa: E712
            "ssd": pd.to_numeric(d["SS_delay"], errors="coerce").to_numpy(),
        })
        m = stop_signal_metrics(canon)
        rows.append({"sub_id": str(subj), "source": "human", "platform": "human", **m})
    out = pd.DataFrame(rows)
    out["stop_acc_in_band"] = out["stop_accuracy"].between(0.25, 0.75)
    return out


def human_stroop_per_subject(csv_path: Path) -> pd.DataFrame:
    """Per-worker Stroop metrics from the Eisenberg trial-level CSV."""
    df = pd.read_csv(csv_path)
    test = df[df["exp_stage"] == "test"].copy()
    test["rt"] = pd.to_numeric(test["rt"], errors="coerce")
    order_col = "trial_num" if "trial_num" in test.columns else "time_elapsed"
    rows = []
    for subj, d in test.groupby("worker_id"):
        d = d.sort_values(order_col)
        rt = d["rt"]
        canon = pd.DataFrame({
            "order": range(len(d)),
            "condition": d["condition"].to_numpy(),
            "rt": rt.to_numpy(),
            "correct": pd.to_numeric(d["correct"], errors="coerce").to_numpy(),
            # human Stroop omissions: negative-RT sentinel (analysis.ipynb)
            "omission": (rt < 0).to_numpy(),
        })
        m = stroop_metrics(canon)
        rows.append({"sub_id": str(subj), "source": "human", "platform": "human", **m})
    return pd.DataFrame(rows)


HUMAN_LOADER = {"stop_signal": human_stop_signal_per_subject, "stroop": human_stroop_per_subject}
KIND_METRICS = {"stop_signal": STOP_SIGNAL_METRICS, "stroop": STROOP_METRICS}


# --------------------------------------------------------------------------- #
# Cohort summary + bot-vs-human comparison
# --------------------------------------------------------------------------- #

def summarize(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Per-metric mean / SD (ddof=1) / n over a per-subject table, NaN-dropped."""
    rows = []
    for m in metrics:
        if m not in df.columns:
            rows.append({"metric": m, "mean": float("nan"), "sd": float("nan"), "n": 0})
            continue
        s = pd.to_numeric(df[m], errors="coerce").dropna()
        rows.append({"metric": m, "mean": float(s.mean()) if len(s) else float("nan"),
                     "sd": float(s.std(ddof=1)) if len(s) > 1 else float("nan"), "n": int(len(s))})
    return pd.DataFrame(rows).set_index("metric")


def comparison_rows(bot_df: pd.DataFrame, human_df: pd.DataFrame, metrics: list[str]) -> list[dict]:
    """Bot cohort mean positioned in the human between-subject distribution:
    ``z = (bot_mean - human_mean) / human_sd`` and a within-1-SD flag (matches
    the abstract's reporting — the CONFIRMATORY analysis).

    Also carries the pre-registered EXPLORATORY distribution-level fields
    (docs/preregistration.md §Analysis): ``sd_ratio`` (bot between-subject SD
    / human between-subject SD; 1.0 = human-like dispersion) and a two-sample
    Kolmogorov-Smirnov test (``ks_D``, ``ks_p``) of the per-subject
    distributions. These detect the failure mode the confirmatory z cannot:
    a cohort whose mean matches while its members are near-identical
    pseudo-replicates."""
    from scipy import stats as _stats

    bs, hs = summarize(bot_df, metrics), summarize(human_df, metrics)
    out = []
    for m in metrics:
        bm, hm, hsd = bs.loc[m, "mean"], hs.loc[m, "mean"], hs.loc[m, "sd"]
        z = (bm - hm) / hsd if (not np.isnan(bm) and not np.isnan(hm) and hsd and not np.isnan(hsd)) else float("nan")
        bv = pd.to_numeric(bot_df[m], errors="coerce").dropna() if m in bot_df.columns else pd.Series(dtype=float)
        hv = pd.to_numeric(human_df[m], errors="coerce").dropna() if m in human_df.columns else pd.Series(dtype=float)
        sd_ratio, ks_d, ks_p = float("nan"), float("nan"), float("nan")
        if len(bv) >= 2 and len(hv) >= 2:
            bsd_raw, hsd_raw = bv.std(ddof=1), hv.std(ddof=1)
            if hsd_raw:
                sd_ratio = float(bsd_raw / hsd_raw)
            ks = _stats.ks_2samp(bv, hv)
            ks_d, ks_p = float(ks.statistic), float(ks.pvalue)
        out.append({
            "metric": m,
            "bot_mean": bm, "bot_sd": bs.loc[m, "sd"], "bot_n": int(bs.loc[m, "n"]),
            "human_mean": hm, "human_sd": hsd, "human_n": int(hs.loc[m, "n"]),
            "z": z, "within_1sd": bool(abs(bm - hm) < hsd) if not np.isnan(z) else None,
            "sd_ratio": sd_ratio, "ks_D": ks_d, "ks_p": ks_p,
        })
    return out

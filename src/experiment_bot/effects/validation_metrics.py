"""Validation-time metric computations.

Each metric: takes a list of bot trials (dicts) and returns a float (the
metric value). Used by the validation oracle to compare bot output against
published canonical norms.
"""
from __future__ import annotations
from statistics import mean

import numpy as np
from scipy import optimize, stats


def lag1_pair_contrast(
    trials: list[dict],
    focal_curr: str,
    prev_a: str,
    prev_b: str,
) -> float:
    """Generic lag-1 contrast: mean RT on (curr=focal_curr ∧ prev=prev_a)
    minus mean RT on (curr=focal_curr ∧ prev=prev_b).

    The bot's library does not name any specific paradigm metric. CSE
    for Stroop is one configuration:
        focal_curr="incongruent", prev_a="incongruent", prev_b="congruent"
    in which case a negative return indicates facilitation (high after
    high faster than high after low). Other paradigms with 2-back
    interactions configure different labels.

    Returns NaN when either pair set is empty (insufficient data).

    Trials list element keys expected: "condition" (str) and "rt" (float).
    """
    a_pairs: list[float] = []
    b_pairs: list[float] = []
    for i, trial in enumerate(trials):
        if i == 0:
            continue
        if trial.get("condition") != focal_curr:
            continue
        prev = trials[i - 1]
        if prev.get("condition") == prev_a:
            a_pairs.append(trial["rt"])
        elif prev.get("condition") == prev_b:
            b_pairs.append(trial["rt"])
    if not a_pairs or not b_pairs:
        return float("nan")
    return mean(a_pairs) - mean(b_pairs)


def cse_magnitude(
    trials: list[dict],
    high_conflict: str,
    low_conflict: str,
) -> float:
    """Conflict-paradigm convenience wrapper around `lag1_pair_contrast`.

    Computes mean RT(high-after-high) − mean RT(high-after-low). The
    bot's runtime mechanism is the generic `lag1_pair_modulation`;
    this metric name is retained because the conflict literature uses
    "CSE magnitude" as the standard name for this contrast. Labels
    are required — the wrapper does not assume any specific condition
    vocabulary.
    """
    return lag1_pair_contrast(
        trials,
        focal_curr=high_conflict,
        prev_a=high_conflict,
        prev_b=low_conflict,
    )


def fit_ex_gaussian(rt_samples: list[float]) -> dict:
    """Maximum-likelihood fit of ex-Gaussian to RT samples. Returns {mu, sigma, tau}.

    Uses Nelder-Mead optimization on the log-likelihood. Returns mu/sigma/tau
    estimates suitable for population-level comparison.
    """
    samples = np.asarray(rt_samples, dtype=float)
    samples = samples[np.isfinite(samples)]
    if len(samples) < 5:
        return {"mu": float("nan"), "sigma": float("nan"), "tau": float("nan")}

    def neg_log_lik(params):
        mu, sigma, tau = params
        if sigma <= 1.0 or tau <= 1.0:
            return 1e10
        z = (samples - mu) / sigma - sigma / tau
        log_pdf = (
            np.log(1.0 / tau)
            + (sigma * sigma / (2 * tau * tau))
            - ((samples - mu) / tau)
            + np.log(stats.norm.cdf(z) + 1e-30)
        )
        return -np.sum(log_pdf)

    x0 = [
        float(np.mean(samples)) - float(np.std(samples)) * 0.5,
        max(float(np.std(samples)) * 0.7, 5.0),
        max(float(np.std(samples)) * 0.7, 5.0),
    ]
    result = optimize.minimize(neg_log_lik, x0=x0, method="Nelder-Mead",
                               options={"maxiter": 5000, "xatol": 0.01, "fatol": 0.01})
    return {"mu": float(result.x[0]), "sigma": float(result.x[1]), "tau": float(result.x[2])}


def lag1_autocorrelation(rts: list[float]) -> float:
    """Pearson correlation between RT_t and RT_{t-1}."""
    arr = np.asarray(rts, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 3:
        return float("nan")
    return float(np.corrcoef(arr[:-1], arr[1:])[0, 1])


def post_error_slowing_magnitude(trials: list[dict]) -> float:
    """Mean RT on trials following errors minus mean RT on trials following correct.

    Trials list element keys expected: "rt" (float) and "correct" (bool).
    Returns NaN if either post-error or post-correct group is empty.
    """
    post_error: list[float] = []
    post_correct: list[float] = []
    for i, trial in enumerate(trials):
        if i == 0:
            continue
        if trial.get("correct") is not True:
            continue
        prev = trials[i - 1]
        if prev.get("correct") is False:
            post_error.append(float(trial["rt"]))
        elif prev.get("correct") is True:
            post_correct.append(float(trial["rt"]))
    if not post_error or not post_correct:
        return float("nan")
    return float(np.mean(post_error) - np.mean(post_correct))


def population_sd_per_param(sessions: list[dict]) -> dict:
    """SD across N sessions of each ex-Gaussian parameter (mu, sigma, tau).

    Each `session` dict carries "mu", "sigma", "tau" keys (the per-session fit).
    Returns NaN per param when fewer than 2 sessions.
    """
    out: dict[str, float] = {}
    for key in ("mu", "sigma", "tau"):
        vals = [float(s[key]) for s in sessions if key in s and np.isfinite(s.get(key, float("nan")))]
        out[key] = float(np.std(vals, ddof=1)) if len(vals) >= 2 else float("nan")
    return out


def ssrt_integration(go_rts: list[float], p_respond_given_stop: float, mean_ssd: float) -> float:
    """Integration-method SSRT (Verbruggen et al. 2019).

    SSRT = nth_percentile(go_RT_distribution, p_respond_given_stop) - mean_SSD.

    Returns NaN when go_rts is empty or p_respond_given_stop is out of [0, 1].
    """
    arr = np.asarray(go_rts, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return float("nan")
    if not (0.0 <= p_respond_given_stop <= 1.0):
        return float("nan")
    nth = float(np.quantile(arr, p_respond_given_stop))
    return nth - float(mean_ssd)

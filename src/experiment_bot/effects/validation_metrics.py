"""Validation-time metric computations.

Each metric: takes a list of bot trials (dicts) and returns a float (the
metric value). Used by the validation oracle to compare bot output against
published canonical norms.
"""
from __future__ import annotations
from statistics import mean

import numpy as np
from scipy import optimize, stats


def cse_magnitude(
    trials: list[dict],
    high_conflict: str = "incongruent",
    low_conflict: str = "congruent",
) -> float:
    """Mean RT on high-after-high minus mean RT on high-after-low.

    Negative values mean facilitation (the conventional CSE direction).
    Returns NaN when either pair set is empty (insufficient data).

    The condition labels default to "incongruent"/"congruent" for back-
    compat with Stroop-style TaskCards. Pass the actual labels from the
    TaskCard's `temporal_effects.congruency_sequence.value` to make this
    metric work on conflict paradigms with other label conventions
    (e.g. "compatible"/"incompatible").

    Trials list element keys expected: "condition" (str) and "rt" (float).
    """
    high_after_high: list[float] = []
    high_after_low: list[float] = []
    for i, trial in enumerate(trials):
        if i == 0:
            continue
        prev = trials[i - 1]
        if trial.get("condition") != high_conflict:
            continue
        if prev.get("condition") == high_conflict:
            high_after_high.append(trial["rt"])
        elif prev.get("condition") == low_conflict:
            high_after_low.append(trial["rt"])
    if not high_after_high or not high_after_low:
        return float("nan")
    return mean(high_after_high) - mean(high_after_low)


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

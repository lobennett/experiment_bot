"""Human-reference comparison: z-position bot metrics within a human
reference distribution.

This is the analysis the paper abstract reports (bot value vs human mean ± SD
from the RDoC battery session-level summaries). The library code here is
generic — five metric kinds computed over canonical trial dicts — and all
paradigm-conventional knowledge (which human CSV column maps to which bot
computation) lives in committed JSON maps under
``data/human/comparison_maps/`` (goal G2: paradigm knowledge in data, not in
bot-library vocabulary).

Estimator parity matters: the human summaries support SSRT only via the mean
method (``go_rt − mean_SSD``), so the maps derive the bot-side SSRT the same
way (named ``ssrt_mean_method``), NOT via the oracle's integration method.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean, stdev

from experiment_bot.effects.validation_metrics import (
    RT_PLAUSIBLE_MIN_MS,
    RT_PLAUSIBLE_MAX_MS,
)

#: Human-CSV columns ending in this suffix are exclusion flags; a row is kept
#: only when every flag equals "Include". On the RDoC reference summaries this
#: filter reproduces the abstract's exact reference Ns (Stroop 2,478;
#: stop-signal 2,412).
EXCLUSION_COLUMN_SUFFIX = "Exclusions"
INCLUDE_VALUE = "Include"


def load_human_reference(csv_path: Path) -> list[dict]:
    """Load a human reference CSV, applying the Include exclusion filter."""
    with Path(csv_path).open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    exclusion_cols = [c for c in rows[0] if c.endswith(EXCLUSION_COLUMN_SUFFIX)]
    if not exclusion_cols:
        return rows
    return [
        r for r in rows
        if all((r.get(c) or "").strip() == INCLUDE_VALUE for c in exclusion_cols)
    ]


def _parse_float(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "null", "none"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def human_metric_values(rows: list[dict], spec: dict) -> list[float]:
    """Per-row human values for one metric spec.

    spec is either ``{"column": name}`` or ``{"subtract": [col_a, col_b]}``
    (row-wise a − b; both must parse).
    """
    out: list[float] = []
    if "column" in spec:
        for r in rows:
            v = _parse_float(r.get(spec["column"]))
            if v is not None:
                out.append(v)
    elif "subtract" in spec:
        col_a, col_b = spec["subtract"]
        for r in rows:
            a = _parse_float(r.get(col_a))
            b = _parse_float(r.get(col_b))
            if a is not None and b is not None:
                out.append(a - b)
    else:
        raise ValueError(f"Unsupported human metric spec: {spec!r}")
    return out


# ---------------------------------------------------------------------------
# Bot-side per-session metric kinds (generic)
# ---------------------------------------------------------------------------

def _matches(trial: dict, condition: str | None) -> bool:
    return condition is None or trial.get("condition") == condition


def _rt_mean(trials: list[dict], condition: str | None, correct_only: bool) -> float:
    rts = [
        float(t["rt"]) for t in trials
        if _matches(t, condition)
        and not t.get("omission")
        and t.get("rt") is not None
        and RT_PLAUSIBLE_MIN_MS <= float(t["rt"]) <= RT_PLAUSIBLE_MAX_MS
        and (not correct_only or t.get("correct") is True)
    ]
    return mean(rts) if rts else float("nan")


def _accuracy(trials: list[dict], condition: str | None) -> float:
    responded = [t for t in trials if _matches(t, condition) and not t.get("omission")]
    if not responded:
        return float("nan")
    return sum(1 for t in responded if t.get("correct") is True) / len(responded)


def _omission_rate(trials: list[dict], condition: str | None) -> float:
    subset = [t for t in trials if _matches(t, condition)]
    if not subset:
        return float("nan")
    return sum(1 for t in subset if t.get("omission")) / len(subset)


def _field_mean(trials: list[dict], field: str, condition: str | None) -> float:
    vals = [
        float(t[field]) for t in trials
        if _matches(t, condition) and t.get(field) is not None
    ]
    return mean(vals) if vals else float("nan")


def bot_session_metrics(trials: list[dict], metrics_map: dict) -> dict[str, float]:
    """Compute every mapped metric for ONE session's canonical trials.

    ``subtract`` kinds reference other metric names in the same map and are
    resolved after the primitive kinds.
    """
    out: dict[str, float] = {}
    deferred: list[tuple[str, dict]] = []
    for name, spec in metrics_map.items():
        bot = spec["bot"]
        kind = bot["kind"]
        cond = bot.get("condition")
        if kind == "rt_mean":
            out[name] = _rt_mean(trials, cond, bot.get("correct_only", True))
        elif kind == "accuracy":
            out[name] = _accuracy(trials, cond)
        elif kind == "omission_rate":
            out[name] = _omission_rate(trials, cond)
        elif kind == "field_mean":
            out[name] = _field_mean(trials, bot["field"], cond)
        elif kind == "subtract":
            deferred.append((name, bot))
        else:
            raise ValueError(f"Unsupported bot metric kind: {kind!r}")
    for name, bot in deferred:
        a, b = out.get(bot["a"], float("nan")), out.get(bot["b"], float("nan"))
        out[name] = a - b
    return out


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_metrics(
    session_dirs: list[Path],
    trial_loader,
    human_rows: list[dict],
    metrics_map: dict,
) -> dict[str, dict]:
    """Per metric: bot per-session distribution vs the human distribution.

    z = (bot_mean − human_mean) / human_sd — the bot cohort mean positioned
    within the human between-session distribution, exactly the abstract's
    arithmetic. Sessions carrying a ``.incomplete`` marker or yielding zero
    trials are skipped.
    """
    per_session: list[dict[str, float]] = []
    for sd in session_dirs:
        sd = Path(sd)
        if (sd / ".incomplete").exists():
            continue
        trials = trial_loader(sd)
        if not trials:
            continue
        per_session.append(bot_session_metrics(trials, metrics_map))

    results: dict[str, dict] = {}
    for name, spec in metrics_map.items():
        bot_vals = [m[name] for m in per_session if not math.isnan(m.get(name, float("nan")))]
        h_vals = human_metric_values(human_rows, spec["human"])
        bot_mean = mean(bot_vals) if bot_vals else None
        bot_sd = stdev(bot_vals) if len(bot_vals) >= 2 else None
        h_mean = mean(h_vals) if h_vals else None
        h_sd = stdev(h_vals) if len(h_vals) >= 2 else None
        z = None
        if bot_mean is not None and h_mean is not None and h_sd:
            z = (bot_mean - h_mean) / h_sd
        results[name] = {
            "bot_mean": bot_mean,
            "bot_sd": bot_sd,
            "bot_n": len(bot_vals),
            "human_mean": h_mean,
            "human_sd": h_sd,
            "human_n": len(h_vals),
            "z": z,
            "within_1sd": (abs(z) < 1.0) if z is not None else None,
        }
    return results

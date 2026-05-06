"""Validation oracle: scores bot sessions against published canonical norms.

Reads bot output (bot_log.json per session) plus a norms dict. Dispatches
each metric in the norms file through a registry that maps metric name ->
(pillar, computer, sub_keys). Pillars accumulate dynamically based on
which metrics appear in the norms file — adding a new metric for a
novel paradigm class means registering one entry, not editing this
oracle.

NULL-range metrics (no canonical meta-analytic range) are descriptive-only:
the oracle reports the bot's computed value alongside a null range and
pass_=None — never gating overall pass/fail.
"""
from __future__ import annotations
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from experiment_bot.effects.validation_metrics import (
    cse_magnitude, fit_ex_gaussian, lag1_autocorrelation,
    population_sd_per_param, post_error_slowing_magnitude,
)

logger = logging.getLogger(__name__)


@dataclass
class MetricResult:
    name: str
    bot_value: float | None
    published_range: tuple[float, float] | None
    pass_: bool | None       # None for descriptive-only metrics
    citations: list = field(default_factory=list)


@dataclass
class PillarResult:
    pillar: str
    metrics: dict[str, MetricResult]
    pass_: bool


@dataclass
class ValidationReport:
    paradigm_class: str
    pillar_results: dict[str, PillarResult]
    overall_pass: bool
    summary: str


def _in_range(value, range_) -> bool | None:
    """Returns True/False if value is in/out of range; None if range is unspecified."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    if range_ is None:
        return None
    if not isinstance(range_, (list, tuple)) or len(range_) != 2:
        return None
    lo, hi = range_
    if lo is None or hi is None:
        return None
    return float(lo) <= float(value) <= float(hi)


def _load_session_log(session_dir: Path) -> list[dict]:
    log_path = Path(session_dir) / "bot_log.json"
    if not log_path.exists():
        return []
    try:
        return json.loads(log_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []


def _gather_bot_rts(sessions: list[Path], condition: str | None = None) -> list[float]:
    out: list[float] = []
    for s in sessions:
        for trial in _load_session_log(s):
            if trial.get("omission"):
                continue
            if condition and trial.get("condition") != condition:
                continue
            rt = trial.get("actual_rt_ms")
            if rt is not None:
                out.append(float(rt))
    return out


def _annotate_correct(trial: dict) -> dict:
    """Attach a 'correct' bool and normalize 'rt' key from bot log format."""
    correct = not trial.get("intended_error", False) and not trial.get("omission", False)
    rt = trial.get("rt") if "rt" in trial else trial.get("actual_rt_ms")
    return {**trial, "correct": correct, "rt": float(rt) if rt is not None else None}


# ---------------------------------------------------------------------------
# Metric dispatch registry
# ---------------------------------------------------------------------------
#
# Each entry maps a metric name (as it appears in a norms file) to:
#   - pillar:   string name of the pillar this metric belongs to. Pillars
#               accumulate dynamically; novel pillars (e.g. "speed_accuracy")
#               work without code changes.
#   - compute:  callable that given (session_dirs, ctx) returns either:
#                 * a single float (single-value metric), or
#                 * a dict[str, float] (multi-value metric, one MetricResult
#                   per sub-key).
#   - sub_keys: None for single-value metrics; for multi-value metrics, the
#               list of sub-keys mapped to range-keys via `range_key_fmt`.
#   - range_key:        the field in the norms entry holding the published
#                       range (used when sub_keys is None). E.g. "range_ms".
#   - range_key_fmt:    when sub_keys is non-None, a format string mapping
#                       each sub-key to its corresponding norms-entry field.
#                       E.g. "{key}_range" → "mu_range", "sigma_range", ...
#   - result_name_fmt:  when sub_keys is non-None, a format string for the
#                       MetricResult.name. E.g. "{key}_sd" or "{key}".
#
# Adding a new metric for a novel paradigm class means appending one entry
# here plus a `compute` function. The norms file declares which metrics
# (and which pillars) apply; the oracle iterates over the norms file rather
# than running hardcoded if-blocks.


@dataclass
class MetricSpec:
    pillar: str
    compute: Callable[[list[Path], dict], Any]
    sub_keys: list[str] | None = None
    range_key: str = "range"
    range_key_fmt: str = "{key}_range"
    result_name_fmt: str = "{key}"


def _compute_rt_distribution(session_dirs: list[Path], ctx: dict) -> dict:
    rts = _gather_bot_rts(session_dirs)
    return fit_ex_gaussian(rts) if rts else {
        "mu": float("nan"), "sigma": float("nan"), "tau": float("nan")
    }


def _compute_lag1(session_dirs: list[Path], ctx: dict) -> float:
    rts = _gather_bot_rts(session_dirs)
    return lag1_autocorrelation(rts) if rts else float("nan")


def _compute_pes(session_dirs: list[Path], ctx: dict) -> float:
    all_trials: list[dict] = []
    for s in session_dirs:
        for t in _load_session_log(s):
            all_trials.append(_annotate_correct(t))
    valid = [t for t in all_trials if t.get("rt") is not None]
    return post_error_slowing_magnitude(valid) if valid else float("nan")


def _compute_cse(session_dirs: list[Path], ctx: dict) -> float:
    cse_labels = ctx.get("cse_labels")
    cse_trials: list[dict] = []
    for s in session_dirs:
        for t in _load_session_log(s):
            if not t.get("omission") and t.get("actual_rt_ms") is not None:
                cse_trials.append({"condition": t.get("condition"),
                                    "rt": float(t["actual_rt_ms"])})
    if not cse_trials:
        return float("nan")
    if cse_labels:
        high, low = cse_labels
        return cse_magnitude(cse_trials, high_conflict=high, low_conflict=low)
    return cse_magnitude(cse_trials)


def _compute_between_subject_sd(session_dirs: list[Path], ctx: dict) -> dict:
    per_session_fits = []
    for s in session_dirs:
        rts = _gather_bot_rts([s])
        if rts:
            per_session_fits.append(fit_ex_gaussian(rts))
    if len(per_session_fits) < 2:
        return {"mu": float("nan"), "sigma": float("nan"), "tau": float("nan")}
    return population_sd_per_param(per_session_fits)


METRIC_REGISTRY: dict[str, MetricSpec] = {
    "rt_distribution": MetricSpec(
        pillar="rt_distribution",
        compute=_compute_rt_distribution,
        sub_keys=["mu", "sigma", "tau"],
        range_key_fmt="{key}_range",
        result_name_fmt="{key}",
    ),
    "lag1_autocorr": MetricSpec(
        pillar="sequential",
        compute=_compute_lag1,
        range_key="range",
    ),
    "post_error_slowing": MetricSpec(
        pillar="sequential",
        compute=_compute_pes,
        range_key="range_ms",
    ),
    "cse_magnitude": MetricSpec(
        pillar="sequential",
        compute=_compute_cse,
        range_key="range_ms",
    ),
    "between_subject_sd": MetricSpec(
        pillar="individual_differences",
        compute=_compute_between_subject_sd,
        sub_keys=["mu", "sigma", "tau"],
        range_key_fmt="{key}_sd_range",
        result_name_fmt="{key}_sd",
    ),
}


def validate_session_set(
    paradigm_class: str,
    session_dirs: list[Path],
    norms: dict,
    cse_labels: tuple[str, str] | None = None,
) -> ValidationReport:
    """Score bot sessions against published canonical norms.

    Iterates over the norms file's metrics dict, dispatching each through
    METRIC_REGISTRY. Pillars accumulate dynamically based on which metrics
    appear; new pillars (e.g. "speed_accuracy") and new metrics work
    without code changes here — register a `MetricSpec` and the norms file
    declares which apply per paradigm class.

    `cse_labels`, when supplied, is `(high_conflict_condition, low_conflict_condition)`.
    The Reasoner-chosen labels override the metric's defaults
    ('incongruent'/'congruent') for paradigms with non-Stroop label
    conventions.
    """
    metrics_def: dict[str, dict] = norms.get("metrics", {})
    pillars: dict[str, PillarResult] = {}
    ctx = {"cse_labels": cse_labels}

    def _pillar(name: str) -> PillarResult:
        if name not in pillars:
            pillars[name] = PillarResult(pillar=name, metrics={}, pass_=True)
        return pillars[name]

    def _add(pillar: PillarResult, mr: MetricResult) -> None:
        pillar.metrics[mr.name] = mr
        if mr.pass_ is False:
            pillar.pass_ = False

    for metric_name, metric_def in metrics_def.items():
        spec = METRIC_REGISTRY.get(metric_name)
        if spec is None:
            logger.warning(
                "Unknown metric %r in norms file (no registered MetricSpec); "
                "skipping. Register one in oracle.METRIC_REGISTRY to compute it.",
                metric_name,
            )
            continue

        pillar = _pillar(spec.pillar)
        value = spec.compute(session_dirs, ctx)
        citations = metric_def.get("citations", [])

        if spec.sub_keys is None:
            # Single-value metric
            rng = metric_def.get(spec.range_key)
            float_value = value if not (isinstance(value, float) and math.isnan(value)) else None
            _add(pillar, MetricResult(
                name=metric_name,
                bot_value=float_value,
                published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
                pass_=_in_range(value, rng),
                citations=citations,
            ))
        else:
            # Multi-value metric: emit one MetricResult per sub-key
            for key in spec.sub_keys:
                rng_field = spec.range_key_fmt.format(key=key)
                rng = metric_def.get(rng_field)
                sub_value = value.get(key, float("nan")) if isinstance(value, dict) else float("nan")
                bot_v = sub_value if not (isinstance(sub_value, float) and math.isnan(sub_value)) else None
                _add(pillar, MetricResult(
                    name=spec.result_name_fmt.format(key=key),
                    bot_value=bot_v,
                    published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
                    pass_=_in_range(sub_value, rng),
                    citations=citations,
                ))

    # Overall pass: AND of all gating metric passes (None = ignored).
    overall = True
    has_any_gate = False
    for p in pillars.values():
        for m in p.metrics.values():
            if m.pass_ is False:
                overall = False
            if m.pass_ is not None:
                has_any_gate = True
    if not has_any_gate:
        overall = False  # no concrete gates means we can't assert pass

    return ValidationReport(
        paradigm_class=paradigm_class,
        pillar_results=pillars,
        overall_pass=overall,
        summary=f"paradigm_class={paradigm_class} pass={overall}",
    )

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


def _default_bot_log_loader(session_dir: Path) -> list[dict]:
    """Default trial loader: reads bot_log.json and produces canonical
    trial dicts (condition, rt, correct, omission). Used as a fallback
    when no platform-data adapter is registered for the label.

    Note: bot_log.json reflects the bot's own polling-loop matches, which
    can over- or under-count actual platform trials depending on
    paradigm-specific stimulus-detection granularity. Prefer a platform
    adapter from `validation/platform_adapters.py` when available.
    """
    log_path = Path(session_dir) / "bot_log.json"
    if not log_path.exists():
        return []
    try:
        raw = json.loads(log_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    out: list[dict] = []
    for t in raw:
        rt = t.get("actual_rt_ms")
        if rt is None and "rt" in t:
            rt = t.get("rt")
        try:
            rt_float = float(rt) if rt is not None else None
        except (TypeError, ValueError):
            rt_float = None
        omission = bool(t.get("omission", False)) or rt_float is None
        # bot_log records intended_error; if False the bot pressed the
        # correct key, if True it deliberately pressed a wrong one
        correct = (not t.get("intended_error", False)) and not omission
        out.append({
            "condition": t.get("condition") or "",
            "rt": rt_float,
            "correct": correct,
            "omission": omission,
        })
    return out


def _gather_rts(
    sessions: list[Path],
    trial_loader,
    condition: str | None = None,
) -> list[float]:
    out: list[float] = []
    for s in sessions:
        for trial in trial_loader(s):
            if trial.get("omission"):
                continue
            if condition and trial.get("condition") != condition:
                continue
            rt = trial.get("rt")
            if rt is not None:
                out.append(float(rt))
    return out


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
    loader = ctx["trial_loader"]
    rts = _gather_rts(session_dirs, loader)
    return fit_ex_gaussian(rts) if rts else {
        "mu": float("nan"), "sigma": float("nan"), "tau": float("nan")
    }


def _compute_lag1(session_dirs: list[Path], ctx: dict) -> float:
    loader = ctx["trial_loader"]
    rts = _gather_rts(session_dirs, loader)
    return lag1_autocorrelation(rts) if rts else float("nan")


def _compute_pes(session_dirs: list[Path], ctx: dict) -> float:
    loader = ctx["trial_loader"]
    all_trials: list[dict] = []
    for s in session_dirs:
        all_trials.extend(loader(s))
    valid = [t for t in all_trials if t.get("rt") is not None]
    return post_error_slowing_magnitude(valid) if valid else float("nan")


def _compute_cse(session_dirs: list[Path], ctx: dict) -> float:
    """Compute the conflict-paradigm CSE contrast using the labels declared
    in the TaskCard's `lag1_pair_modulation.modulation_table`. Returns NaN
    when no labels are supplied — the oracle does not assume any specific
    condition vocabulary.
    """
    loader = ctx["trial_loader"]
    contrast = ctx.get("contrast_labels")
    if not contrast:
        return float("nan")
    high, low = contrast
    cse_trials: list[dict] = []
    for s in session_dirs:
        for t in loader(s):
            if not t.get("omission") and t.get("rt") is not None:
                cse_trials.append({"condition": t.get("condition"), "rt": float(t["rt"])})
    if not cse_trials:
        return float("nan")
    return cse_magnitude(cse_trials, high_conflict=high, low_conflict=low)


def _compute_between_subject_sd(session_dirs: list[Path], ctx: dict) -> dict:
    loader = ctx["trial_loader"]
    per_session_fits = []
    for s in session_dirs:
        rts = _gather_rts([s], loader)
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
    contrast_labels: tuple[str, str] | None = None,
    trial_loader=None,
) -> ValidationReport:
    """Score bot sessions against published canonical norms.

    Iterates over the norms file's metrics dict, dispatching each through
    METRIC_REGISTRY. Pillars accumulate dynamically based on which metrics
    appear; new pillars (e.g. "speed_accuracy") and new metrics work
    without code changes here — register a `MetricSpec` and the norms file
    declares which apply per paradigm class.

    `contrast_labels`, when supplied, is the (high, low) pair of condition
    labels driving any 2-back contrast metric (e.g. cse_magnitude). The
    CLI extracts these from the TaskCard's
    `lag1_pair_modulation.modulation_table`; oracle does not assume any
    specific condition vocabulary.

    `trial_loader`, when supplied, is a callable
    `(session_dir: Path) -> list[trial_dict]` returning canonical trial
    records `{condition, rt, correct, omission}`. The CLI passes a
    platform-data adapter from `validation/platform_adapters.py` here so
    metrics are computed against the experiment's own data export rather
    than `bot_log.json` (which can over-/under-count platform trials).
    Defaults to `_default_bot_log_loader` for back-compat.
    """
    metrics_def: dict[str, dict] = norms.get("metrics", {})
    pillars: dict[str, PillarResult] = {}
    if trial_loader is None:
        trial_loader = _default_bot_log_loader
    ctx = {"contrast_labels": contrast_labels, "trial_loader": trial_loader}

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

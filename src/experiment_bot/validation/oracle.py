"""Validation oracle: scores bot sessions against published canonical norms.

Reads bot output (bot_log.json per session) plus a norms dict. Computes
universal metrics (RT distribution shape, lag-1 autocorr, PES, population SD)
and paradigm-specific metrics (CSE for conflict, SSRT for interrupt) where
applicable. Reports per-pillar pass/fail.

NULL-range metrics (no canonical meta-analytic range) are descriptive-only:
the oracle reports the bot's computed value alongside a null range and
pass_=None — never gating overall pass/fail.
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from experiment_bot.effects.validation_metrics import (
    cse_magnitude, fit_ex_gaussian, lag1_autocorrelation,
    population_sd_per_param, post_error_slowing_magnitude,
)


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


def validate_session_set(
    paradigm_class: str,
    session_dirs: list[Path],
    norms: dict,
    cse_labels: tuple[str, str] | None = None,
) -> ValidationReport:
    """Score bot sessions against published canonical norms.

    Returns a ValidationReport with three pillars (rt_distribution, sequential,
    individual_differences) plus an overall_pass = AND of gating-metric passes.
    Metrics whose published range is None (or list of nulls) are descriptive-
    only with pass_=None and do not contribute to gating.

    `cse_labels`, when supplied, is `(high_conflict_condition, low_conflict_condition)`
    — the Reasoner-chosen TaskCard labels for this paradigm's high/low conflict
    trials. Without it, cse_magnitude defaults to 'incongruent'/'congruent'
    (Stroop convention) and may report NaN on paradigms using other labels.
    """
    metrics_def: dict[str, dict] = norms.get("metrics", {})

    # Helpers for pillar accumulation
    rt_pillar = PillarResult(pillar="rt_distribution", metrics={}, pass_=True)
    seq_pillar = PillarResult(pillar="sequential", metrics={}, pass_=True)
    ind_pillar = PillarResult(pillar="individual_differences", metrics={}, pass_=True)

    def _add(pillar: PillarResult, mr: MetricResult) -> None:
        pillar.metrics[mr.name] = mr
        if mr.pass_ is False:
            pillar.pass_ = False

    # Pillar 1: RT distribution
    rt_def = metrics_def.get("rt_distribution", {})
    if rt_def:
        all_rts = _gather_bot_rts(session_dirs)
        fit = fit_ex_gaussian(all_rts) if all_rts else {"mu": float("nan"), "sigma": float("nan"), "tau": float("nan")}
        for param in ("mu", "sigma", "tau"):
            range_key = f"{param}_range"
            rng = rt_def.get(range_key)
            value = fit[param]
            pass_ = _in_range(value, rng)
            _add(rt_pillar, MetricResult(
                name=param, bot_value=value if not math.isnan(value) else None,
                published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
                pass_=pass_,
                citations=rt_def.get("citations", []),
            ))

    # Pillar 2: Sequential effects
    if "lag1_autocorr" in metrics_def:
        rts = _gather_bot_rts(session_dirs)
        bot_lag1 = lag1_autocorrelation(rts) if rts else float("nan")
        rng = metrics_def["lag1_autocorr"].get("range")
        _add(seq_pillar, MetricResult(
            name="lag1_autocorr",
            bot_value=bot_lag1 if not math.isnan(bot_lag1) else None,
            published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
            pass_=_in_range(bot_lag1, rng),
            citations=metrics_def["lag1_autocorr"].get("citations", []),
        ))

    if "post_error_slowing" in metrics_def:
        all_trials: list[dict] = []
        for s in session_dirs:
            for t in _load_session_log(s):
                all_trials.append(_annotate_correct(t))
        # Filter out trials where rt could not be determined
        valid_trials = [t for t in all_trials if t.get("rt") is not None]
        bot_pes = post_error_slowing_magnitude(valid_trials) if valid_trials else float("nan")
        rng = metrics_def["post_error_slowing"].get("range_ms")
        _add(seq_pillar, MetricResult(
            name="post_error_slowing",
            bot_value=bot_pes if not math.isnan(bot_pes) else None,
            published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
            pass_=_in_range(bot_pes, rng),
            citations=metrics_def["post_error_slowing"].get("citations", []),
        ))

    if "cse_magnitude" in metrics_def:
        cse_trials: list[dict] = []
        for s in session_dirs:
            for t in _load_session_log(s):
                if not t.get("omission") and t.get("actual_rt_ms") is not None:
                    cse_trials.append({"condition": t.get("condition"), "rt": float(t["actual_rt_ms"])})
        if cse_labels:
            high_label, low_label = cse_labels
            bot_cse = cse_magnitude(
                cse_trials, high_conflict=high_label, low_conflict=low_label,
            ) if cse_trials else float("nan")
        else:
            bot_cse = cse_magnitude(cse_trials) if cse_trials else float("nan")
        rng = metrics_def["cse_magnitude"].get("range_ms")
        _add(seq_pillar, MetricResult(
            name="cse_magnitude",
            bot_value=bot_cse if not math.isnan(bot_cse) else None,
            published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
            pass_=_in_range(bot_cse, rng),
            citations=metrics_def["cse_magnitude"].get("citations", []),
        ))

    # Pillar 3: Individual differences (population SD)
    bsd_def = metrics_def.get("between_subject_sd", {})
    if bsd_def:
        per_session_fits = []
        for s in session_dirs:
            rts = _gather_bot_rts([s])
            if rts:
                per_session_fits.append(fit_ex_gaussian(rts))
        sds = population_sd_per_param(per_session_fits) if len(per_session_fits) >= 2 else {
            "mu": float("nan"), "sigma": float("nan"), "tau": float("nan")
        }
        for param in ("mu", "sigma", "tau"):
            range_key = f"{param}_sd_range"
            rng = bsd_def.get(range_key)
            value = sds[param]
            _add(ind_pillar, MetricResult(
                name=f"{param}_sd",
                bot_value=value if not math.isnan(value) else None,
                published_range=tuple(rng) if rng and all(v is not None for v in rng) else None,
                pass_=_in_range(value, rng),
                citations=bsd_def.get("citations", []),
            ))

    # Overall pass: AND of all gating metric passes (None = ignored).
    pillars = [rt_pillar, seq_pillar, ind_pillar]
    overall = True
    has_any_gate = False
    for p in pillars:
        for m in p.metrics.values():
            if m.pass_ is False:
                overall = False
            if m.pass_ is not None:
                has_any_gate = True
    if not has_any_gate:
        overall = False  # no concrete gates means we can't assert pass

    return ValidationReport(
        paradigm_class=paradigm_class,
        pillar_results={
            "rt_distribution": rt_pillar,
            "sequential": seq_pillar,
            "individual_differences": ind_pillar,
        },
        overall_pass=overall,
        summary=f"paradigm_class={paradigm_class} pass={overall}",
    )

"""Calibration offset estimator.

Given a list of :class:`KeypressEvent` from the calibration phase,
compute the offset model the executor will subtract from sampled RTs
at trial time so that ``platform_recorded_rt ≈ sampler_target_rt``.

Three escalating model forms, picked automatically by the estimator:

1. **fixed-offset** — when correctly-recorded events have a small,
   unimodal SD (≤ 30 ms), use a single
   ``(mean_offset_ms, sd_offset_ms)`` pair. The trial-time
   adjustment subtracts ``mean_offset_ms`` from each sampled RT.

2. **per-trial regression** — when SD > 30 ms (the fixed-offset
   residual would re-inflate the recorded distribution's sigma),
   fit a linear regression of ``platform_rt`` on ``bot_intended_rt``.
   Trial-time adjustment uses ``(slope, intercept)``: the
   adjusted-sampled-RT solves ``slope * adj + intercept = target_rt``.

3. **escalate** — when the offset distribution is bimodal (per the
   spec criterion: two cluster means separated by >50 ms AND
   smaller cluster has ≥20% of mass), the platform is using two
   distinct recording paths and a single fitted model wouldn't
   capture either. Calibration returns
   ``CalibrationResult(model="escalate", ...)`` and the executor
   stops; project owner decides remediation.

The estimator never raises on data shape; it always returns a
:class:`CalibrationResult` with a clear ``model`` field. Callers
inspect the model and decide whether to apply it or escalate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from experiment_bot.calibration.deliverer import KeypressEvent


# Thresholds per the calibration spec.
_SD_FIXED_OFFSET_THRESHOLD_MS = 30.0
_BIMODAL_SEPARATION_THRESHOLD_MS = 50.0
_BIMODAL_MASS_THRESHOLD = 0.20
# Within-cluster SD ratio: declaring bimodal requires the cluster
# separation to be large relative to within-cluster spread, not just
# large in absolute terms. Without this, k-means on a unimodal-but-
# high-SD distribution would falsely declare bimodality (k=2 always
# finds two "clusters" — the question is whether they're real).
# Empirical calibration: a unimodal Gaussian with SD=50 has within-
# cluster SD ~30 after median split and centroids at ±40ms, ratio
# ~80/30 ≈ 2.7. A bimodal mixture of two narrow modes has ratio
# 10+. Threshold of 3.0 separates them cleanly.
_BIMODAL_SEPARATION_TO_WITHIN_SD_RATIO = 3.0
_MIN_CALIBRATION_EVENTS = 5  # Below this, even fixed-offset is unreliable


@dataclass
class CalibrationResult:
    """Result of the calibration estimator.

    ``model`` is one of:
      - ``"fixed_offset"``: use ``mean_offset_ms`` directly. Apply
        as ``adjusted_rt = sampler_target_rt − mean_offset_ms``.
      - ``"regression"``: fit was a linear model. Apply as
        ``adjusted_rt = (sampler_target_rt − intercept_ms) / slope``
        (inverse of the platform's mapping). When ``slope = 1``
        this collapses to the fixed-offset form with
        ``mean_offset_ms = intercept_ms``.
      - ``"escalate"``: don't apply ANY adjustment; the platform's
        offset distribution is bimodal or too sparse to fit safely.
        Phase 7 should report the un-calibrated z-score with explicit
        scope-of-validity disclosure.
      - ``"too_few_events"``: fewer than the minimum 5 correctly-
        recorded events survived the filter. Treat as escalate.

    All ``ms`` fields are in milliseconds. ``n_events_*`` counts
    are reported descriptively for the deliverable.
    """
    model: Literal["fixed_offset", "regression", "escalate", "too_few_events"]
    mean_offset_ms: float = 0.0
    sd_offset_ms: float = 0.0
    slope: float = 1.0
    intercept_ms: float = 0.0
    n_events_total: int = 0
    n_events_correctly_recorded: int = 0
    n_events_dropped: int = 0
    n_events_misrecorded: int = 0
    bimodal_detected: bool = False
    bimodal_cluster_means_ms: tuple[float, float] | None = None
    bimodal_smaller_mass: float | None = None
    reason: str = ""
    # Raw filtered offsets (for downstream histogram in deliverable doc).
    offsets_ms: list[float] = field(default_factory=list)

    def adjust(self, sampler_target_rt_ms: float) -> float:
        """Apply the fitted model to a sampler-target RT, returning the
        bot-intended RT that the executor should request from the
        deliverer in order for the platform's recorded RT to land near
        ``sampler_target_rt_ms``.

        For ``escalate`` / ``too_few_events`` models, returns the
        input unchanged (no adjustment applied — Phase 7 reports the
        un-calibrated z-score).
        """
        if self.model == "fixed_offset":
            return sampler_target_rt_ms - self.mean_offset_ms
        if self.model == "regression":
            if self.slope == 0:
                return sampler_target_rt_ms - self.intercept_ms
            return (sampler_target_rt_ms - self.intercept_ms) / self.slope
        return sampler_target_rt_ms


def _filter_events(events: Iterable[KeypressEvent]) -> tuple[
    list[KeypressEvent], dict[str, int]
]:
    """Apply the calibration-spec filter:
       only correctly-recorded events (platform recorded the bot's key).

    Returns the filtered list plus a counts dict for the
    deliverable.
    """
    correct: list[KeypressEvent] = []
    counts = {"total": 0, "dropped": 0, "misrecorded": 0, "correct": 0}
    for ev in events:
        counts["total"] += 1
        if ev.platform_recorded_key is None or ev.platform_recorded_rt_ms is None:
            counts["dropped"] += 1
            continue
        if ev.platform_recorded_key != ev.key:
            counts["misrecorded"] += 1
            continue
        correct.append(ev)
        counts["correct"] += 1
    return correct, counts


def _is_bimodal(offsets: list[float]) -> tuple[bool, tuple[float, float] | None, float | None]:
    """Detect bimodality per the calibration spec criterion:
       two cluster means separated by > 50 ms AND smaller cluster has
       ≥ 20% of mass.

    Uses k=2 k-means with simple median-split init (no sklearn
    dependency for a 30-point clustering).

    Returns ``(is_bimodal, (mean_a, mean_b), smaller_mass)``. The
    cluster-means tuple is ordered ascending. ``smaller_mass`` is the
    fraction of points in the less-populated cluster.
    """
    if len(offsets) < 10:
        # Too few points to reason about bimodality at all.
        return False, None, None

    # Simple 2-means via median-split init, 1-D
    sorted_off = sorted(offsets)
    median = sorted_off[len(sorted_off) // 2]
    centroid_a = sum(o for o in offsets if o < median) / max(
        1, sum(1 for o in offsets if o < median)
    )
    centroid_b = sum(o for o in offsets if o >= median) / max(
        1, sum(1 for o in offsets if o >= median)
    )
    # 10 iterations of Lloyd's
    for _ in range(10):
        cluster_a, cluster_b = [], []
        for o in offsets:
            if abs(o - centroid_a) < abs(o - centroid_b):
                cluster_a.append(o)
            else:
                cluster_b.append(o)
        if cluster_a:
            new_a = sum(cluster_a) / len(cluster_a)
        else:
            new_a = centroid_a
        if cluster_b:
            new_b = sum(cluster_b) / len(cluster_b)
        else:
            new_b = centroid_b
        if abs(new_a - centroid_a) < 0.1 and abs(new_b - centroid_b) < 0.1:
            break
        centroid_a, centroid_b = new_a, new_b
    # Reassign one last time
    cluster_a, cluster_b = [], []
    for o in offsets:
        if abs(o - centroid_a) < abs(o - centroid_b):
            cluster_a.append(o)
        else:
            cluster_b.append(o)
    # Order ascending for stable reporting
    if centroid_a > centroid_b:
        centroid_a, centroid_b = centroid_b, centroid_a
        cluster_a, cluster_b = cluster_b, cluster_a
    separation = abs(centroid_b - centroid_a)
    smaller_count = min(len(cluster_a), len(cluster_b))
    smaller_mass = smaller_count / len(offsets)
    # Within-cluster SD: average of the two cluster SDs. A unimodal-
    # but-high-SD distribution will have within-cluster SD that's a
    # large fraction of separation (k-means just splits the
    # distribution in half). A true bimodal mixture has within-
    # cluster SD that's much smaller than separation.
    def _sd(xs: list[float]) -> float:
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
    within_sd = (_sd(cluster_a) + _sd(cluster_b)) / 2.0
    separation_to_within = separation / within_sd if within_sd > 0.5 else float("inf")
    is_bimodal = (
        separation > _BIMODAL_SEPARATION_THRESHOLD_MS
        and smaller_mass >= _BIMODAL_MASS_THRESHOLD
        and separation_to_within >= _BIMODAL_SEPARATION_TO_WITHIN_SD_RATIO
    )
    return is_bimodal, (centroid_a, centroid_b), smaller_mass


def _fit_linear_regression(events: list[KeypressEvent]) -> tuple[float, float]:
    """Fit ``platform_rt = slope * bot_intended_rt + intercept`` via
    ordinary least squares. Returns ``(slope, intercept)``.

    Falls back to ``(1.0, mean_offset)`` if the variance of
    bot_intended_rt is zero (e.g., all calibration events fired at
    the same intended RT).
    """
    xs = [ev.bot_intended_rt_ms for ev in events]
    ys = [ev.platform_recorded_rt_ms for ev in events]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs) / n
    if var_x < 1e-9:
        return 1.0, mean_y - mean_x
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x
    return slope, intercept


def estimate_calibration(events: Iterable[KeypressEvent]) -> CalibrationResult:
    """Pick the appropriate calibration model from the events.

    Decision flow:
    1. Filter to correctly-recorded events (key match + platform
       recorded something).
    2. If fewer than ``_MIN_CALIBRATION_EVENTS`` survive → escalate
       (``model="too_few_events"``).
    3. Compute offsets; check bimodality. If bimodal → escalate
       (``model="escalate"``).
    4. Compute SD. If SD ≤ 30 ms → fixed_offset model.
    5. Else → regression model.
    """
    events = list(events)
    correct, counts = _filter_events(events)
    base_fields = dict(
        n_events_total=counts["total"],
        n_events_correctly_recorded=counts["correct"],
        n_events_dropped=counts["dropped"],
        n_events_misrecorded=counts["misrecorded"],
    )
    if counts["correct"] < _MIN_CALIBRATION_EVENTS:
        return CalibrationResult(
            model="too_few_events", **base_fields,
            reason=(
                f"only {counts['correct']} correctly-recorded events; "
                f"minimum is {_MIN_CALIBRATION_EVENTS}. The platform may "
                f"be dropping the bot's keypresses, the bot may be "
                f"firing during a non-listening state, or the "
                f"calibration sequence may need to be longer."
            ),
        )
    offsets = [
        ev.platform_recorded_rt_ms - ev.bot_intended_rt_ms
        for ev in correct
    ]
    is_bimodal, cluster_means, smaller_mass = _is_bimodal(offsets)
    if is_bimodal:
        return CalibrationResult(
            model="escalate",
            bimodal_detected=True,
            bimodal_cluster_means_ms=cluster_means,
            bimodal_smaller_mass=smaller_mass,
            offsets_ms=offsets,
            reason=(
                f"Offset distribution is bimodal: cluster means at "
                f"{cluster_means[0]:.1f} and {cluster_means[1]:.1f} ms "
                f"(separation {cluster_means[1] - cluster_means[0]:.1f} ms, "
                f">{_BIMODAL_SEPARATION_THRESHOLD_MS} threshold), smaller "
                f"cluster has {smaller_mass:.2%} of mass (≥"
                f"{_BIMODAL_MASS_THRESHOLD:.0%} threshold). The platform "
                f"is using two distinct recording paths; a single fitted "
                f"model wouldn't capture either. Escalate to project owner."
            ),
            **base_fields,
        )
    # Unimodal: pick fixed-offset or regression based on SD
    n = len(offsets)
    mean = sum(offsets) / n
    var = sum((o - mean) ** 2 for o in offsets) / (n - 1) if n > 1 else 0.0
    sd = var ** 0.5
    if sd <= _SD_FIXED_OFFSET_THRESHOLD_MS:
        return CalibrationResult(
            model="fixed_offset",
            mean_offset_ms=mean,
            sd_offset_ms=sd,
            offsets_ms=offsets,
            reason=(
                f"Fixed-offset model: mean = {mean:.2f} ms, sd = "
                f"{sd:.2f} ms (≤ {_SD_FIXED_OFFSET_THRESHOLD_MS} threshold)."
            ),
            **base_fields,
        )
    # High-SD: fit per-trial regression instead. Document why.
    slope, intercept = _fit_linear_regression(correct)
    return CalibrationResult(
        model="regression",
        mean_offset_ms=mean,
        sd_offset_ms=sd,
        slope=slope,
        intercept_ms=intercept,
        offsets_ms=offsets,
        reason=(
            f"Regression model: sd = {sd:.2f} ms exceeds the "
            f"{_SD_FIXED_OFFSET_THRESHOLD_MS} threshold, so fixed-offset "
            f"subtraction would leave a residual that re-inflates the "
            f"recorded distribution's sigma. Fitted slope={slope:.3f}, "
            f"intercept={intercept:.2f} ms."
        ),
        **base_fields,
    )

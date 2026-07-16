"""Capture-time stall flags (A5b).

After the platform's own data export is captured, scan its trial rows for
``rt`` values exceeding a mechanical ceiling (default 4x the card's
configured max response window, else a fixed 10s). Flag-only: this never
excludes trials or changes any analysis — it just makes an obviously-broken
capture (e.g. a hung poll recorded as a multi-second "response") visible in
``run_metadata.json``.

Handles both CSV and JSON platform exports and is robust to missing or
renamed rt columns — paradigms vary in what they call the field.
"""
from __future__ import annotations

import csv
import io
import json

DEFAULT_CEILING_MS = 10_000.0

# Column names observed (or plausible) across paradigms/platforms for a
# per-trial response-time field, checked case-insensitively.
_RT_COLUMN_CANDIDATES = (
    "rt",
    "rt_ms",
    "response_time",
    "response_time_ms",
    "reaction_time",
    "reaction_time_ms",
    "latency",
    "latency_ms",
)


def _rows_from_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _rows_from_json(text: str) -> list[dict]:
    obj = json.loads(text)
    if isinstance(obj, list):
        return [row for row in obj if isinstance(row, dict)]
    if isinstance(obj, dict):
        # Some exports wrap the trial array under a top-level key.
        for value in obj.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def _find_rt_column(rows: list[dict]) -> str | None:
    if not rows:
        return None
    lower_map = {str(col).lower(): col for col in rows[0].keys()}
    for candidate in _RT_COLUMN_CANDIDATES:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


def compute_stall_flags(data: str, fmt: str, ceiling_ms: float) -> dict:
    """Scan a captured platform export for stalled (implausibly slow) trials.

    Returns ``{"stall_trials": N, "max_rt_ms": X, "ceiling_ms": C}`` when an
    rt column is found, or ``{"stall_trials": None, "note": <reason>}`` when
    the export can't be parsed, is empty, or has no recognizable rt column.
    """
    fmt = (fmt or "csv").lower()
    try:
        rows = _rows_from_json(data) if fmt == "json" else _rows_from_csv(data)
    except Exception as e:
        return {"stall_trials": None, "note": f"parse failed: {e!r}"}

    if not rows:
        return {"stall_trials": None, "note": "no rows in captured export"}

    rt_col = _find_rt_column(rows)
    if rt_col is None:
        return {"stall_trials": None, "note": "no recognizable rt column in captured export"}

    rt_values: list[float] = []
    for row in rows:
        raw = row.get(rt_col)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            rt_values.append(value)

    if not rt_values:
        return {
            "stall_trials": None,
            "note": f"rt column {rt_col!r} had no positive numeric values",
        }

    stall_trials = sum(1 for v in rt_values if v > ceiling_ms)
    return {
        "stall_trials": stall_trials,
        "max_rt_ms": max(rt_values),
        "ceiling_ms": ceiling_ms,
    }

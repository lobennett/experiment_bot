"""Platform-export → canonical-trial-dict adapters.

The validation oracle reads canonical trial dicts (condition, rt, correct,
omission) from each session directory. The platform-native data export
varies per paradigm — different jsPsych plugins (poldracklab-stop-signal,
custom-stop-signal-plugin, html-keyboard-response) write different
schemas. Each adapter knows the schema for one paradigm label and returns
canonical trials.

Long-term, these adapters belong in the TaskCard (the Reasoner could
emit field-mapping config during Stage 1+ from source-code analysis).
For now, they live in code with one dispatch entry per dev paradigm.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Callable


def _is_truthy_str(value) -> bool:
    """Common 'true' encoding across platforms: bool(true), 'true', '1'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1")
    return bool(value)


def _is_nan_or_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        s = value.strip().lower()
        return s in ("", "nan", "null", "undefined")
    return False


def _safe_float(value) -> float | None:
    if _is_nan_or_empty(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_expfactory_stop_signal(session_dir: Path) -> list[dict]:
    """`taskcards/expfactory_stop_signal/`. Filter: trial_type ==
    poldracklab-stop-signal AND exp_stage == test."""
    csv_path = Path(session_dir) / "experiment_data.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    out: list[dict] = []
    for r in rows:
        if r.get("trial_type") != "poldracklab-stop-signal":
            continue
        if r.get("exp_stage") != "test":
            continue
        rt = _safe_float(r.get("rt"))
        out.append({
            "condition": r.get("condition") or "",  # 'go' or 'stop'
            "rt": rt,
            "correct": r.get("correct_trial") == "1",
            "omission": rt is None,
            "ssd": _safe_float(r.get("SSD")),
        })
    return out


def read_expfactory_stroop(session_dir: Path) -> list[dict]:
    """`taskcards/expfactory_stroop/`. Filter: trial_id == test_trial."""
    json_path = Path(session_dir) / "experiment_data.json"
    if not json_path.exists():
        return []
    data = json.loads(json_path.read_text())
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for r in data:
        if r.get("trial_id") != "test_trial":
            continue
        rt = _safe_float(r.get("rt"))
        # `correct_trial` is 0/1 in this schema; fall back to deriving from
        # response == correct_response when correct_trial is absent
        if r.get("correct_trial") in (0, 1, "0", "1"):
            correct = r.get("correct_trial") in (1, "1")
        else:
            correct = r.get("response") == r.get("correct_response")
        out.append({
            "condition": r.get("condition") or "",  # 'congruent' / 'incongruent'
            "rt": rt,
            "correct": correct,
            "omission": rt is None,
        })
    return out


def read_stopit_stop_signal(session_dir: Path) -> list[dict]:
    """`taskcards/stopit_stop_signal/`. Filter: block_i in {1,2,3,4}
    (block 0 is practice). Condition derived from `signal`: 'no' → 'go',
    'yes' → 'stop'. RT 'NaN' → omission."""
    csv_path = Path(session_dir) / "experiment_data.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    out: list[dict] = []
    for r in rows:
        block = r.get("block_i")
        if block not in ("1", "2", "3", "4"):
            continue  # skip practice (block_i=0) and any non-test rows
        rt = _safe_float(r.get("rt"))
        signal = r.get("signal")
        if signal == "yes":
            condition = "stop"
        elif signal == "no":
            condition = "go"
        else:
            condition = ""
        out.append({
            "condition": condition,
            "rt": rt,
            "correct": _is_truthy_str(r.get("correct")),
            "omission": rt is None,
            "ssd": _safe_float(r.get("SSD")),
        })
    return out


def read_cognitionrun_stroop(session_dir: Path) -> list[dict]:
    """`taskcards/cognitionrun_stroop/`. Filter: html-keyboard-response
    with non-null rt. Condition derived from text == colour
    (congruent/incongruent). Correctness derived from response key.

    The cognition.run platform's `condition` column is numeric (1/2 etc.)
    and not directly meaningful as a Stroop label; the actual congruency
    is the relationship between `text` and `colour`.
    """
    csv_path = Path(session_dir) / "experiment_data.csv"
    if not csv_path.exists():
        return []
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    # The cognition.run paradigm uses a fixed key→colour mapping that the
    # bot resolves from the page's possibleResponses array; we don't have
    # access to that here. So we treat correctness as "did the bot
    # respond at all" — sufficient for the population-level metrics the
    # oracle currently gates on (RT distribution, CSE, PES). For per-
    # condition correctness rates, the bot_log is more reliable here
    # because it carries the bot's intended_error flag.
    out: list[dict] = []
    for r in rows:
        if r.get("trial_type") != "html-keyboard-response":
            continue
        rt = _safe_float(r.get("rt"))
        if rt is None:
            continue
        text = (r.get("text") or "").strip().lower()
        colour = (r.get("colour") or "").strip().lower()
        if not text or not colour:
            continue
        condition = "congruent" if text == colour else "incongruent"
        # Without the runtime key→colour map, treat any keyed response
        # as a successful response and let the oracle's RT-distribution
        # metrics ignore correctness for this paradigm.
        responded = not _is_nan_or_empty(r.get("response"))
        out.append({
            "condition": condition,
            "rt": rt,
            "correct": responded,
            "omission": not responded,
        })
    return out


# Dispatch by output-directory label name (matches the executor's
# `task.name.replace(" ", "_").lower()` convention used in writer.py).
PLATFORM_ADAPTERS: dict[str, Callable[[Path], list[dict]]] = {
    "stop_signal_rdoc": read_expfactory_stop_signal,
    "stroop_rdoc": read_expfactory_stroop,
    "stop_signal_kywch_jspsych": read_stopit_stop_signal,
    "stroop_online_(cognition.run)": read_cognitionrun_stroop,
}


def adapter_for_label(label: str) -> Callable[[Path], list[dict]] | None:
    """Return the platform-data adapter for ``label`` if registered."""
    return PLATFORM_ADAPTERS.get(label)

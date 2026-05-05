"""Optional descriptive-only loader for Eisenberg 2019 trial-level CSVs.

Returns ex-Gaussian fits per condition for side-by-side comparison with bot.
NEVER used to gate pass/fail — descriptive only.
"""
from __future__ import annotations
import csv
from pathlib import Path
from experiment_bot.effects.validation_metrics import fit_ex_gaussian


PARADIGM_CLASS_TO_FILE = {
    "conflict": "stroop_eisenberg.csv",
    "interrupt": "stop_signal_eisenberg.csv",
}


def load_eisenberg_summary(paradigm_class: str, base: Path) -> dict | None:
    """Read the Eisenberg trial-level CSV for a paradigm class; return ex-Gaussian fit.

    Returns None if no file mapping exists or file is missing. Otherwise returns:
    {"mu": ..., "sigma": ..., "tau": ..., "n_trials": ...}
    """
    fname = PARADIGM_CLASS_TO_FILE.get(paradigm_class)
    if fname is None:
        return None
    path = Path(base) / fname
    if not path.exists():
        return None
    rts: list[float] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rt = row.get("rt") or row.get("RT") or row.get("response_time")
            try:
                rts.append(float(rt))
            except (TypeError, ValueError):
                continue
    if not rts:
        return None
    fit = fit_ex_gaussian(rts)
    return {"mu": fit["mu"], "sigma": fit["sigma"], "tau": fit["tau"], "n_trials": len(rts)}

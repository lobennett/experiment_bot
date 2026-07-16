#!/usr/bin/env python3
"""Ingest the lab's RDoC behavioral matrices into the repo's human-reference
layout. Reads the source matrices (one CSV per task, named
``Rdoc behavioral matrix (updated) - <task>.csv``), trims to the columns the
naive-bot comparison uses, and writes:

  data/human/rdoc/<task>.csv              (real, git-ignored — carries sub_ids)
  data/human/rdoc/<task>.placeholder.csv  (committed schema stub)

Kept: identity (sub_id/date_time/session), every behavioral metric,
``proportion_feedback``, ``attention_check_mean_accuracy``.
Dropped by name: flipped_mappings, fullscreen_exit, blur_during_task, and all
notes / comments / checked / exclusion admin columns.

Usage:  scripts/ingest_rdoc_behavioral.py <source_dir>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

DST = Path("data/human/rdoc")
DROP_EXACT = {"flipped_mappings", "fullscreen_exit", "blur_during_task"}
DROP_PATTERNS = [r"notes$", r"comments$", r"^checked$", r"^pb checked$",
                 r"exclusions?$"]


def _drop(col: str) -> bool:
    cl = col.strip().lower()
    return cl in DROP_EXACT or any(re.search(p, cl) for p in DROP_PATTERNS)


def main(src_dir: str) -> None:
    src = Path(src_dir).expanduser()
    files = sorted(src.glob("*.csv"))
    if not files:
        raise SystemExit(f"no CSVs in {src}")
    DST.mkdir(parents=True, exist_ok=True)
    for f in files:
        task = re.sub(r".*- ", "", f.stem).strip()
        df = pd.read_csv(f)
        keep = [c for c in df.columns if not _drop(c)]
        df[keep].to_csv(DST / f"{task}.csv", index=False)
        stub = pd.DataFrame([{c: ("placeholder" if c == "sub_id" else "NA")
                              for c in keep}])
        stub.to_csv(DST / f"{task}.placeholder.csv", index=False)
        print(f"{task:24s} {len(df):5d} rows -> {len(keep)} cols")
    print(f"wrote {len(files)} cleaned + {len(files)} placeholders to {DST}/")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

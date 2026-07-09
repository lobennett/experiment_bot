"""Wave C4: deterministic seed -> program assignment for K-program runs.

Pure function, no I/O. ``scripts/naive_run.sh`` calls it (via a python -c
one-liner) with the FULL ordered target seed list — never the residual
missing-seeds list — so a re-run assigns every seed the same program it got
the first time (idempotency by seed). Which program served which seed is
already recorded per-session in run_metadata via the program sha.
"""
from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def split_seeds(seeds: Sequence[int], programs: Sequence[T]) -> dict[int, T]:
    """Assign each seed a program by seed index mod K (even split).

    ``seeds`` must be the full ordered target list; ``programs`` must be in
    a stable order (naive_run.sh sorts gate-passed program paths). K=1
    degenerates to the pre-registered single-program flow.
    """
    if not programs:
        raise ValueError("split_seeds requires at least one program")
    return {seed: programs[i % len(programs)] for i, seed in enumerate(seeds)}

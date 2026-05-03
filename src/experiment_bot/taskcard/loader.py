from __future__ import annotations
import json
from pathlib import Path
from experiment_bot.taskcard.hashing import taskcard_sha256
from experiment_bot.taskcard.types import TaskCard


def save_taskcard(tc: TaskCard, base_dir: Path, label: str) -> Path:
    """Compute hash, name file by first 8 hex chars, write JSON."""
    out_dir = Path(base_dir) / label
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = tc.to_dict()
    h = taskcard_sha256(payload)
    payload["produced_by"]["taskcard_sha256"] = h
    out_path = out_dir / f"{h[:8]}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def load_latest(base_dir: Path, label: str) -> TaskCard:
    """Load most recently modified TaskCard for a label."""
    out_dir = Path(base_dir) / label
    if not out_dir.exists():
        raise FileNotFoundError(f"No TaskCards directory for label '{label}' at {out_dir}")
    candidates = sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No TaskCards in {out_dir}")
    return TaskCard.from_dict(json.loads(candidates[0].read_text()))


def load_by_hash(base_dir: Path, label: str, hash_prefix: str) -> TaskCard:
    """Load TaskCard by hash prefix (typically the first 8 hex chars)."""
    candidates = list((Path(base_dir) / label).glob(f"{hash_prefix}*.json"))
    if not candidates:
        raise FileNotFoundError(f"No TaskCard matching {hash_prefix} in {base_dir}/{label}")
    if len(candidates) > 1:
        raise ValueError(f"Multiple TaskCards match {hash_prefix}: {candidates}")
    return TaskCard.from_dict(json.loads(candidates[0].read_text()))

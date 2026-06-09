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


def load_by_hash(base_dir: Path, label: str, sha256: str) -> TaskCard:
    """Load the TaskCard for `label` whose canonical content hash equals `sha256`.

    Hermetic-replay path: reproduce a past session by loading the EXACT card
    recorded in its run_metadata, rather than the newest-by-mtime card that
    `load_latest` returns. Matching is on the recomputed canonical hash
    (`taskcard_sha256`), not the on-disk filename, so a stale or truncated
    filename never silently selects the wrong card.

    `sha256` may be a full 64-char hex digest or an unambiguous prefix.
    Raises FileNotFoundError if no card matches or a prefix is ambiguous.
    """
    out_dir = Path(base_dir) / label
    if not out_dir.exists():
        raise FileNotFoundError(f"No TaskCards directory for label '{label}' at {out_dir}")
    needle = sha256.strip().lower()
    if not needle:
        raise FileNotFoundError(f"Empty hash provided for label '{label}'")

    matches: list[tuple[Path, dict, str]] = []
    for path in sorted(out_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        full_hash = taskcard_sha256(payload)
        if full_hash == needle or full_hash.startswith(needle):
            matches.append((path, payload, full_hash))

    if not matches:
        raise FileNotFoundError(
            f"No TaskCard in {out_dir} with content hash matching '{sha256}'"
        )

    # An exact full-hash match is unambiguous even if a shorter needle would
    # also prefix-match other cards.
    exact = [m for m in matches if m[2] == needle]
    if exact:
        return TaskCard.from_dict(exact[0][1])

    if len(matches) > 1:
        hits = ", ".join(sorted(m[2] for m in matches))
        raise FileNotFoundError(
            f"Hash prefix '{sha256}' is ambiguous for label '{label}' "
            f"({len(matches)} matches: {hits}); provide a longer prefix"
        )

    return TaskCard.from_dict(matches[0][1])

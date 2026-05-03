from __future__ import annotations
import copy
import hashlib
import json


def canonical_json_dumps(obj: dict) -> str:
    """Stable serialization: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def taskcard_sha256(taskcard_dict: dict) -> str:
    """sha256 over canonicalized TaskCard, with produced_by.taskcard_sha256 zeroed.

    Content-addressed: identical content (modulo the hash field itself and
    JSON whitespace/key-order) produces identical hashes.
    """
    cloned = copy.deepcopy(taskcard_dict)
    cloned.setdefault("produced_by", {})["taskcard_sha256"] = ""
    payload = canonical_json_dumps(cloned).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

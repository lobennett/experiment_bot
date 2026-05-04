# src/experiment_bot/reasoner/normalize.py
"""Normalize LLM-output partials to match the strict TaskConfig schema.

Stage 1 of the Reasoner asks Claude to produce structural fields, but the
exact key conventions vary across LLM responses. This module maps common
aliases to the canonical keys before TaskCard construction.
"""
from __future__ import annotations
import copy


def normalize_partial(partial: dict) -> dict:
    """Apply all stage-1 normalizations to a partial TaskCard dict."""
    p = copy.deepcopy(partial)
    p["stimuli"] = [_normalize_stimulus(s) for s in p.get("stimuli", [])]
    return p


def _normalize_stimulus(s: dict) -> dict:
    """Coerce one stimulus dict into the strict StimulusConfig schema."""
    out = dict(s)

    # 1. Identifier: id <- name <- condition
    if "id" not in out:
        if "name" in out:
            out["id"] = out["name"]
        elif "condition" in out:
            out["id"] = out["condition"]
        else:
            out["id"] = "unknown_stimulus"

    # 2. Description: ensure present
    out.setdefault("description", "")

    # 3. Detection: type -> method, expression -> selector
    detection = dict(out.get("detection", {}))
    if "method" not in detection:
        if "type" in detection:
            detection["method"] = detection.pop("type")
        else:
            detection["method"] = "js_eval"  # safe default
    if "selector" not in detection:
        if "expression" in detection:
            detection["selector"] = detection.pop("expression")
        else:
            detection["selector"] = ""
    out["detection"] = detection

    # 4. Response: ensure condition is present (copy from top-level condition or id)
    response = dict(out.get("response", {}))
    if "condition" not in response or not response.get("condition"):
        response["condition"] = out.get("condition") or out.get("name") or out["id"]
    if "key" not in response:
        response["key"] = None
    out["response"] = response

    return out

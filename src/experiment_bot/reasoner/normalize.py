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
    p["task"] = _normalize_task(p.get("task", {}))
    p["navigation"] = _normalize_navigation(p.get("navigation"))
    p["runtime"] = _normalize_runtime(p.get("runtime", {}))
    p["performance"] = _normalize_performance(p.get("performance", {}))
    if "temporal_effects" in p or "response_distributions" in p:
        # Migrate old paradigm-shaped effect names to generic mechanisms
        p["temporal_effects"] = _migrate_temporal_effects(
            p.get("temporal_effects", {})
        )
    return p


def _unwrap_value(entry):
    """ParameterValue-like dicts have shape {value: {...}, ...}; unwrap to
    just the value dict for migration. Returns the dict to read fields
    from, plus the surrounding envelope to preserve."""
    if isinstance(entry, dict) and "value" in entry and isinstance(entry["value"], dict):
        return entry["value"], entry
    return (entry if isinstance(entry, dict) else {}), {}


def _migrate_temporal_effects(te: dict) -> dict:
    """Convert paradigm-shaped TaskCard effect entries (congruency_sequence,
    post_error_slowing, post_interrupt_slowing) into the generic
    mechanism shapes (lag1_pair_modulation, post_event_slowing).

    The bot's effect library only knows generic mechanisms. Old TaskCards
    that emit paradigm-named entries get their config translated here so
    they keep working without regeneration.
    """
    if not isinstance(te, dict):
        return te
    out = dict(te)

    # 1. congruency_sequence → lag1_pair_modulation
    if "congruency_sequence" in out and "lag1_pair_modulation" not in out:
        cse_value, cse_envelope = _unwrap_value(out.pop("congruency_sequence"))
        high = cse_value.get("high_conflict_condition", "incongruent") or "incongruent"
        low = cse_value.get("low_conflict_condition", "congruent") or "congruent"
        fac = cse_value.get("sequence_facilitation_ms", 0.0) or 0.0
        cost = cse_value.get("sequence_cost_ms", 0.0) or 0.0
        new_value = {
            "enabled": cse_value.get("enabled", False),
            "skip_after_error": True,
            "modulation_table": [
                {"prev": high, "curr": high, "delta_ms": -float(fac)},
                {"prev": low, "curr": high, "delta_ms": float(cost)},
            ],
        }
        out["lag1_pair_modulation"] = (
            {**cse_envelope, "value": new_value} if cse_envelope else new_value
        )

    # 2. post_error_slowing + post_interrupt_slowing → post_event_slowing
    if (("post_error_slowing" in out or "post_interrupt_slowing" in out)
            and "post_event_slowing" not in out):
        triggers = []
        envelope = {}
        # Interrupt takes priority over error in the historical executor;
        # encode that by listing it first in the triggers list.
        if "post_interrupt_slowing" in out:
            pi_value, pi_env = _unwrap_value(out.pop("post_interrupt_slowing"))
            envelope = pi_env or envelope
            if pi_value.get("enabled", False):
                triggers.append({
                    "event": "interrupt",
                    "slowing_ms_min": pi_value.get("slowing_ms_min", 0.0),
                    "slowing_ms_max": pi_value.get("slowing_ms_max", 0.0),
                    "exclusive_with_prior_triggers": True,
                })
        if "post_error_slowing" in out:
            pe_value, pe_env = _unwrap_value(out.pop("post_error_slowing"))
            envelope = envelope or pe_env
            if pe_value.get("enabled", False):
                triggers.append({
                    "event": "error",
                    "slowing_ms_min": pe_value.get("slowing_ms_min", 0.0),
                    "slowing_ms_max": pe_value.get("slowing_ms_max", 0.0),
                    "decay_weights": pe_value.get("decay_weights", []) or [],
                    "exclusive_with_prior_triggers": True,
                })
        new_value = {
            "enabled": bool(triggers),
            "triggers": triggers,
        }
        out["post_event_slowing"] = (
            {**envelope, "value": new_value} if envelope else new_value
        )

    return out


def _normalize_runtime(r: dict | None) -> dict:
    """Ensure runtime sub-dicts (trial_interrupt, etc.) are dicts not None."""
    out = dict(r or {})
    # Sub-dicts the LLM sometimes returns as null when the feature is N/A
    for key in ("trial_interrupt", "advance_behavior", "data_capture",
                "attention_check", "phase_detection", "timing"):
        if out.get(key) is None:
            out[key] = {}
    return out


def _normalize_performance(p: dict | None) -> dict:
    """Ensure performance.accuracy is present (LLM occasionally omits it on tasks
    where accuracy isn't a primary measure, e.g. interrupt tasks measuring
    inhibition rate).
    """
    out = dict(p or {})
    if "accuracy" not in out or out["accuracy"] is None:
        out["accuracy"] = {"default": 0.95}
    return out


def _normalize_stimulus(s: dict) -> dict:
    """Coerce one stimulus dict into the strict StimulusConfig schema."""
    out = dict(s)

    # 0. Block name: `detect` -> `detection` (LLM alias)
    if "detection" not in out and "detect" in out:
        out["detection"] = out.pop("detect")

    # 1. Identifier: id <- name <- condition <- response.condition
    if "id" not in out:
        if "name" in out:
            out["id"] = out["name"]
        elif "condition" in out:
            out["id"] = out["condition"]
        elif isinstance(out.get("response"), dict) and out["response"].get("condition"):
            out["id"] = out["response"]["condition"]
        else:
            out["id"] = "unknown_stimulus"

    # 2. Description: ensure present
    out.setdefault("description", "")

    # 3. Detection: type -> method, expression/value -> selector
    detection = dict(out.get("detection", {}))
    if "method" not in detection:
        if "type" in detection:
            detection["method"] = detection.pop("type")
        else:
            detection["method"] = "js_eval"  # safe default
    if "selector" not in detection:
        if "expression" in detection:
            detection["selector"] = detection.pop("expression")
        elif "value" in detection:
            detection["selector"] = detection.pop("value")
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


def _normalize_task(t: dict | None) -> dict:
    """Ensure task dict has a 'name' key."""
    out = dict(t or {})
    if "name" not in out or not out["name"]:
        # Try common alternatives the LLM might use
        for alt in ("title", "task_name", "id"):
            if alt in out and out[alt]:
                out["name"] = out[alt]
                break
        else:
            out["name"] = "unknown"
    out.setdefault("constructs", [])
    out.setdefault("reference_literature", [])
    return out


def _normalize_navigation(n) -> dict:
    """Ensure navigation is shaped as {'phases': [normalized_phase, ...]}."""
    if n is None:
        return {"phases": []}
    if isinstance(n, list):
        phases = n
    elif isinstance(n, dict):
        phases = n.get("phases", [])
    else:
        phases = []
    return {"phases": [_normalize_navigation_phase(p) for p in phases]}


def _normalize_navigation_phase(phase: dict) -> dict:
    """Coerce one navigation phase dict into the strict NavigationPhase schema.

    LLM aliases mapped:
      - type -> action
      - selector -> target
      - duration -> duration_ms
      - step (singleton, used in repeat) -> [step] in steps list
    Sub-step lists in `steps` are recursively normalized.
    """
    out = dict(phase or {})
    # type -> action
    if "action" not in out and "type" in out:
        out["action"] = out.pop("type")
    # selector -> target
    if "target" not in out and "selector" in out:
        out["target"] = out.pop("selector")
    # duration -> duration_ms
    if "duration_ms" not in out and "duration" in out:
        try:
            out["duration_ms"] = int(out.pop("duration"))
        except (TypeError, ValueError):
            out["duration_ms"] = 0
    # singleton `step` -> steps list (LLM uses this on `repeat` actions)
    if "steps" not in out and "step" in out:
        single = out.pop("step")
        out["steps"] = [single] if single else []
    # Ensure required string keys exist
    out.setdefault("phase", "")
    out.setdefault("action", "")
    out.setdefault("target", "")
    out.setdefault("key", "")
    out.setdefault("duration_ms", 0)
    # Recursively normalize sub-steps when phase action is `sequence` or `repeat`
    if isinstance(out.get("steps"), list):
        out["steps"] = [_normalize_navigation_phase(s) for s in out["steps"]]
    else:
        out["steps"] = []
    return out

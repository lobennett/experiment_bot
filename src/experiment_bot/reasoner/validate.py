from __future__ import annotations
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Stage1ValidationError(ValueError):
    """Raised when Stage 1 output is missing executor-required fields."""


class Stage2SchemaError(ValueError):
    """Raised when Stage 2 output violates the runtime schema contract.

    The error string includes a list of every violation found, formatted
    so the LLM can correct each one when given the message back as
    feedback in a refinement turn.
    """

    def __init__(self, errors: list[tuple[str, str]]):
        self.errors = errors
        lines = [f"  - {path}: {msg}" for path, msg in errors]
        super().__init__(
            "Stage 2 output failed schema validation:\n" + "\n".join(lines)
        )


_SCHEMA_PATH = Path(__file__).parent.parent / "prompts" / "schema.json"


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def _value_only(node):
    """Stage 2 wraps each parameter in a {value: <inner>, rationale, ...}
    envelope. Some envelopes wrap dict values (temporal_effects.*); some
    wrap bare numbers (performance.*) — both are valid since SP4a's
    schema generalization. This helper unwraps either shape; non-envelope
    nodes pass through unchanged so the validator can still apply.
    """
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node


def validate_stage2_schema(partial: dict) -> None:
    """Validate Stage 2's behavioral fields against the runtime schema
    contract. Currently checks:

    - `temporal_effects.<mechanism>.value` against the mechanism's
      schema.json subschema. Catches the silently-non-firing-effect
      bug — e.g. a `post_event_slowing.triggers[]` entry with
      `condition`+`slowing_ms` instead of the runtime-required
      `event`+`slowing_ms_min`+`slowing_ms_max`.
    - `between_subject_jitter.value` against its schema.json
      properties (field names, types, minima).

    Field names and enum values come from the bot's runtime contract
    (what the executor reads) — not paradigm knowledge. The validator
    never prescribes which mechanisms to enable or which event sources
    to include; it only enforces the shape an enabled config must take.

    Raises Stage2SchemaError listing every violation found. The error
    message is suitable for inclusion in a refinement-turn user prompt
    so the LLM can self-correct without paradigm-specific coaching.
    """
    import jsonschema

    schema = _load_schema()
    props = schema.get("properties", {})
    errors: list[tuple[str, str]] = []

    # temporal_effects: every key must be a registered mechanism (or, if
    # extending via register_effect() in code, a key listed in schema).
    # An unrecognized key means the runtime won't apply the effect — the
    # same configured-but-non-firing failure mode that motivated this
    # validator. Common cause: LLM regressing to old paradigm-named keys
    # like `congruency_sequence` / `post_error_slowing` that were
    # removed from the registry.
    te_props = props.get("temporal_effects", {}).get("properties", {})
    from experiment_bot.effects.registry import EFFECT_REGISTRY
    known_mechanisms = set(te_props.keys()) | set(EFFECT_REGISTRY.keys())
    for mech, entry in (partial.get("temporal_effects") or {}).items():
        if mech not in known_mechanisms:
            errors.append((
                f"temporal_effects.{mech}",
                f"unknown mechanism {mech!r}; the bot's library exposes "
                f"only: {sorted(known_mechanisms)}. The runtime will "
                f"silently ignore any key not in this list.",
            ))
            continue
        if mech not in te_props:
            # Registered in code but not in schema — accept without
            # shape check (no jsonschema definition to enforce).
            continue
        value = _value_only(entry)
        # Skip shape check if the mechanism is disabled — the LLM may
        # emit a placeholder value with no other fields, and that's fine.
        if isinstance(value, dict) and value.get("enabled") is False:
            continue
        try:
            jsonschema.validate(value, te_props[mech])
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path)
            err_path = f"temporal_effects.{mech}.value"
            if path:
                err_path += f".{path}"
            errors.append((err_path, e.message))

    # between_subject_jitter: the value object against its schema.
    bsj_schema = props.get("between_subject_jitter")
    if bsj_schema:
        bsj_entry = partial.get("between_subject_jitter") or {}
        value = _value_only(bsj_entry)
        if isinstance(value, dict) and value:
            try:
                jsonschema.validate(value, bsj_schema)
            except jsonschema.ValidationError as e:
                path = ".".join(str(p) for p in e.absolute_path)
                err_path = "between_subject_jitter.value"
                if path:
                    err_path += f".{path}"
                errors.append((err_path, e.message))

    # performance.accuracy / omission_rate: each value must be a number in
    # [0,1]. Caught regression: LLM emitting {target, rationale} dicts
    # nested under each condition instead of plain floats — the executor's
    # PerformanceConfig.get_accuracy() returns whatever is at
    # accuracy[condition] and the trial loop crashes with TypeError when
    # it tries to compare random() < dict.
    perf_schema = props.get("performance")
    perf = partial.get("performance") or {}
    if perf_schema and isinstance(perf, dict) and perf:
        for sub in ("accuracy", "omission_rate"):
            sub_schema = perf_schema.get("properties", {}).get(sub)
            sub_value = perf.get(sub)
            if sub_schema and isinstance(sub_value, dict) and sub_value:
                try:
                    jsonschema.validate(sub_value, sub_schema)
                except jsonschema.ValidationError as e:
                    path = ".".join(str(p) for p in e.absolute_path)
                    err_path = f"performance.{sub}"
                    if path:
                        err_path += f".{path}"
                    errors.append((err_path, e.message))

    # task_specific.key_map: each value is a string the executor presses
    # as a literal Playwright key (or a withhold/dynamic sentinel). Caught
    # regression: LLM emitting prose like 'dynamic (ArrowLeft for left
    # arrow, ArrowRight for right arrow; resolved per stimulus_id)' which
    # the executor faithfully tries to press, raising
    # `Keyboard.press: Unknown key`. The schema's pattern + maxLength
    # catches descriptive strings without prescribing which keys are
    # paradigm-appropriate.
    ts_schema = props.get("task_specific", {}).get("properties", {})
    km_schema = ts_schema.get("key_map")
    km_value = (partial.get("task_specific") or {}).get("key_map")
    if km_schema and isinstance(km_value, dict) and km_value:
        try:
            jsonschema.validate(km_value, km_schema)
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path)
            err_path = "task_specific.key_map"
            if path:
                err_path += f".{path}"
            errors.append((err_path, e.message))

    if errors:
        raise Stage2SchemaError(errors)


def validate_stage1_output(partial: dict) -> None:
    """SP10 minimal Stage 1 validator: paradigm-agnostic fields only.

    Under SP10, the platform driver owns response_key_js / navigation /
    phase_detection / attention_check / data_capture. Stage 1 emits only
    LITERATURE + paradigm metadata + driver recommendation, so the
    validator's surface area shrinks accordingly.
    """
    errors: list[str] = []

    task = partial.get("task") or {}
    if not task.get("name"):
        errors.append("task.name is required")
    pc = task.get("paradigm_classes")
    if not (isinstance(pc, list) and len(pc) >= 1
            and all(isinstance(c, str) for c in pc)):
        errors.append(
            "task.paradigm_classes must be a non-empty list of strings"
        )

    stim = partial.get("stimuli")
    if not (isinstance(stim, list) and len(stim) >= 1):
        errors.append("stimuli must be a non-empty list")
    else:
        for i, s in enumerate(stim):
            if not isinstance(s, dict):
                errors.append(f"stimuli[{i}] must be a dict")
                continue
            if not s.get("id"):
                errors.append(f"stimuli[{i}].id is required")
            # Stimuli can carry `condition` either at the top level (SP10
            # minimal shape) or nested under `response.condition` (legacy
            # Stage-1 partials emitted before SP10). Accept either.
            cond = s.get("condition") or (s.get("response") or {}).get("condition")
            if not cond:
                errors.append(f"stimuli[{i}].condition is required")

    perf = partial.get("performance") or {}
    if not isinstance(perf.get("accuracy"), dict):
        errors.append("performance.accuracy must be a dict")

    rd = partial.get("recommended_driver")
    KNOWN = {"JsPsychDriver", "CognitionRunDriver", "PsychoJsDriver", "unknown"}
    if rd is None or rd not in KNOWN:
        errors.append(
            f"recommended_driver must be one of {sorted(KNOWN)} "
            f"(got {rd!r})"
        )

    if errors:
        raise Stage1ValidationError("; ".join(errors))
